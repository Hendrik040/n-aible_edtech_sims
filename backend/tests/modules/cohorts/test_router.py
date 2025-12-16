"""
Tests for the cohort router endpoints.

These tests cover:
1. Cohort CRUD operations
2. Student management (add, update, remove)
3. Simulation assignment to cohorts
4. Student simulation instances
5. Invite link management
"""
import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.orm import Session


# Helper functions for test setup
async def create_professor_user(async_client: AsyncClient) -> dict:
    """Create and login a professor user, return user data and cookies."""
    unique_id = str(uuid.uuid4())[:8]
    user_data = {
        "email": f"professor_{unique_id}@test.com",
        "password": "TestPassword123!",
        "full_name": "Test Professor",
        "username": f"professor_{unique_id}",
        "role": "professor"
    }
    
    # Register
    reg_response = await async_client.post("/api/auth/users/register", json=user_data)
    assert reg_response.status_code == 200, f"Failed to register professor: {reg_response.text}"
    
    # Login
    login_response = await async_client.post("/api/auth/users/login", json={
        "email": user_data["email"],
        "password": user_data["password"]
    })
    assert login_response.status_code == 200, f"Failed to login professor: {login_response.text}"
    
    login_data = login_response.json()
    # The user data is nested under "user" key in UserLoginResponse
    user_info = login_data.get("user", login_data)
    
    return {
        **user_info,
        "cookies": login_response.cookies,
        "password": user_data["password"]
    }


async def create_student_user(async_client: AsyncClient) -> dict:
    """Create and login a student user, return user data and cookies."""
    unique_id = str(uuid.uuid4())[:8]
    user_data = {
        "email": f"student_{unique_id}@test.com",
        "password": "TestPassword123!",
        "full_name": "Test Student",
        "username": f"student_{unique_id}",
        "role": "student"
    }
    
    # Register
    reg_response = await async_client.post("/api/auth/users/register", json=user_data)
    assert reg_response.status_code == 200, f"Failed to register student: {reg_response.text}"
    
    # Login
    login_response = await async_client.post("/api/auth/users/login", json={
        "email": user_data["email"],
        "password": user_data["password"]
    })
    assert login_response.status_code == 200, f"Failed to login student: {login_response.text}"
    
    login_data = login_response.json()
    # The user data is nested under "user" key in UserLoginResponse
    user_info = login_data.get("user", login_data)
    
    return {
        **user_info,
        "cookies": login_response.cookies,
        "password": user_data["password"]
    }


# ============================================================================
# COHORT CRUD TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_cohort(async_client: AsyncClient):
    """Test creating a new cohort as a professor."""
    professor = await create_professor_user(async_client)
    
    cohort_data = {
        "title": "Test Cohort 101",
        "description": "A test cohort for unit testing",
        "course_code": "TEST101",
        "semester": "Fall",
        "year": 2025,
        "max_students": 30,
        "is_active": True
    }
    
    response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200, f"Failed to create cohort: {response.text}"
    data = response.json()
    
    assert data["title"] == cohort_data["title"]
    assert data["description"] == cohort_data["description"]
    assert data["course_code"] == cohort_data["course_code"]
    assert "unique_id" in data
    assert len(data["unique_id"]) > 0


@pytest.mark.asyncio
async def test_get_cohorts(async_client: AsyncClient):
    """Test listing cohorts for a professor."""
    professor = await create_professor_user(async_client)
    
    # Create a cohort first
    cohort_data = {
        "title": "List Test Cohort",
        "description": "Testing cohort listing",
        "course_code": "LIST101"
    }
    
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    assert create_response.status_code == 200
    
    # Get cohorts list
    response = await async_client.get(
        "/professor/cohorts",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    cohorts = response.json()
    assert isinstance(cohorts, list)
    assert len(cohorts) >= 1
    
    # Find our cohort
    our_cohort = next((c for c in cohorts if c["title"] == "List Test Cohort"), None)
    assert our_cohort is not None


@pytest.mark.asyncio
async def test_get_cohort_by_id(async_client: AsyncClient):
    """Test getting a specific cohort by unique_id."""
    professor = await create_professor_user(async_client)
    
    # Create a cohort
    cohort_data = {
        "title": "Get Single Cohort",
        "description": "Testing single cohort retrieval",
        "course_code": "GET101"
    }
    
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    assert create_response.status_code == 200
    created = create_response.json()
    
    # Get the cohort
    response = await async_client.get(
        f"/professor/cohorts/{created['unique_id']}",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == cohort_data["title"]
    assert data["unique_id"] == created["unique_id"]


@pytest.mark.asyncio
async def test_update_cohort(async_client: AsyncClient):
    """Test updating a cohort."""
    professor = await create_professor_user(async_client)
    
    # Create a cohort
    cohort_data = {
        "title": "Update Test Cohort",
        "description": "Original description",
        "course_code": "UPD101"
    }
    
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    assert create_response.status_code == 200
    created = create_response.json()
    
    # Update the cohort
    update_data = {
        "title": "Updated Cohort Title",
        "description": "Updated description"
    }
    
    response = await async_client.put(
        f"/professor/cohorts/{created['unique_id']}",
        json=update_data,
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == update_data["title"]
    assert updated["description"] == update_data["description"]


@pytest.mark.asyncio
async def test_delete_cohort(async_client: AsyncClient):
    """Test deleting a cohort."""
    professor = await create_professor_user(async_client)
    
    # Create a cohort
    cohort_data = {
        "title": "Delete Test Cohort",
        "course_code": "DEL101"
    }
    
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    assert create_response.status_code == 200
    created = create_response.json()
    
    # Delete the cohort
    response = await async_client.delete(
        f"/professor/cohorts/{created['unique_id']}",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    
    # Verify it's deleted
    get_response = await async_client.get(
        f"/professor/cohorts/{created['unique_id']}",
        cookies=professor["cookies"]
    )
    assert get_response.status_code in [404, 500]  # Should not be found


# ============================================================================
# STUDENT MANAGEMENT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_add_student_to_cohort(async_client: AsyncClient):
    """Test adding a student to a cohort."""
    professor = await create_professor_user(async_client)
    student = await create_student_user(async_client)
    
    # Create a cohort
    cohort_data = {"title": "Student Add Test", "course_code": "STU101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    assert create_response.status_code == 200
    cohort = create_response.json()
    
    # Add student - use cohort['id'] (integer) not unique_id
    student_data = {
        "student_id": student["id"],
        "status": "approved"
    }
    
    response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/students",
        json=student_data,
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200, f"Failed to add student: {response.text}"
    data = response.json()
    assert data["student_id"] == student["id"]


@pytest.mark.asyncio
async def test_get_cohort_students(async_client: AsyncClient):
    """Test getting list of students in a cohort."""
    professor = await create_professor_user(async_client)
    student = await create_student_user(async_client)
    
    # Create cohort and add student
    cohort_data = {"title": "Students List Test", "course_code": "SLT101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Add student - use cohort['id'] for add
    await async_client.post(
        f"/professor/cohorts/{cohort['id']}/students",
        json={"student_id": student["id"], "status": "approved"},
        cookies=professor["cookies"]
    )
    
    # Get students - uses unique_id
    response = await async_client.get(
        f"/professor/cohorts/{cohort['unique_id']}/students",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    students = response.json()
    assert isinstance(students, list)
    assert len(students) >= 1


@pytest.mark.asyncio
async def test_update_student_status(async_client: AsyncClient):
    """Test updating a student's enrollment status."""
    professor = await create_professor_user(async_client)
    student = await create_student_user(async_client)
    
    # Create cohort and add student as pending
    cohort_data = {"title": "Status Update Test", "course_code": "SUP101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Add student as pending - use id
    add_response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/students",
        json={"student_id": student["id"], "status": "pending"},
        cookies=professor["cookies"]
    )
    assert add_response.status_code == 200, f"Failed to add student: {add_response.text}"
    
    # Update to approved - uses unique_id and student_id (not enrollment id)
    response = await async_client.put(
        f"/professor/cohorts/{cohort['unique_id']}/students/{student['id']}",
        json={"status": "approved"},
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "approved"


@pytest.mark.asyncio
async def test_remove_student_from_cohort(async_client: AsyncClient):
    """Test removing a student from a cohort."""
    professor = await create_professor_user(async_client)
    student = await create_student_user(async_client)
    
    # Create cohort and add student
    cohort_data = {"title": "Remove Student Test", "course_code": "REM101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Add student - use id
    add_response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/students",
        json={"student_id": student["id"], "status": "approved"},
        cookies=professor["cookies"]
    )
    assert add_response.status_code == 200, f"Failed to add student: {add_response.text}"
    enrollment = add_response.json()
    
    # Remove student - uses unique_id
    response = await async_client.delete(
        f"/professor/cohorts/{cohort['unique_id']}/students/{enrollment['id']}",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200


# ============================================================================
# SIMULATION ASSIGNMENT TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_assign_simulation_to_cohort(async_client: AsyncClient, db_session: Session):
    """Test assigning a simulation to a cohort."""
    professor = await create_professor_user(async_client)
    
    # Create a cohort
    cohort_data = {"title": "Sim Assignment Test", "course_code": "SIM101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    assert create_response.status_code == 200
    cohort = create_response.json()
    
    # Create a simulation (scenario) directly in the database
    from common.db.models import Simulation
    import secrets
    simulation = Simulation(
        unique_id=f"SIM-{secrets.token_hex(4).upper()}",
        title="Test Simulation",
        description="A test simulation",
        created_by=professor["id"],
        is_draft=False,
        status="active"
    )
    db_session.add(simulation)
    db_session.commit()
    db_session.refresh(simulation)
    
    # Assign simulation to cohort
    assignment_data = {
        "simulation_id": simulation.id,
        "is_required": True
    }
    
    response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/simulations",
        json=assignment_data,
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200, f"Failed to assign simulation: {response.text}"
    data = response.json()
    assert data["simulation_id"] == simulation.id
    assert data["is_required"] == True


@pytest.mark.asyncio
async def test_get_cohort_simulations(async_client: AsyncClient, db_session: Session):
    """Test getting simulations assigned to a cohort."""
    professor = await create_professor_user(async_client)
    
    # Create a cohort
    cohort_data = {"title": "Get Sims Test", "course_code": "GSM101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Create and assign a simulation
    from common.db.models import Simulation
    import secrets
    simulation = Simulation(
        unique_id=f"SIM-{secrets.token_hex(4).upper()}",
        title="List Test Simulation",
        description="Testing simulation listing",
        created_by=professor["id"],
        is_draft=False,
        status="active"
    )
    db_session.add(simulation)
    db_session.commit()
    db_session.refresh(simulation)
    
    # Assign it
    await async_client.post(
        f"/professor/cohorts/{cohort['id']}/simulations",
        json={"simulation_id": simulation.id, "is_required": True},
        cookies=professor["cookies"]
    )
    
    # Get simulations
    response = await async_client.get(
        f"/professor/cohorts/{cohort['unique_id']}/simulations",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    simulations = response.json()
    assert isinstance(simulations, list)
    assert len(simulations) >= 1


@pytest.mark.asyncio
async def test_remove_simulation_from_cohort(async_client: AsyncClient, db_session: Session):
    """Test removing a simulation assignment from a cohort."""
    professor = await create_professor_user(async_client)
    
    # Create cohort
    cohort_data = {"title": "Remove Sim Test", "course_code": "RSM101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Create and assign simulation
    from common.db.models import Simulation
    import secrets
    simulation = Simulation(
        unique_id=f"SIM-{secrets.token_hex(4).upper()}",
        title="Remove Test Simulation",
        description="Test simulation for removal",
        created_by=professor["id"],
        is_draft=False,
        status="active"
    )
    db_session.add(simulation)
    db_session.commit()
    db_session.refresh(simulation)
    
    assign_response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/simulations",
        json={"simulation_id": simulation.id, "is_required": True},
        cookies=professor["cookies"]
    )
    assignment = assign_response.json()
    
    # Remove the assignment
    response = await async_client.delete(
        f"/professor/cohorts/{cohort['id']}/simulations/{assignment['id']}",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200


# ============================================================================
# STUDENT SIMULATION INSTANCES TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_student_sees_assigned_simulations(async_client: AsyncClient, db_session: Session):
    """Test that students can see simulations assigned to their cohort."""
    professor = await create_professor_user(async_client)
    student = await create_student_user(async_client)
    
    # Create cohort
    cohort_data = {"title": "Student View Test", "course_code": "SVT101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Add student to cohort as approved - use id
    await async_client.post(
        f"/professor/cohorts/{cohort['id']}/students",
        json={"student_id": student["id"], "status": "approved"},
        cookies=professor["cookies"]
    )
    
    # Create and assign simulation
    from common.db.models import Simulation
    import secrets
    simulation = Simulation(
        unique_id=f"SIM-{secrets.token_hex(4).upper()}",
        title="Student View Simulation",
        description="Students should see this",
        created_by=professor["id"],
        is_draft=False,
        status="active"
    )
    db_session.add(simulation)
    db_session.commit()
    db_session.refresh(simulation)
    
    await async_client.post(
        f"/professor/cohorts/{cohort['id']}/simulations",
        json={"simulation_id": simulation.id, "is_required": True},
        cookies=professor["cookies"]
    )
    
    # Student fetches their simulation instances
    response = await async_client.get(
        f"/student-simulation-instances/?cohort_id={cohort['id']}",
        cookies=student["cookies"]
    )
    
    assert response.status_code == 200
    instances = response.json()
    assert isinstance(instances, list)
    # The auto-backfill should create instances
    assert len(instances) >= 1
    
    # Verify the simulation details are included
    instance = instances[0]
    assert "cohort_assignment" in instance
    assert instance["cohort_assignment"]["simulation"]["title"] == "Student View Simulation"


@pytest.mark.asyncio
async def test_student_gets_cohorts(async_client: AsyncClient):
    """Test that students can see their enrolled cohorts."""
    professor = await create_professor_user(async_client)
    student = await create_student_user(async_client)
    
    # Create cohort and add student
    cohort_data = {"title": "Student Cohort View", "course_code": "SCV101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Add student as approved - use id
    await async_client.post(
        f"/professor/cohorts/{cohort['id']}/students",
        json={"student_id": student["id"], "status": "approved"},
        cookies=professor["cookies"]
    )
    
    # Student fetches their cohorts
    response = await async_client.get(
        "/student/cohorts",
        cookies=student["cookies"]
    )
    
    assert response.status_code == 200
    cohorts = response.json()
    assert isinstance(cohorts, list)
    assert len(cohorts) >= 1


# ============================================================================
# INVITE LINK TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_create_invite_link(async_client: AsyncClient):
    """Test creating an invite link for a cohort."""
    professor = await create_professor_user(async_client)
    
    # Create cohort
    cohort_data = {"title": "Invite Link Test", "course_code": "INV101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Create invite link - use cohort id and correct schema fields
    invite_data = {
        "type": "MULTI_USE",
        "max_uses": 10,
        "expires_in_days": 7
    }
    
    response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/invites",
        json=invite_data,
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200, f"Failed to create invite: {response.text}"
    invite = response.json()
    assert "invite_url" in invite
    assert "invite_id" in invite


@pytest.mark.asyncio
async def test_get_cohort_invites(async_client: AsyncClient):
    """Test getting invite links for a cohort."""
    professor = await create_professor_user(async_client)
    
    # Create cohort
    cohort_data = {"title": "Get Invites Test", "course_code": "GIT101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Create an invite - use cohort id
    await async_client.post(
        f"/professor/cohorts/{cohort['id']}/invites",
        json={"type": "MULTI_USE", "max_uses": 5, "expires_in_days": 7},
        cookies=professor["cookies"]
    )
    
    # Get invites - use cohort id
    response = await async_client.get(
        f"/professor/cohorts/{cohort['id']}/invites",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "invites" in data
    assert len(data["invites"]) >= 1


@pytest.mark.asyncio
async def test_delete_invite_link(async_client: AsyncClient):
    """Test deleting an invite link."""
    professor = await create_professor_user(async_client)
    
    # Create cohort
    cohort_data = {"title": "Delete Invite Test", "course_code": "DIT101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Create an invite - use cohort id
    invite_response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/invites",
        json={"type": "MULTI_USE", "max_uses": 5, "expires_in_days": 7},
        cookies=professor["cookies"]
    )
    invite = invite_response.json()
    
    # Delete the invite - use cohort id and invite_id field
    response = await async_client.delete(
        f"/professor/cohorts/{cohort['id']}/invites/{invite['invite_id']}",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200


# ============================================================================
# ACCESS CONTROL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_student_cannot_create_cohort(async_client: AsyncClient):
    """Test that students cannot create cohorts."""
    student = await create_student_user(async_client)
    
    cohort_data = {"title": "Unauthorized Cohort", "course_code": "UNA101"}
    
    response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=student["cookies"]
    )
    
    # Should be forbidden
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_student_cannot_modify_cohort(async_client: AsyncClient):
    """Test that students cannot modify cohorts."""
    professor = await create_professor_user(async_client)
    student = await create_student_user(async_client)
    
    # Create cohort as professor
    cohort_data = {"title": "Professor's Cohort", "course_code": "PRO101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Try to update as student
    response = await async_client.put(
        f"/professor/cohorts/{cohort['unique_id']}",
        json={"title": "Hacked!"},
        cookies=student["cookies"]
    )
    
    # Should be forbidden
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_professor_cannot_access_another_professors_cohort(async_client: AsyncClient):
    """Test that professors cannot access other professors' cohorts."""
    professor1 = await create_professor_user(async_client)
    professor2 = await create_professor_user(async_client)
    
    # Professor 1 creates a cohort
    cohort_data = {"title": "Professor 1's Cohort", "course_code": "P1C101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor1["cookies"]
    )
    cohort = create_response.json()
    
    # Professor 2 tries to access it
    response = await async_client.get(
        f"/professor/cohorts/{cohort['unique_id']}",
        cookies=professor2["cookies"]
    )
    
    # Should be forbidden or not found
    assert response.status_code in [403, 404, 500]


# ============================================================================
# EDGE CASES AND ERROR HANDLING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_get_nonexistent_cohort(async_client: AsyncClient):
    """Test getting a cohort that doesn't exist."""
    professor = await create_professor_user(async_client)
    
    response = await async_client.get(
        "/professor/cohorts/nonexistent-cohort-id-12345",
        cookies=professor["cookies"]
    )
    
    assert response.status_code in [404, 500]


@pytest.mark.asyncio
async def test_add_same_student_twice(async_client: AsyncClient):
    """Test adding the same student to a cohort twice."""
    professor = await create_professor_user(async_client)
    student = await create_student_user(async_client)
    
    # Create cohort
    cohort_data = {"title": "Duplicate Student Test", "course_code": "DUP101"}
    create_response = await async_client.post(
        "/professor/cohorts",
        json=cohort_data,
        cookies=professor["cookies"]
    )
    cohort = create_response.json()
    
    # Add student first time - use id
    first_response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/students",
        json={"student_id": student["id"], "status": "approved"},
        cookies=professor["cookies"]
    )
    assert first_response.status_code == 200
    
    # Add student second time (should fail or return existing)
    second_response = await async_client.post(
        f"/professor/cohorts/{cohort['id']}/students",
        json={"student_id": student["id"], "status": "approved"},
        cookies=professor["cookies"]
    )
    
    # Either returns conflict error or the existing enrollment
    assert second_response.status_code in [200, 400, 409]


@pytest.mark.asyncio
async def test_cohort_search(async_client: AsyncClient):
    """Test searching for cohorts."""
    professor = await create_professor_user(async_client)
    
    # Create cohorts with different names
    await async_client.post(
        "/professor/cohorts",
        json={"title": "Alpha Course", "course_code": "ALP101"},
        cookies=professor["cookies"]
    )
    await async_client.post(
        "/professor/cohorts",
        json={"title": "Beta Course", "course_code": "BET101"},
        cookies=professor["cookies"]
    )
    
    # Search for "Alpha"
    response = await async_client.get(
        "/professor/cohorts?search=Alpha",
        cookies=professor["cookies"]
    )
    
    assert response.status_code == 200
    cohorts = response.json()
    
    # Should find the Alpha cohort
    alpha_cohorts = [c for c in cohorts if "Alpha" in c["title"]]
    assert len(alpha_cohorts) >= 1

