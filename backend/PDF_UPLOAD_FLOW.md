# PDF Case Study Upload Flow

## Overview
This document explains how PDF case studies are uploaded to S3 and loaded in the frontend.

## Flow

### 1. PDF Upload & Parsing (`backend/api/parse_pdf.py`)
- User uploads PDF in simulation builder
- PDF is parsed and `pdf_metadata` is created with:
  - `filename`: Original filename
  - `file_size`: File size in bytes
  - `file_type`: MIME type (usually "application/pdf")
  - **Small files (≤1MB)**: `file_contents_base64` - base64 encoded PDF content
  - **Large files (>1MB)**: `temp_pdf_url` - URL to temporary S3 location
  - **If scenario_id available during autofill**: `wasabi_url` - final S3 URL (uploaded immediately)

### 2. Save Scenario (`backend/api/publishing.py`)
- When user clicks "Save" or "Publish", `pdf_metadata` is passed in the request body
- `_save_scenario_to_db()` extracts `pdf_metadata` from `ai_result`
- Scenario is saved to database FIRST (non-blocking)
- PDF upload happens in **background task** (asynchronous)

### 3. PDF Storage (`backend/api/publishing.py::_handle_pdf_storage`)
The function handles PDFs in this priority order:

1. **Check if already uploaded**:
   - Check `scenario.case_study_url` (if already set, skip)
   - Check `ScenarioFile` record (if exists with Wasabi URL, skip)
   - Check if PDF exists in final S3 location (`scenarios/{scenario_id}/case_study/{filename}`)

2. **Base64 encoded files** (small files):
   - Decode base64 to bytes
   - Upload to `scenarios/{scenario_id}/case_study/{filename}`
   - Update `scenario.case_study_url` and create `ScenarioFile` record

3. **Temporary URL files** (large files):
   - Download PDF from `temp_pdf_url`
   - Upload to final location `scenarios/{scenario_id}/case_study/{filename}`
   - Delete temporary file
   - Update `scenario.case_study_url` and create `ScenarioFile` record

4. **Already uploaded files** (from autofill):
   - If `wasabi_url` is in metadata, use it directly
   - Update database records

### 4. Frontend Display
- Frontend fetches simulation data from `/api/simulation/start` or `/api/student/simulation-instances/{instance_id}/start-simulation`
- Response includes `scenario.case_study_url`
- Frontend displays PDF in iframe: `<iframe src={case_study_url} />`

## S3 Path Structure
```
scenarios/{scenario_id}/case_study/{filename}
```

Example:
```
scenarios/1/case_study/case_study.pdf
```

## Debugging

### Check if PDFs are uploaded:
```bash
cd backend
python3 scripts/check_pdf_upload.py
```

### Check backend logs:
Look for these log messages:
- `[PDF_STORAGE] 🔵 Starting PDF storage for scenario {id}`
- `[PDF_STORAGE] ✅ Updated Scenario.case_study_url to: {url}`
- `[PDF_STORAGE] ✅ Background PDF upload completed`

### Common Issues:

1. **PDF metadata not passed**:
   - Check frontend: `autofillResult?.pdf_metadata` or `autofillResult?.data?.pdf_metadata`
   - Check backend logs: `[PDF_STORAGE] ⚠️ No pdf_metadata found in AI result`

2. **Background task not running**:
   - Check backend logs for `[PDF_STORAGE] 📤 PDF upload started in background`
   - Check for errors: `[PDF_STORAGE] ❌ ERROR during PDF storage`

3. **PDF URL not accessible**:
   - Verify S3 bucket is public or CORS is configured
   - Check URL format in browser console
   - Verify file exists in S3 using the check script

4. **case_study_url is NULL**:
   - Background task might not have completed yet (check logs)
   - PDF upload might have failed (check error logs)
   - Refresh the simulation page after a few seconds

## Database Schema

### Scenario Table
- `case_study_url` (String, nullable): Direct URL to PDF in S3

### ScenarioFile Table
- `scenario_id` (Integer): Foreign key to Scenario
- `filename` (String): Original filename
- `file_path` (String): Full S3 URL
- `file_size` (Integer): File size in bytes
- `file_type` (String): MIME type

## Testing

1. Upload a PDF in simulation builder
2. Save the scenario
3. Check backend logs for PDF upload messages
4. Run `check_pdf_upload.py` to verify S3 upload
5. Start simulation and check if PDF displays in case study tab

