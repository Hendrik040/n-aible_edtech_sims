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

export default function LoginPage() {
  const router = useRouter()
  const { user, login, loginWithGoogle, linkGoogleAccount } = useAuth()
  
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [rememberMe, setRememberMe] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [showLinkingDialog, setShowLinkingDialog] = useState(false)
  const [linkingData, setLinkingData] = useState<AccountLinkingData | null>(null)

  // Handle redirect after successful login
  useEffect(() => {
    // Check if we're in a popup window
    const isPopup = window.opener !== null || window.parent !== window
    
    if (isPopup) {
      console.log('Main page: In popup context, preventing automatic redirection')
      // Don't redirect automatically when in popup - let the OAuth flow complete
      return
    }
    
    if (user && !loading) {
      console.log('Main page: User authenticated, redirecting based on role:', user.role)
      // User just logged in, redirect based on role
      if (user.role === 'professor' || user.role === 'admin') {
        console.log('Main page: Redirecting to professor dashboard')
        router.push('/professor/dashboard')
      } else if (user.role === 'student') {
        console.log('Main page: Redirecting to student dashboard')
        router.push('/student/dashboard')
      } else {
        console.log('Main page: Redirecting to generic dashboard')
        // Fallback to generic dashboard
        router.push('/dashboard')
      }
    }
  }, [user, loading, router])

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")

    try {
      await login(email, password)
      // Explicit redirect after successful login
      console.log('Login successful, redirecting to dashboard')
      router.push('/dashboard')
    } catch (error) {
      setError(error instanceof Error ? error.message : "Login failed. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  // Clear error when user starts typing
  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEmail(e.target.value)
    if (error) setError("")
  }

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPassword(e.target.value)
    if (error) setError("")
  }

  const handleGoogleLogin = async () => {
    console.log('Login Page: Starting Google login')
    setLoading(true)
    setError("")
    
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
    <div className="min-h-screen bg-black text-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 mb-6">
            <img src="/n-aiblelogo.png" alt="Logo" className="w-30 h-16" />
          </div>
          <h1 className="text-2xl font-semibold text-white">Log in to your account</h1>
        </div>

        {/* Google Login Button */}
        <Button
          onClick={handleGoogleLogin}
          variant="outline"
          className="w-full mb-6 bg-white text-black hover:bg-gray-100 border-gray-300"
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

        {/* OR Divider */}
        <div className="relative mb-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-600"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-black text-gray-400">OR</span>
          </div>
        </div>

        {/* Login Form */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email" className="text-white">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={handleEmailChange}
              className="bg-black border-gray-600 text-white placeholder-gray-400 focus:border-white"
              required
            />
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="password" className="text-white">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={handlePasswordChange}
              className="bg-black border-gray-600 text-white placeholder-gray-400 focus:border-white"
              required
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
            <Link href="#" className="text-white text-sm hover:underline">
              Forgot password?
            </Link>
          </div>

          {error && (
            <div className="bg-red-900/20 border border-red-500/50 rounded-md p-3 mb-4">
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
            className="w-full bg-white text-black hover:bg-gray-100"
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