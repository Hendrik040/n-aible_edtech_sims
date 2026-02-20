"""
AWS S3 Service for file storage.

Handles uploading and managing files in AWS S3 bucket.
Replaces the legacy wasabi_service with AWS S3 implementation.
"""

import asyncio
import os
from typing import Optional
from urllib.parse import urlparse
import boto3
from botocore.exceptions import ClientError
import httpx
from io import BytesIO

from common.config import get_settings

settings = get_settings()


class S3Service:
    """Service for interacting with AWS S3."""
    
    def __init__(self):
        """Initialize S3 client."""
        self.bucket_name = settings.aws_bucket_name
        self.region = settings.aws_region
        self.public_read = settings.aws_public_read
        
        # Initialize S3 client
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=self.region
            )
        else:
            # Use default credentials (IAM role, environment, etc.)
            self.s3_client = boto3.client('s3', region_name=self.region)
    
    def get_case_study_key(self, scenario_id: int, filename: str) -> str:
        """Get S3 key for case study PDF."""
        return f"scenarios/{scenario_id}/case-study/{filename}"
    
    def get_persona_avatar_key(self, scenario_id: int, persona_id: int, ext: str = "png") -> str:
        """Get S3 key for persona avatar."""
        return f"scenarios/{scenario_id}/personas/{persona_id}/avatar.{ext}"
    
    def get_scene_image_key(self, scenario_id: int, scene_id: int, ext: str = "png") -> str:
        """Get S3 key for scene image."""
        return f"scenarios/{scenario_id}/scenes/{scene_id}/image.{ext}"
    
    def _build_public_url(self, s3_key: str) -> str:
        """Build public URL for S3 object."""
        if self.public_read:
            # Public URL format: https://{bucket}.s3.{region}.amazonaws.com/{key}
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
        else:
            # Generate presigned URL (expires in 1 hour)
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=3600
            )
    
    async def file_exists(self, s3_key: str) -> bool:
        """Check if file exists in S3."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            )
            return True
        except ClientError as e:
            error_code = (e.response.get("Error", {}) or {}).get("Code")
            # Treat not-found and common permission-denied outcomes as non-fatal "missing"
            # so image checks don't break parsing flow.
            if error_code in {"404", "NoSuchKey", "NotFound", "403", "AccessDenied"}:
                return False
            raise
    
    async def upload_from_bytes(
        self,
        file_bytes: bytes,
        s3_key: str,
        content_type: str = "application/octet-stream"
    ) -> Optional[str]:
        """Upload file from bytes to S3."""
        try:
            # Don't set ACL if bucket doesn't allow it - use bucket policy instead
            # If public_read is True, ensure bucket policy allows public access
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=file_bytes,
                    ContentType=content_type
                    # Removed ACL parameter - bucket policy should handle public access
                )
            )
            
            return self._build_public_url(s3_key)
        except Exception as e:
            print(f"Error uploading to S3: {str(e)}")
            return None
    
    async def upload_from_url(
        self,
        url: str,
        s3_key: str,
        content_type: Optional[str] = None
    ) -> Optional[str]:
        """Download file from URL and upload to S3."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                file_bytes = response.content
                if not content_type:
                    content_type = response.headers.get('content-type', 'application/octet-stream')
                
                return await self.upload_from_bytes(file_bytes, s3_key, content_type)
        except Exception as e:
            print(f"Error uploading from URL to S3: {str(e)}")
            return None
    
    async def download_file(self, s3_key: str) -> Optional[bytes]:
        """Download file from S3."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            )
            return response['Body'].read()
        except Exception as e:
            print(f"Error downloading from S3: {str(e)}")
            return None
    
    async def delete_file(self, s3_key: str) -> bool:
        """Delete file from S3."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            )
            return True
        except Exception as e:
            print(f"Error deleting from S3: {str(e)}")
            return False
    
    async def cleanup_temp_pdfs(self, days_old: int = 7) -> int:
        """Clean up temporary PDF files older than specified days."""
        try:
            from datetime import datetime, timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix="temp-pdfs/"
                )
            )
            
            deleted_count = 0
            if 'Contents' in response:
                for obj in response['Contents']:
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        await self.delete_file(obj['Key'])
                        deleted_count += 1
            
            return deleted_count
        except Exception as e:
            print(f"Error cleaning up temp PDFs: {str(e)}")
            return 0


# Singleton instance
s3_service = S3Service()


# Helper functions for backward compatibility
async def upload_persona_avatar_from_url(
    scenario_id: int,
    persona_id: int,
    url: str
) -> Optional[str]:
    """Upload persona avatar from URL."""
    # Try common extensions
    for ext in ['png', 'jpg', 'webp']:
        s3_key = s3_service.get_persona_avatar_key(scenario_id, persona_id, ext)
        if await s3_service.file_exists(s3_key):
            return s3_service._build_public_url(s3_key)
    
    # Upload with png extension by default
    s3_key = s3_service.get_persona_avatar_key(scenario_id, persona_id, 'png')
    return await s3_service.upload_from_url(url, s3_key)


async def upload_scene_image_from_url(
    scenario_id: int,
    scene_id: int,
    url: str
) -> Optional[str]:
    """Upload scene image from URL."""
    # Try common extensions
    for ext in ['png', 'jpg', 'webp']:
        s3_key = s3_service.get_scene_image_key(scenario_id, scene_id, ext)
        if await s3_service.file_exists(s3_key):
            return s3_service._build_public_url(s3_key)
    
    # Upload with png extension by default
    s3_key = s3_service.get_scene_image_key(scenario_id, scene_id, 'png')
    return await s3_service.upload_from_url(url, s3_key)



def parse_data_url(data_url: str) -> tuple[bytes, str, str]:
    """Parse a data URL and return (bytes, content_type, extension)."""
    import base64
    import re
    
    # Parse data:image/png;base64,iVBORw0KGgo...
    match = re.match(r'data:image/(\w+);base64,(.+)', data_url)
    if not match:
        raise ValueError("Invalid data URL format")
    
    image_type = match.group(1).lower()
    base64_data = match.group(2)
    
    # Map image types to extensions
    ext_map = {'jpeg': 'jpg', 'png': 'png', 'webp': 'webp', 'gif': 'gif'}
    ext = ext_map.get(image_type, 'png')
    content_type = f"image/{image_type}"
    
    image_bytes = base64.b64decode(base64_data)
    return image_bytes, content_type, ext


async def upload_persona_avatar_from_base64(
    scenario_id: int,
    persona_id: int,
    data_url: str
) -> Optional[str]:
    """Upload persona avatar from base64 data URL."""
    try:
        image_bytes, content_type, ext = parse_data_url(data_url)
        s3_key = s3_service.get_persona_avatar_key(scenario_id, persona_id, ext)
        return await s3_service.upload_from_bytes(image_bytes, s3_key, content_type)
    except Exception as e:
        print(f"Error uploading persona avatar from base64: {str(e)}")
        return None


async def upload_scene_image_from_base64(
    scenario_id: int,
    scene_id: int,
    data_url: str
) -> Optional[str]:
    """Upload scene image from base64 data URL."""
    try:
        image_bytes, content_type, ext = parse_data_url(data_url)
        s3_key = s3_service.get_scene_image_key(scenario_id, scene_id, ext)
        return await s3_service.upload_from_bytes(image_bytes, s3_key, content_type)
    except Exception as e:
        print(f"Error uploading scene image from base64: {str(e)}")
        return None

