"use client"

import { useState, useEffect } from "react"
import type { FormEvent } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/lib/auth-context"

export default function SignupPage() {
  const router = useRouter()
  const { user, register } = useAuth()
  
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [selectedRole, setSelectedRole] = useState<"student" | "professor" | null>(null)
  const [formData, setFormData] = useState({
    email: "",
    full_name: "",
    password: "",
    role: "" as "student" | "professor" | "",
  })
  const [error, setError] = useState("")

  // Debug: Log error state changes
  useEffect(() => {
    console.log('Signup: Error state changed:', error, 'Length:', error?.length)
    if (error) {
      console.log('Signup: Error should be displayed in UI:', error)
    }
  }, [error])

  useEffect(() => {
    if (user && !loading && step === 1) {
      if (user.role === 'professor' || user.role === 'admin') {
        router.push('/professor/dashboard')
      } else if (user.role === 'student') {
        router.push('/student/dashboard')
      } else {
        router.push('/dashboard')
      }
    }
  }, [user, loading, router, step])

  const handleRoleSelect = (role: "student" | "professor") => {
    setSelectedRole(role)
    setFormData(prev => ({ ...prev, role }))
    setError("")
  }

  const handleContinue = () => {
    if (selectedRole) {
      setStep(2)
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")

    if (formData.password.length < 8) {
      setError("Password must be at least 8 characters long")
      setLoading(false)
      return
    }

    if (!formData.role || formData.role === "") {
      setError("Please select a role")
      setLoading(false)
      return
    }

    try {
      const username = formData.email.split('@')[0]
      const registerData = {
        email: formData.email,
        password: formData.password,
        full_name: formData.full_name || undefined,
        username: username,
        role: formData.role
      }
      console.log('Signup: Sending registration data:', { ...registerData, password: '[REDACTED]' })
      await register(registerData)
      
      if (typeof window !== 'undefined') {
        window.location.reload()
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Registration failed"
      console.log('Signup: Caught error, setting error state:', errorMessage)
      // Set error state - React will re-render automatically
      setError(errorMessage)
      console.log('Signup: Error state set to:', errorMessage)
    } finally {
      setLoading(false)
    }
  }

  if (step === 1) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
          <div className="absolute bottom-0 right-0 w-96 h-96 bg-green-500/10 rounded-full blur-3xl animate-pulse" style={{animationDelay: '1s'}}></div>
        </div>

        <button
          type="button"
          onClick={() => router.push('/login')}
          className="fixed top-4 left-4 z-20 inline-flex items-center gap-1.5 text-base text-white/85 hover:text-white transition-colors focus:outline-none backdrop-blur-sm bg-black/20 px-3 py-2 rounded-lg"
        >
          <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M12.707 15.707a1 1 0 01-1.414 0l-5-5a1 1 0 010-1.414l5-5a1 1 0 111.414 1.414L8.414 9H17a1 1 0 110 2H8.414l4.293 4.293a1 1 0 010 1.414z" clipRule="evenodd"/></svg>
          <span>Back</span>
        </button>

        <div className="w-full max-w-md relative z-10">
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center mb-4">
              <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
            </div>
            <h1 className="text-3xl font-bold text-white mb-2">Choose your role</h1>
            <p className="text-gray-400 text-sm">Select how you'll use the platform</p>
          </div>

          <div className="space-y-4">
            <button
              type="button"
              onClick={() => handleRoleSelect("student")}
              className={`w-full p-6 rounded-lg border-2 transition-all ${
                selectedRole === "student"
                  ? "border-blue-500 bg-blue-500/10"
                  : "border-gray-700 bg-gray-900/50 hover:border-gray-600"
              }`}
            >
              <h3 className="text-xl font-semibold mb-2">Student</h3>
              <p className="text-gray-400 text-sm">Participate in simulations and learn</p>
            </button>

            <button
              type="button"
              onClick={() => handleRoleSelect("professor")}
              className={`w-full p-6 rounded-lg border-2 transition-all ${
                selectedRole === "professor"
                  ? "border-blue-500 bg-blue-500/10"
                  : "border-gray-700 bg-gray-900/50 hover:border-gray-600"
              }`}
            >
              <h3 className="text-xl font-semibold mb-2">Professor</h3>
              <p className="text-gray-400 text-sm">Create and manage simulations</p>
            </button>
          </div>

          <Button
            onClick={handleContinue}
            disabled={!selectedRole}
            className="w-full mt-6 btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold"
          >
            Continue
          </Button>

          <div className="text-center mt-4">
            <span className="text-gray-400">Already have an account? </span>
            <Link href="/login" className="text-white hover:underline">
              Sign In
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-green-500/10 rounded-full blur-3xl animate-pulse" style={{animationDelay: '1s'}}></div>
      </div>

      <button
        type="button"
        onClick={() => setStep(1)}
        className="fixed top-4 left-4 z-20 inline-flex items-center gap-1.5 text-base text-white/85 hover:text-white transition-colors focus:outline-none backdrop-blur-sm bg-black/20 px-3 py-2 rounded-lg"
      >
        <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M12.707 15.707a1 1 0 01-1.414 0l-5-5a1 1 0 010-1.414l5-5a1 1 0 111.414 1.414L8.414 9H17a1 1 0 110 2H8.414l4.293 4.293a1 1 0 010 1.414z" clipRule="evenodd"/></svg>
        <span>Back</span>
      </button>

      <div className="w-full max-w-md relative z-10">
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center mb-4">
            <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">Create an account</h1>
          <p className="text-gray-400 text-sm">Join us and start your learning journey</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="full_name" className="text-white font-medium">Full Name</Label>
            <Input 
              id="full_name" 
              type="text" 
              placeholder="Enter your full name" 
              value={formData.full_name} 
              onChange={(e) => setFormData(prev => ({ ...prev, full_name: e.target.value }))} 
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg" 
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email" className="text-white font-medium">Email</Label>
            <Input 
              id="email" 
              type="email" 
              placeholder="Enter your email" 
              value={formData.email} 
              onChange={(e) => {
                setFormData(prev => ({ ...prev, email: e.target.value }))
                // Clear error when user starts typing
                if (error) setError("")
              }} 
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
              onChange={(e) => setFormData(prev => ({ ...prev, password: e.target.value }))} 
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg" 
              required 
            />
            <p className="text-sm text-gray-400">Password must be at least 8 characters</p>
          </div>

          {error && error.length > 0 && (
            <div className="bg-red-900/40 border-2 border-red-500 rounded-lg p-4 shadow-xl relative z-50 animate-in fade-in slide-in-from-top-2">
              <div className="flex items-start">
                <svg className="w-5 h-5 text-red-400 mr-3 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <div className="flex-1">
                  <p className="text-red-300 text-sm font-semibold mb-1">Registration Error</p>
                  <p className="text-red-200 text-sm font-medium">{error}</p>
                </div>
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

        <div className="text-center mt-4">
          <span className="text-gray-400">Already have an account? </span>
          <Link href="/login" className="text-white hover:underline font-medium">Sign In</Link>
        </div>
      </div>
    </div>
  )
}

