#!/usr/bin/env python3
"""
Script to check if PDFs are being uploaded to S3 and if case_study_url is set correctly.
This helps diagnose issues with PDF case study storage.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal
from database.models import Scenario, ScenarioFile
from services.wasabi_service import wasabi_service
import asyncio

async def check_scenario_pdfs():
    """Check all scenarios for PDF case study URLs"""
    db = SessionLocal()
    try:
        scenarios = db.query(Scenario).all()
        print(f"\n{'='*80}")
        print(f"Checking {len(scenarios)} scenarios for PDF case studies...")
        print(f"{'='*80}\n")
        
        for scenario in scenarios:
            case_study_url = getattr(scenario, 'case_study_url', None)
            scenario_files = db.query(ScenarioFile).filter(
                ScenarioFile.scenario_id == scenario.id
            ).all()
            
            print(f"Scenario ID: {scenario.id} - {scenario.title}")
            print(f"  case_study_url: {case_study_url}")
            print(f"  ScenarioFile records: {len(scenario_files)}")
            
            for sf in scenario_files:
                print(f"    - {sf.filename}: {sf.file_path}")
                if sf.file_path:
                    # Check if file exists in S3
                    if 'case_study' in sf.file_path or 'case-study' in sf.file_path:
                        # Extract S3 key from URL
                        from urllib.parse import urlparse, unquote
                        parsed = urlparse(sf.file_path)
                        path = parsed.path.lstrip('/')
                        # Remove bucket name if present
                        if path.startswith(wasabi_service.bucket_name + '/'):
                            s3_key = path[len(wasabi_service.bucket_name) + 1:]
                        else:
                            s3_key = path
                        s3_key = unquote(s3_key)
                        print(f"      S3 Key: {s3_key}")
                        exists = await wasabi_service.file_exists(s3_key)
                        print(f"      Exists in S3: {'✅ YES' if exists else '❌ NO'}")
            
            print()
        
        print(f"{'='*80}\n")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(check_scenario_pdfs())

