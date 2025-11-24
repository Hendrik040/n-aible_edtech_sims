# Database Structure Documentation

## Overview

The AI Agent Education Platform uses PostgreSQL as its primary database with Alembic for migrations. The database supports an educational simulation platform with user management, scenario creation, cohort management, and AI-powered conversation tracking.

## Database Configuration

- **Database Type**: PostgreSQL
- **Migration Tool**: Alembic
- **Vector Support**: pgvector (when configured)
- **Connection Pooling**: SQLAlchemy with connection pooling
- **Environment**: Development/Production ready

## Core Tables

### 1. Users (`users`)
**Purpose**: User account management and authentication

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `email` | VARCHAR | Unique email address |
| `full_name` | VARCHAR | User's full name |
| `username` | VARCHAR | Unique username |
| `password_hash` | VARCHAR | Hashed password (nullable for OAuth) |
| `bio` | TEXT | User biography |
| `avatar_url` | VARCHAR | Profile picture URL |
| `role` | VARCHAR | User role (admin, teacher, student, user) |
| `google_id` | VARCHAR | Google OAuth ID |
| `provider` | VARCHAR | Authentication provider (password/google) |
| `published_scenarios` | INTEGER | Count of published scenarios |
| `total_simulations` | INTEGER | Count of completed simulations |
| `reputation_score` | FLOAT | Community reputation score |
| `profile_public` | BOOLEAN | Whether profile is public |
| `allow_contact` | BOOLEAN | Whether others can contact user |
| `is_active` | BOOLEAN | Account active status |
| `is_verified` | BOOLEAN | Email verification status |
| `created_at` | TIMESTAMP | Account creation time |
| `updated_at` | TIMESTAMP | Last update time |

**Indexes**: email, username, role, created_at, google_id, provider

### 2. Scenarios (`scenarios`)
**Purpose**: Educational simulation scenarios

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `unique_id` | VARCHAR | Unique, unguessable identifier |
| `title` | VARCHAR | Scenario title |
| `description` | TEXT | Scenario description |
| `challenge` | TEXT | Main challenge/objective |
| `industry` | VARCHAR | Industry context |
| `learning_objectives` | JSON | Array of learning objectives |
| `source_type` | VARCHAR | Creation method (manual/pdf_upload/template) |
| `pdf_content` | TEXT | Original PDF content |
| `student_role` | VARCHAR | Role student plays |
| `category` | VARCHAR | Scenario category |
| `difficulty_level` | VARCHAR | Difficulty rating |
| `estimated_duration` | INTEGER | Duration in minutes |
| `tags` | JSON | Array of tags |
| `pdf_title` | VARCHAR | Original PDF title |
| `pdf_source` | VARCHAR | PDF source information |
| `processing_version` | VARCHAR | AI processing version |
| `rating_avg` | FLOAT | Average rating |
| `rating_count` | INTEGER | Number of ratings |
| `is_public` | BOOLEAN | Public visibility |
| `is_template` | BOOLEAN | Template status |
| `allow_remixes` | BOOLEAN | Allow others to remix |
| `status` | VARCHAR | Status (draft/active/archived) |
| `is_draft` | BOOLEAN | Draft status |
| `published_version_id` | INTEGER (FK) | Reference to published version |
| `draft_of_id` | INTEGER (FK) | Reference to original if draft |
| `usage_count` | INTEGER | Usage statistics |
| `clone_count` | INTEGER | Clone statistics |
| `created_by` | INTEGER (FK) | Creator user ID |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |
| `deleted_at` | TIMESTAMP | Soft deletion timestamp |
| `deleted_by` | INTEGER (FK) | User who deleted |
| `deletion_reason` | VARCHAR | Reason for deletion |

**Indexes**: title, industry, is_public, created_by, created_at, rating_avg, deleted_at

### 3. Scenario Personas (`scenario_personas`)
**Purpose**: AI personas within scenarios

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `scenario_id` | INTEGER (FK) | Parent scenario |
| `name` | VARCHAR | Persona name |
| `role` | VARCHAR | Persona role |
| `background` | TEXT | Persona background |
| `correlation` | TEXT | Relationship context |
| `primary_goals` | JSON | Persona goals |
| `personality_traits` | JSON | Personality characteristics |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 4. Scenario Scenes (`scenario_scenes`)
**Purpose**: Individual scenes within scenarios

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `scenario_id` | INTEGER (FK) | Parent scenario |
| `title` | VARCHAR | Scene title |
| `description` | TEXT | Scene description |
| `user_goal` | TEXT | User's objective |
| `scene_order` | INTEGER | Display order |
| `estimated_duration` | INTEGER | Duration in minutes |
| `timeout_turns` | INTEGER | Turn timeout limit |
| `success_metric` | VARCHAR | Success measurement |
| `max_attempts` | INTEGER | Maximum attempts allowed |
| `success_threshold` | FLOAT | Success threshold (0.0-1.0) |
| `goal_criteria` | JSON | Success criteria |
| `hint_triggers` | JSON | Hint trigger conditions |
| `scene_context` | TEXT | Additional context |
| `persona_instructions` | JSON | Persona-specific instructions |
| `image_url` | VARCHAR | Scene image URL |
| `image_prompt` | VARCHAR | Image generation prompt |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 5. Scene-Persona Junction (`scene_personas`)
**Purpose**: Many-to-many relationship between scenes and personas

| Column | Type | Description |
|--------|------|-------------|
| `scene_id` | INTEGER (FK) | Scene ID |
| `persona_id` | INTEGER (FK) | Persona ID |
| `involvement_level` | VARCHAR | Involvement level (key/participant/mentioned) |
| `created_at` | TIMESTAMP | Creation time |

## Simulation System Tables

### 6. User Progress (`user_progress`)
**Purpose**: Track user simulation progress

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `user_id` | INTEGER (FK) | User ID |
| `scenario_id` | INTEGER (FK) | Scenario ID |
| `current_scene_id` | INTEGER (FK) | Current scene |
| `simulation_status` | VARCHAR | Status (not_started/in_progress/completed/abandoned) |
| `scenes_completed` | JSON | Array of completed scene IDs |
| `total_attempts` | INTEGER | Total attempts |
| `hints_used` | INTEGER | Hints used count |
| `forced_progressions` | INTEGER | Forced progressions |
| `orchestrator_data` | JSON | AI orchestrator state |
| `completion_percentage` | FLOAT | Completion percentage |
| `total_time_spent` | INTEGER | Time in seconds |
| `session_count` | INTEGER | Number of sessions |
| `final_score` | FLOAT | Final performance score |
| `started_at` | TIMESTAMP | Simulation start time |
| `completed_at` | TIMESTAMP | Completion time |
| `last_activity` | TIMESTAMP | Last activity time |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |
| `archived_at` | TIMESTAMP | Archive timestamp |
| `archived_reason` | VARCHAR | Archive reason |

### 7. Scene Progress (`scene_progress`)
**Purpose**: Track progress within individual scenes

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `user_progress_id` | INTEGER (FK) | Parent user progress |
| `scene_id` | INTEGER (FK) | Scene ID |
| `status` | VARCHAR | Scene status |
| `attempts` | INTEGER | Attempt count |
| `hints_used` | INTEGER | Hints used |
| `goal_achieved` | BOOLEAN | Goal achievement |
| `forced_progression` | BOOLEAN | Forced progression |
| `time_spent` | INTEGER | Time in seconds |
| `messages_sent` | INTEGER | User messages |
| `ai_responses` | INTEGER | AI responses |
| `goal_achievement_score` | FLOAT | Achievement score |
| `interaction_quality` | FLOAT | Quality score |
| `scene_feedback` | TEXT | Feedback text |
| `started_at` | TIMESTAMP | Start time |
| `completed_at` | TIMESTAMP | Completion time |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 8. Conversation Logs (`conversation_logs`)
**Purpose**: Store all conversation interactions

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `user_progress_id` | INTEGER (FK) | User progress reference |
| `scene_id` | INTEGER (FK) | Scene reference |
| `message_type` | VARCHAR | Message type (user/ai_persona/system/hint) |
| `sender_name` | VARCHAR | Sender name |
| `persona_id` | INTEGER (FK) | AI persona reference |
| `message_content` | TEXT | Message text |
| `message_order` | INTEGER | Message sequence |
| `attempt_number` | INTEGER | Attempt number |
| `is_hint` | BOOLEAN | Is hint message |
| `ai_context_used` | JSON | AI context data |
| `ai_model_version` | VARCHAR | AI model version |
| `processing_time` | FLOAT | Processing time |
| `user_reaction` | VARCHAR | User reaction |
| `led_to_progress` | BOOLEAN | Progress indicator |
| `timestamp` | TIMESTAMP | Message timestamp |

## Cohort Management Tables

### 9. Cohorts (`cohorts`)
**Purpose**: Educational cohort management

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `unique_id` | VARCHAR | Unique identifier |
| `title` | VARCHAR | Cohort title |
| `description` | TEXT | Cohort description |
| `course_code` | VARCHAR | Course code |
| `semester` | VARCHAR | Academic semester |
| `year` | INTEGER | Academic year |
| `max_students` | INTEGER | Maximum students |
| `auto_approve` | BOOLEAN | Auto-approve enrollments |
| `allow_self_enrollment` | BOOLEAN | Allow self-enrollment |
| `is_active` | BOOLEAN | Active status |
| `created_by` | INTEGER (FK) | Creator user ID |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 10. Cohort Students (`cohort_students`)
**Purpose**: Student enrollment in cohorts

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `cohort_id` | INTEGER (FK) | Cohort ID |
| `student_id` | INTEGER (FK) | Student user ID |
| `status` | VARCHAR | Enrollment status (pending/approved/rejected/withdrawn) |
| `enrollment_date` | TIMESTAMP | Enrollment time |
| `approved_by` | INTEGER (FK) | Approver user ID |
| `approved_at` | TIMESTAMP | Approval time |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 11. Cohort Simulations (`cohort_simulations`)
**Purpose**: Simulations assigned to cohorts

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `cohort_id` | INTEGER (FK) | Cohort ID |
| `simulation_id` | INTEGER (FK) | Scenario ID |
| `assigned_by` | INTEGER (FK) | Assigner user ID |
| `assigned_at` | TIMESTAMP | Assignment time |
| `due_date` | TIMESTAMP | Due date |
| `is_required` | BOOLEAN | Required assignment |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

## AI and LangChain Integration Tables

### 12. Vector Embeddings (`vector_embeddings`)
**Purpose**: Store vector embeddings for similarity search

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `content_type` | VARCHAR | Content type (scenario/persona/conversation) |
| `content_id` | INTEGER | Original content ID |
| `content_hash` | VARCHAR | Content hash for deduplication |
| `embedding_vector` | JSON/VECTOR | Vector embedding |
| `embedding_model` | VARCHAR | Embedding model used |
| `embedding_dimension` | INTEGER | Vector dimension |
| `original_content` | TEXT | Original text content |
| `content_metadata` | JSON | Additional metadata |
| `similarity_threshold` | FLOAT | Similarity threshold |
| `is_active` | BOOLEAN | Active status |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 13. Session Memory (`session_memory`)
**Purpose**: Store session-specific memory for LangChain agents

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `session_id` | VARCHAR | Session identifier |
| `user_progress_id` | INTEGER (FK) | User progress reference |
| `scene_id` | INTEGER (FK) | Scene reference |
| `memory_type` | VARCHAR | Memory type (conversation/context/summary/insight) |
| `memory_content` | TEXT | Memory content |
| `memory_metadata` | JSON | Additional metadata |
| `parent_memory_id` | INTEGER (FK) | Parent memory reference |
| `related_persona_id` | INTEGER (FK) | Related persona |
| `importance_score` | FLOAT | Importance score (0.0-1.0) |
| `access_count` | INTEGER | Access count |
| `last_accessed` | TIMESTAMP | Last access time |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 14. Conversation Summaries (`conversation_summaries`)
**Purpose**: AI-generated conversation summaries

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `user_progress_id` | INTEGER (FK) | User progress reference |
| `scene_id` | INTEGER (FK) | Scene reference |
| `summary_type` | VARCHAR | Summary type |
| `summary_text` | TEXT | Summary content |
| `key_points` | JSON | Key points extracted |
| `learning_moments` | JSON | Learning moments |
| `insights` | JSON | AI insights |
| `recommendations` | JSON | Recommendations |
| `conversation_count` | INTEGER | Conversation count |
| `message_count` | INTEGER | Message count |
| `summary_metadata` | JSON | Additional metadata |
| `quality_score` | FLOAT | Summary quality score |
| `relevance_score` | FLOAT | Relevance score |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 15. Agent Sessions (`agent_sessions`)
**Purpose**: LangChain agent session management

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `session_id` | VARCHAR | Unique session ID |
| `user_progress_id` | INTEGER (FK) | User progress reference |
| `agent_type` | VARCHAR | Agent type (persona/grading/summarization/retrieval) |
| `agent_id` | VARCHAR | Specific agent identifier |
| `session_state` | JSON | Current session state |
| `session_config` | JSON | Session configuration |
| `session_metadata` | JSON | Additional metadata |
| `total_interactions` | INTEGER | Total interactions |
| `total_tokens_used` | INTEGER | Tokens consumed |
| `average_response_time` | FLOAT | Average response time |
| `error_count` | INTEGER | Error count |
| `is_active` | BOOLEAN | Active status |
| `last_activity` | TIMESTAMP | Last activity time |
| `expires_at` | TIMESTAMP | Session expiration |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

## Supporting Tables

### 16. Scenario Files (`scenario_files`)
**Purpose**: File attachments for scenarios

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `scenario_id` | INTEGER (FK) | Parent scenario |
| `filename` | VARCHAR | Original filename |
| `file_path` | VARCHAR | File storage path |
| `file_size` | INTEGER | File size in bytes |
| `file_type` | VARCHAR | MIME type |
| `original_content` | TEXT | Original content |
| `processed_content` | TEXT | Processed content |
| `processing_status` | VARCHAR | Processing status |
| `processing_log` | JSON | Processing log |
| `llamaparse_job_id` | VARCHAR | Llamaparse job ID |
| `uploaded_at` | TIMESTAMP | Upload time |
| `processed_at` | TIMESTAMP | Processing completion time |

### 17. Scenario Reviews (`scenario_reviews`)
**Purpose**: User reviews of scenarios

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `scenario_id` | INTEGER (FK) | Scenario ID |
| `reviewer_id` | INTEGER (FK) | Reviewer user ID |
| `rating` | INTEGER | Rating (1-5 stars) |
| `review_text` | TEXT | Review text |
| `pros` | JSON | Pros list |
| `cons` | JSON | Cons list |
| `use_case` | VARCHAR | Use case description |
| `helpful_votes` | INTEGER | Helpful votes |
| `total_votes` | INTEGER | Total votes |
| `created_at` | TIMESTAMP | Creation time |

### 18. Cache Entries (`cache_entries`)
**Purpose**: Performance optimization cache

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `cache_key` | VARCHAR | Unique cache key |
| `cache_type` | VARCHAR | Cache type (embedding/response/summary/context) |
| `cache_data` | JSON | Cached data |
| `cache_size` | INTEGER | Cache size in bytes |
| `hit_count` | INTEGER | Cache hit count |
| `miss_count` | INTEGER | Cache miss count |
| `last_accessed` | TIMESTAMP | Last access time |
| `expires_at` | TIMESTAMP | Expiration time |
| `is_expired` | BOOLEAN | Expired status |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |

### 19. User Progress Archive (`user_progress_archive`)
**Purpose**: Long-term storage of archived user progress

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `original_user_progress_id` | INTEGER | Original progress ID |
| `user_id` | INTEGER | User ID |
| `scenario_id` | INTEGER | Scenario ID |
| `current_scene_id` | INTEGER | Current scene ID |
| `simulation_status` | VARCHAR | Simulation status |
| `scenes_completed` | JSON | Completed scenes |
| `total_attempts` | INTEGER | Total attempts |
| `hints_used` | INTEGER | Hints used |
| `forced_progressions` | INTEGER | Forced progressions |
| `orchestrator_data` | JSON | Orchestrator data |
| `completion_percentage` | FLOAT | Completion percentage |
| `total_time_spent` | INTEGER | Time spent |
| `session_count` | INTEGER | Session count |
| `final_score` | FLOAT | Final score |
| `started_at` | TIMESTAMP | Start time |
| `completed_at` | TIMESTAMP | Completion time |
| `last_activity` | TIMESTAMP | Last activity |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update time |
| `archived_at` | TIMESTAMP | Archive time |
| `archived_reason` | VARCHAR | Archive reason |

## Messaging and Communication Tables

### 20. Professor Student Messages (`professor_student_messages`)
**Purpose**: Messages between professors and students

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `professor_id` | INTEGER (FK) | Professor user ID |
| `student_id` | INTEGER (FK) | Student user ID |
| `cohort_id` | INTEGER (FK) | Associated cohort (nullable) |
| `subject` | VARCHAR(255) | Message subject |
| `message` | TEXT | Message content |
| `message_type` | VARCHAR(50) | Message type (general, assignment, feedback, etc.) |
| `parent_message_id` | INTEGER (FK) | Parent message for replies |
| `is_reply` | BOOLEAN | Is this a reply message |
| `professor_read` | BOOLEAN | Professor has read the message |
| `student_read` | BOOLEAN | Student has read the message |
| `created_at` | TIMESTAMP | Message creation time |
| `updated_at` | TIMESTAMP | Last update time |

**Indexes**: professor_id, student_id, cohort_id, parent_message_id, created_at, professor_read, student_read

### 21. Notifications (`notifications`)
**Purpose**: In-app notifications for users

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `user_id` | INTEGER (FK) | User who receives notification |
| `type` | VARCHAR(50) | Notification type (cohort_invitation, assignment, message, etc.) |
| `title` | VARCHAR(255) | Notification title |
| `message` | TEXT | Notification message |
| `data` | JSON | Additional notification data |
| `is_read` | BOOLEAN | Notification read status |
| `created_at` | TIMESTAMP | Notification creation time |

**Indexes**: user_id, type, is_read, created_at

### 22. Cohort Invitations (`cohort_invitations`)
**Purpose**: Invitations for students to join cohorts

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER (PK) | Primary key |
| `cohort_id` | INTEGER (FK) | Cohort being invited to |
| `professor_id` | INTEGER (FK) | Professor sending invitation |
| `student_id` | INTEGER (FK) | Student being invited |
| `status` | VARCHAR(20) | Invitation status (pending, accepted, declined, expired) |
| `invitation_token` | VARCHAR(255) | Unique invitation token |
| `expires_at` | TIMESTAMP | Invitation expiration time |
| `accepted_at` | TIMESTAMP | Acceptance time |
| `declined_at` | TIMESTAMP | Decline time |
| `created_at` | TIMESTAMP | Invitation creation time |
| `updated_at` | TIMESTAMP | Last update time |

**Indexes**: cohort_id, professor_id, student_id, status, invitation_token, expires_at

## LangChain Integration Tables

### 23. LangChain PG Collection (`langchain_pg_collection`)
**Purpose**: LangChain collection metadata

### 24. LangChain PG Embedding (`langchain_pg_embedding`)
**Purpose**: LangChain embedding storage

## Key Relationships

### Core Entity Relationships
- **Users** → **Scenarios** (1:many) - Users create scenarios
- **Scenarios** → **Scenario Personas** (1:many) - Scenarios contain personas
- **Scenarios** → **Scenario Scenes** (1:many) - Scenarios contain scenes
- **Scenes** ↔ **Personas** (many:many) - Scenes involve personas

### Simulation Flow
- **Users** → **User Progress** (1:many) - Users have progress records
- **User Progress** → **Scene Progress** (1:many) - Progress tracks scene completion
- **User Progress** → **Conversation Logs** (1:many) - Progress contains conversations
- **Scenes** → **Conversation Logs** (1:many) - Scenes generate conversations

### Cohort Management
- **Users** → **Cohorts** (1:many) - Users create cohorts
- **Cohorts** → **Cohort Students** (1:many) - Cohorts have students
- **Cohorts** → **Cohort Simulations** (1:many) - Cohorts have assigned simulations
- **Cohorts** → **Cohort Invitations** (1:many) - Cohorts have invitations
- **Users** → **Cohort Invitations** (1:many) - Users receive invitations

### Messaging and Communication
- **Users** → **Professor Student Messages** (1:many) - Users send/receive messages
- **Cohorts** → **Professor Student Messages** (1:many) - Messages can be cohort-specific
- **Professor Student Messages** → **Professor Student Messages** (1:many) - Message replies
- **Users** → **Notifications** (1:many) - Users receive notifications

### AI Integration
- **User Progress** → **Session Memory** (1:many) - Progress has memory
- **User Progress** → **Agent Sessions** (1:many) - Progress has agent sessions
- **User Progress** → **Conversation Summaries** (1:many) - Progress has summaries

## Indexes and Performance

### Primary Indexes
- All primary keys are automatically indexed
- Foreign key columns have indexes for join performance
- Unique constraints create unique indexes

### Custom Indexes
- **Users**: email, username, role, created_at, google_id, provider
- **Scenarios**: title, industry, is_public, created_by, created_at, rating_avg, deleted_at
- **Cohorts**: created_by, is_active, year, course_code
- **Vector Embeddings**: content_type, content_id, content_hash, is_active, created_at
- **Session Memory**: session_id, user_progress_id, scene_id, memory_type, importance_score, last_accessed
- **Agent Sessions**: session_id, user_progress_id, agent_type, is_active, last_activity
- **Cache Entries**: cache_key, cache_type, expires_at, last_accessed
- **Professor Student Messages**: professor_id, student_id, cohort_id, parent_message_id, created_at, professor_read, student_read
- **Notifications**: user_id, type, is_read, created_at
- **Cohort Invitations**: cohort_id, professor_id, student_id, status, invitation_token, expires_at

### Soft Deletion Support
- **Scenarios**: `deleted_at`, `deleted_by`, `deletion_reason` for soft deletion
- **User Progress**: `archived_at`, `archived_reason` for archiving
- Partial indexes for active records (WHERE deleted_at IS NULL)

## Migration History

1. **0001_consolidated_schema**: Initial schema creation
2. **da94850967cc_add_soft_deletion_support**: Added soft deletion support
3. **df317c1d90a5_fix_cohort_simulations_foreign_key**: Fixed foreign key reference
4. **add_messaging_system**: Added messaging and notification system
5. **add_cohort_invitations**: Added cohort invitation system

## Database Features

### Vector Support
- pgvector integration for similarity search
- Fallback to JSON storage when pgvector unavailable
- Configurable vector dimensions

### Soft Deletion
- Scenarios support soft deletion with audit trail
- User progress supports archiving
- Archive table for long-term storage

### Performance Optimization
- Connection pooling with SQLAlchemy
- Comprehensive indexing strategy
- Cache system for frequently accessed data
- JSON columns for flexible data storage

### Data Integrity
- Foreign key constraints maintain referential integrity
- Unique constraints prevent duplicates
- Check constraints for data validation
- Cascade deletes for dependent records
- Message threading with parent-child relationships
- Notification system with template-based messaging

## Security Considerations

- Password hashing for user authentication
- OAuth integration for Google authentication
- Soft deletion preserves audit trails
- Secure logging for sensitive data
- Environment-based configuration
- Role-based access control for messaging
- Message read status tracking
- Invitation token-based security

## Messaging System Features

### Message Types
- **General Messages**: Standard communication between users
- **Assignment Messages**: Messages related to specific assignments
- **Feedback Messages**: Messages containing feedback or grades
- **Cohort Messages**: Messages associated with specific cohorts

### Notification Types
- **Cohort Invitations**: New cohort invitation notifications
- **Assignment Notifications**: Assignment due dates and updates
- **Message Notifications**: New messages and replies
- **Grade Notifications**: Grade postings and feedback
- **Cohort Updates**: Changes to cohort information

### Message Threading
- **Parent Messages**: Original messages that can receive replies
- **Reply Messages**: Messages that respond to parent messages
- **Thread Viewing**: Complete conversation history
- **Read Status**: Separate read tracking for professors and students

### Cohort Integration
- **Cohort-Specific Messages**: Messages linked to specific cohorts
- **Student Enrollment Validation**: Messages only sent to enrolled students
- **Professor Access Control**: Professors can only message their cohort students

This database structure supports a comprehensive educational simulation platform with AI-powered conversations, cohort management, detailed progress tracking, and a complete messaging and notification system.
