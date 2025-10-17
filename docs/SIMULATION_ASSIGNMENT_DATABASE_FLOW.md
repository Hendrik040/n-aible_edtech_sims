# Simulation Assignment Database Flow

## Overview

This document outlines the database tables and data flow when a professor assigns a simulation to a cohort in the AI Agent Education Platform. The system creates multiple interconnected records to track the assignment, student progress, and notifications.

## Database Tables Involved

### 1. Core Assignment Tables

#### `cohort_simulations` - Main Assignment Record
**Purpose**: Links a simulation (scenario) to a cohort with assignment details

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `cohort_id` | INTEGER (FK) | Reference to cohorts table |
| `simulation_id` | INTEGER (FK) | Reference to scenarios table |
| `assigned_by` | INTEGER (FK) | Professor who made the assignment |
| `assigned_at` | TIMESTAMP | When assignment was created |
| `due_date` | TIMESTAMP | Optional due date for the assignment |
| `is_required` | BOOLEAN | Whether assignment is mandatory |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last update time |

**Indexes**: cohort_id, simulation_id, assigned_by, due_date

#### `student_simulation_instances` - Individual Student Records
**Purpose**: Tracks each student's progress on the assigned simulation

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `cohort_assignment_id` | INTEGER (FK) | Reference to cohort_simulations |
| `student_id` | INTEGER (FK) | Reference to users table |
| `user_progress_id` | INTEGER (FK) | Reference to user_progress table |
| `status` | VARCHAR | not_started, in_progress, completed, submitted, graded |
| `started_at` | TIMESTAMP | When student started |
| `completed_at` | TIMESTAMP | When student completed |
| `submitted_at` | TIMESTAMP | When student submitted |
| `grade` | FLOAT | Grade (0.0-100.0) |
| `feedback` | TEXT | Professor feedback |
| `graded_by` | INTEGER (FK) | Professor who graded |
| `graded_at` | TIMESTAMP | When graded |
| `completion_percentage` | FLOAT | Progress percentage |
| `total_time_spent` | INTEGER | Time in seconds |
| `attempts_count` | INTEGER | Number of attempts |
| `hints_used` | INTEGER | Hints used count |
| `is_overdue` | BOOLEAN | Whether past due date |
| `days_late` | INTEGER | Days past due |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last update time |

**Indexes**: cohort_assignment_id, student_id, user_progress_id, status, grade, completed_at

### 2. Supporting Tables

#### `user_progress` - Simulation Progress Tracking
**Purpose**: Tracks detailed simulation progress for each student

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `user_id` | INTEGER (FK) | Reference to users table (nullable) |
| `scenario_id` | INTEGER (FK) | Reference to scenarios table |
| `current_scene_id` | INTEGER (FK) | Current scene in simulation |
| `simulation_status` | VARCHAR | not_started, in_progress, completed, abandoned |
| `scenes_completed` | JSON | Array of completed scene IDs |
| `total_attempts` | INTEGER | Total attempts across all scenes |
| `hints_used` | INTEGER | Total hints used |
| `forced_progressions` | INTEGER | Forced scene progressions |
| `orchestrator_data` | JSON | AI orchestrator state |
| `completion_percentage` | FLOAT | Overall completion percentage |
| `total_time_spent` | INTEGER | Total time in seconds |
| `session_count` | INTEGER | Number of sessions |
| `final_score` | FLOAT | Final performance score |
| `started_at` | TIMESTAMP | Simulation start time |
| `completed_at` | TIMESTAMP | Completion time |
| `last_activity` | TIMESTAMP | Last activity time |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last update time |

#### `cohort_students` - Student Enrollment
**Purpose**: Tracks which students are enrolled in the cohort

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `cohort_id` | INTEGER (FK) | Reference to cohorts table |
| `student_id` | INTEGER (FK) | Reference to users table |
| `status` | VARCHAR | pending, approved, rejected, withdrawn |
| `enrollment_date` | TIMESTAMP | When enrolled |
| `approved_by` | INTEGER (FK) | Who approved enrollment |
| `approved_at` | TIMESTAMP | When approved |
| `created_at` | TIMESTAMP | Record creation time |
| `updated_at` | TIMESTAMP | Last update time |

#### `notifications` - Assignment Notifications
**Purpose**: Notifies students about new assignments

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `user_id` | INTEGER (FK) | Reference to users table |
| `type` | VARCHAR | notification type (assignment, grade, etc.) |
| `title` | VARCHAR | Notification title |
| `message` | TEXT | Notification message |
| `data` | JSON | Additional data (cohort_id, simulation_id, etc.) |
| `is_read` | BOOLEAN | Whether notification was read |
| `created_at` | TIMESTAMP | Notification creation time |

## Data Flow Process

### Step 1: Professor Assigns Simulation
When a professor assigns a simulation to a cohort via the API endpoint `POST /cohorts/{cohort_id}/simulations`:

1. **Create `cohort_simulations` record**:
   ```sql
   INSERT INTO cohort_simulations (
       cohort_id, simulation_id, assigned_by, 
       due_date, is_required, created_at
   ) VALUES (
       {cohort_id}, {simulation_id}, {professor_id},
       {due_date}, {is_required}, NOW()
   );
   ```

### Step 2: Create Student Instances
For each approved student in the cohort:

2. **Create `user_progress` record**:
   ```sql
   INSERT INTO user_progress (
       user_id, scenario_id, simulation_status,
       created_at, started_at, last_activity
   ) VALUES (
       {student_id}, {simulation_id}, 'not_started',
       NOW(), NOW(), NOW()
   );
   ```

3. **Create `student_simulation_instances` record**:
   ```sql
   INSERT INTO student_simulation_instances (
       cohort_assignment_id, student_id, user_progress_id,
       status, created_at
   ) VALUES (
       {cohort_simulation_id}, {student_id}, {user_progress_id},
       'not_started', NOW()
   );
   ```

4. **Create `notifications` record**:
   ```sql
   INSERT INTO notifications (
       user_id, type, title, message, data, is_read, created_at
   ) VALUES (
       {student_id}, 'assignment', 'New Simulation Assignment',
       'You have been assigned a new simulation...',
       '{"cohort_id": {cohort_id}, "simulation_id": {simulation_id}}',
       false, NOW()
   );
   ```

### Step 3: Student Progress Tracking
As students work on the simulation:

5. **Update `user_progress`** with scene completion, time spent, etc.
6. **Update `student_simulation_instances`** with status changes, completion times
7. **Create `scene_progress`** records for detailed scene tracking
8. **Create `conversation_logs`** for all AI interactions

### Step 4: Grading and Completion
When professor grades or student completes:

9. **Update `student_simulation_instances`** with grade, feedback, completion status
10. **Update `user_progress`** with final score and completion status

## Key Relationships

```
cohorts (1) ←→ (many) cohort_simulations (1) ←→ (many) student_simulation_instances
     ↓                                                      ↓
cohort_students (many) ←→ (1) users ←→ (many) user_progress (1) ←→ (many) scene_progress
     ↓                                                      ↓
notifications (many) ←→ (1) users                    conversation_logs (many)
```

## Example Data Flow

### Scenario: Professor assigns "Marketing Strategy Simulation" to "Business 101 - Fall 2024" cohort

**Input Data**:
- Cohort ID: 123
- Simulation ID: 456
- Professor ID: 789
- Due Date: 2024-12-15
- Students: [101, 102, 103, 104]

**Database Records Created**:

1. **cohort_simulations** (1 record):
   ```json
   {
     "id": 1001,
     "cohort_id": 123,
     "simulation_id": 456,
     "assigned_by": 789,
     "assigned_at": "2024-11-01T10:00:00Z",
     "due_date": "2024-12-15T23:59:59Z",
     "is_required": true
   }
   ```

2. **user_progress** (4 records, one per student):
   ```json
   {
     "id": 2001,
     "user_id": 101,
     "scenario_id": 456,
     "simulation_status": "not_started",
     "completion_percentage": 0.0
   }
   // ... similar records for students 102, 103, 104
   ```

3. **student_simulation_instances** (4 records):
   ```json
   {
     "id": 3001,
     "cohort_assignment_id": 1001,
     "student_id": 101,
     "user_progress_id": 2001,
     "status": "not_started",
     "completion_percentage": 0.0
   }
   // ... similar records for other students
   ```

4. **notifications** (4 records):
   ```json
   {
     "id": 4001,
     "user_id": 101,
     "type": "assignment",
     "title": "New Simulation Assignment",
     "message": "You have been assigned 'Marketing Strategy Simulation' for Business 101",
     "data": {"cohort_id": 123, "simulation_id": 456},
     "is_read": false
   }
   // ... similar records for other students
   ```

## API Endpoints

### Professor Endpoints
- `POST /cohorts/{cohort_id}/simulations` - Assign simulation to cohort
- `GET /cohorts/{cohort_id}/simulations` - Get cohort simulations
- `DELETE /cohorts/{cohort_id}/simulations/{assignment_id}` - Remove assignment

### Student Endpoints
- `GET /student/simulation-instances` - Get student's simulation instances
- `POST /student/simulation-instances` - Create simulation instance
- `GET /student/cohorts/{cohort_id}/simulations` - Get cohort simulations

## Status Flow

```
Assignment Created → Student Notified → Student Starts → In Progress → Completed → Graded
     ↓                    ↓                ↓              ↓            ↓          ↓
not_started         notification      started_at      in_progress  completed  graded
```

## Performance Considerations

1. **Indexes**: All foreign key columns are indexed for fast joins
2. **Batch Operations**: Student instances are created in batches
3. **Notifications**: Created asynchronously to avoid blocking
4. **Progress Tracking**: Uses JSON columns for flexible scene tracking
5. **Soft Deletion**: Supports archiving without data loss

## Security and Data Isolation

1. **Role-based Access**: Only professors can assign simulations
2. **Cohort Ownership**: Professors can only assign to their own cohorts
3. **Student Enrollment**: Only approved students receive assignments
4. **Data Isolation**: Students can only see their own progress
5. **Audit Trail**: All assignments tracked with timestamps and user IDs

This database structure ensures comprehensive tracking of simulation assignments while maintaining data integrity and performance.
