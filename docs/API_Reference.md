# 🔌 API Reference - Enhanced

## Overview

The AI Agent Education Platform provides a comprehensive REST API for managing educational simulations, AI agents, and user interactions. This enhanced reference includes all current endpoints with detailed schemas and examples.

**Base URL:** `http://localhost:8000`  
**API Version:** 2.0.0  
**Authentication:** JWT Bearer tokens (where required)

## 📋 Table of Contents

1. [Authentication](#authentication)
2. [User Management](#user-management)
3. [Scenario Management](#scenario-management)
4. [PDF Processing](#pdf-processing)
5. [Simulation System](#simulation-system)
6. [AI Agents](#ai-agents)
7. [Cohort Management](#cohort-management)
8. [Data Management & Soft Deletion](#data-management--soft-deletion)
9. [Publishing & Marketplace](#publishing--marketplace)
10. [System Endpoints](#system-endpoints)
11. [Error Handling](#error-handling)
12. [Rate Limiting](#rate-limiting)

---

## 🔐 Authentication

### User Registration

**`POST /users/register`**

Register a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "full_name": "John Doe",
  "username": "johndoe",
  "password": "securepassword123",
  "bio": "Business student interested in strategic management",
  "avatar_url": "https://example.com/avatar.jpg",
  "profile_public": true,
  "allow_contact": true
}
```

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "username": "johndoe",
  "role": "user",
  "bio": "Business student interested in strategic management",
  "avatar_url": "https://example.com/avatar.jpg",
  "published_scenarios": 0,
  "total_simulations": 0,
  "reputation_score": 0.0,
  "profile_public": true,
  "allow_contact": true,
  "is_active": true,
  "is_verified": false,
  "created_at": "2025-01-06T12:00:00Z",
  "updated_at": "2025-01-06T12:00:00Z"
}
```

### User Login

**`POST /users/login`**

Authenticate user and receive JWT token.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "full_name": "John Doe",
    "username": "johndoe",
    "role": "user"
  }
}
```

### Get Current User

**`GET /users/me`** 🔒

Get the authenticated user's profile information.

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "full_name": "John Doe",
  "username": "johndoe",
  "role": "user",
  "bio": "Business student interested in strategic management",
  "avatar_url": "https://example.com/avatar.jpg",
  "published_scenarios": 5,
  "total_simulations": 12,
  "reputation_score": 4.2,
  "profile_public": true,
  "allow_contact": true,
  "is_active": true,
  "is_verified": true,
  "created_at": "2025-01-06T12:00:00Z",
  "updated_at": "2025-01-06T15:30:00Z"
}
```

---

## 👥 User Management

### Update User Profile

**`PUT /users/me`** 🔒

Update the authenticated user's profile.

**Request Body:**
```json
{
  "full_name": "John Smith",
  "bio": "Updated bio information",
  "avatar_url": "https://example.com/new-avatar.jpg",
  "profile_public": false,
  "allow_contact": false
}
```

### Change Password

**`POST /users/change-password`** 🔒

Change user password.

**Request Body:**
```json
{
  "current_password": "oldpassword123",
  "new_password": "newpassword456"
}
```

### Get User Profile (Public)

**`GET /users/{user_id}`**

Get public user profile information.

**Response:**
```json
{
  "id": 1,
  "username": "johndoe",
  "full_name": "John Doe",
  "bio": "Business student interested in strategic management",
  "avatar_url": "https://example.com/avatar.jpg",
  "published_scenarios": 5,
  "total_simulations": 12,
  "reputation_score": 4.2,
  "created_at": "2025-01-06T12:00:00Z"
}
```

---

## 📚 Scenario Management

### Get All Scenarios

**`GET /scenarios/`**

Get list of all available scenarios.

**Query Parameters:**
- `skip` (integer, optional) - Number of records to skip (default: 0)
- `limit` (integer, optional) - Number of records to return (default: 100)
- `is_public` (boolean, optional) - Filter by public scenarios
- `industry` (string, optional) - Filter by industry
- `difficulty_level` (string, optional) - Filter by difficulty

**Response:**
```json
[
  {
    "id": 1,
    "title": "E-commerce Platform Launch",
    "description": "Launch a new e-commerce platform in competitive market",
    "industry": "Technology",
    "challenge": "Compete with established players while building customer trust",
    "learning_objectives": [
      "Market analysis and positioning",
      "Customer acquisition strategies",
      "Technology stack decisions"
    ],
    "student_role": "Product Manager",
    "category": "business_strategy",
    "difficulty_level": "intermediate",
    "estimated_duration": 60,
    "tags": ["strategy", "market_analysis", "decision_making"],
    "rating_avg": 4.5,
    "rating_count": 23,
    "usage_count": 156,
    "is_public": true,
    "created_at": "2025-01-06T12:00:00Z"
  }
]
```

### Get Scenario Details

**`GET /scenarios/{scenario_id}`**

Get detailed information about a specific scenario.

**Response:**
```json
{
  "id": 1,
  "title": "E-commerce Platform Launch",
  "description": "Launch a new e-commerce platform...",
  "challenge": "Compete with established players...",
  "industry": "Technology",
  "learning_objectives": [
    "Market analysis and positioning",
    "Customer acquisition strategies"
  ],
  "student_role": "Product Manager",
  "category": "business_strategy",
  "difficulty_level": "intermediate",
  "estimated_duration": 60,
  "tags": ["strategy", "market_analysis"],
  "rating_avg": 4.5,
  "rating_count": 23,
  "usage_count": 156,
  "persona_count": 3,
  "scene_count": 4,
  "is_public": true,
  "created_at": "2025-01-06T12:00:00Z"
}
```

### Get Full Scenario with Personas and Scenes

**`GET /api/scenarios/{scenario_id}/full`**

Get complete scenario information including personas and scenes.

**Response:**
```json
{
  "id": 1,
  "title": "E-commerce Platform Launch",
  "description": "Launch a new e-commerce platform...",
  "challenge": "Compete with established players...",
  "industry": "Technology",
  "learning_objectives": [
    "Market analysis and positioning",
    "Customer acquisition strategies"
  ],
  "student_role": "Product Manager",
  "category": "business_strategy",
  "difficulty_level": "intermediate",
  "estimated_duration": 60,
  "tags": ["strategy", "market_analysis"],
  "is_public": true,
  "created_at": "2025-01-06T12:00:00Z",
  "personas": [
    {
      "id": 1,
      "name": "Sarah Chen",
      "role": "Marketing Director",
      "background": "10+ years in digital marketing...",
      "correlation": "Key stakeholder in customer acquisition strategy",
      "primary_goals": [
        "Increase brand awareness",
        "Improve conversion rates"
      ],
      "personality_traits": {
        "analytical": 8,
        "creative": 7,
        "assertive": 6,
        "collaborative": 9,
        "detail_oriented": 8
      }
    }
  ],
  "scenes": [
    {
      "id": 1,
      "scenario_id": 1,
      "title": "Market Analysis Meeting",
      "description": "Initial market research discussion...",
      "user_goal": "Understand target market segments",
      "scene_order": 1,
      "estimated_duration": 30,
      "image_url": "https://example.com/scene1.jpg",
      "image_prompt": "Professional business meeting room",
      "timeout_turns": 20,
      "success_metric": "Identify 3 key market segments",
      "personas_involved": ["Sarah Chen", "Mike Johnson"],
      "created_at": "2025-01-06T12:00:00Z",
      "personas": [
        {
          "id": 1,
          "name": "Sarah Chen",
          "role": "Marketing Director",
          "background": "10+ years in digital marketing...",
          "personality_traits": {
            "analytical": 8,
            "creative": 7
          }
        }
      ]
    }
  ]
}
```

---

## 📄 PDF Processing

### Upload and Process PDF

**`POST /api/parse-pdf/`**

Upload a PDF case study and process it with AI to extract scenarios, personas, and scenes.

**Request:**
- **Content-Type:** `multipart/form-data`
- **file:** PDF file (required)
- **context_files:** Additional context files (optional)
- **save_to_db:** Boolean to save results (default: false)
- **user_id:** User ID (default: 1)

**Example using curl:**
```bash
curl -X POST "http://localhost:8000/api/parse-pdf/" \
  -F "file=@business_case.pdf" \
  -F "context_files=@additional_context.txt" \
  -F "save_to_db=true" \
  -F "user_id=1"
```

**Response:**
```json
{
  "status": "completed",
  "scenario_id": 15,
  "ai_result": {
    "title": "KasKazi Network Ltd – Distributing to the Bottom of the Pyramid",
    "description": "This case examines the challenges faced by KasKazi Network...",
    "student_role": "Business Strategy Consultant",
    "key_figures": [
      {
        "name": "John Smith",
        "role": "Founder/CEO of KasKazi Network",
        "background": "Entrepreneur with deep market knowledge...",
        "correlation": "Primary decision maker facing strategic challenges",
        "primary_goals": [
          "Achieve year-round business operations",
          "Build sustainable competitive advantage",
          "Expand market reach"
        ],
        "personality_traits": {
          "analytical": 9,
          "creative": 7,
          "assertive": 8,
          "collaborative": 6,
          "detail_oriented": 8
        }
      }
    ],
    "scenes": [
      {
        "title": "Crisis Assessment Meeting",
        "description": "Emergency meeting to assess seasonal contract challenges...",
        "user_goal": "Understand the scope and impact of seasonal dependency",
        "sequence_order": 1,
        "image_url": "https://generated-image-url.com/scene1.jpg"
      }
    ],
    "learning_outcomes": [
      "1. Analyze business model sustainability challenges",
      "2. Evaluate market entry strategies for emerging markets",
      "3. Develop solutions for supply chain continuity"
    ]
  }
}
```

**Status Codes:**
- `200` - PDF processed successfully
- `400` - Invalid file format or missing file
- `500` - Processing error (LlamaParse or OpenAI issues)

---

## 🎮 Simulation System

### Start Linear Simulation

**`POST /api/simulation/start`**

Start a new linear simulation with ChatOrchestrator integration.

**Request Body:**
```json
{
  "scenario_id": 1,
  "user_id": 1
}
```

**Response:**
```json
{
  "user_progress_id": 123,
  "scenario": {
    "id": 1,
    "title": "KasKazi Network Strategic Challenge",
    "description": "Navigate seasonal contract dependencies...",
    "challenge": "Develop sustainable business model",
    "industry": "Distribution",
    "learning_objectives": [
      "Analyze market dynamics",
      "Develop strategic solutions"
    ],
    "student_role": "Business Strategy Consultant"
  },
  "current_scene": {
    "id": 1,
    "scenario_id": 1,
    "title": "Crisis Assessment Meeting",
    "description": "Emergency meeting in the boardroom...",
    "user_goal": "Assess scope of seasonal dependency crisis",
    "scene_order": 1,
    "estimated_duration": 30,
    "image_url": "https://example.com/scene1.jpg",
    "timeout_turns": 20,
    "success_metric": "Identify key challenges and stakeholders",
    "personas": [
      {
        "id": 1,
        "name": "John Smith",
        "role": "Founder/CEO",
        "background": "Experienced entrepreneur...",
        "personality_traits": {
          "analytical": 9,
          "assertive": 8
        }
      }
    ]
  },
  "simulation_status": "waiting_for_begin"
}
```

### Linear Chat with Orchestrator

**`POST /api/simulation/linear-chat`**

Send a message to the ChatOrchestrator for linear simulation experience.

**Request Body:**
```json
{
  "scenario_id": 1,
  "user_id": 1,
  "scene_id": 1,
  "message": "begin"
}
```

**Response:**
```json
{
  "message": "# KasKazi Network Strategic Challenge\n\nWelcome to this multi-scene simulation where you'll navigate complex business challenges...\n\n**Scene 1 — Crisis Assessment Meeting**\n\n*You're in the main conference room with senior leadership, reviewing urgent seasonal contract issues...*\n\n**Objective:** Assess the scope and impact of seasonal dependency\n\n**Active Participants:**\n• @john_smith: John Smith (Founder/CEO)\n\n*You have 20 turns to achieve the objective.*\n\n**@john_smith:** Welcome to our emergency strategy session. As you can see from the reports, our seasonal contract model is creating significant gaps in our operations. What's your initial assessment of our situation?",
  "scene_id": 1,
  "scene_completed": false,
  "next_scene_id": null,
  "turns_remaining": 19,
  "orchestrator_data": {
    "current_turn": 1,
    "scene_status": "in_progress",
    "active_personas": ["john_smith"],
    "conversation_context": "Initial scene introduction"
  }
}
```

**Special Commands:**
- `"begin"` - Start the simulation
- `"help"` - Get available commands and current status
- `@mention` - Interact with specific personas (e.g., `@john_smith`)

### Get User Responses

**`GET /api/simulation/user-responses`**

Fetch all user responses for a simulation, optionally filtered by scene.

**Query Parameters:**
- `user_progress_id` (integer, required) - User progress ID
- `scene_id` (integer, optional) - Filter by specific scene

**Response:**
```json
{
  "user_messages": [
    {
      "id": 1,
      "content": "What are the main challenges we're facing?",
      "timestamp": "2025-01-06T12:00:00Z",
      "scene_id": 1,
      "message_order": 1
    }
  ],
  "all_messages": [
    {
      "id": 1,
      "type": "user",
      "sender": "User",
      "content": "What are the main challenges we're facing?",
      "timestamp": "2025-01-06T12:00:00Z",
      "scene_id": 1,
      "message_order": 1
    },
    {
      "id": 2,
      "type": "ai_persona",
      "sender": "John Smith",
      "content": "The main challenges are...",
      "timestamp": "2025-01-06T12:01:00Z",
      "scene_id": 1,
      "message_order": 2
    }
  ],
  "scene_meta": {
    "id": 1,
    "title": "Crisis Assessment Meeting",
    "description": "Emergency meeting to assess challenges",
    "success_metric": "Identify key challenges and stakeholders",
    "learning_outcomes": ["Strategic analysis", "Stakeholder identification"],
    "teaching_notes": "Focus on systematic problem identification"
  }
}
```

### Get Simulation Grading

**`GET /api/simulation/grade`**

Get detailed grading and assessment for a simulation.

**Query Parameters:**
- `user_progress_id` (integer, required) - User progress ID

**Response:**
```json
{
  "overall_score": 85.5,
  "completion_percentage": 100.0,
  "scenes_completed": 4,
  "total_scenes": 4,
  "total_time_spent": 1800,
  "hints_used": 2,
  "scene_scores": [
    {
      "scene_id": 1,
      "scene_title": "Crisis Assessment Meeting",
      "score": 90.0,
      "time_spent": 450,
      "turns_taken": 8,
      "hints_used": 0,
      "feedback": "Excellent analysis of the situation. You identified all key challenges and stakeholders effectively."
    }
  ],
  "learning_objectives": [
    {
      "objective": "Analyze market dynamics",
      "achieved": true,
      "score": 88.0,
      "feedback": "Strong understanding of market forces and competitive landscape."
    }
  ],
  "recommendations": [
    "Consider exploring alternative revenue streams",
    "Focus on building strategic partnerships"
  ]
}
```

---

## 🤖 AI Agents

### Create Agent Session

**`POST /api/agents/sessions/create`**

Create a new AI agent session.

**Request Body:**
```json
{
  "user_id": 1,
  "scenario_id": 1,
  "scene_id": 1,
  "agent_type": "persona",
  "agent_id": "john_smith",
  "session_config": {
    "temperature": 0.7,
    "max_tokens": 1000,
    "memory_type": "conversation_buffer"
  }
}
```

**Response:**
```json
{
  "session_id": "session_123_456_789",
  "agent_type": "persona",
  "agent_id": "john_smith",
  "status": "active",
  "started_at": "2025-01-06T12:00:00Z",
  "configuration": {
    "temperature": 0.7,
    "max_tokens": 1000,
    "memory_type": "conversation_buffer"
  }
}
```

### Interact with Agent

**`POST /api/agents/sessions/{session_id}/interact`**

Send a message to a specific AI agent.

**Request Body:**
```json
{
  "message": "What are your main concerns about the current situation?",
  "context": {
    "scene_id": 1,
    "user_progress_id": 123,
    "additional_context": "User is new to business strategy"
  }
}
```

**Response:**
```json
{
  "response": "As the founder, I'm deeply concerned about our revenue gaps during off-season periods. We need to find sustainable solutions that don't compromise our core values.",
  "agent_id": "john_smith",
  "session_id": "session_123_456_789",
  "processing_time": 0.8,
  "token_count": 45,
  "memory_updated": true,
  "context_retrieved": [
    "Previous discussion about seasonal challenges",
    "User's background in business strategy"
  ]
}
```

### Get Agent Session Status

**`GET /api/agents/sessions/{session_id}`**

Get current status and information about an agent session.

**Response:**
```json
{
  "session_id": "session_123_456_789",
  "agent_type": "persona",
  "agent_id": "john_smith",
  "status": "active",
  "started_at": "2025-01-06T12:00:00Z",
  "last_activity": "2025-01-06T12:05:00Z",
  "total_interactions": 5,
  "average_response_time": 0.7,
  "error_count": 0,
  "memory_summary": "User has shown interest in strategic planning and stakeholder management"
}
```

---

## 👥 Cohort Management

### List Cohorts

**`GET /cohorts/`**

Get all cohorts with optional filtering.

**Query Parameters:**
- `skip` (int, optional): Number of records to skip (default: 0)
- `limit` (int, optional): Maximum number of records to return (default: 100)
- `search` (string, optional): Search term for title, description, or course code
- `status` (string, optional): Filter by status ("active", "inactive")

**Response:**
```json
[
  {
    "id": 1,
    "unique_id": "CH-ABC123",
    "title": "Business Strategy Fall 2024",
    "description": "Advanced business strategy course",
    "course_code": "BUS-401",
    "semester": "Fall",
    "year": 2024,
    "max_students": 30,
    "is_active": true,
    "created_by": 1,
    "created_at": "2024-09-18T10:00:00Z",
    "student_count": 15,
    "simulation_count": 3
  }
]
```

### Create Cohort

**`POST /cohorts/`**

Create a new cohort.

**Request Body:**
```json
{
  "title": "Business Strategy Fall 2024",
  "description": "Advanced business strategy course",
  "course_code": "BUS-401",
  "semester": "Fall",
  "year": 2024,
  "max_students": 30,
  "auto_approve": true,
  "allow_self_enrollment": false
}
```

**Response:**
```json
{
  "id": 1,
  "unique_id": "CH-ABC123",
  "title": "Business Strategy Fall 2024",
  "description": "Advanced business strategy course",
  "course_code": "BUS-401",
  "semester": "Fall",
  "year": 2024,
  "max_students": 30,
  "auto_approve": true,
  "allow_self_enrollment": false,
  "is_active": true,
  "created_by": 1,
  "created_at": "2024-09-18T10:00:00Z",
  "students": [],
  "simulations": []
}
```

### Get Cohort Details

**`GET /cohorts/{cohort_unique_id}`**

Get detailed information about a specific cohort.

**Response:**
```json
{
  "id": 1,
  "unique_id": "CH-ABC123",
  "title": "Business Strategy Fall 2024",
  "description": "Advanced business strategy course",
  "course_code": "BUS-401",
  "semester": "Fall",
  "year": 2024,
  "max_students": 30,
  "auto_approve": true,
  "allow_self_enrollment": false,
  "is_active": true,
  "created_by": 1,
  "created_at": "2024-09-18T10:00:00Z",
  "updated_at": "2024-09-18T10:00:00Z",
  "students": [
    {
      "id": 1,
      "student_id": 2,
      "student_name": "Jane Smith",
      "student_email": "jane@example.com",
      "status": "approved",
      "enrollment_date": "2024-09-18T10:00:00Z",
      "approved_at": "2024-09-18T10:00:00Z"
    }
  ],
  "simulations": [
    {
      "id": 1,
      "simulation_id": 1,
      "assigned_by": 1,
      "assigned_at": "2024-09-18T10:00:00Z",
      "due_date": "2024-12-15T23:59:59Z",
      "is_required": true
    }
  ]
}
```

### Update Cohort

**`PUT /cohorts/{cohort_unique_id}`**

Update cohort information.

**Request Body:**
```json
{
  "title": "Updated Business Strategy Fall 2024",
  "description": "Updated description",
  "max_students": 35,
  "is_active": false
}
```

### Delete Cohort

**`DELETE /cohorts/{cohort_unique_id}`**

Delete a cohort and all related data.

**Response:**
```json
{
  "message": "Cohort deleted successfully",
  "deleted_students": 15,
  "deleted_simulations": 3
}
```

### Get Cohort Students

**`GET /cohorts/{cohort_unique_id}/students`**

Get all students enrolled in a cohort.

**Response:**
```json
[
  {
    "id": 1,
    "student_id": 2,
    "student_name": "Jane Smith",
    "student_email": "jane@example.com",
    "status": "approved",
    "enrollment_date": "2024-09-18T10:00:00Z",
    "approved_at": "2024-09-18T10:00:00Z"
  }
]
```

### Add Student to Cohort

**`POST /cohorts/{cohort_id}/students`**

Add a student to a cohort.

**Request Body:**
```json
{
  "student_id": 2,
  "status": "approved"
}
```

### Get Cohort Simulations

**`GET /cohorts/{cohort_unique_id}/simulations`**

Get all simulations assigned to a cohort.

**Response:**
```json
[
  {
    "id": 1,
    "simulation_id": 1,
    "assigned_by": 1,
    "assigned_at": "2024-09-18T10:00:00Z",
    "due_date": "2024-12-15T23:59:59Z",
    "is_required": true
  }
]
```

### Assign Simulation to Cohort

**`POST /cohorts/{cohort_id}/simulations`**

Assign a simulation to a cohort.

**Request Body:**
```json
{
  "simulation_id": 1,
  "due_date": "2024-12-15T23:59:59Z",
  "is_required": true
}
```

## 🗄️ Data Management & Soft Deletion

### Soft Delete Scenario

**`POST /api/scenarios/{scenario_id}/soft-delete`**

Safely delete a scenario with data archiving.

**Request Body:**
```json
{
  "reason": "User deletion",
  "deleted_by": 1
}
```

**Response:**
```json
{
  "message": "Scenario soft deleted successfully",
  "archived_progress_records": 25,
  "deletion_timestamp": "2024-09-18T10:00:00Z"
}
```

### Restore Scenario

**`POST /api/scenarios/{scenario_id}/restore`**

Restore a soft-deleted scenario.

**Request Body:**
```json
{
  "restored_by": 1
}
```

**Response:**
```json
{
  "message": "Scenario restored successfully",
  "restoration_timestamp": "2024-09-18T10:00:00Z"
}
```

### Get Archive Statistics

**`GET /api/archives/stats`**

Get statistics about archived data.

**Response:**
```json
{
  "total_archives": 150,
  "unique_scenarios": 5,
  "unique_users": 25,
  "oldest_archive": "2024-01-15T10:00:00Z",
  "newest_archive": "2024-09-18T10:00:00Z"
}
```

### Cleanup Old Archives

**`POST /api/archives/cleanup`**

Clean up old archived records.

**Request Body:**
```json
{
  "days_old": 30
}
```

**Response:**
```json
{
  "message": "Archive cleanup completed",
  "records_deleted": 50,
  "cleanup_timestamp": "2024-09-18T10:00:00Z"
}
```

---

## 🏪 Publishing & Marketplace

### Publish Scenario

**`POST /api/scenarios/publish`** 🔒

Publish a scenario to the public marketplace.

**Request Body:**
```json
{
  "scenario_id": 1,
  "category": "business_strategy",
  "difficulty_level": "intermediate",
  "estimated_duration": 60,
  "tags": ["strategy", "market_analysis", "decision_making"],
  "description": "Comprehensive business strategy simulation",
  "learning_objectives": [
    "Strategic thinking development",
    "Market analysis skills",
    "Decision-making under uncertainty"
  ]
}
```

**Response:**
```json
{
  "message": "Scenario published successfully",
  "scenario": {
    "id": 1,
    "title": "E-commerce Platform Launch",
    "is_public": true,
    "category": "business_strategy",
    "difficulty_level": "intermediate",
    "estimated_duration": 60,
    "tags": ["strategy", "market_analysis", "decision_making"],
    "published_at": "2025-01-06T12:00:00Z"
  }
}
```

### Get Marketplace Scenarios

**`GET /api/scenarios/marketplace`**

Get published scenarios from the marketplace.

**Query Parameters:**
- `category` (string, optional) - Filter by category
- `difficulty` (string, optional) - Filter by difficulty level
- `search` (string, optional) - Search in titles and descriptions
- `page` (integer, optional) - Page number (default: 1)
- `page_size` (integer, optional) - Items per page (default: 20)
- `sort_by` (string, optional) - Sort by: rating, usage, created_at (default: rating)
- `sort_order` (string, optional) - Sort order: asc, desc (default: desc)

**Response:**
```json
{
  "scenarios": [
    {
      "id": 1,
      "title": "E-commerce Platform Launch",
      "description": "Strategic launch simulation...",
      "category": "business_strategy",
      "difficulty_level": "intermediate",
      "estimated_duration": 60,
      "tags": ["strategy", "market_analysis"],
      "rating_avg": 4.5,
      "rating_count": 23,
      "usage_count": 156,
      "created_by": {
        "id": 5,
        "username": "business_prof",
        "full_name": "Dr. Sarah Johnson"
      },
      "created_at": "2025-01-06T12:00:00Z"
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 20,
  "total_pages": 3,
  "filters": {
    "categories": ["business_strategy", "leadership", "operations"],
    "difficulty_levels": ["beginner", "intermediate", "advanced"],
    "tags": ["strategy", "market_analysis", "decision_making", "leadership"]
  }
}
```

### Clone Scenario

**`POST /api/scenarios/{scenario_id}/clone`** 🔒

Clone an existing scenario for customization.

**Request Body:**
```json
{
  "new_title": "My Custom E-commerce Launch",
  "new_description": "Customized version for my class",
  "modifications": {
    "difficulty_level": "beginner",
    "estimated_duration": 45,
    "learning_objectives": [
      "Basic market analysis",
      "Introduction to strategic thinking"
    ]
  }
}
```

**Response:**
```json
{
  "message": "Scenario cloned successfully",
  "original_scenario_id": 1,
  "new_scenario": {
    "id": 25,
    "title": "My Custom E-commerce Launch",
    "description": "Customized version for my class",
    "difficulty_level": "beginner",
    "estimated_duration": 45,
    "is_public": false,
    "created_at": "2025-01-06T12:00:00Z"
  }
}
```

### Create Scenario Review

**`POST /api/scenarios/{scenario_id}/reviews`** 🔒

Create a review for a scenario.

**Request Body:**
```json
{
  "rating": 5,
  "title": "Excellent simulation for strategic thinking",
  "review_text": "This simulation really helped my students understand complex business decisions. The AI personas were very realistic and engaging.",
  "helpful_aspects": [
    "Realistic business scenarios",
    "Engaging AI interactions",
    "Clear learning objectives"
  ],
  "improvement_suggestions": [
    "Could use more visual aids",
    "Additional hints for beginners"
  ]
}
```

**Response:**
```json
{
  "id": 15,
  "scenario_id": 1,
  "reviewer_id": 3,
  "rating": 5,
  "title": "Excellent simulation for strategic thinking",
  "review_text": "This simulation really helped my students understand complex business decisions...",
  "helpful_count": 0,
  "is_verified": true,
  "created_at": "2025-01-06T12:00:00Z"
}
```

### Get Scenario Reviews

**`GET /api/scenarios/{scenario_id}/reviews`**

Get reviews for a specific scenario.

**Query Parameters:**
- `page` (integer, optional) - Page number (default: 1)
- `page_size` (integer, optional) - Items per page (default: 10)
- `sort_by` (string, optional) - Sort by: rating, helpful, created_at (default: created_at)
- `sort_order` (string, optional) - Sort order: asc, desc (default: desc)

**Response:**
```json
{
  "reviews": [
    {
      "id": 15,
      "rating": 5,
      "title": "Excellent simulation for strategic thinking",
      "review_text": "This simulation really helped my students...",
      "helpful_count": 8,
      "is_verified": true,
      "reviewer": {
        "id": 3,
        "username": "prof_smith",
        "full_name": "Dr. John Smith"
      },
      "created_at": "2025-01-06T12:00:00Z"
    }
  ],
  "total": 23,
  "page": 1,
  "page_size": 10,
  "total_pages": 3,
  "average_rating": 4.5,
  "rating_distribution": {
    "5": 12,
    "4": 8,
    "3": 2,
    "2": 1,
    "1": 0
  }
}
```

---

## 🔧 System Endpoints

### Health Check

**`GET /health/`**

Check the system health and status.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-01-06T12:00:00Z",
  "framework": "FastAPI",
  "platform": "AI Agent Education Platform",
  "version": "2.0.0",
  "database": "connected",
  "ai_services": {
    "openai": "connected",
    "llamaparse": "connected"
  },
  "performance": {
    "response_time_ms": 45,
    "memory_usage_mb": 256,
    "cpu_usage_percent": 12.5
  }
}
```

### Root Endpoint

**`GET /`**

Get basic API information.

**Response:**
```json
{
  "message": "AI Agent Education Platform - PDF to Simulation Pipeline",
  "version": "2.0.0",
  "status": "active",
  "features": [
    "PDF Processing with AI Analysis",
    "Linear Simulation with ChatOrchestrator",
    "Multi-Scene Progression",
    "AI Persona Interactions",
    "Marketplace Publishing",
    "LangChain Integration",
    "Vector Store Service",
    "Session Management"
  ],
  "documentation": {
    "api_docs": "/docs",
    "redoc": "/redoc",
    "openapi_spec": "/openapi.json"
  }
}
```

### API Documentation

**`GET /docs`**

Interactive API documentation (Swagger UI).

**`GET /redoc`**

Alternative API documentation (ReDoc).

**`GET /openapi.json`**

OpenAPI specification in JSON format.

---

## ❌ Error Handling

### Standard Error Response Format

```json
{
  "detail": "Error description",
  "error_code": "SPECIFIC_ERROR_CODE",
  "timestamp": "2025-01-06T12:00:00Z",
  "request_id": "req_123456789",
  "path": "/api/simulation/start",
  "method": "POST"
}
```

### Common HTTP Status Codes

- **200** - Success
- **201** - Created
- **400** - Bad Request (validation error, missing file)
- **401** - Unauthorized (authentication required)
- **403** - Forbidden (insufficient permissions)
- **404** - Not Found (scenario, user, scene not found)
- **422** - Unprocessable Entity (request format error)
- **429** - Too Many Requests (rate limit exceeded)
- **500** - Internal Server Error (AI processing, database error)

### Specific Error Examples

**PDF Processing Error (500):**
```json
{
  "detail": "Failed to parse PDF: LlamaParse service unavailable",
  "error_code": "PDF_PROCESSING_ERROR",
  "timestamp": "2025-01-06T12:00:00Z",
  "request_id": "req_123456789"
}
```

**Simulation Not Found (404):**
```json
{
  "detail": "No active simulation found for user",
  "error_code": "SIMULATION_NOT_FOUND",
  "timestamp": "2025-01-06T12:00:00Z",
  "request_id": "req_123456789"
}
```

**Validation Error (422):**
```json
{
  "detail": [
    {
      "loc": ["body", "scenario_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ],
  "error_code": "VALIDATION_ERROR",
  "timestamp": "2025-01-06T12:00:00Z",
  "request_id": "req_123456789"
}
```

**Rate Limit Exceeded (429):**
```json
{
  "detail": "Rate limit exceeded. Try again in 60 seconds.",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "timestamp": "2025-01-06T12:00:00Z",
  "request_id": "req_123456789",
  "retry_after": 60
}
```

---

## 🚦 Rate Limiting

### Default Limits

- **PDF Processing:** 5 uploads per hour per user
- **Simulation endpoints:** 100 requests per minute per user
- **Chat endpoints:** 60 messages per minute per simulation
- **General API endpoints:** 1000 requests per hour per user
- **Authentication endpoints:** 10 attempts per minute per IP

### Rate Limit Headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1625097600
X-RateLimit-Retry-After: 60
```

### Rate Limit Response

```json
{
  "detail": "Rate limit exceeded",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "retry_after": 60,
  "limit": 100,
  "remaining": 0,
  "reset_time": "2025-01-06T13:00:00Z"
}
```

---

## 📚 Integration Examples

### Python SDK Example

```python
import requests

class AIEducationClient:
    def __init__(self, base_url="http://localhost:8000", token=None):
        self.base_url = base_url
        self.token = token
        self.session = requests.Session()
        if token:
            self.session.headers.update({
                'Authorization': f'Bearer {token}'
            })
    
    def upload_pdf_case_study(self, pdf_path, save_to_db=True):
        """Upload and process PDF case study"""
        with open(pdf_path, 'rb') as f:
            files = {'file': f}
            data = {'save_to_db': save_to_db, 'user_id': 1}
            response = self.session.post(
                f'{self.base_url}/api/parse-pdf/',
                files=files,
                data=data
            )
        return response.json()
    
    def start_linear_simulation(self, scenario_id, user_id=1):
        """Start a new linear simulation"""
        return self.session.post(
            f'{self.base_url}/api/simulation/start',
            json={
                'scenario_id': scenario_id,
                'user_id': user_id
            }
        ).json()
    
    def chat_with_orchestrator(self, scenario_id, user_id, scene_id, message):
        """Send message to ChatOrchestrator"""
        return self.session.post(
            f'{self.base_url}/api/simulation/linear-chat',
            json={
                'scenario_id': scenario_id,
                'user_id': user_id,
                'scene_id': scene_id,
                'message': message
            }
        ).json()

# Usage Example
client = AIEducationClient()

# 1. Upload and process PDF case study
pdf_result = client.upload_pdf_case_study('harvard_case.pdf', save_to_db=True)
scenario_id = pdf_result['scenario_id']

# 2. Start linear simulation
simulation = client.start_linear_simulation(scenario_id)
scene_id = simulation['current_scene']['id']

# 3. Begin simulation
begin_response = client.chat_with_orchestrator(
    scenario_id, 1, scene_id, "begin"
)

# 4. Interact with personas
response = client.chat_with_orchestrator(
    scenario_id, 1, scene_id, "@john_smith What are the main challenges?"
)

print(response['message'])
```

### JavaScript/Node.js Example

```javascript
class AIEducationClient {
  constructor(baseUrl = 'http://localhost:8000', token = null) {
    this.baseUrl = baseUrl;
    this.token = token;
  }

  async uploadPDFCaseStudy(pdfFile, saveToDb = true) {
    const formData = new FormData();
    formData.append('file', pdfFile);
    formData.append('save_to_db', saveToDb);
    formData.append('user_id', '1');

    const response = await fetch(`${this.baseUrl}/api/parse-pdf/`, {
      method: 'POST',
      body: formData,
      headers: this.token ? { Authorization: `Bearer ${this.token}` } : {}
    });
    return response.json();
  }

  async startLinearSimulation(scenarioId, userId = 1) {
    const response = await fetch(`${this.baseUrl}/api/simulation/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(this.token && { Authorization: `Bearer ${this.token}` })
      },
      body: JSON.stringify({
        scenario_id: scenarioId,
        user_id: userId
      })
    });
    return response.json();
  }

  async chatWithOrchestrator(scenarioId, userId, sceneId, message) {
    const response = await fetch(`${this.baseUrl}/api/simulation/linear-chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(this.token && { Authorization: `Bearer ${this.token}` })
      },
      body: JSON.stringify({
        scenario_id: scenarioId,
        user_id: userId,
        scene_id: sceneId,
        message: message
      })
    });
    return response.json();
  }
}

// Usage Example
const client = new AIEducationClient();

// Upload PDF and start simulation
const pdfFile = document.getElementById('pdf-input').files[0];
const pdfResult = await client.uploadPDFCaseStudy(pdfFile, true);
const scenarioId = pdfResult.scenario_id;

const simulation = await client.startLinearSimulation(scenarioId);
const sceneId = simulation.current_scene.id;

// Begin and interact
const beginResponse = await client.chatWithOrchestrator(
  scenarioId, 1, sceneId, "begin"
);

const chatResponse = await client.chatWithOrchestrator(
  scenarioId, 1, sceneId, "@john_smith What should be our first priority?"
);

console.log(chatResponse.message);
```

---

## 🔄 Changelog

### Version 2.0.0 (Current)
- ✅ **ChatOrchestrator Integration** - Linear simulation flow with multi-scene progression
- ✅ **PDF-to-Simulation Pipeline** - AI-powered case study processing
- ✅ **Enhanced Persona System** - Rich AI character interactions with personality traits
- ✅ **Scene Management** - Visual scene progression with AI-generated images
- ✅ **Publishing System** - Marketplace for sharing scenarios
- ✅ **LangChain Integration** - Advanced AI agent orchestration framework
- ✅ **Vector Store Service** - Semantic search and memory management
- ✅ **Session Management** - Persistent conversation state and memory
- ✅ **Specialized AI Agents** - Persona, Summarization, and Grading agents
- ✅ **Enhanced API Documentation** - Comprehensive endpoint documentation
- ✅ **Improved Error Handling** - Detailed error responses and logging

### Version 1.0.0 (Legacy)
- Basic agent and scenario management
- Simple simulation execution
- User authentication and profiles

---

## 📞 Support

For API support and questions:
- **Documentation:** [GitHub Repository](https://github.com/amybihag/forked-ai-agent-education-platform)
- **Issues:** Create an issue on GitHub
- **API Testing:** Use the interactive docs at `/docs`

---

**Legend:**
- 🔒 = Authentication required
- 📄 = File upload required
- 🤖 = AI processing involved
- ⚡ = Real-time response