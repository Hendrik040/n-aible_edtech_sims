# 🚀 Complete Railway Setup Guide

## 📋 **Prerequisites**

1. **Railway Account** with PostgreSQL and Redis services added
2. **Environment Variables** configured in Railway
3. **pgvector Extension** enabled in PostgreSQL (optional)

## 🔧 **Step 1: Configure Environment Variables**

In your Railway app service, set these environment variables:

### **Required Variables:**
```bash
DATABASE_URL=<automatically provided by Railway PostgreSQL>
OPENAI_API_KEY=<your OpenAI API key>
SECRET_KEY=<generate with: python generate_secret_key.py>
ENVIRONMENT=production
```

### **Optional Variables:**
```bash
REDIS_URL=<automatically provided by Railway Redis>
GOOGLE_CLIENT_ID=<your Google OAuth client ID>
GOOGLE_CLIENT_SECRET=<your Google OAuth client secret>
GOOGLE_REDIRECT_URI=<your production redirect URI>
```

### **How to Reference Redis URL:**
1. Go to your app service → **Variables** tab
2. Click **Add Variable Reference**
3. Variable name: `REDIS_URL`
4. Reference: Select your Redis service → `REDIS_URL`

## 🗄️ **Step 2: Database Setup**

### **Automatic Setup (Recommended)**
Your deployment will automatically:
1. ✅ Test database connection
2. ✅ Run Alembic migrations
3. ✅ Set up pgvector extension (if possible)
4. ✅ Test Redis connection

### **Manual Setup (If Needed)**
If automatic setup fails, connect to your Railway PostgreSQL and run:
```sql
-- Enable pgvector extension for vector search (optional)
CREATE EXTENSION IF NOT EXISTS vector;

-- Check if extension was created
SELECT * FROM pg_extension WHERE extname = 'vector';
```

## 🚀 **Step 3: Deploy**

### **Option A: Railway CLI**
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Deploy from project root
railway up
```

### **Option B: Git Integration**
1. Connect your GitHub repository to Railway
2. Push changes to your main branch
3. Railway will auto-deploy

## 🔍 **Step 4: Verify Deployment**

### **Check Deployment Logs**
```bash
railway logs
```

Look for these success messages:
- ✅ `Database connection successful`
- ✅ `Database migrations completed successfully`
- ✅ `pgvector extension created successfully` (or warning if not available)
- ✅ `Redis connection successful` (or warning if not available)
- ✅ `Deployment setup completed successfully!`
- ✅ `Application startup completed successfully!`

### **Test Endpoints**
- **Health Check**: `GET https://your-app.railway.app/health`
- **API Info**: `GET https://your-app.railway.app/`
- **Scenarios**: `GET https://your-app.railway.app/api/scenarios/`

## 🛠️ **Troubleshooting**

### **Database Connection Issues**
```
❌ Database connection failed
```
**Solution**: Check that `DATABASE_URL` environment variable is set correctly

### **Migration Failures**
```
❌ Database migrations failed
```
**Solution**: 
1. Check database permissions
2. Manually run: `railway run python deploy_railway.py`
3. Check migration files in `backend/database/migrations/versions/`

### **pgvector Extension Issues**
```
⚠️ Could not create pgvector extension
```
**Solution**: This is okay! Vector search will be disabled but app will work fine.

### **Redis Connection Issues**
```
⚠️ Redis connection failed
```
**Solution**: 
1. Check that `REDIS_URL` environment variable is set
2. Verify Redis service is running in Railway
3. App will work without Redis (caching disabled)

## 🔄 **Database Migrations**

### **How It Works**
1. **Automatic**: Migrations run on every deployment via `deploy_railway.py`
2. **Alembic**: Uses your existing migration files in `backend/database/migrations/versions/`
3. **Safe**: Only applies new migrations, won't re-run existing ones

### **Manual Migration Commands**
```bash
# Run migrations manually
railway run python deploy_railway.py

# Or run Alembic directly
railway run bash
cd backend/database
alembic upgrade head
```

### **Create New Migrations (Development)**
```bash
# In your local environment
cd backend/database
alembic revision --autogenerate -m "Description of changes"
alembic upgrade head
```

## 📊 **Service Architecture**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   PostgreSQL    │    │     Redis       │
│                 │    │                 │    │                 │    │                 │
│ - Next.js       │◄──►│ - FastAPI       │◄──►│ - Database      │    │ - Caching       │
│ - React         │    │ - Alembic       │    │ - pgvector      │    │ - Sessions      │
│ - TypeScript    │    │ - Migrations    │    │ - Migrations    │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
     /frontend              /backend              (Railway)           (Railway)
```

**Railway Services:**
- **Frontend Service** → Points to `/frontend` directory
- **Backend Service** → Points to `/backend` directory  
- **PostgreSQL Service** → Managed database
- **Redis Service** → Managed cache

## 🎯 **Success Checklist**

- [ ] All environment variables set in Railway
- [ ] PostgreSQL service connected
- [ ] Redis service connected (optional)
- [ ] `REDIS_URL` variable reference configured
- [ ] Deployment completes without errors
- [ ] Health check endpoint responds
- [ ] Database migrations applied successfully
- [ ] App logs show successful startup

## 🔐 **Security Notes**

- ✅ Environment variables are encrypted in Railway
- ✅ Database connections use SSL by default
- ✅ Redis connections are secured
- ✅ No secrets in your code repository
- ✅ JWT tokens use secure secret key

## 📞 **Support**

If you encounter issues:
1. Check Railway deployment logs: `railway logs`
2. Run manual setup: `railway run python deploy_railway.py`
3. Check environment variables in Railway dashboard
4. Verify services are running in Railway

Your app is now ready for production! 🎉
