# 🚀 Frontend Railway Deployment Guide

## 📋 **Prerequisites**
- ✅ Backend deployed and working at: `https://n-aibleedtechsims-production.up.railway.app`
- ✅ Railway account with frontend service configured
- ✅ Frontend service points to `/frontend` directory

## 🔧 **Step 1: Environment Variables**

In your Railway **frontend service**, set these environment variables:

### **Required Variables:**
```bash
NEXT_PUBLIC_API_URL=https://n-aibleedtechsims-production.up.railway.app
NODE_ENV=production
NEXT_TELEMETRY_DISABLED=1
```

### **Optional Variables (if using Google OAuth):**
```bash
GOOGLE_CLIENT_ID=<your Google OAuth client ID>
GOOGLE_CLIENT_SECRET=<your Google OAuth client secret>
GOOGLE_REDIRECT_URI=<your frontend URL>/auth/google/callback
```

## 🗂️ **Step 2: File Structure**

Your frontend deployment files are now in place:
```
/frontend/
├── railway.toml          ← Railway deployment config
├── nixpacks.toml         ← Build configuration  
├── .env.production       ← Production environment variables
├── package.json          ← Dependencies and scripts
└── ... (your Next.js app)
```

## 🚀 **Step 3: Deploy**

### **Option A: Railway CLI**
```bash
# From your project root
railway up
```

### **Option B: Git Integration**
1. Commit and push your changes
2. Railway will auto-deploy your frontend service

## 🔍 **Step 4: Verify Deployment**

### **Check Build Logs**
```bash
railway logs --service=<your-frontend-service-name>
```

Look for these success indicators:
- ✅ `npm ci` - Dependencies installed
- ✅ `npm run build` - Next.js build successful
- ✅ `npm start` - Server started
- ✅ `ready - started server on 0.0.0.0:3000`

### **Test Your App**
1. **Frontend URL**: `https://your-frontend-app.railway.app`
2. **API Connection**: Check if frontend can connect to backend
3. **Authentication**: Test login/signup functionality
4. **Features**: Test core app functionality

## 🔗 **Step 5: Connect Frontend to Backend**

Your frontend is already configured to connect to your backend:
- ✅ API calls use `NEXT_PUBLIC_API_URL` environment variable
- ✅ Points to: `https://n-aibleedtechsims-production.up.railway.app`
- ✅ Includes credentials for authentication cookies
- ✅ Proper CORS handling

## 🛠️ **Troubleshooting**

### **Build Failures**
```
❌ npm run build failed
```
**Solutions**:
1. Check for TypeScript errors in your code
2. Verify all dependencies are in `package.json`
3. Check build logs for specific error messages

### **API Connection Issues**
```
❌ Unable to connect to the server
```
**Solutions**:
1. Verify `NEXT_PUBLIC_API_URL` is set correctly
2. Check that backend is running and accessible
3. Verify CORS settings in backend allow your frontend domain

### **Environment Variable Issues**
```
❌ API URL not found
```
**Solutions**:
1. Ensure `NEXT_PUBLIC_API_URL` is set in Railway frontend service
2. Restart the frontend service after adding variables
3. Check that variable names match exactly (case-sensitive)

## 📊 **Expected Architecture**

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Users         │    │   Frontend      │    │   Backend       │
│                 │    │                 │    │                 │
│ - Web Browser   │◄──►│ - Next.js       │◄──►│ - FastAPI       │
│ - Mobile        │    │ - React         │    │ - Database      │
│ - Tablet        │    │ - TypeScript    │    │ - Redis         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                        Railway Frontend       Railway Backend
                        your-app.railway.app   n-aibleedtechsims...
```

## 🎯 **Success Checklist**

- [ ] Frontend service deployed successfully
- [ ] `NEXT_PUBLIC_API_URL` environment variable set
- [ ] Frontend can reach backend API
- [ ] Authentication works (login/signup)
- [ ] Core app features functional
- [ ] No CORS errors in browser console
- [ ] Build completes without errors

## 🔐 **Security Notes**

- ✅ API URL is public (prefixed with `NEXT_PUBLIC_`)
- ✅ Authentication uses secure HttpOnly cookies
- ✅ No sensitive data exposed in frontend
- ✅ CORS properly configured between services

## 🚀 **Next Steps**

Once your frontend is deployed:
1. **Update Google OAuth redirect URIs** (if using OAuth)
2. **Test all functionality** end-to-end
3. **Monitor logs** for any issues
4. **Set up custom domain** (optional)

Your full-stack app will be live! 🎉
