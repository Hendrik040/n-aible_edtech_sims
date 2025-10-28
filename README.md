# 🎓 AI Agent Education Platform
An innovative educational platform that transforms business case studies into immersive AI-powered simulations. Upload PDF case studies, let AI extract key figures and scenarios, then engage students in **linear simulation experiences** with dynamic **ChatOrchestrator** system and intelligent **AI persona interactions**.

![AI Agent Education Platform](https://img.shields.io/badge/AI-Education-blue?style=for-the-badge)
![Next.js](https://img.shields.io/badge/Next.js%2015-TypeScript-000000?style=for-the-badge&logo=nextdotjs)
![FastAPI](https://img.shields.io/badge/FastAPI-Python-009688?style=for-the-badge&logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-316192?style=for-the-badge&logo=postgresql)
![Alembic](https://img.shields.io/badge/Alembic-Migrations-009688?style=for-the-badge)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991?style=for-the-badge&logo=openai)

## 🚀 Quick Start

### 🐳 Option 1: Docker Compose (Recommended)

The fastest way to get started! This will set up PostgreSQL and Redis automatically.

#### Prerequisites
- **Docker** and **Docker Compose**
- **Node.js** 18+ and **pnpm** (for frontend)
- **Python** 3.11+ (for backend)

#### 1. Clone and Setup
```bash
git clone <repository-url>
cd n-aible_EdTech_Sims

# Start database services
docker-compose up -d

# Wait for services to be ready (about 30 seconds)
docker-compose logs postgres redis
```

#### 2. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp ../env_template.txt .env
```

**Edit `.env` file with these Docker-ready values:**
```bash
# Database (Docker PostgreSQL)
DATABASE_URL=postgresql://username:password@localhost:5432/ai_agent_platform

# Redis (Docker Redis)
REDIS_URL=redis://localhost:6379

# Required API Keys (get from providers)
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Security
SECRET_KEY=your_super_secret_key_here_at_least_32_chars

# Development settings
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:3000
COOKIE_SECURE=false

# Optional: Google OAuth (leave as placeholders for now)
GOOGLE_CLIENT_ID=REPLACE_WITH_YOUR_GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=REPLACE_WITH_YOUR_GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

#### 3. Initialize Database
```bash
# Run database migrations
alembic upgrade head

# Start the backend server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 4. Frontend Setup
```bash
cd ../frontend

# Install dependencies
pnpm install

# Start development server
pnpm dev
```

#### 5. Access the Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Database**: localhost:5432 (username/password)
- **Redis**: localhost:6379

---

### 💻 Option 2: Manual Setup (Advanced)

If you prefer to set up PostgreSQL and Redis manually:

#### Prerequisites
- **Node.js** 18+ and **pnpm**
- **Python** 3.11+
- **PostgreSQL** 14+ (with pgvector extension)
- **Redis** 6+

#### Setup Steps
```bash
# 1. Clone repository
git clone <repository-url>
cd n-aible_EdTech_Sims

# 2. Set up PostgreSQL database
createdb ai_agent_platform
psql ai_agent_platform -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 3. Follow backend and frontend setup from Option 1
# (Skip docker-compose step, configure DATABASE_URL for your local PostgreSQL)
```

## 📋 Environment Variables

Copy `env_template.txt` to `.env` in the backend directory and configure:

### Required Variables
- `DATABASE_URL`: PostgreSQL connection string
- `OPENAI_API_KEY`: Your OpenAI API key
- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `SECRET_KEY`: Strong secret key for JWT tokens
- `GOOGLE_CLIENT_ID`: Google OAuth client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth client secret

### Optional Variables
- `REDIS_URL`: Redis connection for caching
- `CORS_ORIGINS`: Allowed CORS origins
- `ENVIRONMENT`: development/production

## 🏗️ Architecture

### Backend (FastAPI + Python)
- **API Layer**: RESTful endpoints with automatic documentation
- **AI Agents**: LangChain-powered agents for personas, grading, and summarization
- **Database**: PostgreSQL with Alembic migrations
- **Authentication**: JWT + Google OAuth integration
- **Vector Storage**: Semantic search and memory management

### Frontend (Next.js 15 + TypeScript)
- **Modern UI**: Tailwind CSS + shadcn/ui components
- **Real-time Chat**: Interactive simulation interface
- **State Management**: React Context + custom hooks
- **Authentication**: Google OAuth integration

## 🎯 Key Features

- **PDF-to-Simulation Pipeline**: Upload case studies and generate interactive scenarios
- **AI Persona System**: Dynamic characters with personality traits
- **Linear Simulation Flow**: Structured multi-scene learning progression
- **Community Marketplace**: Share and discover educational content
- **Progress Tracking**: Analytics and learning outcomes

## 📚 Documentation

Detailed documentation is available in the `docs/` directory:

- [Developer Guide](docs/Developer_Guide.md)
- [API Reference](docs/API_Reference.md)
- [Database Guide](docs/Database_Guide.md)
- [Features Overview](docs/Features_Overview.md)
- [Quick Start Guide](docs/QUICK_START.md)

## 🤝 Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

If you encounter any issues:

1. Check the [documentation](docs/)
2. Review the [troubleshooting guide](docs/Developer_Guide.md#troubleshooting)
3. Create an issue in the repository

## 🏃‍♂️ Development Commands

### Docker Services
```bash
# Start all services (PostgreSQL + Redis)
docker-compose up -d

# View service logs
docker-compose logs -f postgres redis

# Stop all services
docker-compose down

# Reset database (removes all data!)
docker-compose down -v
docker-compose up -d
```

### Backend
```bash
# Start development server with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run database migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Run tests
pytest

# Clear database (development only)
python clear_database.py
```

### Frontend
```bash
# Start development server
pnpm dev

# Build for production
pnpm build

# Start production server
pnpm start

# Run linting
pnpm lint
```

## 🔧 Troubleshooting

### Common Issues

#### Authentication Problems
- **Login redirects back to login page**: Check the [Authentication Troubleshooting Guide](docs/AUTHENTICATION_TROUBLESHOOTING.md)
- **"Could not validate credentials"**: Clear browser cookies and login again
- **Google OAuth "Load failed"**: Configure Google OAuth credentials in `.env`

#### Database Issues
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# View PostgreSQL logs
docker-compose logs postgres

# Reset database completely
docker-compose down -v && docker-compose up -d
alembic upgrade head
```

#### Backend Issues
```bash
# Check if all required environment variables are set
python -c "from database.connection import settings; print('✅ Config loaded successfully')"

# Test database connection
python -c "from database.connection import engine; engine.execute('SELECT 1')"
```

#### Frontend Issues
```bash
# Clear Next.js cache
rm -rf .next
pnpm dev

# Check if backend is accessible
curl http://localhost:8000/docs
```

### Getting Help
1. Check the [documentation](docs/) directory
2. Review the [Authentication Troubleshooting Guide](docs/AUTHENTICATION_TROUBLESHOOTING.md)
3. Ensure Docker services are running: `docker-compose ps`
4. Check logs: `docker-compose logs`

---

**Ready to transform education with AI?** Start building immersive learning experiences today! 🚀
