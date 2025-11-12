"use client"

import { useState, useEffect, useRef } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { useAuth } from "@/lib/auth-context"
import { AccountLinkingDialog } from "@/components/AccountLinkingDialog"
import { AccountLinkingData } from "@/lib/google-oauth"
import { apiClient } from "@/lib/api"

export default function LoginPage() {
  const router = useRouter()
  const { user, isLoading: authLoading, login, loginWithGoogle, linkGoogleAccount } = useAuth()
  
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [rememberMe, setRememberMe] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [showLinkingDialog, setShowLinkingDialog] = useState(false)
  const [linkingData, setLinkingData] = useState<AccountLinkingData | null>(null)
  const errorRef = useRef<string>("")
  
  // Restore error from sessionStorage on mount (survives Fast Refresh)
  useEffect(() => {
    try {
      const storedError = sessionStorage.getItem('loginError')
      if (storedError && !error) {
        console.log('🟢 Restoring error from sessionStorage on mount:', storedError)
        errorRef.current = storedError
        setError(storedError)
      }
    } catch (e) {
      // SessionStorage might not be available
      console.warn('Could not read error from sessionStorage:', e)
      // Fallback to ref
      if (!error && errorRef.current) {
        console.log('🟢 Restoring error from ref on mount:', errorRef.current)
        setError(errorRef.current)
      }
    }
  }, []) // Only run on mount
  
  // Persist error in ref to survive Fast Refresh - NEVER clear the ref automatically
  useEffect(() => {
    if (error) {
      // Only update ref when error is set (don't overwrite if ref already has value and state is clearing)
      if (errorRef.current !== error) {
        errorRef.current = error
        console.log('🔵 Error state set, ref updated:', error)
      }
    } else {
      // Don't clear ref when error is cleared - preserve it for display
      // Only log if ref actually has something worth preserving
      if (errorRef.current) {
        console.log('🔵 Error state cleared, but REF PRESERVED:', errorRef.current)
      }
    }
  }, [error])

  // Catch any unhandled errors that might cause page reload
  useEffect(() => {
    const handleUnhandledRejection = (e: PromiseRejectionEvent) => {
      console.log('🔴 UNHANDLED PROMISE REJECTION:', e.reason)
      // Prevent default browser behavior (which might cause reload)
      e.preventDefault()
    }

    const handleError = (e: ErrorEvent) => {
      console.log('🔴 GLOBAL ERROR:', e.error, e.message)
      // Don't prevent default - let errors log, but check if they're causing reload
    }

    window.addEventListener('unhandledrejection', handleUnhandledRejection)
    window.addEventListener('error', handleError)
    
    return () => {
      window.removeEventListener('unhandledrejection', handleUnhandledRejection)
      window.removeEventListener('error', handleError)
    }
  }, [])

  // Handle redirect after successful login
  useEffect(() => {
    // Check if we're in a popup window
    const isPopup = window.opener !== null || window.parent !== window
    
    if (isPopup) {
      // Don't redirect automatically when in popup - let the OAuth flow complete
      return
    }
    
    // Wait for auth to finish loading before checking redirect
    // This ensures we don't redirect based on stale sessionStorage data
    if (authLoading) {
      return
    }
    
    // Only redirect if user is logged in, not loading, and there's no error
    // IMPORTANT: Don't redirect if there's an error - let user see the error message
    if (user && !loading && !error) {
      // User just logged in successfully, redirect based on role
      if (user.role === 'professor' || user.role === 'admin') {
        router.push('/professor/dashboard')
      } else if (user.role === 'student') {
        router.push('/student/dashboard')
      } else {
        // Fallback to generic dashboard
        router.push('/dashboard')
      }
    }
  }, [user, loading, authLoading, router, error])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    
    try {
      // Call login API to authenticate and get user data
      const response = await apiClient.login({ email, password })
      
      // Update auth context state (login function handles sessionStorage and state)
      await login(email, password)
      
      // Clear error on success only
      setError("")
      errorRef.current = ""
      try {
        sessionStorage.removeItem('loginError')
      } catch (e) {}
      
      // Explicitly redirect immediately using the response data
      // This ensures redirect happens even if state update is delayed
      if (response && response.user) {
        const userRole = response.user.role
        if (userRole === 'professor' || userRole === 'admin') {
          router.push('/professor/dashboard')
        } else if (userRole === 'student') {
          router.push('/student/dashboard')
        } else {
          router.push('/dashboard')
        }
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Login failed. Please check your email and password."
      console.log('🔴 Setting error:', errorMessage)
      
      // CRITICAL: Store in sessionStorage to survive Fast Refresh
      // This persists across component remounts caused by Fast Refresh
      try {
        sessionStorage.setItem('loginError', errorMessage)
      } catch (e) {
        // SessionStorage might not be available in some contexts
        console.warn('Could not store error in sessionStorage:', e)
      }
      
      // Also set ref and state
      errorRef.current = errorMessage
      setError(errorMessage)
      setLoading(false)
      
      console.log('🔴 Error set - ref:', errorRef.current, 'sessionStorage:', sessionStorage.getItem('loginError'))
    }
  }


  // Clear error when user starts typing
  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEmail(e.target.value)
    // Clear error when user starts typing (user action)
    if (error || errorRef.current || (typeof window !== 'undefined' && sessionStorage.getItem('loginError'))) {
      setError("")
      errorRef.current = ""
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('loginError')
        }
      } catch (e) {}
    }
  }

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPassword(e.target.value)
    // Clear error when user starts typing (user action)
    if (error || errorRef.current || (typeof window !== 'undefined' && sessionStorage.getItem('loginError'))) {
      setError("")
      errorRef.current = ""
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('loginError')
        }
      } catch (e) {}
    }
  }

  const handleGoogleLogin = async () => {
    console.log('Login Page: Starting Google login')
    setLoading(true)
    setError("")
    // Don't clear errorRef for Google login - let it persist
    
    try {
      console.log('Login Page: Calling loginWithGoogle')
      const result = await loginWithGoogle()
      console.log('Login Page: Received result from loginWithGoogle:', result)
      
      if (result && 'action' in result && result.action === 'link_required') {
        console.log('Login Page: Account linking required, showing dialog')
        // Show account linking dialog
        setLinkingData(result as AccountLinkingData)
        setShowLinkingDialog(true)
      } else {
        console.log('Login Page: Direct login success, redirecting to dashboard')
        // Direct login success
        router.push("/dashboard")
      }
    } catch (error) {
      console.error('Login Page: Google login error:', error)
      setError(error instanceof Error ? error.message : "Google login failed. Please try again.")
    } finally {
      console.log('Login Page: Setting loading to false')
      setLoading(false)
    }
  }

  const handleLinkAccount = async (action: 'link' | 'create_separate') => {
    if (!linkingData) return
    
    try {
      await linkGoogleAccount(action, linkingData.existing_user.id, linkingData.google_data, linkingData.state)
      setShowLinkingDialog(false)
      setLinkingData(null)
      router.push("/dashboard")
    } catch (error) {
      setError(error instanceof Error ? error.message : "Account linking failed. Please try again.")
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-green-500/10 rounded-full blur-3xl animate-pulse" style={{animationDelay: '1s'}}></div>
      </div>
      
      <div className="w-full max-w-md relative z-10 animate-fade-scale">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center mb-6 animate-scale-in">
            <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Log in to your account</h1>
          <p className="text-gray-400 text-sm">Welcome back! Please enter your details.</p>
        </div>

        {/* Google Login Button - Hidden for now */}
        {/* <Button
          onClick={handleGoogleLogin}
          variant="outline"
          className="w-full mb-6 bg-white/95 backdrop-blur-sm text-black hover:bg-white border-gray-300/50 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-medium"
        >
          <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
            <path
              fill="#4285F4"
              d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
            />
            <path
              fill="#34A853"
              d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            />
            <path
              fill="#FBBC05"
              d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            />
            <path
              fill="#EA4335"
              d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            />
          </svg>
          Log in with Google
        </Button>
        <div className="relative mb-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-600"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-black text-gray-400">OR</span>
          </div>
        </div> */}

        {/* Login Form */}
        <form 
          onSubmit={handleLogin}
          className="space-y-4" 
          noValidate
        >
          <div className="space-y-3">
            <Label htmlFor="email" className="text-white font-medium">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={handleEmailChange}
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
            />
          </div>
          
          <div className="space-y-3">
            <Label htmlFor="password" className="text-white font-medium">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={handlePasswordChange}
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
            />
          </div>

          {/* Remember me and Forgot password */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="remember"
                checked={rememberMe}
                onCheckedChange={(checked) => setRememberMe(checked === true)}
                className="border-gray-600 data-[state=checked]:bg-white data-[state=checked]:text-black"
              />
              <Label htmlFor="remember" className="text-white text-sm">Remember me</Label>
            </div>
            <Link href="/forgot-password" className="text-white text-sm hover:underline">
              Forgot password?
            </Link>
          </div>

          {(error || errorRef.current || (typeof window !== 'undefined' && sessionStorage.getItem('loginError'))) && (
            <div className="bg-red-900/20 border border-red-500/50 rounded-md p-3">
              <div className="flex items-center">
                <svg className="w-5 h-5 text-red-400 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <p className="text-red-400 text-sm font-medium">{error || errorRef.current || (typeof window !== 'undefined' ? sessionStorage.getItem('loginError') : '')}</p>
              </div>
            </div>
          )}

          <Button
            type="submit"
            className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold"
            disabled={loading}
          >
            {loading ? "Logging in..." : "Log In"}
          </Button>
        </form>

        {/* Sign up link */}
        <div className="text-center mt-6">
          <span className="text-gray-400">Don't have an account yet? </span>
          <Link href="/signup" className="text-white hover:underline">
            Sign up now
          </Link>
        </div>
      </div>

      {/* Account Linking Dialog */}
      {showLinkingDialog && linkingData && (
        <AccountLinkingDialog
          isOpen={showLinkingDialog}
          onClose={() => {
            setShowLinkingDialog(false)
            setLinkingData(null)
          }}
          linkingData={linkingData}
          onLinkAccount={handleLinkAccount}
          isLoading={loading}
        />
      )}
    </div>
  )
}