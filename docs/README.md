# 🎓 AI Agent Education Platform

An innovative educational platform that transforms business case studies into immersive AI-powered simulations. Upload PDF case studies, let AI extract key figures and scenarios, then engage students in **linear simulation experiences** with dynamic **ChatOrchestrator** system and intelligent **AI persona interactions**.

![AI Agent Education Platform](https://img.shields.io/badge/AI-Education-blue?style=for-the-badge)
![Next.js](https://img.shields.io/badge/Next.js%2015-TypeScript-000000?style=for-the-badge&logo=nextdotjs)
![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688?style=for-the-badge&logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-316192?style=for-the-badge&logo=postgresql)
![Alembic](https://img.shields.io/badge/Alembic-Migrations-009688?style=for-the-badge)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991?style=for-the-badge&logo=openai)

## 🌟 Features

### 📄 **PDF-to-Simulation Pipeline**
- **Intelligent PDF Processing**: Upload Harvard Business Review cases or any business case study PDF
- **AI Content Analysis**: LlamaParse + OpenAI GPT-4 extract scenarios, key figures, and learning objectives
- **Automatic Persona Generation**: AI creates realistic business personas with personality traits and backgrounds
- **Scene Creation**: Generate sequential learning scenes with clear objectives and visual imagery

### 🎭 **ChatOrchestrator System**
- **Linear Simulation Flow**: Structured multi-scene progression with clear learning objectives
- **AI Persona Interactions**: Dynamic conversations with AI characters based on personality traits
- **Smart Command System**: Built-in commands (`begin`, `help`, `@mentions`) for natural interaction
- **Adaptive Difficulty**: Intelligent hint system and scene progression based on student performance

### 🎮 **Immersive Learning Experiences**
- **Multi-Scene Progression**: Students advance through carefully designed business scenarios
- **Goal-Oriented Learning**: Each scene has specific objectives and success criteria
- **Real-Time Feedback**: AI assesses understanding and provides contextual hints
- **Progress Tracking**: Comprehensive analytics on learning outcomes and engagement

### 🤖 **Advanced AI Agent System**
- **LangChain Integration**: Professional AI agent orchestration framework
- **Specialized Agents**: Dedicated agents for personas, summarization, and grading
- **Vector Memory**: Semantic search and persistent memory across sessions
- **Session Management**: Intelligent session state and conversation history
- **Context Awareness**: Agents maintain context across multiple interactions

### 🏪 **Community Marketplace**
- **Scenario Sharing**: Publish successful simulations for the educational community
- **Content Discovery**: Browse scenarios by industry, difficulty, and user ratings
- **Remix & Customize**: Clone and adapt existing scenarios for specific needs
- **Quality Assurance**: Community ratings and reviews ensure high-quality content

### 👥 **Cohort Management System**
- **Educational Groups**: Create and manage student cohorts for organized learning
- **Student Enrollment**: Invite students and manage enrollment with approval workflows
- **Simulation Assignment**: Assign specific simulations to cohorts with due dates
- **Progress Tracking**: Monitor student progress and completion across cohorts
- **Cohort Analytics**: Comprehensive metrics and performance insights

### 🎨 **Modern UI/UX**
- **Next.js 15 with TypeScript**: Latest version with App Router for optimal performance
- **Tailwind CSS + shadcn/ui**: Professional, accessible component library with dark/light mode
- **Responsive Design**: Seamless experience across desktop, tablet, and mobile
- **Real-Time Chat Interface**: Immersive conversation experience with AI personas

## 🏗️ Architecture

```mermaid
graph TB
    A[Next.js Frontend] --> B[FastAPI Backend]
    B --> C[PostgreSQL Database]
    B --> D[Alembic Migrations]
    B --> E[OpenAI GPT-4]
    B --> F[LlamaParse API]
    B --> G[ChatOrchestrator]
    B --> H[LangChain Integration]
    
    subgraph "Frontend (Next.js + TypeScript)"
        I[PDF Upload Interface]
        J[Simulation Builder]
        K[Chat-Box Experience]
        L[Marketplace]
    end
    
    subgraph "Backend (FastAPI + Python)"
        M[PDF Processing API]
        N[Linear Simulation API]
        O[ChatOrchestrator Engine]
        P[Publishing System]
        Q[Agent Services]
        R[Session Management]
        S[Vector Store]
    end
    
    subgraph "AI Processing Layer"
        T[PDF Analysis]
        U[Persona Generation]
        V[Scene Creation]
        W[Image Generation]
        X[LangChain Agents]
        Y[Vector Embeddings]
    end
    
    subgraph "New Services"
        Z[Persona Agent]
        AA[Summarization Agent]
        BB[Grading Agent]
        CC[Session Manager]
        DD[Vector Store Service]
        EE[Scene Memory]
    end
```

## 🗄️ Database & Migrations

### **PostgreSQL with Alembic**
- **Primary Database**: PostgreSQL for all environments (development and production)
- **Migration Management**: Alembic for professional database version control
- **Development**: PostgreSQL for consistent development experience
- **Schema Management**: Automated migrations with rollback support
- **SQLite Support**: Available only when explicitly configured for development

### **Key Features**
- ✅ **Professional Migrations**: Alembic replaces custom migration scripts
- ✅ **PostgreSQL First**: Optimized for PostgreSQL with fallback to SQLite
- ✅ **Team Collaboration**: Consistent database state across all environments
- ✅ **Production Ready**: Optimized indexes and connection pooling
- ✅ **Development Flexibility**: SQLite available when explicitly configured
- ✅ **Soft Deletion**: Safe deletion with data archiving and recovery capabilities
- ✅ **Cohort Management**: Full educational group management with student tracking

## 🚀 Quick Start

### Prerequisites
- **Node.js** (v18 or higher)
- **Python** (3.11 or higher)
- **PostgreSQL** (for database)
- **Git**
- **OpenAI API Key** (for ChatOrchestrator and content generation)
- **LlamaParse API Key** (for PDF processing)

> **Note**: PostgreSQL is the primary database. SQLite is available only when explicitly configured for development.

### 5-Minute Setup

#### ⚠️ **IMPORTANT: Virtual Environment Required**
**You MUST create a virtual environment before starting the backend. This is NOT automatic.**

#### 🚀 **Quick Setup (Recommended)**

```bash
# 1. Create and activate virtual environment (REQUIRED)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Clone and setup
git clone <repository-url>
cd ai-agent-education-platform

# 3. Start the backend - setup happens automatically!
cd backend
uvicorn main:app --reload
# The backend will automatically:
# - Install PostgreSQL (if needed)
# - Install Python dependencies
# - Create database and user
# - Set up .env file
# - Run database migrations

# 4. Edit .env file with your API keys (after first run)
# OPENAI_API_KEY=your_openai_api_key
# LLAMAPARSE_API_KEY=your_llamaparse_api_key
```

#### 🤖 **What's Automatic vs Manual**

**Manual (You Must Do):**
- ✅ **Create virtual environment** (python -m venv venv)
- ✅ **Activate virtual environment** (source venv/bin/activate)
- ✅ **Add API keys to .env file** (after first run)

**Automatic (Platform Handles):**
- ✅ Install PostgreSQL (if needed)
- ✅ Install Python dependencies
- ✅ Create database and user
- ✅ Set up .env file from template
- ✅ Run database migrations

#### 🔧 **Manual Setup (Alternative)**

```bash
# 1. Clone and setup
git clone <repository-url>
cd ai-agent-education-platform

# 2. Create and activate virtual environment (REQUIRED)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp env_template.txt .env
# Edit .env with your API keys

# 5. Start the application
cd backend
uvicorn main:app --reload
```

**Access Points:**
- 🌐 **Frontend**: http://localhost:3000 (run `cd frontend && npm run dev`)
- 🔧 **Backend API**: http://localhost:8000
- 📚 **API Docs**: http://localhost:8000/docs
- 🗄️ **Database Admin**: http://localhost:5001 (run `cd backend/db_admin && python simple_viewer.py`)

### Detailed Setup

#### 1. Clone the Repository
```bash
git clone https://github.com/HendrikKrack/ai-agent-education-platform.git
cd ai-agent-education-platform
```

#### 2. Backend Setup
```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies (from root directory)
pip install -r requirements.txt

# Set up environment variables (from root directory)
cp env_template.txt .env
# Edit .env with your API keys:
# OPENAI_API_KEY=your_openai_api_key
# LLAMAPARSE_API_KEY=your_llamaparse_api_key
# DATABASE_URL=sqlite:///./backend/ai_agent_platform.db

# Initialize database using Alembic migrations
cd backend/database
alembic upgrade head
cd ..

# Start the backend server
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

The backend will be available at **http://localhost:8000**

#### 3. Frontend Setup
```bash
# Navigate to frontend directory (in a new terminal)
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend will be available at **http://localhost:3000**

**Note**: The frontend has been restructured to use Next.js 15 with App Router, TypeScript, and shadcn/ui components.

## 🔧 Environment Configuration

### Backend (.env)
```env
# Database Configuration (PostgreSQL - primary database)
DATABASE_URL=postgresql://username:password@localhost:5432/ai_agent_platform

# AI Service API Keys
OPENAI_API_KEY=your_openai_api_key_here
LLAMAPARSE_API_KEY=your_llamaparse_api_key_here

# Application Settings
SECRET_KEY=your_secret_key_here
ENVIRONMENT=development
DEBUG=true

# Optional: Image Generation
DALLE_API_KEY=your_dalle_api_key_here
```

### Database Setup
1. PostgreSQL database is the primary database for all environments
2. Tables are created automatically using Alembic migrations
3. For manual setup, run `alembic upgrade head` in the backend/database directory
4. The system will automatically create default scenarios
5. The .env file is located at the project root and is read by all components

## 🔐 Google OAuth Setup

The platform supports Google OAuth for user authentication. Follow these steps to get your Google OAuth credentials:

### 1. Google Cloud Console Setup

1. **Go to Google Cloud Console**: https://console.cloud.google.com/
2. **Create a new project** or select an existing one
3. **Configure OAuth consent screen**:
   - Go to "APIs & Services" > "OAuth consent screen"
   - Set up scopes (openid, email, profile) and test users (if internal)
4. **Create OAuth 2.0 Client ID (Google Identity Services)**:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth 2.0 Client IDs"
   - Choose "Web application"
   - Add authorized redirect URIs:
     - `http://localhost:8000/auth/google/callback` (backend callback, dev)
     - `https://yourdomain.com/auth/google/callback` (backend callback, prod)
   - (Optional) Enable People API only if you call it explicitly

### 2. Get Your Credentials

After creating the OAuth 2.0 Client ID, you'll get:
- **Client ID**: Something like `123456789-abcdefg.apps.googleusercontent.com`
- **Client Secret**: Something like `GOCSPX-abcdefghijklmnop`

### 3. Configure Your Application

Set these environment variables when starting your backend:

```bash
GOOGLE_CLIENT_ID="your_actual_client_id_here"
GOOGLE_CLIENT_SECRET="your_actual_client_secret_here"
GOOGLE_REDIRECT_URI="your_authorized_redirect_uri"
```

**Important**: Set your Google Cloud Console redirect URI to:
- `http://localhost:8000/auth/google/callback` (development FastAPI)

### 🔒 Security Note

**Never commit OAuth credentials to version control!** Always use environment variables or a secure secrets management system for production deployments. The `.env` file should be excluded from version control (it's already in `.gitignore`). For production, consider using services like AWS Secrets Manager, Azure Key Vault, or similar secure credential storage solutions.

### 4. Testing

Once configured:
1. Start your backend and frontend
2. Go to `http://localhost:3000`
3. Click "Login with Google"
4. Complete the OAuth flow
5. You should be redirected to the dashboard


## 📚 API Documentation

Once the backend is running, visit:
- **Interactive API Docs**: http://localhost:8000/docs
- **ReDoc Documentation**: http://localhost:8000/redoc

### Key Endpoints
```
# PDF Processing & Scenario Creation
POST /api/parse-pdf/                    # Upload and process PDF case study
GET  /scenarios/                        # List all scenarios
GET  /scenarios/{id}                    # Get scenario with personas and scenes

# Linear Simulation System
POST /api/simulation/start              # Initialize ChatOrchestrator simulation
POST /api/simulation/linear-chat        # Chat with AI personas in simulation

# Legacy Business Simulation
POST /api/simulate/                     # Phase-based business simulation

# Community Marketplace
POST /api/publishing/publish-scenario   # Publish scenario to marketplace
GET  /api/publishing/marketplace        # Browse published scenarios

# Cohort Management
GET  /cohorts/                          # List all cohorts
POST /cohorts/                          # Create new cohort
GET  /cohorts/{id}                      # Get cohort details
PUT  /cohorts/{id}                      # Update cohort
DELETE /cohorts/{id}                    # Delete cohort
GET  /cohorts/{id}/students             # Get cohort students
POST /cohorts/{id}/students             # Add student to cohort
GET  /cohorts/{id}/simulations          # Get cohort simulations
POST /cohorts/{id}/simulations          # Assign simulation to cohort

# Soft Deletion & Data Management
POST /api/scenarios/{id}/soft-delete    # Soft delete scenario
POST /api/scenarios/{id}/restore        # Restore soft-deleted scenario
GET  /api/archives/stats                # Get archive statistics

# System Health
GET  /health/                           # System health check
```

## 🎓 Usage Guide

### For Educators

1. **Upload Business Case Study**
   - Upload PDF case studies (Harvard Business Review, custom cases)
   - AI automatically extracts scenarios, key figures, and learning objectives
   - Review and customize generated personas and scenes

2. **Create and Manage Cohorts**
   - Create educational cohorts for organized student groups
   - Invite students and manage enrollment with approval workflows
   - Assign specific simulations to cohorts with due dates
   - Monitor cohort progress and analytics

3. **Launch Linear Simulation**
   - Students progress through structured scenes with clear objectives
   - ChatOrchestrator manages multi-persona interactions
   - Monitor student progress and learning outcomes

4. **Publish to Community**
   - Share successful scenarios with other educators
   - Set difficulty levels, categories, and learning objectives
   - Receive community feedback and ratings

### For Students

1. **Start Simulation Experience**
   - Review scenario overview and learning objectives
   - Understand your role in the business challenge
   - Meet AI personas and their backgrounds

2. **Engage with ChatOrchestrator**
   - Type `begin` to start the simulation
   - Use `@mentions` to interact with specific personas
   - Type `help` for available commands and guidance

3. **Progress Through Scenes**
   - Complete objectives in each scene to advance
   - Receive real-time feedback and hints
   - Build understanding through natural conversation

### Example Simulation Flow
```
Student: begin
ChatOrchestrator: Welcome to KasKazi Network Strategic Challenge...

Student: @john_smith What are your main concerns about seasonal contracts?
John Smith: As the founder, I'm deeply concerned about our revenue gaps...

Student: What alternatives have you considered?
ChatOrchestrator: [Multiple personas respond with different perspectives]

Student: help
ChatOrchestrator: Available commands: @mention, progress, hint...
```

## 🛠️ Technology Stack

### Frontend
- **Next.js 15** with TypeScript and App Router
- **Tailwind CSS** for utility-first styling with dark/light mode
- **shadcn/ui** for modern, accessible components
- **React Hook Form + Zod** for form management and validation
- **Next Themes** for theme management

### Backend
- **FastAPI** with async Python for high performance
- **SQLAlchemy** ORM with PostgreSQL
- **Pydantic** for data validation and serialization
- **Uvicorn** ASGI server with hot reloading

### AI Services
- **OpenAI GPT-4** for ChatOrchestrator and content generation
- **LlamaParse** for advanced PDF processing and content extraction
- **AI Image Generation** for scene visualization
- **Custom ChatOrchestrator** for linear simulation management
- **LangChain Integration** for advanced AI agent orchestration
- **Vector Embeddings** for semantic search and memory
- **Specialized AI Agents** (Persona, Summarization, Grading)

### Database
- **PostgreSQL** for all environments (development and production)
- **Alembic** for professional database migrations
- **SQLAlchemy ORM** for database abstraction
- **SQLite** available only when explicitly configured

## 📁 Project Structure

```
ai-agent-education-platform/
├── backend/                          # FastAPI + SQLAlchemy backend
│   ├── main.py                       # FastAPI application entry point
│   ├── api/                          # API endpoints
│   │   ├── parse_pdf.py             # PDF processing endpoints
│   │   ├── simulation.py            # Linear simulation endpoints
│   │   ├── chat_orchestrator.py     # ChatOrchestrator logic
│   │   ├── publishing.py            # Marketplace publishing
│   │   └── cohorts.py               # Cohort management endpoints
│   ├── agents/                       # AI Agent implementations
│   │   ├── persona_agent.py         # Persona-specific AI interactions
│   │   ├── summarization_agent.py   # Content summarization agent
│   │   └── grading_agent.py         # Assessment and grading agent
│   ├── database/                     # Database layer
│   │   ├── models.py                 # SQLAlchemy models (scenarios, personas, scenes, cohorts)
│   │   ├── schemas.py                # Pydantic schemas for API validation
│   │   ├── connection.py             # Database connection setup
│   │   └── migrations/               # Alembic migration files
│   ├── services/                     # Business logic layer
│   │   ├── simulation_engine.py     # Core simulation business logic
│   │   ├── session_manager.py       # Session and memory management
│   │   ├── vector_store.py          # Vector embeddings and search
│   │   ├── scene_memory.py          # Scene-specific memory handling
│   │   └── soft_deletion.py         # Soft deletion and data archiving
│   ├── utilities/                    # Helper utilities
│   │   ├── auth.py                   # Authentication utilities
│   │   └── image_storage.py          # Image handling utilities
│   ├── langchain_config.py          # LangChain configuration and setup
│   ├── startup_check.py             # Application startup validation
│   ├── setup_dev_environment.py     # Development environment setup
│   ├── clear_database.py            # Database cleanup utilities
│   ├── db_admin/                     # Database administration tools
│   └── static/                      # Static files
├── frontend/                         # Next.js + TypeScript frontend
│   ├── app/                          # Next.js app router pages
│   │   ├── chat-box/                # Interactive chat interface
│   │   ├── simulation-builder/      # PDF upload and simulation creation
│   │   ├── dashboard/               # User progress and analytics
│   │   ├── cohorts/                 # Cohort management interface
│   │   ├── cohorts/[id]/           # Individual cohort details
│   │   ├── login/                   # Authentication pages
│   │   ├── signup/                  # User registration
│   │   ├── layout.tsx               # Root layout component
│   │   ├── page.tsx                 # Home page
│   │   └── globals.css              # Global styles
│   ├── components/                   # React components
│   │   ├── ui/                      # shadcn/ui components
│   │   ├── PersonaCard.tsx          # AI persona display components
│   │   ├── SceneCard.tsx            # Scene progression UI
│   │   └── theme-provider.tsx       # Theme context provider
│   ├── lib/                         # Utility functions and API clients
│   │   ├── api.ts                   # API client functions
│   │   ├── auth-context.tsx         # Authentication context
│   │   └── utils.ts                 # Utility functions
│   ├── hooks/                       # Custom React hooks
│   └── public/                      # Static assets
├── .env                              # Environment variables (create from template)
├── .gitignore                        # Git ignore rules (consolidated)
├── env_template.txt                  # Environment variables template
├── requirements.txt                  # All Python dependencies
├── docs/                             # Comprehensive documentation
│   ├── README.md                     # Main project documentation
│   ├── QUICK_START.md               # Quick setup guide
│   ├── API_Reference.md             # Complete API documentation
│   ├── Developer_Guide.md           # Development guide
│   └── architecture/                # Architecture documentation
└── README.md                        # This file
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Workflow
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style
- **Python**: Follow PEP 8 with Black formatting and type hints
- **TypeScript**: Use Prettier with ESLint and strict TypeScript
- **Commits**: Use conventional commits format
- **Testing**: Write tests for new features and maintain 80%+ coverage

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🌟 Acknowledgments

- **OpenAI GPT-4** for powering intelligent ChatOrchestrator interactions
- **LlamaParse** for advanced PDF processing and content extraction
- **shadcn/ui** for beautiful, accessible React components
- **FastAPI** for high-performance async Python web framework
- **Next.js** for modern React development with server-side rendering

## 📞 Support

- **Quick Start Guide**: [QUICK_START.md](QUICK_START.md)
- **API Reference**: [API_Reference.md](API_Reference.md)
- **Developer Guide**: [Developer_Guide.md](Developer_Guide.md)
- **Architecture Documentation**: [architecture/](architecture/)
- **Issues**: [GitHub Issues](../../issues)
- **Discussions**: [GitHub Discussions](../../discussions)

## 🗺️ Roadmap

### Phase 1: Core Platform (✅ Complete)
- [x] **PDF-to-Simulation Pipeline** with AI processing
- [x] **ChatOrchestrator Integration** with linear simulation flow
- [x] **Multi-Scene Progression** with goal tracking
- [x] **Community Marketplace** with publishing system
- [x] **LangChain Integration** with advanced AI agents
- [x] **Vector Store Service** for semantic search and memory
- [x] **Session Management** with persistent memory
- [x] **Specialized AI Agents** (Persona, Summarization, Grading)
- [x] **Cohort Management System** with student enrollment and tracking
- [x] **Soft Deletion System** with data archiving and recovery

### Phase 2: Enhanced Learning (🚧 In Progress)
- [ ] **Advanced Analytics Dashboard** for educators
- [ ] **Learning Outcome Assessment** with AI evaluation
- [ ] **Multi-User Simulations** for collaborative learning
- [ ] **Voice Interaction** with AI personas

### Phase 3: Enterprise Features (🔮 Planned)
- [ ] **LMS Integration** (Canvas, Blackboard, Moodle)
- [ ] **SSO Authentication** for institutional use
- [ ] **White-Label Solutions** for educational institutions
- [ ] **Mobile Native Apps** (iOS/Android)

### Phase 4: Advanced AI (🔮 Future)
- [ ] **Custom Model Training** for domain-specific scenarios
- [ ] **VR/AR Integration** for immersive experiences
- [ ] **Multi-Language Support** with i18n
- [ ] **Real-Time Collaboration** with WebRTC

---

<div align="center">

**[⭐ Star this repository](../../stargazers) • [🐛 Report Bug](../../issues) • [✨ Request Feature](../../issues)**

**Transform business education with AI-powered simulations**

Made with ❤️ for educators and students worldwide

</div> 