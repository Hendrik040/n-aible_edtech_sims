"use client"

import { useState } from "react"
import type { FormEvent } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiClient } from "@/lib/api"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [message, setMessage] = useState("")
  const [error, setError] = useState("")

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError("")

    try {
      const result = await apiClient.requestPasswordReset({ email: email.trim() })
      setMessage(
        result?.message ||
          "If an account exists with this email, a reset link has been sent."
      )
      setSubmitted(true)
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Unable to send reset email. Please try again."
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div
          className="absolute bottom-0 right-0 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse"
          style={{ animationDelay: "1s" }}
        ></div>
      </div>

      <div className="w-full max-w-md relative z-10 animate-fade-scale">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center mb-6 animate-scale-in">
            <img
              src="/n-aiblelogo.png"
              alt="Logo"
              className="h-16 w-auto opacity-95 object-contain"
            />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">
            Forgot your password?
          </h1>
          <p className="text-gray-400 text-sm">
            Enter your email and we'll send you a link to reset it.
          </p>
        </div>

        {submitted ? (
          <div
            data-testid="forgot-password-success"
            className="bg-green-900/30 border border-green-500/60 rounded-lg p-6 text-center space-y-4"
          >
            <h2 className="text-xl font-semibold text-green-200">Check your inbox</h2>
            <p className="text-green-100 text-sm">{message}</p>
            <p className="text-green-100/70 text-xs">
              The reset link will expire in 1 hour. Don't forget to check your spam folder.
            </p>
            <Link
              href="/login"
              className="inline-block text-white underline hover:text-green-200"
            >
              Back to login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div className="space-y-3">
              <Label htmlFor="email" className="text-white font-medium">
                Email
              </Label>
              <Input
                id="email"
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  if (error) setError("")
                }}
                className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
                required
              />
            </div>

            {error && error.length > 0 && (
              <div
                data-testid="forgot-password-error"
                className="bg-red-900/40 border-2 border-red-500 rounded-lg p-4"
              >
                <p className="text-red-200 text-sm font-medium">{error}</p>
              </div>
            )}

            <Button
              type="submit"
              className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold"
              disabled={loading}
            >
              {loading ? "Sending..." : "Send reset link"}
            </Button>

            <div className="text-center mt-6">
              <Link href="/login" className="text-gray-400 hover:text-white transition-colors">
                ← Back to login
              </Link>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
