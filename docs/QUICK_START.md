# 🚀 Quick Start Guide

## Prerequisites
- **Python 3.11+** (recommended: 3.11 or higher)
- **Node.js 18+** (recommended: 18 or higher)
- **Git**
- **OpenAI API Key** (for AI features)
- **LlamaParse API Key** (for PDF processing)
- **PostgreSQL** (primary database)
- **Redis** (optional, for caching)

### Database Options

**Option 1: SQLite (Easiest - No Installation Required)**
- SQLite is included with Python
- Just set `DATABASE_URL=sqlite:///./ai_agent_platform.db` in your `.env`
- Perfect for development and testing

**Option 2: PostgreSQL (Production-Ready)**
- Requires separate PostgreSQL server installation
- Better for production and team collaboration
- Set `DATABASE_URL=postgresql://username:password@localhost:5432/ai_agent_platform`

### PostgreSQL Installation by OS (Only if using Option 2)

**🔄 Automatic Installation (Recommended):**
The setup script can automatically install PostgreSQL on all supported platforms:

```bash
# Run the setup script - it will detect your OS and install PostgreSQL automatically
python backend/setup_dev_environment.py
```

**Manual Installation (Alternative):**

**Windows:**
```bash
# Option 1: Download installer
# Visit: https://www.postgresql.org/download/windows/

# Option 2: Using winget (Windows 10/11)
winget install PostgreSQL.PostgreSQL

# Option 3: Using Chocolatey
choco install postgresql
```

**macOS:**
```bash
# Option 1: Using Homebrew
brew install postgresql
brew services start postgresql

# Option 2: Download installer
# Visit: https://www.postgresql.org/download/macosx/
```

**Linux (Ubuntu/Debian):**
```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Linux (CentOS/RHEL/Fedora):**
```bash
# CentOS/RHEL
sudo yum install postgresql-server postgresql-contrib
sudo postgresql-setup initdb
sudo systemctl start postgresql

# Fedora
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup initdb
sudo systemctl start postgresql
```

**Linux (Arch):**
```bash
# Update package database
sudo pacman -Sy

# Install PostgreSQL
sudo pacman -S postgresql

# Initialize database
sudo -u postgres initdb -D /var/lib/postgres/data

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

## Complete Setup (5 minutes)

### ⚠️ **IMPORTANT: UV Required**
**You MUST install UV before starting the backend. UV will automatically create and manage the virtual environment.**

### 📦 **Step 1: Install UV Package Manager**

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc  # or source ~/.bashrc for bash users
```

**Windows (PowerShell - Run as Administrator):**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Windows (CMD - Run as Administrator):**
```cmd
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Verify Installation:**
```bash
uv --version
# Should show: uv 0.9.3 or higher
```

### 🚀 **Step 2: Clone and Setup Project**

**macOS/Linux:**
```bash
# Clone repository
git clone <repository-url>
cd n-aible_edtech_sims

# Navigate to backend
cd backend

# Install dependencies (creates virtual environment automatically)
uv sync

# Set up environment variables
cp ../env_template.txt .env

# Edit .env file with your API keys
# OPENAI_API_KEY=your_openai_api_key
# ANTHROPIC_API_KEY=your_anthropic_api_key
```

**Windows (PowerShell):**
```powershell
# Clone repository
git clone <repository-url>
cd n-aible_edtech_sims

# Navigate to backend
cd backend

# Install dependencies (creates virtual environment automatically)
uv sync

# Set up environment variables
Copy-Item ..\env_template.txt .env

# Edit .env file with your API keys
# OPENAI_API_KEY=your_openai_api_key
# ANTHROPIC_API_KEY=your_anthropic_api_key
```

**Windows (CMD):**
```cmd
# Clone repository
git clone <repository-url>
cd n-aible_edtech_sims

# Navigate to backend
cd backend

# Install dependencies (creates virtual environment automatically)
uv sync

# Set up environment variables
copy ..\env_template.txt .env

# Edit .env file with your API keys
REM OPENAI_API_KEY=your_openai_api_key
REM ANTHROPIC_API_KEY=your_anthropic_api_key
```

### 🗄️ **Step 3: Initialize Database**

**Option A: Using `uv run` (Recommended - No activation needed)**

Works the same on **macOS/Linux/Windows**:
```bash
# Navigate to database directory
cd database

# Run migrations with uv run
uv run alembic upgrade head

# Navigate back to backend directory
cd ..

# Start the backend server
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Option B: Activate Virtual Environment First**

**macOS/Linux:**
```bash
# Activate virtual environment
source .venv/bin/activate

# Navigate to database directory
cd database

# Run migrations
alembic upgrade head

# Navigate back
cd ..

# Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Windows (PowerShell):**
```powershell
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Navigate to database directory
cd database

# Run migrations
alembic upgrade head

# Navigate back
cd ..

# Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Windows (CMD):**
```cmd
# Activate virtual environment
.venv\Scripts\activate.bat

# Navigate to database directory
cd database

# Run migrations
alembic upgrade head

# Navigate back
cd ..

# Start server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 🎨 **Step 4: Start Frontend (New Terminal)**

**macOS/Linux:**
```bash
cd frontend
pnpm install
pnpm dev
```

**Windows (PowerShell/CMD):**
```powershell
cd frontend
pnpm install
pnpm dev
```

### ✅ **Access Your Application**

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

### 🤖 **What's Manual vs Automatic**

**Manual Steps (You Must Do):**
- ✅ **Install UV** package manager
- ✅ **Run `uv sync`** to install dependencies
- ✅ **Add API keys** to .env file
- ✅ **Run database migrations** with alembic
- ✅ **Start servers** (backend and frontend)

**Automatic (UV Handles):**
- ✅ **Creates virtual environment** (.venv directory)
- ✅ **Installs Python dependencies** from pyproject.toml
- ✅ **Manages package versions** and compatibility

### 🔧 **Automatic Setup Behavior**

The platform includes **intelligent automatic setup** that runs when you first start the backend:

- **✅ Detects missing dependencies** (PostgreSQL, Python packages)
- **✅ Installs PostgreSQL automatically** (Windows, macOS, Linux)
- **✅ Creates database and user** with sensible defaults
- **✅ Sets up environment file** from template
- **✅ Runs database migrations** automatically
- **✅ Only runs once** (marked with completion flag)
- **✅ Non-interactive** (no user prompts needed)

**When automatic setup runs:**
- First time starting the backend
- Missing `.env` file
- Database connection fails
- Development environment (not production)

**To force re-setup:**
```bash
FORCE_SETUP=true python backend/main.py
```

> **💡 Pro Tip**: The setup runs automatically when you first start the backend! Just remember to create and activate your virtual environment first.

---

## 🔧 **Alternative: Using Virtual Environment Activation**

If you prefer to activate the virtual environment once and run commands directly (without `uv run` prefix):

**macOS/Linux:**
```bash
# From backend directory
source .venv/bin/activate

# Now you can run commands directly
cd database
alembic upgrade head
cd ..
uvicorn main:app --reload
```

**Windows (PowerShell):**
```powershell
# From backend directory
.venv\Scripts\Activate.ps1

# Now you can run commands directly
cd database
alembic upgrade head
cd ..
uvicorn main:app --reload
```

**Windows (CMD):**
```cmd
# From backend directory
.venv\Scripts\activate.bat

# Now you can run commands directly
cd database
alembic upgrade head
cd ..
uvicorn main:app --reload
```

**To deactivate:**
```bash
deactivate  # Works on all platforms
```

## Database Setup

### **PostgreSQL (Primary Database)**
The application uses PostgreSQL as the primary database for all environments.

**Local Development Setup:**
```bash
# Example for local PostgreSQL
DATABASE_URL=postgresql://username:password@localhost:5432/ai_agent_platform
```

**Production Setup:**
```bash
# Example for production PostgreSQL
DATABASE_URL=postgresql://username:password@hostname:5432/database_name?sslmode=require
```

### **SQLite (Optional Development)**
SQLite is available only when explicitly configured:
```bash
# Only use if you specifically want SQLite for development
DATABASE_URL=sqlite:///./ai_agent_platform.db
```

### **Database Migrations**
The project uses Alembic for database migrations:

```bash
# Navigate to database directory
cd backend/database

# Check current migration status
alembic current

# Apply all pending migrations
alembic upgrade head

# Create new migration (when you modify models)
alembic revision --autogenerate -m "Description of changes"

# View migration history
alembic history
```

## Backend Setup

> **Note**: Virtual environment setup is now covered in the main setup sections above. This section provides additional backend-specific details.

1. **Install dependencies:**
```bash
# From the backend directory
uv sync  # Creates virtual environment and installs dependencies
```

2. **Navigate to backend directory:**
```bash
cd backend
```

3. **Environment setup:**
```bash
# Copy template and edit with your API keys (from root directory)
cp env_template.txt .env

# Edit .env file with your API keys:
# OPENAI_API_KEY=your_openai_api_key_here
# LLAMAPARSE_API_KEY=your_llamaparse_api_key_here

# Database Configuration (choose one):
# DATABASE_URL=sqlite:///./ai_agent_platform.db  # Easiest (SQLite - no installation needed)
# DATABASE_URL=postgresql://username:password@localhost:5432/ai_agent_platform  # Production (PostgreSQL)

# LangChain Configuration (optional):
# LANGCHAIN_REDIS_URL=redis://localhost:6379/0  # For caching (optional)
# LANGCHAIN_EMBEDDING_MODEL=openai  # or huggingface
# LANGCHAIN_HUGGINGFACE_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

5. **Initialize database:**
```bash
# Navigate to database directory and run migrations
cd backend/database
alembic upgrade head
cd ..
```

6. **Start backend:**
```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Backend runs at: http://127.0.0.1:8000

## Frontend Setup

1. **Navigate to frontend (new terminal):**
```bash
cd frontend
```

2. **Install dependencies:**
```bash
npm install
```

3. **Start development server:**
```bash
npm run dev
```
Frontend runs at: http://localhost:3000

**Note**: The frontend is now built with Next.js 15, TypeScript, and Tailwind CSS with shadcn/ui components.

## Frontend Tech Stack

The frontend has been restructured and modernized with:

- **Next.js 15**: Latest version with App Router for optimal performance
- **TypeScript**: Full type safety throughout the application
- **Tailwind CSS**: Utility-first CSS framework for rapid UI development
- **shadcn/ui**: Modern, accessible component library built on Radix UI
- **React Hook Form + Zod**: Robust form handling with validation
- **Next Themes**: Dark/light mode support with system preference detection
- **Lucide React**: Beautiful, customizable icons

## Key Features
- **Simulation Builder**: Upload PDF case studies and create AI-driven business simulations
- **Chat Interface**: Interactive student-agent conversations with ChatOrchestrator
- **Marketplace**: Browse and publish educational scenarios
- **Dashboard**: Track learning progress and analytics

## API Documentation
Visit http://127.0.0.1:8000/docs for interactive API documentation.

## Common Issues

### General Issues
- **Virtual env not found**: Ensure you're in the backend directory when activating
- **Port conflicts**: Backend uses 8000, frontend uses 3000
- **Database issues**: Ensure PostgreSQL is running and DATABASE_URL is correctly configured
- **API key errors**: Ensure .env file is properly configured with valid API keys
- **Migration errors**: Run `alembic upgrade head` in backend/database directory

### OS-Specific Issues

**Windows:**
- **psycopg2 installation**: If you get compilation errors, install Microsoft Visual C++ Build Tools
- **PostgreSQL service**: Ensure PostgreSQL service is running in Services.msc
- **Path issues**: Use forward slashes in DATABASE_URL even on Windows

**macOS:**
- **Homebrew PostgreSQL**: If using Homebrew, ensure PostgreSQL is started with `brew services start postgresql`
- **Permission issues**: You may need to create a PostgreSQL user for your macOS username

**Linux:**
- **PostgreSQL service**: Ensure service is running with `sudo systemctl status postgresql`
- **Firewall**: Check if port 5432 is open for PostgreSQL connections
- **User permissions**: You may need to create a PostgreSQL user and database

## Project Structure
```
ai-agent-education-platform/
├── backend/                    # FastAPI + SQLAlchemy backend
│   ├── main.py                # Application entry point
│   ├── api/                   # API endpoints
│   │   ├── parse_pdf.py       # PDF processing
│   │   ├── simulation.py      # Simulation management
│   │   ├── chat_orchestrator.py # Chat system
│   │   └── publishing.py      # Marketplace features
│   ├── agents/                # AI Agent implementations
│   │   ├── persona_agent.py   # Persona-specific AI interactions
│   │   ├── summarization_agent.py # Content summarization
│   │   └── grading_agent.py   # Assessment and grading
│   ├── database/              # Database models and migrations
│   ├── services/              # Business logic
│   │   ├── simulation_engine.py # Core simulation logic
│   │   ├── session_manager.py # Session and memory management
│   │   ├── vector_store.py    # Vector embeddings and search
│   │   └── scene_memory.py    # Scene-specific memory
│   ├── utilities/             # Helper functions
│   ├── langchain_config.py    # LangChain configuration
│   ├── startup_check.py       # Application startup validation
│   ├── setup_dev_environment.py # Development setup
│   ├── clear_database.py      # Database cleanup utilities
│   ├── db_admin/              # Database admin interface
│   └── docs/                  # API documentation
├── frontend/                  # Next.js + TypeScript frontend
│   ├── app/                   # Next.js app router pages
│   │   ├── simulation-builder/  # PDF upload and simulation creation
│   │   ├── chat-box/          # Interactive chat interface
│   │   ├── signup/           # User registration
│   │   ├── dashboard/         # User analytics
│   │   └── login/            # Authentication pages
│   ├── components/            # React components (shadcn/ui)
│   ├── lib/                   # Utilities and API clients
│   └── hooks/                 # Custom React hooks
├── .env                       # Environment variables (create from template)
├── .gitignore                 # Git ignore rules (consolidated)
├── requirements.txt           # Python dependencies
├── env_template.txt           # Environment variables template
├── README.md                  # Project documentation
├── QUICK_START.md             # This setup guide
├── CONTRIBUTING.md            # Contributor guidelines
└── LICENSE                    # MIT License
```

## Recent Improvements

### **Database & Migration System**
- ✅ **Alembic Integration**: Professional database migrations replacing custom scripts
- ✅ **PostgreSQL Support**: Production-ready database with optimized indexes
- ✅ **Cross-Database Compatibility**: Works with both SQLite (dev) and PostgreSQL (prod)
- ✅ **Migration Management**: Version control for database schema changes

### **LangChain Integration & AI Agents**
- ✅ **LangChain Framework**: Professional AI agent orchestration
- ✅ **Specialized Agents**: Persona, Summarization, and Grading agents
- ✅ **Vector Store Service**: Semantic search and memory with pgvector
- ✅ **Session Management**: Persistent conversation memory and state
- ✅ **Scene Memory**: Context-aware memory for simulation scenes

### **Project Structure Cleanup**
- ✅ **Clean Root Directory**: Removed outdated documentation and duplicate files
- ✅ **Organized Backend**: Streamlined file structure with clear separation of concerns
- ✅ **Updated Documentation**: Current and accurate setup guides
- ✅ **Professional Appearance**: Clean, maintainable codebase

### **OpenAI Integration**
- ✅ **Comprehensive AI Features**: PDF processing, persona generation, scene creation
- ✅ **Real-time Chat**: Interactive AI personas with personality traits
- ✅ **Assessment System**: AI-powered grading and feedback
- ✅ **Image Generation**: DALL-E integration for scene visualization

## Development Workflow

1. **Install Dependencies**: `pip install -r requirements.txt` (from root)
2. **Start Backend**: `cd backend && uvicorn main:app --reload`
3. **Start Frontend**: `cd frontend && npm run dev`
4. **Access Application**: http://localhost:3000
5. **API Docs**: http://localhost:8000/docs

## Optional: Database Admin Interface

The project includes a Flask-based database admin interface for viewing and managing the database:

```bash
# Start the database admin interface
cd backend/db_admin
python simple_viewer.py
```

Access at: http://localhost:5001

## Next Steps
- Upload a business case study PDF to test the simulation builder
- Create your first AI-powered simulation
- Create and manage your simulations
- Check out the comprehensive documentation in `backend/docs/`
- Use the database admin interface to inspect your data

Ready to build AI-powered educational experiences! 🎓 