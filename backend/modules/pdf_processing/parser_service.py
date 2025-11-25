"""
PDF parsing service using LlamaParse.
Extracted from api/parse_pdf.py
"""
import os
import tempfile
import asyncio
from typing import Optional
from fastapi import HTTPException, UploadFile
from llama_parse import LlamaParse
from utilities.debug_logging import debug_log
from utilities.rate_limiter import async_retry
from database.connection import settings

LLAMAPARSE_API_KEY = settings.llamaparse_api_key

# Performance optimization constants
MAX_CONCURRENT_LLAMAPARSE = 3  # Limit concurrent LlamaParse requests

# Global semaphore for LlamaParse requests
_llamaparse_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLAMAPARSE)


class ParserService:
    """Service for parsing PDFs and other documents using LlamaParse"""
    
    def __init__(self):
        self.api_key = LLAMAPARSE_API_KEY
        self.validate_config()
    
    def validate_config(self) -> tuple[bool, str]:
        """Validate LlamaParse configuration and provide helpful error messages"""
        if not self.api_key:
            debug_log("[ERROR] LLAMAPARSE_API_KEY is not configured")
            return False, "LlamaParse API key is not configured. Please set LLAMAPARSE_API_KEY environment variable."
        
        if len(self.api_key) < 20:
            debug_log("[ERROR] LLAMAPARSE_API_KEY appears to be too short")
            return False, "LlamaParse API key appears to be invalid (too short). Please check your API key."
        
        if not self.api_key.startswith(('llx-', 'll-')):
            debug_log("[WARNING] LLAMAPARSE_API_KEY doesn't start with expected prefix")
            # This is just a warning, not an error, as API key formats might change
        
        debug_log(f"[SUCCESS] LlamaParse API key configured (length: {len(self.api_key)})")
        return True, "LlamaParse API key is properly configured"
    
    def get_parser(self) -> LlamaParse:
        """Get LlamaParse parser instance with proper configuration"""
        return LlamaParse(
            api_key=self.api_key,
            result_type="markdown",  # Get markdown output
            verbose=True,
            language="en",
            max_timeout=600,  # 10 minute max timeout for large/complex PDFs
            num_workers=4,    # Parallel processing workers
            show_progress=True,  # Show progress for debugging
            invalidate_cache=True  # Don't use cached results to avoid stale data
        )
    
    @async_retry(retries=3, delay=2.0)
    async def parse_pdf_contents(
        self, 
        file_contents: bytes, 
        filename: str, 
        content_type: str, 
        session_id: Optional[str] = None,
        progress_manager: Optional[any] = None
    ) -> str:
        """Parse file contents using LlamaIndex LlamaParse plugin"""
        debug_log(f"[LLAMAPARSE] Processing file with LlamaIndex plugin: {filename}, content_type: {content_type}")
        
        file_size = len(file_contents)
        debug_log(f"[LLAMAPARSE] File size: {file_size} bytes")
        
        if file_size == 0:
            raise HTTPException(status_code=400, detail="File is empty.")
        
        if not self.api_key:
            debug_log("[ERROR] LlamaParse API key not configured")
            raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
        
        # Validate file before processing
        if not self.validate_config()[0]:
            debug_log("[ERROR] LlamaParse configuration validation failed")
            raise HTTPException(status_code=500, detail="LlamaParse configuration validation failed.")
        
        async with _llamaparse_semaphore:  # Rate limiting
            try:
                # Update progress if session_id provided
                if session_id and progress_manager:
                    progress_manager.update_progress(session_id, "upload", 10, "Preparing file for LlamaParse...")
                
                # Create temporary file for LlamaIndex LlamaParse plugin
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                    temp_file.write(file_contents)
                    temp_file_path = temp_file.name
                
                try:
                    # Update progress
                    if session_id and progress_manager:
                        progress_manager.update_progress(session_id, "processing", 20, "Parsing with LlamaParse...")
                    
                    # Use LlamaIndex LlamaParse plugin
                    parser = self.get_parser()

                    # Parse the file using the plugin (use async method for proper connection handling)
                    documents = await parser.aload_data(temp_file_path)
                    
                    # Update progress
                    if session_id and progress_manager:
                        progress_manager.update_progress(session_id, "processing", 90, "Processing results...")
                    
                    # Extract text from documents
                    if documents and len(documents) > 0:
                        # Combine all document text
                        combined_text = "\n\n".join([doc.text for doc in documents])
                        debug_log(f"[LLAMAPARSE] Successfully parsed {filename}, extracted {len(combined_text)} characters")
                        
                        if session_id and progress_manager:
                            progress_manager.update_progress(session_id, "processing", 100, "Parsing complete!")
                        
                        return combined_text
                    else:
                        debug_log(f"[LLAMAPARSE] No documents returned for {filename}")
                        if session_id and progress_manager:
                            progress_manager.error_processing(session_id, "No content extracted from PDF")
                        raise HTTPException(status_code=500, detail="No content could be extracted from the PDF")
                        
                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(temp_file_path)
                    except Exception as e:
                        debug_log(f"[LLAMAPARSE] Warning: Could not delete temp file {temp_file_path}: {e}")
                        
            except Exception as e:
                debug_log(f"[LLAMAPARSE] LlamaParse failed: {e}")
                if session_id and progress_manager:
                    progress_manager.error_processing(session_id, f"PDF parsing failed: {str(e)}")
                raise HTTPException(status_code=500, detail=f"PDF parsing failed: {str(e)}")
    
    async def parse_file(self, file: UploadFile, session_id: Optional[str] = None, progress_manager: Optional[any] = None) -> str:
        """Send a file to LlamaParse using LlamaIndex plugin and return the parsed markdown content."""
        
        debug_log(f"[LLAMAPARSE] Processing file with LlamaIndex plugin: {file.filename}, content_type: {file.content_type}")
        
        # Read file content once to avoid "read of closed file" errors
        try:
            file_contents = await file.read()
            file_size = len(file_contents)
            debug_log(f"[LLAMAPARSE] File size: {file_size} bytes")
            
            if file_size == 0:
                raise HTTPException(status_code=400, detail="File is empty.")
                
        except Exception as e:
            debug_log(f"[LLAMAPARSE] Could not read file: {e}")
            raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
        
        if not self.api_key:
            debug_log("[ERROR] LlamaParse API key not configured")
            raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
        
        # Validate file before processing
        if not file.filename:
            raise HTTPException(status_code=400, detail="File must have a filename.")
        
        debug_log(f"[LLAMAPARSE] Processing file: {file.filename}, size: {file_size} bytes")
        
        # Use the LlamaIndex plugin implementation
        return await self.parse_pdf_contents(file_contents, file.filename, file.content_type, session_id, progress_manager)
    
    async def parse_text_file(self, file_contents: bytes, filename: str) -> str:
        """Extract text from text-based files (TXT, MD, etc.)"""
        try:
            text = file_contents.decode('utf-8', errors='ignore')
            return f"[File: {filename}]\n{text.strip()}\n"
        except Exception as e:
            return f"[File: {filename}]\n[Could not extract text: {e}]\n"
    
    async def parse_file_flexible(
        self, 
        file: UploadFile, 
        session_id: Optional[str] = None, 
        progress_manager: Optional[any] = None
    ) -> str:
        """Parse a file using the appropriate method based on file type."""
        filename = file.filename.lower() if file.filename else ""
        
        # Read file contents once to avoid "read of closed file" errors
        try:
            # Reset file position to beginning in case it was already read
            if hasattr(file.file, 'seek'):
                file.file.seek(0)
            file_contents = await file.read()
            file_size = len(file_contents)
            debug_log(f"[FILE_PROCESSING] File: {file.filename}, size: {file_size} bytes")
            
            if file_size == 0:
                raise HTTPException(status_code=400, detail="File is empty.")
                
        except Exception as e:
            debug_log(f"[FILE_PROCESSING] Could not read file: {e}")
            raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
        
        # For PDF files, use LlamaParse
        if filename.endswith('.pdf') or file.content_type == "application/pdf":
            return await self.parse_pdf_contents(file_contents, file.filename, file.content_type, session_id, progress_manager)
        
        # For text-based files, extract text directly
        elif filename.endswith(('.txt', '.md')) or file.content_type in ["text/plain", "text/markdown"]:
            return await self.parse_text_file(file_contents, file.filename)
        
        # For Word documents, try to extract text (basic implementation)
        elif filename.endswith(('.doc', '.docx')) or file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
            return await self.parse_text_file(file_contents, file.filename)
        
        else:
            # Fallback: try LlamaParse for other file types
            debug_log(f"Unknown file type {file.content_type}, trying LlamaParse as fallback...")
            return await self.parse_pdf_contents(file_contents, file.filename, file.content_type, session_id, progress_manager)


# Global parser service instance
parser_service = ParserService()
