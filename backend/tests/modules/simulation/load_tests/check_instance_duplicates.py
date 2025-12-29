#!/usr/bin/env python3
"""
Diagnostic script to check for duplicate instance unique_ids and instance assignment issues.
"""
import sys
import os
from pathlib import Path

# Add backend to path so we can import modules
backend_dir = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from common.db.core import get_db
from common.config import get_settings

settings = get_settings()


def check_duplicate_unique_ids(db):
    """Check if any unique_ids are duplicated (should never happen)."""
    print("\n" + "="*80)
    print("1. CHECKING FOR DUPLICATE UNIQUE_IDS (should never happen)")
    print("="*80)
    
    query = text("""
        SELECT 
            unique_id,
            COUNT(*) as count,
            STRING_AGG(id::text, ', ') as instance_ids,
            STRING_AGG(student_id::text, ', ') as student_ids,
            STRING_AGG(DISTINCT student_id::text, ', ') as distinct_student_ids
        FROM student_simulation_instances
        GROUP BY unique_id
        HAVING COUNT(*) > 1
        ORDER BY count DESC;
    """)
    
    if settings.database_url.startswith("sqlite"):
        # SQLite version (no STRING_AGG, use GROUP_CONCAT)
        query = text("""
            SELECT 
                unique_id,
                COUNT(*) as count,
                GROUP_CONCAT(id) as instance_ids,
                GROUP_CONCAT(student_id) as student_ids,
                GROUP_CONCAT(DISTINCT student_id) as distinct_student_ids
            FROM student_simulation_instances
            GROUP BY unique_id
            HAVING COUNT(*) > 1
            ORDER BY count DESC;
        """)
    
    result = db.execute(query).fetchall()
    
    if result:
        print(f"❌ FOUND {len(result)} DUPLICATE UNIQUE_IDS!")
        for row in result:
            print(f"\n  Unique ID: {row[0]}")
            print(f"  Count: {row[1]}")
            print(f"  Instance IDs: {row[2]}")
            print(f"  Student IDs: {row[3]}")
            print(f"  Distinct Student IDs: {row[4]}")
    else:
        print("✅ No duplicate unique_ids found (good!)")


def check_specific_instance(db, unique_id):
    """Check details about a specific instance unique_id."""
    print("\n" + "="*80)
    print(f"2. CHECKING INSTANCE: {unique_id}")
    print("="*80)
    
    query = text("""
        SELECT 
            ssi.id as instance_id,
            ssi.unique_id,
            ssi.student_id,
            ssi.user_progress_id,
            ssi.cohort_assignment_id,
            ssi.status,
            u.email as student_email,
            up.user_id as progress_user_id,
            up.simulation_id as progress_simulation_id
        FROM student_simulation_instances ssi
        LEFT JOIN users u ON ssi.student_id = u.id
        LEFT JOIN user_progress up ON ssi.user_progress_id = up.id
        WHERE ssi.unique_id = :unique_id;
    """)
    
    result = db.execute(query, {"unique_id": unique_id}).fetchall()
    
    if result:
        print(f"Found {len(result)} instance(s) with unique_id={unique_id}:")
        for row in result:
            print(f"\n  Instance ID: {row[0]}")
            print(f"  Unique ID: {row[1]}")
            print(f"  Student ID: {row[2]}")
            print(f"  Student Email: {row[6]}")
            print(f"  User Progress ID: {row[3]}")
            print(f"  Progress User ID: {row[7]} (should match Student ID {row[2]})")
            print(f"  Cohort Assignment ID: {row[4]}")
            print(f"  Status: {row[5]}")
            print(f"  Progress Simulation ID: {row[8]}")
            
            if row[7] and row[7] != row[2]:
                print(f"  ⚠️  WARNING: UserProgress belongs to different user!")
    else:
        print(f"❌ No instance found with unique_id={unique_id}")


def check_students_per_cohort_assignment(db, unique_id):
    """Check how many students have instances for the same cohort assignment."""
    print("\n" + "="*80)
    print("3. CHECKING STUDENTS SHARING SAME COHORT ASSIGNMENT")
    print("="*80)
    
    # First get the cohort_assignment_id for this unique_id
    get_assignment_query = text("""
        SELECT cohort_assignment_id 
        FROM student_simulation_instances 
        WHERE unique_id = :unique_id 
        LIMIT 1;
    """)
    
    assignment_result = db.execute(get_assignment_query, {"unique_id": unique_id}).first()
    
    if not assignment_result or not assignment_result[0]:
        print(f"❌ Could not find cohort_assignment_id for unique_id={unique_id}")
        return
    
    assignment_id = assignment_result[0]
    print(f"Cohort Assignment ID: {assignment_id}\n")
    
    query = text("""
        SELECT 
            ssi.student_id,
            u.email,
            ssi.cohort_assignment_id,
            COUNT(*) as instance_count,
            STRING_AGG(ssi.unique_id, ', ') as instance_unique_ids
        FROM student_simulation_instances ssi
        JOIN users u ON ssi.student_id = u.id
        WHERE ssi.cohort_assignment_id = :assignment_id
        GROUP BY ssi.student_id, u.email, ssi.cohort_assignment_id
        ORDER BY instance_count DESC;
    """)
    
    if settings.database_url.startswith("sqlite"):
        query = text("""
            SELECT 
                ssi.student_id,
                u.email,
                ssi.cohort_assignment_id,
                COUNT(*) as instance_count,
                GROUP_CONCAT(ssi.unique_id) as instance_unique_ids
            FROM student_simulation_instances ssi
            JOIN users u ON ssi.student_id = u.id
            WHERE ssi.cohort_assignment_id = :assignment_id
            GROUP BY ssi.student_id, u.email, ssi.cohort_assignment_id
            ORDER BY instance_count DESC;
        """)
    
    result = db.execute(query, {"assignment_id": assignment_id}).fetchall()
    
    print(f"Found {len(result)} student(s) with instances for this cohort assignment:")
    for row in result:
        print(f"\n  Student ID: {row[0]}")
        print(f"  Email: {row[1]}")
        print(f"  Instance Count: {row[3]}")
        print(f"  Instance Unique IDs: {row[4]}")
        
        if row[3] > 1:
            print(f"  ⚠️  WARNING: Student has {row[3]} instances (should only have 1!)")


def check_user_progress_sharing(db):
    """Check if any user_progress_id is shared across multiple instances."""
    print("\n" + "="*80)
    print("4. CHECKING FOR SHARED USER_PROGRESS (should not happen)")
    print("="*80)
    
    query = text("""
        SELECT 
            user_progress_id,
            COUNT(*) as instance_count,
            STRING_AGG(unique_id, ', ') as instance_unique_ids,
            STRING_AGG(student_id::text, ', ') as student_ids
        FROM student_simulation_instances
        WHERE user_progress_id IS NOT NULL
        GROUP BY user_progress_id
        HAVING COUNT(*) > 1
        ORDER BY instance_count DESC;
    """)
    
    if settings.database_url.startswith("sqlite"):
        query = text("""
            SELECT 
                user_progress_id,
                COUNT(*) as instance_count,
                GROUP_CONCAT(unique_id) as instance_unique_ids,
                GROUP_CONCAT(student_id) as student_ids
            FROM student_simulation_instances
            WHERE user_progress_id IS NOT NULL
            GROUP BY user_progress_id
            HAVING COUNT(*) > 1
            ORDER BY instance_count DESC;
        """)
    
    result = db.execute(query).fetchall()
    
    if result:
        print(f"❌ FOUND {len(result)} USER_PROGRESS_ID(s) SHARED ACROSS MULTIPLE INSTANCES!")
        for row in result:
            print(f"\n  User Progress ID: {row[0]}")
            print(f"  Instance Count: {row[1]}")
            print(f"  Instance Unique IDs: {row[2]}")
            print(f"  Student IDs: {row[3]}")
    else:
        print("✅ No shared user_progress_ids found (good!)")


def check_custom_account_instance(db, email):
    """Check instance details for a custom account."""
    print("\n" + "="*80)
    print(f"5. CHECKING CUSTOM ACCOUNT: {email}")
    print("="*80)
    
    # First find the user
    user_query = text("SELECT id, email FROM users WHERE email = :email")
    user_result = db.execute(user_query, {"email": email}).first()
    
    if not user_result:
        print(f"❌ User with email {email} not found")
        return
    
    user_id = user_result[0]
    print(f"Found user: id={user_id}, email={user_result[1]}\n")
    
    # Get all instances for this user
    instances_query = text("""
        SELECT 
            ssi.id as instance_id,
            ssi.unique_id,
            ssi.student_id,
            ssi.user_progress_id,
            ssi.cohort_assignment_id,
            ssi.status,
            up.user_id as progress_user_id,
            up.simulation_id as progress_simulation_id,
            up.simulation_status as progress_status,
            up.completed_at
        FROM student_simulation_instances ssi
        LEFT JOIN user_progress up ON ssi.user_progress_id = up.id
        WHERE ssi.student_id = :user_id
        ORDER BY ssi.created_at DESC;
    """)
    
    instances = db.execute(instances_query, {"user_id": user_id}).fetchall()
    
    if not instances:
        print(f"❌ No instances found for user {email}")
        return
    
    print(f"Found {len(instances)} instance(s) for {email}:")
    for row in instances:
        print(f"\n  Instance ID: {row[0]}")
        print(f"  Unique ID: {row[1]}")
        print(f"  Student ID: {row[2]}")
        print(f"  Status: {row[5]}")
        print(f"  User Progress ID: {row[3]}")
        if row[3]:  # If user_progress_id exists
            print(f"  Progress User ID: {row[6]} (should match Student ID {row[2]})")
            print(f"  Progress Simulation ID: {row[7]}")
            print(f"  Progress Status: {row[8]}")
            print(f"  Progress Completed At: {row[9]}")
            
            if row[6] and row[6] != row[2]:
                print(f"  ⚠️  CRITICAL: UserProgress belongs to different user (user_id={row[6]}, should be {row[2]})!")
            if row[8] == "completed" or row[9]:
                print(f"  ⚠️  WARNING: UserProgress is already completed! This explains why simulation shows as completed.")
        else:
            print(f"  (No user_progress_id linked)")


def main():
    print("Database Instance Diagnostic Tool")
    print("="*80)
    print(f"Database URL: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")
    
    # Get database session
    db_gen = get_db()
    db = next(db_gen)
    
    try:
        # Run all checks
        check_duplicate_unique_ids(db)
        
        # Check the specific instance the user mentioned
        check_specific_instance(db, "SI-V0PKG2UR")
        
        check_students_per_cohort_assignment(db, "SI-V0PKG2UR")
        
        check_user_progress_sharing(db)
        
        # Check for instances with completed/graded status that might be incorrectly linked
        print("\n" + "="*80)
        print("5. CHECKING COMPLETED/GRADED INSTANCES (might show as completed incorrectly)")
        print("="*80)
        
        completed_query = text("""
            SELECT 
                ssi.id,
                ssi.unique_id,
                ssi.student_id,
                u.email,
                ssi.status,
                ssi.user_progress_id,
                up.user_id as progress_user_id,
                up.simulation_status,
                up.completed_at
            FROM student_simulation_instances ssi
            JOIN users u ON ssi.student_id = u.id
            LEFT JOIN user_progress up ON ssi.user_progress_id = up.id
            WHERE ssi.status IN ('completed', 'graded')
            ORDER BY ssi.completed_at DESC NULLS LAST
            LIMIT 10;
        """)
        
        completed_instances = db.execute(completed_query).fetchall()
        
        if completed_instances:
            print(f"Found {len(completed_instances)} completed/graded instances:")
            for row in completed_instances:
                print(f"\n  Instance: {row[1]} (id={row[0]})")
                print(f"  Student: {row[3]} (id={row[2]})")
                print(f"  Instance Status: {row[4]}")
                print(f"  User Progress ID: {row[5]}")
                if row[5]:
                    print(f"  Progress User ID: {row[6]}")
                    print(f"  Progress Status: {row[7]}")
                    print(f"  Progress Completed At: {row[8]}")
                    if row[6] and row[6] != row[2]:
                        print(f"  ⚠️  WARNING: UserProgress belongs to different user!")
        else:
            print("No completed instances found")
        
        # Check custom account (you'll need to provide the email)
        import sys
        if len(sys.argv) > 1:
            custom_email = sys.argv[1]
            check_custom_account_instance(db, custom_email)
        else:
            print("\n" + "="*80)
            print("6. CUSTOM ACCOUNT CHECK SKIPPED")
            print("="*80)
            print("To check a custom account, run: python check_instance_duplicates.py <email>")
        
        print("\n" + "="*80)
        print("DIAGNOSTIC COMPLETE")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error running diagnostic: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
