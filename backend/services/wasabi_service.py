"""
S3-compatible storage service for the AI Agent Education Platform

This service provides async upload/download functions for AWS S3 or Wasabi storage (S3-compatible).
It handles case study PDFs, persona avatars, and scene images with retry logic,
connection validation, and file organization helpers.

Configuration Requirements (AWS - Recommended):
- AWS_ACCESS_KEY_ID: AWS access key
- AWS_SECRET_ACCESS_KEY: AWS secret key
- AWS_BUCKET_NAME: AWS bucket name
- AWS_REGION: AWS region (default: us-east-1)
- AWS_PUBLIC_READ: Set to 'true' to enable public-read ACL on uploads (optional)

Configuration Requirements (Wasabi - Legacy):
- WASABI_ACCESS_KEY_ID: Wasabi access key
- WASABI_SECRET_ACCESS_KEY: Wasabi secret key
- WASABI_BUCKET_NAME: Wasabi bucket name
- WASABI_ENDPOINT_URL: Wasabi endpoint URL (e.g., https://s3.us-east-1.wasabisys.com)
- WASABI_PUBLIC_READ: Set to 'true' to enable public-read ACL on uploads (optional)

Note: AWS credentials take precedence over Wasabi if both are set.
"""
import os
import json
import asyncio
import logging
import httpx
from typing import BinaryIO, Optional
from urllib.parse import quote
from io import BytesIO
from utilities.debug_logging import debug_log
from database.connection import settings

logger = logging.getLogger(__name__)

# Optional boto3 import - gracefully handle if not installed
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
    BOTO3_AVAILABLE = True
    ClientError = ClientError  # Make available for isinstance checks
except ImportError:
    BOTO3_AVAILABLE = False
    ClientError = None  # type: ignore
    debug_log("[WASABI] boto3 not installed - Wasabi storage will not be available")


def _get_extension_from_content_type(content_type: str) -> str:
    """
    Helper function to determine file extension from Content-Type header.
    
    Args:
        content_type: MIME type (e.g., 'image/jpeg', 'image/png')
        
    Returns:
        File extension without dot (e.g., 'jpg', 'png', 'webp')
    """
    content_type_lower = content_type.lower().strip()
    
    # Map common image MIME types to extensions
    type_to_ext = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/webp': 'webp',
        'image/gif': 'gif',
    }
    
    # Extract base type (handle things like 'image/jpeg; charset=utf-8')
    base_type = content_type_lower.split(';')[0].strip()
    
    return type_to_ext.get(base_type, 'jpg')  # Default to jpg if unknown


class WasabiService:
    """Service for managing file storage on AWS S3 or Wasabi (S3-compatible)"""
    
    def __init__(self):
        if not BOTO3_AVAILABLE:
            debug_log("[S3] boto3 not available, S3 service disabled")
            self.s3_client = None
            self.access_key_id = None
            self.secret_access_key = None
            self.bucket_name = None
            self.endpoint_url = None
            self.region = None
            self.is_aws = False
            self.public_read = False
            return
            
        self.access_key_id = settings.s3_access_key_id
        self.secret_access_key = settings.s3_secret_access_key
        self.bucket_name = settings.s3_bucket_name
        self.endpoint_url = settings.s3_endpoint_url
        self.region = settings.s3_region
        self.is_aws = settings.is_aws
        self.public_read = settings.s3_public_read
        
        # Initialize boto3 S3 client
        if self._check_credentials():
            try:
                client_config = {
                    'aws_access_key_id': self.access_key_id,
                    'aws_secret_access_key': self.secret_access_key
                }
                # Only set endpoint_url for Wasabi (not AWS)
                if self.endpoint_url:
                    client_config['endpoint_url'] = self.endpoint_url
                # Set region for AWS
                if self.is_aws:
                    client_config['region_name'] = self.region
                
                self.s3_client = boto3.client('s3', **client_config)
                provider = "AWS" if self.is_aws else "Wasabi"
                debug_log(f"[S3] {provider} service initialized with bucket: {self.bucket_name}, region: {self.region}, public_read={self.public_read}")
                if self.public_read:
                    if self.is_aws:
                        debug_log(f"[S3] ✅ Public read enabled - will attempt 'public-read' ACL")
                        debug_log(f"[S3] ⚠️ If bucket has ACLs disabled, ensure bucket policy allows public read:")
                        debug_log(f"[S3]    {json.dumps({'Version': '2012-10-17', 'Statement': [{'Sid': 'PublicReadGetObject', 'Effect': 'Allow', 'Principal': '*', 'Action': 's3:GetObject', 'Resource': f'arn:aws:s3:::{self.bucket_name}/*'}]}, indent=2)}")
                    else:
                        debug_log(f"[S3] ✅ Public read enabled - files will be uploaded with 'public-read' ACL")
                else:
                    env_var = "AWS_PUBLIC_READ" if self.is_aws else "WASABI_PUBLIC_READ"
                    debug_log(f"[S3] ⚠️ Public read disabled - files will be private. Set {env_var}=true for public access")
                    debug_log(f"[S3] ⚠️ Private files require bucket policy or presigned URLs to access")
            except Exception as e:
                debug_log(f"[S3] Error initializing S3 client: {str(e)}")
                self.s3_client = None
        else:
            debug_log("[S3] Missing credentials, S3 client not initialized")
            self.s3_client = None
    
    def _check_credentials(self) -> bool:
        """Private method to validate that all required credentials are present"""
        if not self.access_key_id:
            provider = "AWS" if self.is_aws else "Wasabi"
            debug_log(f"[S3] {provider} access key not configured")
            return False
        if not self.secret_access_key:
            provider = "AWS" if self.is_aws else "Wasabi"
            debug_log(f"[S3] {provider} secret key not configured")
            return False
        if not self.bucket_name:
            provider = "AWS" if self.is_aws else "Wasabi"
            debug_log(f"[S3] {provider} bucket name not configured")
            return False
        # Endpoint URL only required for Wasabi, not AWS
        if not self.is_aws and not self.endpoint_url:
            debug_log("[S3] WASABI_ENDPOINT_URL not configured (required for Wasabi)")
            return False
        return True
    
    def _build_public_url(self, s3_key: str) -> str:
        """
        Build a public URL for an S3 key with proper URL encoding.
        Supports both AWS S3 and Wasabi URL formats.

        Args:
            s3_key: S3 key (path) for the file

        Returns:
            Public URL with URL-encoded key
        """
        if not self.bucket_name:
            debug_log(f"[S3] Cannot build URL: bucket_name={self.bucket_name}")
            return ""

        encoded_key = quote(s3_key, safe='/')
        
        # AWS S3 format: https://bucket-name.s3.region.amazonaws.com/key
        # or: https://s3.region.amazonaws.com/bucket-name/key
        if self.is_aws:
            # Use virtual-hosted style (bucket-name.s3.region.amazonaws.com)
            url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{encoded_key}"
        else:
            # Wasabi format: https://endpoint/bucket/key
            if not self.endpoint_url:
                debug_log(f"[S3] Cannot build Wasabi URL: endpoint_url={self.endpoint_url}")
                return ""
            url = f"{self.endpoint_url}/{self.bucket_name}/{encoded_key}"
        
        debug_log(f"[S3] Built public URL: {url} (from key: {s3_key})")
        return url

    def _validate_public_access(self, s3_key: str) -> bool:
        """
        Check if a file is publicly accessible by attempting to HEAD the object.
        Returns True if accessible, False otherwise.
        """
        if not self.public_read:
            debug_log(f"[S3] Skipping public access check - public_read is disabled")
            return False

        try:
            import httpx
            public_url = self._build_public_url(s3_key)
            response = httpx.head(public_url, timeout=5.0)
            if response.status_code == 200:
                debug_log(f"[S3] ✅ File is publicly accessible: {s3_key}")
                return True
            else:
                debug_log(f"[S3] ❌ File not publicly accessible (HTTP {response.status_code}): {s3_key}")
                return False
        except Exception as e:
            debug_log(f"[S3] ❌ Public access check failed: {str(e)}")
            return False

    async def validate_connection(self) -> bool:
        """
        Test S3 connection (AWS or Wasabi) by attempting to list bucket contents or head bucket.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.s3_client:
            debug_log("[S3] Cannot validate connection: S3 client not initialized")
            return False
        
        try:
            # Use executor for blocking boto3 call
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.s3_client.head_bucket(Bucket=self.bucket_name)
            )
            provider = "AWS" if self.is_aws else "Wasabi"
            debug_log(f"[S3] {provider} connection validation successful")
            return True
        except ClientError as e:
            debug_log(f"[S3] Connection validation failed: {str(e)}")
            return False
        except Exception as e:
            debug_log(f"[S3] Connection validation error: {str(e)}")
            return False
    
    async def upload_file(self, file_obj: BinaryIO, s3_key: str, content_type: str) -> str:
        """
        Upload a file object to S3 (AWS or Wasabi) and return the public URL.
        
        Args:
            file_obj: File object (BinaryIO) to upload
            s3_key: S3 key (path) for the file
            content_type: MIME type of the file (e.g., 'application/pdf', 'image/jpeg')
            
        Returns:
            Public URL of the uploaded file (if AWS_PUBLIC_READ=true or WASABI_PUBLIC_READ=true) or storage path,
            or empty string on failure. Note: If public-read ACL is not enabled, the URL
            may not be accessible without proper bucket policy or presigned URL.
        """
        if not self.s3_client:
            debug_log("[S3] Cannot upload file: S3 client not initialized")
            return ""
        
        # Read file contents
        try:
            file_obj.seek(0)
            file_contents = file_obj.read()
        except Exception as e:
            debug_log(f"[S3] Error reading file: {str(e)}")
            return ""
        
        return await self.upload_from_bytes(file_contents, s3_key, content_type)
    
    async def upload_from_bytes(self, file_bytes: bytes, s3_key: str, content_type: str) -> str:
        """
        Upload bytes directly to S3 (AWS or Wasabi).
        
        Args:
            file_bytes: File contents as bytes
            s3_key: S3 key (path) for the file
            content_type: MIME type of the file
            
        Returns:
            Public URL of the uploaded file (if AWS_PUBLIC_READ=true or WASABI_PUBLIC_READ=true) or storage path,
            or empty string on failure. Note: If public-read ACL is not enabled, the URL
            may not be accessible without proper bucket policy or presigned URL.
        """
        if not self.s3_client:
            debug_log("[S3] Cannot upload: S3 client not initialized")
            return ""
        
        # Retry logic with exponential backoff (3 retries, delay * 2^attempt)
        max_retries = 3
        delay = 1.0
        acl_not_supported = False
        
        for attempt in range(max_retries):
            try:
                # Prepare put_object parameters
                put_params = {
                    'Bucket': self.bucket_name,
                    'Key': s3_key,
                    'Body': file_bytes,
                    'ContentType': content_type
                }
                # Only add ACL if public_read is enabled and ACLs haven't been found to be unsupported
                if self.public_read and not acl_not_supported:
                    put_params['ACL'] = 'public-read'
                
                # Wrap blocking boto3 call with executor
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: self.s3_client.put_object(**put_params)
                )
                
                # Generate public URL with URL-encoded key
                public_url = self._build_public_url(s3_key)
                if acl_not_supported and self.public_read:
                    acl_status = "public (via bucket policy)"
                else:
                    acl_status = "public" if self.public_read else "private"
                debug_log(f"[S3] Successfully uploaded file to {s3_key} (ACL: {acl_status})")

                # Optionally validate public access (can be disabled for performance)
                import os
                validate_env = 'AWS_VALIDATE_PUBLIC_ACCESS' if self.is_aws else 'WASABI_VALIDATE_PUBLIC_ACCESS'
                if self.public_read and os.getenv(validate_env, 'false').lower() == 'true':
                    self._validate_public_access(s3_key)

                return public_url
                
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                # If ACLs are not supported, retry without ACL (bucket policy should handle public access)
                if error_code == 'AccessControlListNotSupported' and self.public_read and not acl_not_supported:
                    acl_not_supported = True
                    debug_log(f"[S3] Bucket does not support ACLs, retrying without ACL (bucket policy should provide public access)")
                    continue  # Retry immediately without ACL
                
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)
                    debug_log(f"[S3] Upload attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    debug_log(f"[S3] Upload failed after {max_retries} attempts: {str(e)}")
                    if acl_not_supported and self.public_read:
                        debug_log(f"[S3] ⚠️ Note: Bucket ACLs are disabled. Ensure bucket policy allows public read access.")
                    return ""
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)
                    debug_log(f"[S3] Upload attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    debug_log(f"[S3] Upload failed after {max_retries} attempts: {str(e)}")
                    return ""
        
        return ""
    
    async def upload_from_url(self, url: str, s3_key: str, content_type: str = None) -> str:
        """
        Download from a URL (e.g., DALL-E/FreePik temporary URLs) and upload to S3 (AWS or Wasabi).
        Automatically detects Content-Type from HTTP response headers and adjusts S3 key extension.
        
        Args:
            url: URL to download from
            s3_key: S3 key (path) for the file (may be updated with detected extension)
            content_type: Optional MIME type (if not provided, detected from response headers)
            
        Returns:
            Public URL of the uploaded file, or empty string on failure
        """
        if not self.s3_client:
            debug_log("[S3] Cannot upload from URL: S3 client not initialized")
            return ""
        
        # Download from URL with retry logic
        max_retries = 3
        delay = 1.0
        file_bytes = None
        detected_content_type = content_type
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    file_bytes = response.content
                    
                    # Detect Content-Type from response headers if not provided
                    if not detected_content_type:
                        detected_content_type = response.headers.get('Content-Type', 'image/jpeg')
                        debug_log(f"[S3] Detected Content-Type: {detected_content_type}")
                    
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)
                    debug_log(f"[S3] Download attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    debug_log(f"[S3] Download failed after {max_retries} attempts: {str(e)}")
                    return ""
        
        if not file_bytes:
            debug_log("[S3] No file bytes downloaded from URL")
            return ""
        
        # Determine extension from detected Content-Type
        extension = _get_extension_from_content_type(detected_content_type or 'image/jpeg')
        
        # Update S3 key to use detected extension if current key doesn't have a recognized extension
        if not any(s3_key.endswith(f'.{ext}') for ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']):
            # Remove existing extension if any and append detected extension
            base_key = s3_key.rsplit('.', 1)[0] if '.' in s3_key else s3_key
            s3_key = f"{base_key}.{extension}"
            debug_log(f"[S3] Updated S3 key with detected extension: {s3_key}")
        
        # Upload to S3 with detected content type
        return await self.upload_from_bytes(file_bytes, s3_key, detected_content_type or 'image/jpeg')
    
    async def download_file(self, s3_key: str) -> bytes:
        """
        Download a file from S3 (AWS or Wasabi) and return bytes.
        
        Args:
            s3_key: S3 key (path) of the file to download
            
        Returns:
            File contents as bytes, or empty bytes on failure
        """
        if not self.s3_client:
            debug_log("[S3] Cannot download file: S3 client not initialized")
            return b""
        
        # Retry logic with exponential backoff (3 retries, delay * 2^attempt)
        max_retries = 3
        delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Wrap blocking boto3 call with executor - get_object and read() in single call
                file_bytes = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda key=s3_key: self.s3_client.get_object(Bucket=self.bucket_name, Key=key)['Body'].read()
                )
                debug_log(f"[S3] Successfully downloaded file from {s3_key}")
                return file_bytes
                
            except ClientError as e:
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)
                    debug_log(f"[S3] Download attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    debug_log(f"[S3] Download failed after {max_retries} attempts: {str(e)}")
                    return b""
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = delay * (2 ** attempt)
                    debug_log(f"[S3] Download attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    debug_log(f"[S3] Download failed after {max_retries} attempts: {str(e)}")
                    return b""
        
        return b""
    
    async def get_file_url(self, s3_key: str, expiration: int = 3600) -> str:
        """
        Generate a presigned URL for private file access.
        
        Args:
            s3_key: S3 key (path) of the file
            expiration: URL expiration time in seconds (default: 3600 = 1 hour)
            
        Returns:
            Presigned URL, or empty string on failure
        """
        if not self.s3_client:
            debug_log("[S3] Cannot generate presigned URL: S3 client not initialized")
            return ""
        
        try:
            # Wrap blocking boto3 call with executor
            url = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': s3_key},
                    ExpiresIn=expiration
                )
            )
            debug_log(f"[S3] Generated presigned URL for {s3_key}")
            return url
            
        except ClientError as e:
            debug_log(f"[S3] Presigned URL generation failed: {str(e)}")
            return ""
        except Exception as e:
            debug_log(f"[S3] Presigned URL generation error: {str(e)}")
            return ""
    
    def get_case_study_key(self, scenario_id: int, filename: str) -> str:
        """
        Generate S3 key for case study PDFs using hierarchical structure.

        Args:
            scenario_id: Scenario ID
            filename: Original filename

        Returns:
            S3 key following pattern: scenarios/{scenario_id}/case-study/{filename}
        """
        return f"scenarios/{scenario_id}/case-study/{filename}"

    def get_persona_avatar_key(self, scenario_id: int, persona_id: int, extension: str = 'jpg') -> str:
        """
        Generate S3 key for persona avatars using hierarchical structure.

        Args:
            scenario_id: Scenario ID (parent)
            persona_id: Persona ID
            extension: File extension (default: 'jpg')

        Returns:
            S3 key following pattern: scenarios/{scenario_id}/personas/{persona_id}/avatar.{extension}
        """
        return f"scenarios/{scenario_id}/personas/{persona_id}/avatar.{extension}"

    def get_scene_image_key(self, scenario_id: int, scene_id: int, extension: str = 'png') -> str:
        """
        Generate S3 key for scene images using hierarchical structure.

        Args:
            scenario_id: Scenario ID (parent)
            scene_id: Scene ID
            extension: File extension (default: 'png')

        Returns:
            S3 key following pattern: scenarios/{scenario_id}/scenes/{scene_id}/image.{extension}
        """
        return f"scenarios/{scenario_id}/scenes/{scene_id}/image.{extension}"


# Global Wasabi service instance
wasabi_service = WasabiService()


async def upload_case_study_pdf(scenario_id: int, file_obj: BinaryIO, filename: str) -> str:
    """
    Convenience function to upload case study PDF to S3 (AWS or Wasabi).
    
    Args:
        scenario_id: Scenario ID
        file_obj: File object to upload
        filename: Original filename
        
    Returns:
        Public URL of the uploaded file, or empty string on failure
    """
    s3_key = wasabi_service.get_case_study_key(scenario_id, filename)
    return await wasabi_service.upload_file(file_obj, s3_key, 'application/pdf')


async def upload_persona_avatar_from_url(scenario_id: int, persona_id: int, url: str) -> str:
    """
    Convenience function to upload persona avatar from URL to S3 (AWS or Wasabi) using hierarchical structure.
    Detects Content-Type from HTTP response and uses appropriate extension.

    Args:
        scenario_id: Scenario ID (parent)
        persona_id: Persona ID
        url: URL of the image to download and upload

    Returns:
        Public URL of the uploaded file, or empty string on failure
    """
    # Use base key without extension; upload_from_url will detect and append correct extension
    base_s3_key = f"scenarios/{scenario_id}/personas/{persona_id}/avatar"
    return await wasabi_service.upload_from_url(url, base_s3_key)


async def upload_scene_image_from_url(scenario_id: int, scene_id: int, url: str) -> str:
    """
    Convenience function to upload scene image from URL to S3 (AWS or Wasabi) using hierarchical structure.
    Detects Content-Type from HTTP response and uses appropriate extension.

    Args:
        scenario_id: Scenario ID (parent)
        scene_id: Scene ID
        url: URL of the image to download and upload

    Returns:
        Public URL of the uploaded file, or empty string on failure
    """
    # Use base key without extension; upload_from_url will detect and append correct extension
    base_s3_key = f"scenarios/{scenario_id}/scenes/{scene_id}/image"
    return await wasabi_service.upload_from_url(url, base_s3_key)
