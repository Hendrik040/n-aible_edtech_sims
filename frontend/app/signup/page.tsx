"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import { useAuth } from "@/lib/auth-context"
import { AccountLinkingDialog } from "@/components/AccountLinkingDialog"
import { AccountLinkingData } from "@/lib/google-oauth"
import RoleChooser from "@/components/RoleChooser"

// Reusable white-dot progress indicator
function ProgressDots({ currentStep, totalSteps = 2 }: { currentStep: number; totalSteps?: number }) {
  return (
    <div className="flex justify-center gap-2 my-2" aria-label="Signup progress">
      {Array.from({ length: totalSteps }).map((_, index) => (
        <div
          key={index}
          className={`w-2 h-2 rounded-full ${index < currentStep ? 'bg-white' : 'bg-white/30'}`}
        />
      ))}
    </div>
  )
}

export default function SignupPage() {
  const router = useRouter()
  const { user, register, loginWithGoogle, linkGoogleAccount } = useAuth()
  
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  
  // Debug logging
  console.log("🔍 Current step:", step)
  
  // Handle redirect after successful Google OAuth registration
  useEffect(() => {
    // Check if we're in a popup window
    const isPopup = window.opener !== null || window.parent !== window
    
    if (isPopup) {
      console.log('Signup page: In popup context, preventing automatic redirection')
      // Don't redirect automatically when in popup - let the OAuth flow complete
      return
    }
    
    // Only redirect if user is authenticated AND we're not in the middle of a registration attempt
    if (user && !loading && step === 1) {
      // User just registered via Google OAuth, redirect based on role
      console.log("🔄 User authenticated via Google OAuth, redirecting based on role:", user.role)
      if (user.role === 'professor' || user.role === 'admin') {
        router.push('/professor/dashboard')
      } else if (user.role === 'student') {
        router.push('/student/dashboard')
      } else {
        // Fallback to generic dashboard
        router.push('/dashboard')
      }
    }
  }, [user, loading, router, step])
  
  const [selectedRole, setSelectedRole] = useState<"student" | "professor" | null>(null)
  const [formData, setFormData] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "" as "student" | "professor" | "",
    profile_public: true,
    allow_contact: true
  })
  const [error, setError] = useState("")
  const [showLinkingDialog, setShowLinkingDialog] = useState(false)
  const [linkingData, setLinkingData] = useState<AccountLinkingData | null>(null)

  const handleInputChange = (field: string, value: string | boolean) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }))
  }

  const handleRoleSelect = (role: "student" | "professor") => {
    console.log("🎯 Role selected:", role)
    setSelectedRole(role)
    setFormData(prev => ({ ...prev, role }))
    setError("") // Clear any existing error
    // Don't automatically move to step 2 - let user confirm with Continue button
    console.log("📝 Form data after role selection:", { ...formData, role })
  }

  const handleContinue = () => {
    if (selectedRole) {
      console.log("🔄 Moving to step 2 with role:", selectedRole)
      setStep(2)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")
    
    console.log("🚀 Submitting registration with data:", formData)

    // Validate password length
    if (formData.password.length < 6) {
      setError("Password must be at least 6 characters long")
      setLoading(false)
      return
    }

    try {
      // First, check if email already exists
      console.log("🔍 Checking if email already exists:", formData.email)
      const checkResponse = await fetch('/api/auth/check-email', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: formData.email })
      })
      
      if (checkResponse.ok) {
        const checkData = await checkResponse.json()
        if (checkData.exists) {
          setError("Existing User Already Registered.")
          setLoading(false)
          return
        }
      }
      
      // Generate username from email if not provided
      const username = formData.email.split('@')[0]
      const registerData = {
        ...formData,
        username: username
      }
      await register(registerData)
      
      // Force a full reload so HttpOnly cookie auth state is picked up immediately
      if (typeof window !== 'undefined') {
        window.location.reload()
      }
      // Redirect will be handled by the auth-state effect once user is set
      // router.push('/')
    } catch (error) {
      setError(error instanceof Error ? error.message : "Registration failed")
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSignup = async () => {
    setLoading(true)
    setError("")
    
    try {
      const result = await loginWithGoogle()
      
      if ('action' in result && result.action === 'link_required') {
        // Show account linking dialog
        setLinkingData(result as AccountLinkingData)
        setShowLinkingDialog(true)
      } else {
        // Direct login success
        router.push("/dashboard")
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : "Google signup failed. Please try again.")
    } finally {
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

  // Step 1: Role Selection
  if (step === 1) {
    console.log("🎯 Rendering Step 1 - Role Selection")
    return (
      <>
        {/* Top bar: Back + Centered Progress */}
        <button
          type="button"
          onClick={() => router.push('/')}
          className="fixed top-4 left-4 z-20 inline-flex items-center gap-1.5 text-base text-white/85 hover:text-white transition-colors focus:outline-none backdrop-blur-sm bg-black/20 px-3 py-2 rounded-lg"
          aria-label="Go back to Login"
        >
          <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M12.707 15.707a1 1 0 01-1.414 0l-5-5a1 1 0 010-1.414l5-5a1 1 0 111.414 1.414L8.414 9H17a1 1 0 110 2H8.414l4.293 4.293a1 1 0 010 1.414z" clipRule="evenodd"/></svg>
          <span>Back</span>
        </button>
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-10">
          <ProgressDots currentStep={1} totalSteps={2} />
        </div>

        <RoleChooser
          selectedRole={selectedRole}
          onRoleSelect={handleRoleSelect}
          onContinue={handleContinue}
          showContinueButton={true}
          variant="detailed"
          className="relative"
        />
        
        {/* Sign In Link */}
        <div className="fixed bottom-4 left-1/2 transform -translate-x-1/2 text-center z-30">
          <span className="text-gray-400">Already have an account? </span>
          <Link href="/" className="text-white hover:underline">
            Sign In
          </Link>
        </div>
      </>
    )
  }

  // Step 2: Registration Form
  console.log("🎯 Rendering Step 2 - Registration Form")
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-green-500/10 rounded-full blur-3xl animate-pulse" style={{animationDelay: '1s'}}></div>
      </div>
      
      {/* Back + Centered Progress */}
      <button
        type="button"
        onClick={() => setStep(1)}
        className="fixed top-4 left-4 z-20 inline-flex items-center gap-1.5 text-base text-white/85 hover:text-white transition-colors focus:outline-none backdrop-blur-sm bg-black/20 px-3 py-2 rounded-lg"
        aria-label="Go back to Role Selection"
      >
        <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fillRule="evenodd" d="M12.707 15.707a1 1 0 01-1.414 0l-5-5a1 1 0 010-1.414l5-5a1 1 0 111.414 1.414L8.414 9H17a1 1 0 110 2H8.414l4.293 4.293a1 1 0 010 1.414z" clipRule="evenodd"/></svg>
        <span>Back</span>
      </button>
      <div className="fixed top-4 left-1/2 -translate-x-1/2 z-10">
        <ProgressDots currentStep={2} totalSteps={2} />
      </div>

      <div className="w-full max-w-md relative z-10 animate-fade-scale">
        {/* Logo */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center mb-4 animate-scale-in">
            <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Create an account</h1>
          <p className="text-gray-400 text-sm">Join us and start your learning journey</p>
        </div>

        {/* Google Signup Button - Hidden for now */}
        {/* <Button
          onClick={handleGoogleSignup}
          variant="outline"
          className="w-full mb-4 bg-white/95 backdrop-blur-sm text-black hover:bg-white border-gray-300/50 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-medium py-3"
        >
          <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
          </svg>
          Sign up with Google
        </Button>

        <div className="relative mb-4">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-600"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-black text-gray-400">OR</span>
          </div>
        </div> */}

        {/* Signup Form */}
        <form onSubmit={handleSubmit} className="space-y-4 flex-1">
          <div className="space-y-2">
            <Label htmlFor="full_name" className="text-white font-medium">Full Name</Label>
            <Input 
              id="full_name" 
              type="text" 
              placeholder="Enter your full name" 
              value={formData.full_name} 
              onChange={(e) => handleInputChange("full_name", e.target.value)} 
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg" 
              required 
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email" className="text-white font-medium">Email</Label>
            <Input 
              id="email" 
              type="email" 
              placeholder="Enter your email" 
              value={formData.email} 
              onChange={(e) => handleInputChange("email", e.target.value)} 
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg" 
              required 
            />
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="password" className="text-white font-medium">Password</Label>
            <Input 
              id="password" 
              type="password" 
              placeholder="Create a password" 
              value={formData.password} 
              onChange={(e) => handleInputChange("password", e.target.value)} 
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg" 
              required 
            />
            <p className="text-sm text-gray-400">Password must be at least 6 characters</p>
          </div>

          {error && (
            <div className="bg-red-900/20 border border-red-500/50 rounded-md p-3">
              <div className="flex items-center">
                <svg className="w-5 h-5 text-red-400 mr-2 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <p className="text-red-400 text-sm font-medium">{error}</p>
              </div>
            </div>
          )}
          

          <Button 
            type="submit" 
            className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold" 
            disabled={loading}
          >
            {loading ? "Creating account..." : "Sign Up"}
          </Button>
        </form>

        {/* Login link */}
        <div className="text-center mt-4">
          <span className="text-gray-400">Already have an account? </span>
          <Link href="/" className="text-white hover:underline font-medium">Sign In</Link>
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