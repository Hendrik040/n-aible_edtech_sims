# Root Cause Analysis: Session Expiry Not Triggering Logout

**Date:** December 24, 2024  
**Issue:** User could navigate dashboard after 4-hour absence but simulations weren't showing. Re-login fixed it.

---

## 🔍 Executive Summary

The frontend does **not properly detect or handle session expiration**. When the HttpOnly cookie expires, API calls fail with 401, but the user remains "logged in" from the React state perspective. This creates a broken state where:
- Pages load (Next.js routes work)
- Data doesn't load (API calls fail silently)
- User is confused until they manually log out and back in

---

## 📊 Evidence from Logs

### Frontend Terminal (Lines 13-39)
```
GET /api/proxy/professor/notifications?limit=50&offset=0&unread_only=true 401  ← API failing
GET /api/proxy/api/publishing/simulations?include_drafts=true 401               ← API failing
GET /professor/dashboard 200                                                    ← Page loads!
```

### Backend Terminal (Lines 204-220)
```
INFO: 127.0.0.1 - "GET /professor/notifications?..." 401 Unauthorized
INFO: 127.0.0.1 - "GET /api/publishing/simulations/..." 401 Unauthorized
```

### Key Observation
The page routes return **200** (they load), but API calls return **401** (authentication failed). The frontend doesn't react to these 401s by logging the user out.

---

## 🎯 Root Causes

### 1. **No Next.js Middleware for Route Protection**

**Location:** `frontend/middleware.ts` - **FILE DOES NOT EXIST**

**Impact:** Next.js serves all pages without checking authentication. There's no server-side validation that the user is still logged in when navigating between routes.

**What should happen:** A middleware should check for valid session cookies on protected routes (`/professor/*`, `/student/*`) and redirect to `/login` if missing/expired.

---

### 2. **AuthContext Only Validates Once on Mount**

**Location:** `frontend/lib/auth-context.tsx` (lines 50-76)

```typescript
useEffect(() => {
  const initializeAuth = async () => {
    // ... validation logic
  }
  initializeAuth()
}, [])  // ← Empty dependency! Only runs on initial mount
```

**Impact:** The auth state is only validated when the app first loads. If the session expires while the user is away:
- They come back
- The old `user` state is still in React
- No re-validation happens
- User appears "logged in" but API calls fail

**What should happen:** Auth should be re-validated:
- When the browser tab becomes visible (after sleep/switching tabs)
- Periodically (every few minutes)
- After certain user actions

---

### 3. **`getNotifications()` Swallows 401 Errors**

**Location:** `frontend/lib/api.ts` (lines 561-567)

```typescript
const response = await fetch(url, { credentials: 'include' })
if (response.status === 404) {
  return []
}
if (!response.ok) {
  throw new Error('Failed to fetch notifications')  // ← Generic error, doesn't identify 401!
}
```

**Impact:** When the session expires:
1. `getNotifications()` gets a 401 response
2. It throws `'Failed to fetch notifications'` (not `'Authentication failed'`)
3. The sidebar catches this error and ignores it (line 80-82 in RoleBasedSidebar.tsx)
4. No logout is triggered

**What should happen:** 401 responses should be detected and trigger a session invalidation/logout.

---

### 4. **Dashboard's Auth Error Check is Too Specific**

**Location:** `frontend/app/professor/dashboard/page.tsx` (lines 117-123)

```typescript
} catch (error) {
  // Check if it's an authentication error
  if (error instanceof Error && error.message.includes('Authentication failed')) {
    logout()
    router.push('/')
    return
  }
```

**Impact:** This only triggers logout if the error message contains `'Authentication failed'`. But:
- `getNotifications()` throws `'Failed to fetch notifications'`
- `getCohorts()` might throw different messages
- The check fails, user stays "logged in" with broken state

---

### 5. **No Global 401 Handler / Interceptor**

**Location:** `frontend/lib/api.ts` - The `apiRequest()` function

The current flow:
1. `apiRequest()` throws an error with message `'Authentication failed'`
2. Individual components catch errors and check the message
3. Each component must implement logout logic independently

**What should happen:** A global mechanism should:
- Intercept ALL 401 responses
- Automatically clear auth state
- Redirect to login
- Show a "session expired" message

---

## 🔄 What Happened (Full Timeline)

```
1. User logs in
   → Backend sets HttpOnly cookie (30-min expiry)
   → AuthProvider sets `user` state in React
   → User sees dashboard with simulations

2. User goes away (4 hours)
   → Cookie expires on backend
   → Frontend knows nothing (cookie is HttpOnly, JS can't read it)
   → React `user` state is unchanged

3. User returns
   → Browser tab becomes visible
   → RoleBasedSidebar's visibility listener fires
   → Calls getNotifications() → 401 → Error caught & ignored
   → User state still has the old user object!

4. User navigates to dashboard
   → Next.js loads page (no middleware check)
   → Dashboard component renders
   → Dashboard fetches simulations → 401
   → Simulations array set to [] (empty)
   → User sees dashboard but no simulations

5. User logs out manually
   → AuthProvider clears `user` state
   → Redirect to login

6. User logs back in
   → New cookie set
   → Everything works
```

---

## ✅ Fix Plan

### Phase 1: Global 401 Handler (Critical)

**File:** `frontend/lib/api.ts`

Add a global auth invalidation mechanism:

```typescript
// Add at the top of api.ts
let authInvalidationCallback: (() => void) | null = null

export const setAuthInvalidationCallback = (callback: () => void) => {
  authInvalidationCallback = callback
}

// Modify apiRequest() function
const apiRequest = async (endpoint: string, options: RequestInit = {}, silentAuthError: boolean = false): Promise<Response> => {
  // ... existing code ...
  
  if (response.status === 401) {
    if (silentAuthError) {
      return response
    }
    
    // NEW: Trigger global auth invalidation
    if (authInvalidationCallback) {
      authInvalidationCallback()
    }
    
    const authErrorMessage = errorData.error || errorData.detail || "Session expired. Please log in again."
    throw new Error(authErrorMessage)
  }
  // ... rest of code ...
}
```

**File:** `frontend/lib/auth-context.tsx`

Register the callback:

```typescript
import { setAuthInvalidationCallback } from './api'

export function AuthProvider({ children }: { children: ReactNode }) {
  // ... existing state ...
  
  const handleAuthInvalidation = useCallback(async () => {
    console.log('Session expired, logging out...')
    setUser(null)
    sessionStorage.clear()
    // The redirect will happen via the protected route check
  }, [])
  
  useEffect(() => {
    setAuthInvalidationCallback(handleAuthInvalidation)
    return () => setAuthInvalidationCallback(null as any)
  }, [handleAuthInvalidation])
  
  // ... rest of code ...
}
```

---

### Phase 2: Visibility Change Re-validation

**File:** `frontend/lib/auth-context.tsx`

Add visibility change listener:

```typescript
useEffect(() => {
  const handleVisibilityChange = async () => {
    if (document.visibilityState === 'visible' && user) {
      // Re-validate session when tab becomes visible
      try {
        const currentUser = await apiClient.getCurrentUser()
        if (!currentUser) {
          // Session expired while tab was hidden
          setUser(null)
          sessionStorage.clear()
        }
      } catch (error) {
        console.log('Session validation failed')
        setUser(null)
        sessionStorage.clear()
      }
    }
  }
  
  document.addEventListener('visibilitychange', handleVisibilityChange)
  return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
}, [user])
```

---

### Phase 3: Fix `getNotifications()` to Handle 401

**File:** `frontend/lib/api.ts`

```typescript
getNotifications: async (userRole: string, limit: number = 50, offset: number = 0, unreadOnly: boolean = false): Promise<any> => {
  // ... existing validation ...
  
  const response = await fetch(url, { credentials: 'include' })
  
  if (response.status === 404) {
    return []
  }
  
  // NEW: Handle 401 specifically
  if (response.status === 401) {
    if (authInvalidationCallback) {
      authInvalidationCallback()
    }
    throw new Error('Authentication failed')  // Use consistent message
  }
  
  if (!response.ok) {
    throw new Error('Failed to fetch notifications')
  }
  
  return response.json()
}
```

---

### Phase 4: Add Next.js Middleware (Optional but Recommended)

**File:** `frontend/middleware.ts` (NEW FILE)

```typescript
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const protectedRoutes = ['/professor', '/student']
  const isProtectedRoute = protectedRoutes.some(route => 
    request.nextUrl.pathname.startsWith(route)
  )
  
  if (isProtectedRoute) {
    // Check for session cookie
    const sessionCookie = request.cookies.get('session')  // Adjust cookie name
    
    if (!sessionCookie) {
      // No session cookie, redirect to login
      const loginUrl = new URL('/login', request.url)
      loginUrl.searchParams.set('redirect', request.nextUrl.pathname)
      return NextResponse.redirect(loginUrl)
    }
  }
  
  return NextResponse.next()
}

export const config = {
  matcher: ['/professor/:path*', '/student/:path*']
}
```

**Note:** This provides server-side protection but requires knowing the cookie name. The HttpOnly cookie might need a companion "flag" cookie for JS-side detection.

---

## 📋 Implementation Checklist

| # | Task | File(s) | Priority |
|---|------|---------|----------|
| 1 | Add global auth invalidation callback | `lib/api.ts`, `lib/auth-context.tsx` | 🔴 Critical |
| 2 | Add visibility change re-validation | `lib/auth-context.tsx` | 🔴 Critical |
| 3 | Fix `getNotifications()` 401 handling | `lib/api.ts` | 🟡 High |
| 4 | Fix other raw `fetch()` calls to handle 401 | `lib/api.ts` | 🟡 High |
| 5 | Add Next.js middleware | `middleware.ts` (new) | 🟢 Nice-to-have |
| 6 | Add "session expired" toast/notification | `lib/auth-context.tsx` | 🟢 Nice-to-have |

---

## 🧪 Test Scenarios

After implementing fixes, test these scenarios:

1. **Tab Sleep Test:**
   - Log in
   - Wait for session to expire (or manually expire on backend)
   - Switch to another tab, wait 1 min
   - Switch back → Should redirect to login

2. **API Call After Expiry:**
   - Log in
   - Expire session on backend
   - Try to load simulations → Should redirect to login

3. **Navigation After Expiry:**
   - Log in
   - Expire session on backend
   - Navigate to another protected page → Should redirect to login

---

## 📝 Summary

The core issue is a **gap between backend session state and frontend auth state**. The backend correctly invalidates sessions after 30 minutes, but the frontend:

1. Has no server-side route protection (no middleware)
2. Doesn't re-validate auth when the user returns
3. Swallows 401 errors without triggering logout
4. Keeps stale user state in React indefinitely

The fix requires adding a **global 401 handler** and **visibility change re-validation** to keep the frontend auth state synchronized with the backend session state.

