"use client"

import { useState, useEffect } from "react"
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
  const [authMode, setAuthMode] = useState<"login" | "signup">("login")
  
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
      if (!user || user.role !== "student" || !token || !inviteData || accepting || success) {
        return
      }

      // User just logged in/signed up, automatically accept the invite
      try {
        setAccepting(true)
        setError(null)
        await apiClient.acceptInviteLink(token)
        setSuccess(true)
        
        // Redirect to student dashboard after a brief delay
        setTimeout(() => {
          router.push("/student/dashboard")
        }, 2000)
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to join cohort")
        setAccepting(false)
      }
    }

    autoAcceptInvite()
  }, [user, token, inviteData, accepting, success, router])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginLoading(true)
    setError(null)

    try {
      await login(email, password)
      // Auto-accept will happen in useEffect when user state updates
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Please try again.")
      setLoginLoading(false)
    }
  }

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    setSignupLoading(true)
    setError(null)

    // Validate password length
    if (signupData.password.length < 6) {
      setError("Password must be at least 6 characters long")
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
          setError("An account with this email already exists. Please sign in instead.")
          setSignupLoading(false)
          setAuthMode("login")
          setEmail(signupData.email)
          return
        }
      }

      // Generate username from email
      const username = signupData.email.split('@')[0]
      const registerData = {
        ...signupData,
        username: username,
        profile_public: true,
        allow_contact: true
      }
      
      await register(registerData)
      
      // Force reload to pick up auth state
      if (typeof window !== 'undefined') {
        window.location.reload()
      }
      // Auto-accept will happen in useEffect when user state updates
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed. Please try again.")
      setSignupLoading(false)
    }
  }

  const handleAccept = async () => {
    if (user.role !== "student") {
      setError("Only students can accept cohort invite links")
      return
    }

    try {
      setAccepting(true)
      setError(null)
      await apiClient.acceptInviteLink(token)
      setSuccess(true)
      
      setTimeout(() => {
        router.push("/student/dashboard")
      }, 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invite link")
      setAccepting(false)
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

  if (success) {
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
          {!user || user.role !== "student" ? (
            <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-700/50 rounded-2xl p-6 shadow-xl">
            {/* Tab Switcher */}
            <div className="flex gap-2 mb-6 bg-gray-800/50 rounded-lg p-1">
              <button
                type="button"
                onClick={() => {
                  setAuthMode("login")
                  setError(null)
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

            {error && (
              <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-3 mb-4">
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
                  <p className="text-red-400 text-sm font-medium">{error}</p>
                </div>
              </div>
            )}

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
                      setError(null)
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
                      setError(null)
                    }}
                    className="bg-gray-800/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
                    required
                  />
                </div>

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
                      setError(null)
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
                      setError(null)
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
                      setError(null)
                    }}
                    className="bg-gray-800/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
                    required
                    minLength={6}
                  />
                </div>

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
                    }}
                    className="text-white hover:underline font-medium"
                  >
                    Sign in
                  </button>
                </>
              )}
            </p>
          </div>
        ) : (
          /* Already authenticated as student - show join button */
          <div className="bg-gray-900/50 backdrop-blur-sm border border-gray-700/50 rounded-2xl p-6 shadow-xl">
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
          </div>
          )}
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
