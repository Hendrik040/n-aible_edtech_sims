#!/usr/bin/env python3
"""
Set up test users with simulation instances for load testing

This script:
1. Assigns test users to an existing cohort
2. Assigns a scenario to the cohort (creates CohortSimulation)
3. This auto-creates StudentSimulationInstance for each test user

Usage:
    python scripts/setup_test_simulations.py
    python scripts/setup_test_simulations.py --cohort-id 1 --scenario-id 1
"""

import sys
import argparse
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from database.connection import get_db_session
from database.models import (
    User, Cohort, Scenario, CohortStudent, CohortSimulation, 
    StudentSimulationInstance, UserProgress
)
from common.utilities.id_generator import generate_unique_simulation_instance_id

def setup_test_simulations(cohort_id: int = None, scenario_id: int = None, count: int = 40):
    """Set up test users with simulation instances"""
    
    with get_db_session() as db:
        # Get or create cohort
        if cohort_id:
            cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
            if not cohort:
                print(f"❌ Cohort {cohort_id} not found")
                return
        else:
            cohort = db.query(Cohort).first()
            if not cohort:
                print("❌ No cohorts found in database. Please create a cohort first.")
                return
        
        print(f"✅ Using cohort ID: {cohort.id}")
        
        # Get or create scenario
        if scenario_id:
            scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
            if not scenario:
                print(f"❌ Scenario {scenario_id} not found")
                return
        else:
            scenario = db.query(Scenario).first()
            if not scenario:
                print("❌ No scenarios found in database. Please create a scenario first.")
                return
        
        print(f"✅ Using scenario ID: {scenario.id} - {scenario.title[:50]}")
        
        # Get a professor to assign the simulation
        professor = db.query(User).filter(User.role == 'professor').first()
        if not professor:
            print("❌ No professor found. Need a professor to assign simulations.")
            return
        
        print(f"✅ Using professor ID: {professor.id} to assign simulation")
        print()
        
        # Get test users
        test_users = db.query(User).filter(
            User.email.like('teststudent%@test.com')
        ).limit(count).all()
        
        if not test_users:
            print(f"❌ No test users found. Run create_test_users.py first.")
            return
        
        print(f"👥 Found {len(test_users)} test users")
        
        # Step 1: Assign test users to cohort
        enrolled_count = 0
        for user in test_users:
            existing = db.query(CohortStudent).filter(
                CohortStudent.cohort_id == cohort.id,
                CohortStudent.student_id == user.id
            ).first()
            
            if not existing:
                cohort_student = CohortStudent(
                    cohort_id=cohort.id,
                    student_id=user.id,
                    status="approved"
                )
                db.add(cohort_student)
                enrolled_count += 1
        
        if enrolled_count > 0:
            db.commit()
            print(f"✅ Enrolled {enrolled_count} test users into cohort")
        else:
            print(f"⏭️  All test users already enrolled in cohort")
        
        # Step 2: Create or get CohortSimulation
        cohort_simulation = db.query(CohortSimulation).filter(
            CohortSimulation.cohort_id == cohort.id,
            CohortSimulation.simulation_id == scenario.id
        ).first()
        
        if not cohort_simulation:
            cohort_simulation = CohortSimulation(
                cohort_id=cohort.id,
                simulation_id=scenario.id,
                assigned_by=professor.id,
                is_required=True
            )
            db.add(cohort_simulation)
            db.commit()
            db.refresh(cohort_simulation)
            print(f"✅ Created cohort simulation assignment (ID: {cohort_simulation.id})")
        else:
            print(f"✅ Using existing cohort simulation assignment (ID: {cohort_simulation.id})")
        
        # Step 3: Create simulation instances for test users
        instances_created = 0
        instances_existing = 0
        
        for user in test_users:
            # Check if instance already exists
            existing_instance = db.query(StudentSimulationInstance).filter(
                StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id,
                StudentSimulationInstance.student_id == user.id
            ).first()
            
            if existing_instance:
                instances_existing += 1
                continue
            
            # Create UserProgress
            user_progress = UserProgress(
                user_id=user.id,
                scenario_id=scenario.id,
                simulation_status="not_started"
            )
            db.add(user_progress)
            db.flush()
            
            # Create StudentSimulationInstance
            instance = StudentSimulationInstance(
                unique_id=generate_unique_simulation_instance_id(db),
                cohort_assignment_id=cohort_simulation.id,
                student_id=user.id,
                user_progress_id=user_progress.id
            )
            db.add(instance)
            instances_created += 1
        
        if instances_created > 0:
            db.commit()
            print(f"✅ Created {instances_created} simulation instances")
        
        if instances_existing > 0:
            print(f"⏭️  {instances_existing} simulation instances already exist")
        
        # Verify
        total_instances = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id
        ).count()
        
        print()
        print("=" * 60)
        print("📊 Setup Complete!")
        print("=" * 60)
        print(f"   Cohort ID: {cohort.id}")
        print(f"   Scenario ID: {scenario.id}")
        print(f"   Total simulation instances: {total_instances}")
        print(f"   Test users ready for load testing!")
        print()

def main():
    parser = argparse.ArgumentParser(description="Set up test users with simulation instances")
    parser.add_argument("--cohort-id", type=int, default=None, help="Cohort ID to use (default: first available)")
    parser.add_argument("--scenario-id", type=int, default=None, help="Scenario ID to use (default: first available)")
    parser.add_argument("--count", type=int, default=40, help="Number of test users to set up (default: 40)")
    
    args = parser.parse_args()
    
    setup_test_simulations(args.cohort_id, args.scenario_id, args.count)

if __name__ == "__main__":
    main()

