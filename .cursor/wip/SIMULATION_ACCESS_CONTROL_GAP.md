# Simulation Access Control Gap

**Created:** 2024-12-28  
**Status:** To Do  
**Priority:** Medium (Security)  
**Discovered During:** Load Testing Investigation

---

## Summary

The `/api/simulation/start` endpoint does **not validate** whether a user is enrolled in a cohort that has access to the requested simulation. Any authenticated user can start any simulation by ID.

---

## Current Behavior

### Endpoint: `POST /api/simulation/start`

**Location:** `backend/modules/simulation/services/lifecycle_service.py`

```python
async def start_simulation(self, user_id: int, simulation_id: int):
    # Only checks if simulation EXISTS
    simulation = self.repository.get_simulation_by_id(simulation_id)
    if not simulation:
        raise NotFoundError("Simulation not found")
    
    # ❌ NO enrollment/cohort access check
    # Proceeds to start simulation...
```

### What This Means

| User Type | Can Access Any Simulation? |
|-----------|---------------------------|
| Student (not enrolled) | ✅ Yes (shouldn't be able to) |
| Student (enrolled) | ✅ Yes |
| Professor | ✅ Yes (expected) |
| Admin | ✅ Yes (expected) |

---

## Expected Behavior

Students should only be able to start simulations if:
1. They are enrolled in a cohort (`CohortStudent`)
2. That cohort has the simulation assigned (`CohortSimulation`)
3. Their enrollment status is `approved`

Professors/Admins can access any simulation (for testing/review).

---

## Two Access Paths Exist

### Path 1: Via Student Instance (SECURE ✅)
```
POST /api/student/instances/{instance_unique_id}/start-simulation
```
- Validates student owns the `StudentSimulationInstance`
- Gets simulation_id from cohort assignment
- This is what the frontend uses

### Path 2: Direct Start (INSECURE ❌)
```
POST /api/simulation/start
Body: { "simulation_id": 123 }
```
- Only checks simulation exists
- No enrollment validation
- Used by load tests, possibly exposed in API

---

## Risk Assessment

| Factor | Assessment |
|--------|------------|
| **Exploitability** | Low - requires authentication |
| **Impact** | Medium - students could access unassigned simulations |
| **Likelihood** | Low - frontend uses secure path |
| **Data Exposure** | Simulation content, personas, scenes |

---

## Proposed Fix

### Option A: Add Access Check to `lifecycle_service.py`

```python
async def start_simulation(self, user_id: int, simulation_id: int):
    # Verify simulation exists
    simulation = self.repository.get_simulation_by_id(simulation_id)
    if not simulation:
        raise NotFoundError("Simulation not found")
    
    # NEW: Check access for non-admin users
    user = self.db.query(User).filter(User.id == user_id).first()
    if user.role not in ['professor', 'admin']:
        # Check if student has a simulation instance for this simulation
        has_access = self.repository.check_student_simulation_access(user_id, simulation_id)
        if not has_access:
            raise ForbiddenError("You don't have access to this simulation")
    
    # Continue with simulation start...
```

### Option B: Add Repository Method

```python
# In simulation/repository.py
def check_student_simulation_access(self, user_id: int, simulation_id: int) -> bool:
    """Check if a student has access to a simulation via any cohort."""
    from common.db.models import CohortStudent, CohortSimulation
    
    return self.db.query(CohortSimulation).join(
        CohortStudent, CohortStudent.cohort_id == CohortSimulation.cohort_id
    ).filter(
        CohortStudent.student_id == user_id,
        CohortStudent.status == 'approved',
        CohortSimulation.simulation_id == simulation_id
    ).first() is not None
```

---

## Files to Modify

1. `backend/modules/simulation/services/lifecycle_service.py` - Add access check
2. `backend/modules/simulation/repository.py` - Add `check_student_simulation_access()`
3. `backend/modules/simulation/router.py` - Update error handling for ForbiddenError

---

## Testing Considerations

After implementing the fix:
1. **Unit tests:** Test access check with enrolled vs non-enrolled students
2. **Load tests:** Will need to use enrollment flow OR test users need to be enrolled
3. **Integration tests:** Verify frontend still works with secure path

---

## Load Testing Impact

The current load test (`chat_load_test.py`) uses the direct path:
- It will **fail** after this fix is implemented
- Options:
  1. Pre-enroll test users in test cohort with test simulation
  2. Update load test to use `/api/student/instances/.../start-simulation`
  3. Add a flag to bypass check in test environments (not recommended)

---

## Related Files

- `backend/modules/simulation/services/lifecycle_service.py`
- `backend/modules/simulation/router.py`
- `backend/modules/student/routers/student_instances.py` (secure path)
- `backend/modules/cohorts/service.py` (enrollment logic)
- `backend/tests/load_testing/user_behaviors/chat_user.py`

---

## Notes

- Discovered during load testing investigation (2024-12-28)
- The load test was successfully testing chat performance, but bypassing the enrollment layer
- This is not an urgent fix as the frontend uses the secure path
- Should be addressed before the API is documented publicly or used by third parties

