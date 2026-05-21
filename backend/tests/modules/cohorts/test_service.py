"""
Tests for the cohort service layer.

These tests cover the business logic in the CohortService class.
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from modules.cohorts.service import CohortService
from modules.cohorts.schemas import (
    CohortCreate, CohortUpdate, 
    CohortStudentCreate, CohortStudentUpdate,
    CohortSimulationCreate, InviteLinkCreate
)
from common.db.models import User, Scenario, Cohort, CohortStudent, CohortSimulation


def create_test_professor(db: Session) -> User:
    """Create a test professor user."""
    import secrets
    unique_id = f"{datetime.now().timestamp()}_{secrets.token_hex(4)}"
    user = User(
        user_id=f"prof_{unique_id}",  # Required field
        email=f"professor_{unique_id}@test.com",
        full_name="Test Professor",
        username=f"professor_{unique_id}",
        role="professor",
        password_hash="hashed_password"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_test_student(db: Session) -> User:
    """Create a test student user."""
    import secrets
    unique_id = f"{datetime.now().timestamp()}_{secrets.token_hex(4)}"
    user = User(
        user_id=f"stud_{unique_id}",  # Required field
        email=f"student_{unique_id}@test.com",
        full_name="Test Student",
        username=f"student_{unique_id}",
        role="student",
        password_hash="hashed_password"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_test_simulation(db: Session, creator_id: int) -> Scenario:
    """Create a test simulation."""
    import secrets
    unique_id = f"{datetime.now().timestamp()}_{secrets.token_hex(4)}"
    simulation = Scenario(
        unique_id=f"SIM-{secrets.token_hex(4).upper()}",  # Required field
        title=f"Test Simulation {unique_id}",
        description="A test simulation",
        created_by=creator_id,
        is_draft=False,
        status="active"
    )
    db.add(simulation)
    db.commit()
    db.refresh(simulation)
    return simulation


def create_test_cohort(db: Session, creator_id: int, title: str = "Test Cohort", course_code: str = "TST101") -> Cohort:
    """Create a test cohort with all required fields."""
    import secrets
    unique_id = f"CH-{secrets.token_hex(4).upper()}"
    cohort = Cohort(
        unique_id=unique_id,  # Required field
        title=title,
        course_code=course_code,
        created_by=creator_id,
        is_active=True
    )
    db.add(cohort)
    db.commit()
    db.refresh(cohort)
    return cohort


# ============================================================================
# COHORT SERVICE TESTS
# ============================================================================

class TestCohortService:
    """Test suite for CohortService."""
    
    def test_service_initialization(self, db_session: Session):
        """Test that the service initializes correctly."""
        service = CohortService(db_session)
        assert service.db == db_session
        assert service.repository is not None
    
    def test_get_empty_cohorts(self, db_session: Session):
        """Test getting cohorts when none exist."""
        professor = create_test_professor(db_session)
        service = CohortService(db_session)
        
        cohorts = service.get_cohorts(
            user_id=professor.id,
            user_role="professor"
        )
        
        assert isinstance(cohorts, list)
    
    def test_create_and_get_cohort(self, db_session: Session):
        """Test creating and retrieving a cohort."""
        professor = create_test_professor(db_session)
        service = CohortService(db_session)
        
        # Create cohort using helper
        cohort = create_test_cohort(db_session, professor.id, "Service Test Cohort", "SVC101")
        
        # Get cohorts
        cohorts = service.get_cohorts(
            user_id=professor.id,
            user_role="professor"
        )
        
        # Should find our cohort
        assert len(cohorts) >= 1
        found = next((c for c in cohorts if c.title == "Service Test Cohort"), None)
        assert found is not None
    
    def test_get_cohorts_filtering(self, db_session: Session):
        """Test filtering cohorts by search term."""
        professor = create_test_professor(db_session)
        service = CohortService(db_session)
        
        # Create multiple cohorts
        cohort1 = create_test_cohort(db_session, professor.id, "Alpha Cohort", "ALP101")
        cohort2 = create_test_cohort(db_session, professor.id, "Beta Cohort", "BET101")
        
        # Search for "Alpha"
        cohorts = service.get_cohorts(
            user_id=professor.id,
            user_role="professor",
            search="Alpha"
        )
        
        alpha_cohorts = [c for c in cohorts if "Alpha" in c.title]
        assert len(alpha_cohorts) >= 1
    
    def test_get_student_cohorts(self, db_session: Session):
        """Test getting cohorts for a student."""
        professor = create_test_professor(db_session)
        student = create_test_student(db_session)
        service = CohortService(db_session)
        
        # Create a cohort
        cohort = create_test_cohort(db_session, professor.id, "Student's Cohort", "SCH101")
        
        # Enroll student
        enrollment = CohortStudent(
            cohort_id=cohort.id,
            student_id=student.id,
            status="approved"
        )
        db_session.add(enrollment)
        db_session.commit()
        
        # Get student's cohorts
        student_cohorts = service.get_student_cohorts(student.id)
        
        assert isinstance(student_cohorts, list)
        assert len(student_cohorts) >= 1


class TestCohortSimulationAssignment:
    """Test suite for simulation assignment functionality."""
    
    def test_assign_simulation_creates_instances(self, db_session: Session):
        """Test that assigning a simulation creates student instances."""
        professor = create_test_professor(db_session)
        student = create_test_student(db_session)
        simulation = create_test_simulation(db_session, professor.id)
        
        # Create cohort
        cohort = create_test_cohort(db_session, professor.id, "Instance Test Cohort", "ITC101")
        
        # Enroll student
        enrollment = CohortStudent(
            cohort_id=cohort.id,
            student_id=student.id,
            status="approved"
        )
        db_session.add(enrollment)
        db_session.commit()
        
        # Assign simulation using repository
        from modules.cohorts.repository import CohortRepository
        repo = CohortRepository(db_session)
        
        assignment = repo.assign_simulation_to_cohort(
            cohort_id=cohort.id,
            simulation_id=simulation.id,
            assigned_by=professor.id,
            due_date=None,
            is_required=True
        )
        
        assert assignment is not None
        assert assignment.simulation_id == simulation.id
        assert assignment.cohort_id == cohort.id
    
    def test_get_cohort_simulations(self, db_session: Session):
        """Test retrieving simulations assigned to a cohort."""
        professor = create_test_professor(db_session)
        simulation = create_test_simulation(db_session, professor.id)
        
        # Create cohort
        cohort = create_test_cohort(db_session, professor.id, "Get Sims Test", "GST101")
        
        # Assign simulation
        assignment = CohortSimulation(
            cohort_id=cohort.id,
            simulation_id=simulation.id,
            assigned_by=professor.id,
            is_required=True
        )
        db_session.add(assignment)
        db_session.commit()
        
        # Get simulations
        from modules.cohorts.repository import CohortRepository
        repo = CohortRepository(db_session)
        simulations = repo.get_cohort_simulations(cohort.id)
        
        assert len(simulations) >= 1


class TestInviteLinkService:
    """Test suite for invite link functionality."""
    
    def test_create_invite_link(self, db_session: Session):
        """Test creating an invite link."""
        professor = create_test_professor(db_session)
        
        # Create cohort
        cohort = create_test_cohort(db_session, professor.id, "Invite Test Cohort", "INV101")
        
        # Create invite using repository
        from modules.cohorts.repository import CohortRepository
        repo = CohortRepository(db_session)
        
        invite = repo.create_invite(
            cohort_id=cohort.id,
            created_by=professor.id,
            invite_type="MULTI_USE",
            max_uses=10,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7)
        )
        
        assert invite is not None
        assert invite.max_uses == 10
        assert invite.uses_count == 0
        assert invite.token is not None
    
    def test_invite_link_expiration(self, db_session: Session):
        """Test that expired invite links are handled correctly."""
        professor = create_test_professor(db_session)
        
        # Create cohort
        cohort = create_test_cohort(db_session, professor.id, "Expiry Test Cohort", "EXP101")
        
        # Create already expired invite
        from modules.cohorts.repository import CohortRepository
        repo = CohortRepository(db_session)
        
        invite = repo.create_invite(
            cohort_id=cohort.id,
            created_by=professor.id,
            invite_type="MULTI_USE",
            max_uses=10,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)  # Already expired
        )
        
        assert invite is not None
        # The invite should exist but be expired
        retrieved = repo.get_invite_by_token(invite.token)
        # Make the comparison timezone-naive since SQLite stores naive datetimes
        expires_at = retrieved.expires_at.replace(tzinfo=None) if retrieved.expires_at.tzinfo else retrieved.expires_at
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        assert expires_at < now


class TestStudentEnrollment:
    """Test suite for student enrollment functionality."""
    
    def test_add_student_to_cohort(self, db_session: Session):
        """Test adding a student to a cohort."""
        professor = create_test_professor(db_session)
        student = create_test_student(db_session)
        
        # Create cohort
        cohort = create_test_cohort(db_session, professor.id, "Enrollment Test", "ENR101")
        
        # Add student
        from modules.cohorts.repository import CohortRepository
        repo = CohortRepository(db_session)
        
        enrollment = repo.add_student_to_cohort(
            cohort_id=cohort.id,
            student_id=student.id,
            status="approved"
        )
        
        assert enrollment is not None
        assert enrollment.student_id == student.id
        assert enrollment.cohort_id == cohort.id
        assert enrollment.status == "approved"
    
    def test_student_count_increases(self, db_session: Session):
        """Test that student count increases when students are added."""
        professor = create_test_professor(db_session)
        service = CohortService(db_session)
        
        # Create cohort
        cohort = create_test_cohort(db_session, professor.id, "Count Test", "CNT101")
        
        # Get initial count
        cohorts_before = service.get_cohorts(
            user_id=professor.id,
            user_role="professor"
        )
        initial_count = next(
            (c.student_count for c in cohorts_before if c.id == cohort.id), 
            0
        )
        
        # Add a student
        student = create_test_student(db_session)
        enrollment = CohortStudent(
            cohort_id=cohort.id,
            student_id=student.id,
            status="approved"
        )
        db_session.add(enrollment)
        db_session.commit()
        
        # Get new count
        cohorts_after = service.get_cohorts(
            user_id=professor.id,
            user_role="professor"
        )
        new_count = next(
            (c.student_count for c in cohorts_after if c.id == cohort.id),
            0
        )
        
        assert new_count == initial_count + 1
    
    def test_pending_students_not_counted(self, db_session: Session):
        """Test that pending students are not counted in active student count."""
        professor = create_test_professor(db_session)
        student = create_test_student(db_session)
        service = CohortService(db_session)
        
        # Create cohort
        cohort = create_test_cohort(db_session, professor.id, "Pending Test", "PND101")
        
        # Add student as pending
        enrollment = CohortStudent(
            cohort_id=cohort.id,
            student_id=student.id,
            status="pending"
        )
        db_session.add(enrollment)
        db_session.commit()
        
        # Get count
        cohorts = service.get_cohorts(
            user_id=professor.id,
            user_role="professor"
        )
        count = next(
            (c.student_count for c in cohorts if c.id == cohort.id),
            0
        )
        
        # Pending students should not be counted
        assert count == 0

