# Wasabi S3 Storage Configuration Guide

## Overview

This application uses **Wasabi** as an S3-compatible object storage service for permanent file storage. Wasabi provides cost-effective, high-performance storage for:

- **PDF Case Studies**: Organized per scenario
- **Persona Avatars**: Grouped under their parent scenario
- **Scene Images**: Grouped under their parent scenario

Wasabi is fully compatible with the AWS S3 API, so we use the `boto3` library to interact with it.

---

## Hierarchical Folder Structure

**NEW STRUCTURE (Hierarchical - Current):**

All assets for a scenario are organized under a single parent folder:

```
scenarios/{scenario_id}/
├── case-study/
│   └── {filename}.pdf
├── personas/
│   ├── {persona_id}/
│   │   └── avatar.{ext}
│   ├── {persona_id}/
│   │   └── avatar.{ext}
│   └── {persona_id}/
│       └── avatar.{ext}
└── scenes/
    ├── {scene_id}/
    │   └── image.{ext}
    ├── {scene_id}/
    │   └── image.{ext}
    └── {scene_id}/
        └── image.{ext}
```

**Example:**
```
n-gage/  (bucket)
└── scenarios/
    └── 550e8400-e29b-41d4-a716-446655440000/
        ├── case-study/
        │   └── Marketing_Strategy.pdf
        ├── personas/
        │   ├── 101/
        │   │   └── avatar.png
        │   ├── 102/
        │   │   └── avatar.webp
        │   └── 103/
        │       └── avatar.png
        └── scenes/
            ├── 201/
            │   └── image.png
            ├── 202/
            │   └── image.webp
            └── 203/
                └── image.png
```

**Benefits of Hierarchical Structure:**
✅ All assets for one scenario in one place
✅ Easy to backup/restore entire scenarios
✅ Delete scenario → delete entire folder (clean sweep)
✅ Clear ownership: personas/scenes belong to a scenario
✅ Matches database relationships (1 scenario has many personas/scenes)
✅ Intuitive for manual management in Wasabi Console

---

## Required Configuration

### Environment Variables

Add these to your `.env` file (local development) or Railway environment variables (production):

```bash
# Wasabi Credentials (get from https://console.wasabisys.com/)
WASABI_ACCESS_KEY_ID=your_access_key_here
WASABI_SECRET_ACCESS_KEY=your_secret_key_here
WASABI_BUCKET_NAME=your_bucket_name
WASABI_ENDPOINT_URL=https://s3.wasabisys.com

# CRITICAL: Enable public read access for files
WASABI_PUBLIC_READ=true
```

### Getting Wasabi Credentials

1. **Sign up for Wasabi**: Visit [https://wasabi.com/](https://wasabi.com/) and create an account
2. **Create Access Keys**:
   - Go to Wasabi Console → Access Keys
   - Click "Create New Access Key"
   - Save both the Access Key ID and Secret Access Key (secret is only shown once!)
3. **Create a Bucket**:
   - Go to Wasabi Console → Buckets
   - Click "Create Bucket"
   - Choose a unique bucket name (e.g., `n-gage`, `my-app-storage`)
   - Select a region (US East 1 is default)
4. **Get Endpoint URL**:
   - Default: `https://s3.wasabisys.com`
   - Regional: `https://s3.us-east-1.wasabisys.com`, `https://s3.us-west-1.wasabisys.com`, etc.
   - Must match your bucket's region

---

## Public Access Configuration

**CRITICAL**: Files must be publicly accessible for images to display in simulations and PDFs to be downloadable.

### Option 1: Per-File ACL (Recommended)

Set `WASABI_PUBLIC_READ=true` in your environment variables.

**How it works:**
- Each file is uploaded with `ACL='public-read'`
- Files are individually marked as public
- More granular control over access

**Pros:**
- Easy to implement (just set the environment variable)
- Can mix public and private files if needed in the future
- Works immediately without Wasabi Console configuration

**Cons:**
- Slightly slower uploads (ACL set per file)
- Must be set correctly in environment variables

### Option 2: Bucket Policy (Alternative)

Keep `WASABI_PUBLIC_READ=false` and configure a bucket policy in Wasabi Console.

**How to configure:**
1. Go to Wasabi Console → Your Bucket → Policies
2. Add this JSON policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/*"
    }
  ]
}
```

3. Replace `YOUR_BUCKET_NAME` with your actual bucket name
4. Save the policy

**Pros:**
- Faster uploads (no ACL overhead)
- Applies to all files automatically
- Centralized access control

**Cons:**
- ALL files in the bucket become public
- Requires manual Wasabi Console configuration
- Less flexible if you need private files later

---

## Troubleshooting

### Problem: Images don't appear in simulation (403 Forbidden)

**Symptoms:**
- Broken image placeholders in simulation interface
- Browser console shows 403 Forbidden errors for image URLs
- Images exist in Wasabi bucket but can't be accessed

**Diagnosis:**
1. Open browser DevTools (F12) → Network tab
2. Look for failed image requests (red status)
3. Click on failed request and check status code (should be 403)

**Cause:** Files are private - no public-read ACL was set during upload

**Solution:**
1. Set `WASABI_PUBLIC_READ=true` in your environment variables
2. Restart your application
3. Re-upload the PDF to create new scenario with public images
4. **OR** configure bucket policy (see Option 2 above) to make all existing files public

**Verification:**
1. After setting `WASABI_PUBLIC_READ=true`, check application logs for:
   ```
   [WASABI] ✅ Public read enabled - files will be uploaded with 'public-read' ACL
   [WASABI] Successfully uploaded file to scenarios/{scenario_id}/personas/{persona_id}/avatar.png (ACL: public)
   ```
2. Try accessing image URL directly in browser - should display the image
3. Use browser DevTools to confirm 200 OK status for image requests

---

### Problem: Files in old folder structure

**Symptoms:**
- Logs show warnings about old paths:
  ```
  ⚠️ WARNING: PDF in old flat structure (case-studies/), should be in scenarios/{id}/case-study/
  ```
- Files scattered across `case-studies/`, `personas/`, `scenes/` instead of `scenarios/`

**Cause:** Old code used flat folder structure before hierarchical redesign

**Solution:** All new uploads automatically use the hierarchical structure. Old files will continue to work.

**Cleanup (Optional):**
1. **Option A**: Leave old files in place - they still work
2. **Option B**: Delete old folders manually in Wasabi Console
3. **Option C**: Re-upload scenarios to migrate to new structure

---

### Problem: Wasabi credentials not working

**Symptoms:**
- Application logs show: `[WASABI] Missing credentials, S3 client not initialized`
- Or: `[WASABI] Upload failed: Access Denied`

**Diagnosis Steps:**

1. **Check environment variables are set:**
   ```bash
   # In Railway dashboard, verify all 5 variables are present:
   WASABI_ACCESS_KEY_ID
   WASABI_SECRET_ACCESS_KEY
   WASABI_BUCKET_NAME
   WASABI_ENDPOINT_URL
   WASABI_PUBLIC_READ
   ```

2. **Verify credentials in Wasabi Console:**
   - Go to Access Keys section
   - Confirm your Access Key ID matches the one in environment variables
   - If secret key is wrong, create a new access key pair

3. **Check endpoint URL matches bucket region:**
   - In Wasabi Console → Buckets, note your bucket's region
   - Use corresponding endpoint:
     - US East 1: `https://s3.us-east-1.wasabisys.com`
     - US East 2: `https://s3.us-east-2.wasabisys.com`
     - US West 1: `https://s3.us-west-1.wasabisys.com`
     - EU Central 1: `https://s3.eu-central-1.wasabisys.com`
     - Asia Pacific: `https://s3.ap-northeast-1.wasabisys.com`

4. **Test with AWS CLI:**
   ```bash
   # Install AWS CLI if needed
   pip install awscli

   # Configure profile
   aws configure --profile wasabi
   # Enter your Wasabi Access Key ID
   # Enter your Wasabi Secret Access Key
   # Region: us-east-1 (or your bucket's region)

   # Test bucket access
   aws s3 ls s3://your-bucket-name \
     --endpoint-url=https://s3.wasabisys.com \
     --profile wasabi
   ```

---

## Railway Deployment

### Setting Environment Variables

1. Go to your Railway project dashboard
2. Click on your backend service
3. Navigate to "Variables" tab
4. Add each Wasabi variable:
   - Click "+ New Variable"
   - Enter variable name and value
   - Click "Add"
5. **Important**: After adding variables, Railway will automatically redeploy

### Screenshot Guide

```
Railway Dashboard
  └── Your Project
      └── Backend Service
          └── Variables Tab
              ├── WASABI_ACCESS_KEY_ID = your_key
              ├── WASABI_SECRET_ACCESS_KEY = your_secret
              ├── WASABI_BUCKET_NAME = n-gage
              ├── WASABI_ENDPOINT_URL = https://s3.wasabisys.com
              └── WASABI_PUBLIC_READ = true
```

### Restart Requirement

- Railway auto-restarts after variable changes
- Check deployment logs to confirm Wasabi initialization:
  ```
  [WASABI] Service initialized with bucket: n-gage, public_read=True
  [WASABI] ✅ Public read enabled - files will be uploaded with 'public-read' ACL
  ```

---

## Local Development

### Using .env File

1. Copy `env_template.txt` to `.env`:
   ```bash
   cp env_template.txt .env
   ```

2. Edit `.env` and fill in Wasabi credentials:
   ```bash
   WASABI_ACCESS_KEY_ID=your_access_key_here
   WASABI_SECRET_ACCESS_KEY=your_secret_key_here
   WASABI_BUCKET_NAME=n-gage
   WASABI_ENDPOINT_URL=https://s3.wasabisys.com
   WASABI_PUBLIC_READ=true
   ```

3. **IMPORTANT**: Never commit `.env` to git
   - `.env` is already in `.gitignore`
   - If you accidentally commit it, rotate your Wasabi keys immediately

### Testing Wasabi Connection

You can test the connection programmatically:

```python
# In Python console or test script
from services.wasabi_service import wasabi_service
import asyncio

async def test():
    result = await wasabi_service.validate_connection()
    if result:
        print("✅ Wasabi connection successful!")
    else:
        print("❌ Wasabi connection failed - check credentials")

asyncio.run(test())
```

### Viewing Uploaded Files

1. Go to Wasabi Console: [https://console.wasabisys.com/](https://console.wasabisys.com/)
2. Click on your bucket name
3. Browse the hierarchical folder structure:
   - `scenarios/` → `{scenario_id}/` → `case-study/`, `personas/`, `scenes/`
4. Click on any file to view details or download
5. Copy public URL to test accessibility in browser

---

## Security Best Practices

### Credential Management

1. **Never commit credentials to git**
   - Always use `.env` file (already in `.gitignore`)
   - Use environment variables in production
   - Review git history if you suspect accidental commits

2. **Use Railway environment variables for production**
   - Set in Railway dashboard, not in code
   - Railway encrypts environment variables
   - Can be rotated without code changes

3. **Rotate access keys regularly**
   - Wasabi Console → Access Keys → Create New Access Key
   - Update environment variables with new keys
   - Delete old access keys after verifying new ones work

4. **Use separate keys for development and production**
   - Create different Wasabi access keys for local vs Railway
   - Makes key rotation easier
   - Limits blast radius if keys are compromised

### Access Control

1. **Public vs Private Files:**
   - Current setup: All files are public (required for the app to work)
   - Future: Could implement presigned URLs for sensitive documents
   - Consider: Do personas/scenes need to be public? (Yes, for student access)

2. **Bucket Permissions:**
   - Limit access keys to single bucket (if Wasabi supports it)
   - Don't reuse keys across multiple projects
   - Monitor Wasabi access logs if available

---

## Performance Considerations

### Parallel Uploads (Already Implemented)

The system uploads multiple images in parallel for better performance:

**Code reference:** `backend/api/publishing.py` line 361-457

```python
# Personas and scenes are uploaded concurrently using asyncio.gather()
async def _handle_image_uploads(personas_to_upload, scenes_to_upload, db):
    # Upload all persona avatars in parallel
    persona_tasks = [upload_persona_avatar(...) for persona in personas_to_upload]

    # Upload all scene images in parallel
    scene_tasks = [upload_scene_image(...) for scene in scenes_to_upload]

    # Wait for all uploads to complete
    await asyncio.gather(*persona_tasks, *scene_tasks)
```

**Performance impact:**
- Sequential: 6 images × 2s each = 12s total
- Parallel: max(2s) = 2s total (6x faster!)

### Retry Logic (Already Implemented)

Automatic retries with exponential backoff handle transient network issues:

**Code reference:** `backend/services/wasabi_service.py` line 238-275

```python
max_retries = 3
delay = 1.0

for attempt in range(max_retries):
    try:
        # Upload attempt
        ...
    except ClientError as e:
        if attempt < max_retries - 1:
            wait_time = delay * (2 ** attempt)  # 1s, 2s, 4s
            await asyncio.sleep(wait_time)
```

**Benefits:**
- Handles temporary network glitches
- Exponential backoff prevents overwhelming the service
- Logs all retry attempts for debugging

---

## Debug Logging

### Enable Detailed Wasabi Logs

The application logs all Wasabi operations. Look for these log patterns:

**Initialization:**
```
[WASABI] Service initialized with bucket: n-gage, public_read=True
[WASABI] ✅ Public read enabled - files will be uploaded with 'public-read' ACL
```

**Upload Success (Hierarchical Structure):**
```
[WASABI] Successfully uploaded file to scenarios/550e8400.../case-study/file.pdf (ACL: public)
[PDF_STORAGE] ✅ PDF uploaded to correct hierarchical path: https://...
[WASABI] Successfully uploaded file to scenarios/550e8400.../personas/101/avatar.png (ACL: public)
[WASABI] Successfully uploaded file to scenarios/550e8400.../scenes/201/image.webp (ACL: public)
```

**Upload Failure:**
```
[WASABI] Upload attempt 1 failed: Access Denied. Retrying in 1.0s...
[WASABI] Upload failed after 3 attempts: Access Denied
```

**Path Validation Warnings:**
```
[PDF_STORAGE] ⚠️ WARNING: PDF in old flat structure (case-studies/), should be in scenarios/{id}/case-study/
[PDF_STORAGE] ⚠️ WARNING: PDF in temporary path, should be in scenarios/{id}/case-study/
```

### Enable Public Access Validation (Optional)

For extra debugging, enable public access checks:

```bash
# Add to .env or Railway variables
WASABI_VALIDATE_PUBLIC_ACCESS=true
```

This will test each uploaded file's public accessibility:

```
[WASABI] ✅ File is publicly accessible: scenarios/123/scenes/456/image.png
[WASABI] ❌ File not publicly accessible (HTTP 403): scenarios/123/scenes/456/image.png
```

**Warning:** This adds latency to uploads (1 extra HTTP request per file). Only enable for debugging.

---

## FAQ

### Q: Why use Wasabi instead of AWS S3?

**A:** Wasabi is more cost-effective for storage-heavy applications:
- Wasabi: $5.99/TB/month, no egress fees
- AWS S3: $23/TB/month + egress charges
- For an app storing thousands of PDFs/images, Wasabi saves significant costs

### Q: Can I use AWS S3 instead?

**A:** Yes! The code is S3-compatible. Just change environment variables:
- `WASABI_ENDPOINT_URL` → Leave blank or use S3 endpoint
- `WASABI_ACCESS_KEY_ID` → AWS Access Key ID
- `WASABI_SECRET_ACCESS_KEY` → AWS Secret Access Key
- `WASABI_BUCKET_NAME` → Your S3 bucket name

The `boto3` library works with both services.

### Q: What if I don't want files to be public?

**A:** Current implementation requires public access for images to display. To make files private:

1. Set `WASABI_PUBLIC_READ=false`
2. Modify code to generate presigned URLs:
   ```python
   # In wasabi_service.py
   def generate_presigned_url(self, s3_key: str, expiration=3600):
       return self.s3_client.generate_presigned_url(
           'get_object',
           Params={'Bucket': self.bucket_name, 'Key': s3_key},
           ExpiresIn=expiration
       )
   ```
3. Update database to store presigned URLs (expires after 1 hour)
4. Implement URL refresh logic before expiration

**Tradeoff:** More complex code, URLs expire and need regeneration.

### Q: How much does Wasabi cost for this application?

**Rough estimate:**
- 100 scenarios × 5MB PDF each = 500MB
- 100 scenarios × 6 scenes × 500KB each = 300MB
- 100 scenarios × 4 personas × 300KB each = 120MB
- **Total: ~1GB storage = $0.006/month** (negligible)

Wasabi minimum is $5.99/month for up to 1TB, so you're basically paying a flat fee regardless of usage for this scale.

### Q: Why hierarchical structure instead of flat?

**A:** The hierarchical structure (`scenarios/{id}/personas/` vs `personas/{id}/`) provides:
- **Logical organization**: All assets for one scenario in one place
- **Easy cleanup**: Delete scenario folder = delete everything
- **Clear ownership**: Folder structure matches data relationships
- **Better backup/restore**: Can archive individual scenarios
- **Easier management**: Intuitive for developers and administrators

---

## Code References

### Wasabi Service

**File:** `backend/services/wasabi_service.py`

**Key Methods:**
- `get_case_study_key(scenario_id, filename)` → `scenarios/{scenario_id}/case-study/{filename}`
- `get_persona_avatar_key(scenario_id, persona_id, ext)` → `scenarios/{scenario_id}/personas/{persona_id}/avatar.{ext}`
- `get_scene_image_key(scenario_id, scene_id, ext)` → `scenarios/{scenario_id}/scenes/{scene_id}/image.{ext}`
- `upload_from_bytes(file_bytes, s3_key, content_type)` → Upload bytes to Wasabi
- `upload_from_url(url, base_s3_key)` → Download from URL and upload to Wasabi

### Publishing API

**File:** `backend/api/publishing.py`

**Key Functions:**
- `_handle_pdf_storage(scenario, pdf_metadata, db)` → Upload PDFs to hierarchical structure (line 243)
- `_handle_image_uploads(personas_to_upload, scenes_to_upload, db)` → Parallel upload of images (line 361)

---

## Additional Resources

- **Wasabi Documentation:** [https://docs.wasabi.com/](https://docs.wasabi.com/)
- **Wasabi Console:** [https://console.wasabisys.com/](https://console.wasabisys.com/)
- **boto3 S3 Documentation:** [https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
- **Railway Documentation:** [https://docs.railway.app/](https://docs.railway.app/)

---

**Last Updated:** 2025-11-03
**Maintained By:** Development Team
**Version:** 2.0 (Hierarchical Structure)
