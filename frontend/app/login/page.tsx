"use client"

import { useState, useEffect } from "react"
import type { FormEvent } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import ThemeToggle from "@/components/ThemeToggle"
import { useAuth } from "@/lib/auth-context"
import { toast } from "sonner"
import { GoogleOAuth } from "@/lib/google-oauth"

export default function LoginPage() {
  const router = useRouter()
  const { user, isLoading: authLoading, login } = useAuth()
  
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [isRedirecting, setIsRedirecting] = useState(false)
  const [error, setError] = useState("")
  const authPanelClassName =
    "w-full max-w-md relative z-10 animate-fade-scale rounded-[32px] border border-border/60 bg-background/70 p-8 shadow-2xl backdrop-blur-xl"
  const authInputClassName =
    "rounded-lg border-border/60 bg-background/70 text-foreground placeholder:text-muted-foreground shadow-sm backdrop-blur-sm transition-all focus-visible:ring-2 focus-visible:ring-blue-500/30 focus-visible:ring-offset-0"

  useEffect(() => {
    if (authLoading) return
    
    if (user && !error) {
      setIsRedirecting(true)
      if (user.role === 'professor' || user.role === 'admin') {
        router.push('/professor/dashboard')
      } else if (user.role === 'student') {
        router.push('/student/dashboard')
      } else {
        router.push('/dashboard')
      }
    }
  }, [user, authLoading, router, error])

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")
    
    try {
      await login(email, password)
      // Don't set loading to false on success - let the redirect happen
      setIsRedirecting(true)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Login failed. Please check your email and password."
      setError(errorMessage)
      toast.error("Login Failed", {
        description: errorMessage,
        duration: 5000,
      })
      setLoading(false)
    }
  }

  const handleGoogleLogin = async () => {
    setLoading(true)
    setError("")
    
    try {
      const googleOAuth = GoogleOAuth.getInstance()
      const result = await googleOAuth.openAuthWindow()
      
      if (result && 'user' in result) {
        setIsRedirecting(true)
        window.location.reload()
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Google login failed"
      setError(errorMessage)
      toast.error("Google Login Failed", {
        description: errorMessage,
        duration: 5000,
      })
    } finally {
      setLoading(false)
    }
  }

  // Show loading overlay during auth check, form submission, or redirect
  if (authLoading || isRedirecting) {
    return (
      <div className="auth-shell min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="relative">
            <div className="w-16 h-16 border-4 border-blue-500/30 rounded-full"></div>
            <div className="absolute top-0 left-0 w-16 h-16 border-4 border-transparent border-t-blue-500 rounded-full animate-spin"></div>
          </div>
          <p className="text-lg font-medium text-foreground/80">
            {isRedirecting ? "Signing you in..." : "Loading..."}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-shell pattern-grid relative flex min-h-screen items-center justify-center overflow-hidden p-4 text-foreground">
      <ThemeToggle className="fixed right-4 top-4 z-20" />
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="auth-glow-primary absolute top-0 left-0 h-96 w-96 rounded-full blur-3xl animate-pulse"></div>
        <div className="auth-glow-secondary absolute bottom-0 right-0 h-96 w-96 rounded-full blur-3xl animate-pulse" style={{ animationDelay: "1s" }}></div>
      </div>
      
      <div className={authPanelClassName}>
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center mb-6 animate-scale-in">
            <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
          </div>
          <h1 className="mb-2 text-3xl font-bold tracking-tight text-foreground">Log in to your account</h1>
          <p className="text-sm text-muted-foreground">Welcome back! Please enter your details.</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div className="space-y-3">
            <Label htmlFor="email" className="font-medium text-foreground">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                if (error) setError("")
              }}
              className={authInputClassName}
              required
            />
          </div>
          
          <div className="space-y-3">
            <Label htmlFor="password" className="font-medium text-foreground">Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                if (error) setError("")
              }}
              className={authInputClassName}
              required
            />
          </div>

          {error && error.length > 0 && (
            <div className="relative z-50 rounded-lg border border-red-500/30 bg-red-500/10 p-4 shadow-xl animate-in fade-in slide-in-from-top-2">
              <div className="flex items-start">
                <svg className="w-5 h-5 text-red-400 mr-3 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <div className="flex-1">
                  <p className="mb-1 text-sm font-semibold text-red-500 dark:text-red-300">Login Error</p>
                  <p className="text-sm font-medium text-red-600 dark:text-red-200">{error}</p>
                </div>
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

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border/70"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="bg-background/85 px-4 text-muted-foreground">or</span>
            </div>
          </div>

          {/* Google Sign In Button */}
          <Button
            type="button"
            variant="outline"
            className="h-11 w-full border-border/70 bg-background/80 font-medium text-foreground shadow-sm hover:bg-background hover:text-foreground"
            onClick={handleGoogleLogin}
            disabled={loading}
          >
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Continue with Google
          </Button>
        </form>

        <div className="text-center mt-6">
          <span className="text-muted-foreground">Don't have an account yet? </span>
          <Link href="/signup" className="text-foreground hover:underline">
            Sign up now
          </Link>
        </div>
      </div>
    </div>
  )
}
