"use client"

import { useState, useEffect, useRef } from "react"
import { useRouter, useParams } from "next/navigation"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"
import { Users, Clock, AlertCircle, CheckCircle, Loader2, LogIn, UserPlus } from "lucide-react"

export default function InviteLinkPage() {
  const router = useRouter()
  const params = useParams()
  const { user, isLoading: authLoading, login, register } = useAuth()
  const token = params.token as string

  const [inviteData, setInviteData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [accepting, setAccepting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [alreadyEnrolled, setAlreadyEnrolled] = useState(false)
  const [attemptedAccept, setAttemptedAccept] = useState(false) // Prevent infinite loops
  const [authMode, setAuthMode] = useState<"login" | "signup">("login")
  const errorRef = useRef<string | null>(null)
  
  // Sanitize error message to extract safe error code/identifier
  const sanitizeErrorForStorage = (errorMessage: string): string => {
    // Remove emails, URLs, and other PII patterns
    const sanitized = errorMessage
      .replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g, '[email]')
      .replace(/\bhttps?:\/\/[^\s]+/g, '[url]')
      .replace(/\b\d{3,}\b/g, '[id]')
    
    // Map common error patterns to safe codes
    if (sanitized.toLowerCase().includes('already') && sanitized.toLowerCase().includes('member')) {
      return 'ERROR_ALREADY_ENROLLED'
    }
    if (sanitized.toLowerCase().includes('only students')) {
      return 'ERROR_STUDENTS_ONLY'
    }
    if (sanitized.toLowerCase().includes('invalid') || sanitized.toLowerCase().includes('expired')) {
      return 'ERROR_INVALID_LINK'
    }
    if (sanitized.toLowerCase().includes('login failed') || sanitized.toLowerCase().includes('authentication')) {
      return 'ERROR_AUTH_FAILED'
    }
    if (sanitized.toLowerCase().includes('already exists')) {
      return 'ERROR_EMAIL_EXISTS'
    }
    if (sanitized.toLowerCase().includes('password') && sanitized.toLowerCase().includes('characters')) {
      return 'ERROR_PASSWORD_LENGTH'
    }
    if (sanitized.toLowerCase().includes('failed to')) {
      return 'ERROR_GENERIC_FAILURE'
    }
    
    // Fallback: return sanitized version (already stripped of emails/URLs/IDs)
    return sanitized.length > 100 ? sanitized.substring(0, 100) : sanitized
  }
  
  // Map error codes to user-safe messages
  const getSafeErrorMessage = (errorCode: string): string => {
    const errorMap: Record<string, string> = {
      'ERROR_ALREADY_ENROLLED': 'You are already a member of this cohort',
      'ERROR_STUDENTS_ONLY': 'Only students can accept cohort invite links',
      'ERROR_INVALID_LINK': 'Invalid or expired invite link',
      'ERROR_AUTH_FAILED': 'Authentication failed. Please try again.',
      'ERROR_EMAIL_EXISTS': 'An account with this email already exists. Please sign in instead.',
      'ERROR_PASSWORD_LENGTH': 'Password must be at least 6 characters long',
      'ERROR_GENERIC_FAILURE': 'An error occurred. Please try again.',
    }
    
    return errorMap[errorCode] || 'An error occurred. Please try again.'
  }
  
  // Get safe error message from sessionStorage if present
  const getStoredSafeError = (): string | null => {
    try {
      if (typeof window !== 'undefined') {
        const storedCode = sessionStorage.getItem('inviteError')
        if (storedCode) {
          return getSafeErrorMessage(storedCode)
        }
      }
    } catch {
      // Silently handle sessionStorage errors
    }
    return null
  }
  
  // Check if there's any error to display
  const hasError = (): boolean => {
    return !!(error || errorRef.current || getStoredSafeError())
  }
  
  // Get the current error message to display (prefers state, then ref, then storage)
  const getDisplayError = (): string => {
    return error || errorRef.current || getStoredSafeError() || ''
  }
  
  // Restore error from sessionStorage on mount (survives Fast Refresh)
  useEffect(() => {
    try {
      const storedErrorCode = sessionStorage.getItem('inviteError')
      if (storedErrorCode && !error) {
        const safeMessage = getSafeErrorMessage(storedErrorCode)
        errorRef.current = safeMessage
        setError(safeMessage)
      }
    } catch {
      // Fallback to ref - silently handle sessionStorage errors
      if (!error && errorRef.current) {
        setError(errorRef.current)
      }
    }
  }, []) // Only run on mount
  
  // Login form state
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loginLoading, setLoginLoading] = useState(false)
  
  // Signup form state
  const [signupData, setSignupData] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "student" as "student" | "professor"
  })
  const [signupLoading, setSignupLoading] = useState(false)

  // Validate invite link on mount
  useEffect(() => {
    const validateInvite = async () => {
      if (!token) {
        setError("Invalid invite link")
        setLoading(false)
        return
      }

      try {
        setLoading(true)
        setError(null)
        const data = await apiClient.validateInviteLink(token)
        setInviteData(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to validate invite link")
      } finally {
        setLoading(false)
      }
    }

    validateInvite()
  }, [token])

  // Auto-accept invite when user becomes authenticated
  useEffect(() => {
    const autoAcceptInvite = async () => {
      // Prevent multiple attempts (but allow if alreadyEnrolled to show error)
      if (!user || user.role !== "student" || !token || !inviteData || accepting || (success && !alreadyEnrolled) || (attemptedAccept && !alreadyEnrolled)) {
        return
      }

      // User just logged in/signed up, automatically accept the invite
      try {
        setAttemptedAccept(true) // Mark as attempted to prevent loops
        setAccepting(true)
        setError(null)
        errorRef.current = null
        try {
          if (typeof window !== 'undefined') {
            sessionStorage.removeItem('inviteError')
          }
        } catch (e) {}
        const response = await apiClient.acceptInviteLink(token)
        
        // Check if already enrolled (backend returns this as success but with flag)
        if (response && response.already_enrolled) {
          setAccepting(false)
          const safeErrorMessage = 'You are already a member of this cohort'
          const sanitizedErrorCode = 'ERROR_ALREADY_ENROLLED'
          setError(safeErrorMessage)
          errorRef.current = safeErrorMessage
          try {
            if (typeof window !== 'undefined') {
              sessionStorage.setItem('inviteError', sanitizedErrorCode)
            }
          } catch {}
          // Don't redirect, don't show success screen, don't set alreadyEnrolled - just show the error message
          return // Exit early to prevent further processing
        } else {
          // Clear error on success
          setError(null)
          errorRef.current = null
          try {
            if (typeof window !== 'undefined') {
              sessionStorage.removeItem('inviteError')
            }
          } catch (e) {}
          setSuccess(true)
          // Redirect to student dashboard after a brief delay
          setTimeout(() => {
            router.push("/student/dashboard")
          }, 2000)
        }
      } catch (err: any) {
        const errorMessage = err instanceof Error ? err.message : "Failed to join cohort"
        const sanitizedErrorCode = sanitizeErrorForStorage(errorMessage)
        const safeErrorMessage = getSafeErrorMessage(sanitizedErrorCode)
        
        // CRITICAL: Store sanitized error code in sessionStorage to survive Fast Refresh
        try {
          if (typeof window !== 'undefined') {
            sessionStorage.setItem('inviteError', sanitizedErrorCode)
          }
        } catch {
          // Silently handle sessionStorage errors
        }
        
        // Also set ref and state with safe message
        errorRef.current = safeErrorMessage
        setError(safeErrorMessage)
        setAccepting(false)
        setAttemptedAccept(true) // Still mark as attempted to prevent infinite loops
        
        // If it's a professor trying to join, show a more helpful message
        if (errorMessage.includes("Only students can accept") || errorMessage.includes("403")) {
          // Don't retry for professor role
        }
      }
    }

    autoAcceptInvite()
  }, [user, token, inviteData, accepting, success, attemptedAccept, router])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginLoading(true)
    setError(null)
    errorRef.current = null
    try {
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('inviteError')
      }
    } catch (e) {}

    try {
      await login(email, password)
      // Clear error on success
      setError(null)
      errorRef.current = null
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('inviteError')
        }
      } catch (e) {}
      // Auto-accept will happen in useEffect when user state updates
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Login failed. Please try again."
      const sanitizedErrorCode = sanitizeErrorForStorage(errorMessage)
      const safeErrorMessage = getSafeErrorMessage(sanitizedErrorCode)
      
      // CRITICAL: Store sanitized error code in sessionStorage to survive Fast Refresh
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('inviteError', sanitizedErrorCode)
        }
      } catch {
        // Silently handle sessionStorage errors
      }
      
      // Also set ref and state with safe message
      errorRef.current = safeErrorMessage
      setError(safeErrorMessage)
      setLoginLoading(false)
    }
  }

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    setSignupLoading(true)
    setError(null)
    errorRef.current = null
    try {
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('inviteError')
      }
    } catch (e) {}

    // Validate password length
    if (signupData.password.length < 6) {
      const safeErrorMessage = "Password must be at least 6 characters long"
      const sanitizedErrorCode = 'ERROR_PASSWORD_LENGTH'
      setError(safeErrorMessage)
      errorRef.current = safeErrorMessage
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('inviteError', sanitizedErrorCode)
        }
      } catch {}
      setSignupLoading(false)
      return
    }

    try {
      // First, check if email already exists
      const checkResponse = await fetch('/api/auth/check-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: signupData.email })
      })
      
      if (checkResponse.ok) {
        const checkData = await checkResponse.json()
        if (checkData.exists) {
          const safeErrorMessage = "An account with this email already exists. Please sign in instead."
          const sanitizedErrorCode = 'ERROR_EMAIL_EXISTS'
          setError(safeErrorMessage)
          errorRef.current = safeErrorMessage
          try {
            if (typeof window !== 'undefined') {
              sessionStorage.setItem('inviteError', sanitizedErrorCode)
            }
          } catch {}
          setSignupLoading(false)
          setAuthMode("login")
          setEmail(signupData.email)
          return
        }
      }

      // Generate username from entire email to ensure uniqueness
      // Replace @ and . with underscores: scott@student.n-aible.com -> scott_student_n-aible_com
      const username = signupData.email
        .toLowerCase()
        .replace('@', '_')
        .replace(/\./g, '_')
        .replace(/[^a-z0-9_]/g, '') // Remove any other invalid characters
      const registerData = {
        ...signupData,
        username: username,
        profile_public: true,
        allow_contact: true
      }
      
      await register(registerData)
      
      // Clear error on success
      setError(null)
      errorRef.current = null
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('inviteError')
        }
      } catch (e) {}
      
      // Force reload to pick up auth state
      if (typeof window !== 'undefined') {
        window.location.reload()
      }
      // Auto-accept will happen in useEffect when user state updates
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Registration failed. Please try again."
      const sanitizedErrorCode = sanitizeErrorForStorage(errorMessage)
      const safeErrorMessage = getSafeErrorMessage(sanitizedErrorCode)
      
      // CRITICAL: Store sanitized error code in sessionStorage to survive Fast Refresh
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('inviteError', sanitizedErrorCode)
        }
      } catch {
        // Silently handle sessionStorage errors
      }
      
      // Also set ref and state with safe message
      errorRef.current = safeErrorMessage
      setError(safeErrorMessage)
      setSignupLoading(false)
    }
  }

  const handleAccept = async () => {
    if (!user || user.role !== "student") {
      const safeErrorMessage = "Only students can accept cohort invite links"
      const sanitizedErrorCode = 'ERROR_STUDENTS_ONLY'
      setError(safeErrorMessage)
      errorRef.current = safeErrorMessage
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('inviteError', sanitizedErrorCode)
        }
      } catch {}
      setAttemptedAccept(true)
      return
    }

    try {
      setAccepting(true)
      setError(null)
      errorRef.current = null
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('inviteError')
        }
      } catch (e) {}
      setAttemptedAccept(true)
      const response = await apiClient.acceptInviteLink(token)
      
      // Check if already enrolled
      if (response && response.already_enrolled) {
        setAccepting(false)
        const safeErrorMessage = 'You are already a member of this cohort'
        const sanitizedErrorCode = 'ERROR_ALREADY_ENROLLED'
        setError(safeErrorMessage)
        errorRef.current = safeErrorMessage
        try {
          if (typeof window !== 'undefined') {
            sessionStorage.setItem('inviteError', sanitizedErrorCode)
          }
        } catch {}
        // Don't redirect, don't show success screen, don't set alreadyEnrolled - just show the error message
        return // Exit early to prevent further processing
      } else {
        // Clear error on success
        setError(null)
        errorRef.current = null
        try {
          if (typeof window !== 'undefined') {
            sessionStorage.removeItem('inviteError')
          }
        } catch (e) {}
        setSuccess(true)
        setTimeout(() => {
          router.push("/student/dashboard")
        }, 2000)
      }
    } catch (err: any) {
      const errorMessage = err instanceof Error ? err.message : "Failed to accept invite link"
      const sanitizedErrorCode = sanitizeErrorForStorage(errorMessage)
      const safeErrorMessage = getSafeErrorMessage(sanitizedErrorCode)
      
      // CRITICAL: Store sanitized error code in sessionStorage to survive Fast Refresh
      try {
        if (typeof window !== 'undefined') {
          sessionStorage.setItem('inviteError', sanitizedErrorCode)
        }
      } catch {
        // Silently handle sessionStorage errors
      }
      
      // Also set ref and state with safe message
      errorRef.current = safeErrorMessage
      setError(safeErrorMessage)
      setAccepting(false)
      setAttemptedAccept(true) // Prevent retries
    }
  }

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
        <div className="text-center">
          <Loader2 className="h-12 w-12 text-white/80 mx-auto mb-4 animate-spin" />
          <p className="text-white/80">Loading invite link...</p>
        </div>
      </div>
    )
  }

  if (error && !inviteData) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
        <div className="w-full max-w-md relative z-10 animate-fade-scale">
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center mb-4 animate-scale-in">
              <AlertCircle className="h-16 w-16 text-red-400" />
            </div>
            <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Invalid Invite Link</h1>
            <p className="text-gray-400 text-sm mb-6">{error}</p>
            <Link href="/">
              <Button className="btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold">
                Go to Home
              </Button>
            </Link>
          </div>
        </div>
      </div>
    )
  }

  // Only show success screen if not already enrolled (already enrolled shows error message instead)
  if (success && !alreadyEnrolled) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
        <div className="w-full max-w-md relative z-10 animate-fade-scale">
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center mb-4 animate-scale-in">
              <CheckCircle className="h-16 w-16 text-green-400" />
            </div>
            <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Successfully Joined!</h1>
            <p className="text-gray-400 text-sm mb-6">
              You have been added to <strong>{inviteData?.cohort?.title}</strong>
            </p>
            <p className="text-gray-500 text-xs">Redirecting to your dashboard...</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-green-500/10 rounded-full blur-3xl animate-pulse" style={{animationDelay: '1s'}}></div>
      </div>

      <div className="w-full max-w-6xl relative z-10 animate-fade-scale">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center mb-4 animate-scale-in">
            <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Join Cohort</h1>
          <p className="text-gray-400 text-sm">You've been invited to join a cohort</p>
        </div>

        {/* Two Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: Invite Information Card */}
          <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-700/50 rounded-2xl p-6 shadow-xl">
          {inviteData && (
            <div className="space-y-4">
              {/* Cohort Info */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Users className="h-5 w-5 text-blue-400" />
                  <h2 className="text-xl font-bold text-white">{inviteData.cohort.title}</h2>
                </div>
                {inviteData.cohort.description && (
                  <p className="text-gray-400 text-sm mb-4">{inviteData.cohort.description}</p>
                )}
              </div>

              {/* Professor Info */}
              <div className="border-t border-gray-700/50 pt-4">
                <p className="text-xs text-gray-500 mb-1">Invited by</p>
                <p className="text-white font-medium">{inviteData.professor.name}</p>
                <p className="text-gray-400 text-sm">{inviteData.professor.email}</p>
              </div>

              {/* Invite Details */}
              <div className="grid grid-cols-2 gap-4 border-t border-gray-700/50 pt-4">
                <div>
                  <p className="text-xs text-gray-500 mb-1">Type</p>
                  <p className="text-white font-medium">
                    {inviteData.invite_type === "SINGLE_USE" ? "Single Use" : "Multi Use"}
                  </p>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-gray-400" />
                    <div>
                      <p className="text-xs text-gray-500 mb-1">Expires</p>
                      <p className="text-white font-medium text-sm">
                        {new Date(inviteData.expires_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Uses Left (if applicable) */}
              {inviteData.uses_left !== null && (
                <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
                  <p className="text-xs text-blue-400">
                    {inviteData.uses_left === 1 
                      ? "1 use remaining" 
                      : `${inviteData.uses_left} uses remaining`}
                  </p>
                </div>
              )}
            </div>
          )}
          </div>

          {/* Right: Auth Forms - Show only if not authenticated or not a student */}
          {!user ? (
            <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-700/50 rounded-2xl p-6 shadow-xl">
            {/* Tab Switcher */}
            <div className="flex gap-2 mb-6 bg-gray-800/50 rounded-lg p-1">
              <button
                type="button"
                onClick={() => {
                  setAuthMode("login")
                  setError(null)
                  errorRef.current = null
                  try {
                    if (typeof window !== 'undefined') {
                      sessionStorage.removeItem('inviteError')
                    }
                  } catch (e) {}
                }}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-md transition-all font-medium ${
                  authMode === "login"
                    ? "bg-white/10 text-white shadow-md"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                <LogIn className="h-4 w-4" />
                Sign In
              </button>
              <button
                type="button"
                onClick={() => {
                  setAuthMode("signup")
                  setError(null)
                  errorRef.current = null
                  try {
                    if (typeof window !== 'undefined') {
                      sessionStorage.removeItem('inviteError')
                    }
                  } catch (e) {}
                }}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-md transition-all font-medium ${
                  authMode === "signup"
                    ? "bg-white/10 text-white shadow-md"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                <UserPlus className="h-4 w-4" />
                Sign Up
              </button>
            </div>

            {authMode === "login" ? (
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-3">
                  <Label htmlFor="login-email" className="text-white font-medium">Email</Label>
                  <Input
                    id="login-email"
                    type="email"
                    placeholder="Enter your email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value)
                      // Clear error when user starts typing
                      if (hasError()) {
                        setError(null)
                        errorRef.current = null
                        try {
                          if (typeof window !== 'undefined') {
                            sessionStorage.removeItem('inviteError')
                          }
                        } catch {}
                      }
                    }}
                    className="bg-gray-800/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
                    required
                  />
                </div>
                
                <div className="space-y-3">
                  <Label htmlFor="login-password" className="text-white font-medium">Password</Label>
                  <Input
                    id="login-password"
                    type="password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value)
                      // Clear error when user starts typing
                      if (hasError()) {
                        setError(null)
                        errorRef.current = null
                        try {
                          if (typeof window !== 'undefined') {
                            sessionStorage.removeItem('inviteError')
                          }
                        } catch {}
                      }
                    }}
                    className="bg-gray-800/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
                    required
                  />
                </div>

                {hasError() && (
                  <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-3">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                      <p className="text-red-400 text-sm font-medium">
                        {getDisplayError()}
                      </p>
                    </div>
                  </div>
                )}

                <Button
                  type="submit"
                  disabled={loginLoading || accepting}
                  className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold mt-4"
                >
                  {loginLoading || accepting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      {accepting ? "Joining..." : "Signing in..."}
                    </>
                  ) : (
                    "Sign In & Join Cohort"
                  )}
                </Button>
              </form>
            ) : (
              <form onSubmit={handleSignup} className="space-y-4">
                <div className="space-y-3">
                  <Label htmlFor="signup-name" className="text-white font-medium">Full Name</Label>
                  <Input
                    id="signup-name"
                    type="text"
                    placeholder="Enter your full name"
                    value={signupData.full_name}
                    onChange={(e) => {
                      setSignupData({ ...signupData, full_name: e.target.value })
                      // Clear error when user starts typing
                      if (hasError()) {
                        setError(null)
                        errorRef.current = null
                        try {
                          if (typeof window !== 'undefined') {
                            sessionStorage.removeItem('inviteError')
                          }
                        } catch {}
                      }
                    }}
                    className="bg-gray-800/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
                    required
                  />
                </div>

                <div className="space-y-3">
                  <Label htmlFor="signup-email" className="text-white font-medium">Email</Label>
                  <Input
                    id="signup-email"
                    type="email"
                    placeholder="Enter your email"
                    value={signupData.email}
                    onChange={(e) => {
                      setSignupData({ ...signupData, email: e.target.value })
                      // Clear error when user starts typing
                      if (hasError()) {
                        setError(null)
                        errorRef.current = null
                        try {
                          if (typeof window !== 'undefined') {
                            sessionStorage.removeItem('inviteError')
                          }
                        } catch {}
                      }
                    }}
                    className="bg-gray-800/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
                    required
                  />
                </div>
                
                <div className="space-y-3">
                  <Label htmlFor="signup-password" className="text-white font-medium">Password</Label>
                  <Input
                    id="signup-password"
                    type="password"
                    placeholder="Enter your password (min. 6 characters)"
                    value={signupData.password}
                    onChange={(e) => {
                      setSignupData({ ...signupData, password: e.target.value })
                      // Clear error when user starts typing
                      if (hasError()) {
                        setError(null)
                        errorRef.current = null
                        try {
                          if (typeof window !== 'undefined') {
                            sessionStorage.removeItem('inviteError')
                          }
                        } catch {}
                      }
                    }}
                    className="bg-gray-800/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
                    required
                    minLength={6}
                  />
                </div>

                {hasError() && (
                  <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-3">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                      <p className="text-red-400 text-sm font-medium">
                        {getDisplayError()}
                      </p>
                    </div>
                  </div>
                )}

                <Button
                  type="submit"
                  disabled={signupLoading || accepting}
                  className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold mt-4"
                >
                  {signupLoading || accepting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      {accepting ? "Joining..." : "Creating account..."}
                    </>
                  ) : (
                    "Sign Up & Join Cohort"
                  )}
                </Button>
              </form>
            )}

            <p className="text-center text-sm text-gray-400 mt-4">
              {authMode === "login" ? (
                <>
                  Don't have an account?{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setAuthMode("signup")
                      setError(null)
                      errorRef.current = null
                      try {
                        if (typeof window !== 'undefined') {
                          sessionStorage.removeItem('inviteError')
                        }
                      } catch (e) {}
                    }}
                    className="text-white hover:underline font-medium"
                  >
                    Sign up
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setAuthMode("login")
                      setError(null)
                      errorRef.current = null
                      try {
                        if (typeof window !== 'undefined') {
                          sessionStorage.removeItem('inviteError')
                        }
                      } catch (e) {}
                    }}
                    className="text-white hover:underline font-medium"
                  >
                    Sign in
                  </button>
                </>
              )}
            </p>
          </div>
        ) : user && user.role === "student" ? (
          /* Already authenticated as student - show join button or status */
          <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-700/50 rounded-2xl p-6 shadow-xl">
            {alreadyEnrolled ? (
              <div className="text-center space-y-4">
                <CheckCircle className="h-12 w-12 text-green-400 mx-auto" />
                <h3 className="text-xl font-bold text-white">Already Enrolled</h3>
                <p className="text-gray-400 text-sm">
                  You are already a member of this cohort.
                </p>
                <Button
                  onClick={() => router.push("/student/dashboard")}
                  className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all"
                >
                  Go to Dashboard
                </Button>
              </div>
            ) : error && attemptedAccept ? (
              <div className="space-y-4">
                <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
                    <h3 className="text-red-400 font-medium">Cannot Join</h3>
                  </div>
                  <p className="text-red-300 text-sm">{error}</p>
                </div>
                <Button
                  onClick={() => router.push("/student/dashboard")}
                  className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all"
                >
                  Go to Dashboard
                </Button>
              </div>
            ) : (
              <>
                {error && (
                  <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-3 mb-4">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                      <p className="text-red-400 text-sm font-medium">{error}</p>
                    </div>
                  </div>
                )}
                <Button
                  onClick={handleAccept}
                  disabled={accepting}
                  className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold"
                >
                  {accepting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Joining...
                    </>
                  ) : (
                    "Join Cohort"
                  )}
                </Button>
              </>
            )}
          </div>
        ) : user && user.role !== "student" ? (
          /* Authenticated as professor - show error message */
          <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-700/50 rounded-2xl p-6 shadow-xl">
            <div className="text-center space-y-4">
              <AlertCircle className="h-12 w-12 text-yellow-400 mx-auto" />
              <h3 className="text-xl font-bold text-white">Professors Cannot Join</h3>
              <p className="text-gray-400 text-sm">
                Only students can accept cohort invite links. Professors cannot join cohorts as students.
              </p>
              <Button
                onClick={() => router.push("/professor/cohorts")}
                className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all"
              >
                Go to Cohorts
              </Button>
            </div>
          </div>
        ) : null}
        </div>

        {/* Footer */}
        <div className="text-center mt-8">
          <Link href="/" className="text-gray-400 hover:text-white transition-colors text-sm">
            Return to home
          </Link>
        </div>
      </div>
    </div>
  )
}
