"use client"

import { Suspense, useState } from "react"
import type { FormEvent } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { apiClient } from "@/lib/api"

function ResetPasswordForm() {
  const searchParams = useSearchParams()
  const token = searchParams.get("token") || ""

  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState(false)

  if (!token) {
    return (
      <div
        data-testid="reset-password-missing-token"
        className="bg-red-900/30 border border-red-500/60 rounded-lg p-6 text-center space-y-4"
      >
        <h2 className="text-xl font-semibold text-red-200">Invalid reset link</h2>
        <p className="text-red-100 text-sm">
          This password reset link is missing a token. Please request a new one from the forgot
          password page.
        </p>
        <Link href="/forgot-password" className="inline-block text-white underline">
          Request a new link
        </Link>
      </div>
    )
  }

  if (success) {
    return (
      <div
        data-testid="reset-password-success"
        className="bg-green-900/30 border border-green-500/60 rounded-lg p-6 text-center space-y-4"
      >
        <h2 className="text-xl font-semibold text-green-200">Password reset</h2>
        <p className="text-green-100 text-sm">
          Your password has been updated. You can now log in with your new password.
        </p>
        <Link
          href="/login"
          className="inline-block bg-white text-gray-900 font-semibold px-4 py-2 rounded-md hover:bg-green-100"
        >
          Go to login
        </Link>
      </div>
    )
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError("")

    if (password.length < 6) {
      setError("New password must be at least 6 characters long.")
      return
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    setLoading(true)
    try {
      await apiClient.resetPassword({ token, new_password: password })
      setSuccess(true)
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Unable to reset password. Please try again."
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <div className="space-y-3">
        <Label htmlFor="password" className="text-white font-medium">
          New password
        </Label>
        <Input
          id="password"
          type="password"
          placeholder="At least 6 characters"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value)
            if (error) setError("")
          }}
          className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
          required
          minLength={6}
        />
      </div>

      <div className="space-y-3">
        <Label htmlFor="confirmPassword" className="text-white font-medium">
          Confirm new password
        </Label>
        <Input
          id="confirmPassword"
          type="password"
          placeholder="Retype your new password"
          value={confirmPassword}
          onChange={(e) => {
            setConfirmPassword(e.target.value)
            if (error) setError("")
          }}
          className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
          required
          minLength={6}
        />
      </div>

      {error && error.length > 0 && (
        <div
          data-testid="reset-password-error"
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
        {loading ? "Resetting..." : "Reset password"}
      </Button>

      <div className="text-center mt-6">
        <Link href="/login" className="text-gray-400 hover:text-white transition-colors">
          ← Back to login
        </Link>
      </div>
    </form>
  )
}

export default function ResetPasswordPage() {
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
            Set a new password
          </h1>
          <p className="text-gray-400 text-sm">
            Enter a new password for your account.
          </p>
        </div>

        <Suspense fallback={<p className="text-gray-400 text-center">Loading…</p>}>
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  )
}
