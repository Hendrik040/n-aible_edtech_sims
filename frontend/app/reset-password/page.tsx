"use client"

import { useState, useEffect, Suspense } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

function ResetPasswordForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get("token")

  const [newPassword, setNewPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    if (!token) {
      setError("No reset token found. Please request a new password reset link.")
    }
  }, [token])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)

    if (!newPassword || !confirmPassword) {
      setError("Please fill in both password fields.")
      return
    }

    if (newPassword.length < 6) {
      setError("Password must be at least 6 characters long.")
      return
    }

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.")
      return
    }

    if (!token) {
      setError("Invalid reset link. Please request a new one.")
      return
    }

    setLoading(true)
    try {
      const response = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.error || data.detail || "Failed to reset password.")
      }

      setSuccess(true)
      setTimeout(() => router.push("/"), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset password. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full max-w-md relative z-10 animate-fade-scale">
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center mb-6 animate-scale-in">
          <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
        </div>
        <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Set a new password</h1>
        <p className="text-gray-400 text-sm">
          Choose a new password for your account.
        </p>
      </div>

      {success ? (
        <div className="space-y-5">
          <div className="bg-emerald-900/20 border border-emerald-500/50 rounded-md p-4">
            <p className="text-emerald-400 text-sm font-medium">
              Password updated successfully! Redirecting you to login…
            </p>
          </div>
          <div className="text-center">
            <Link href="/" className="text-white hover:underline text-sm">
              Go to login now
            </Link>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          <div className="space-y-3">
            <Label htmlFor="newPassword" className="text-white font-medium">New password</Label>
            <Input
              id="newPassword"
              type="password"
              placeholder="At least 6 characters"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
            />
          </div>

          <div className="space-y-3">
            <Label htmlFor="confirmPassword" className="text-white font-medium">Confirm new password</Label>
            <Input
              id="confirmPassword"
              type="password"
              placeholder="Repeat your new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
            />
          </div>

          {error && (
            <div className="bg-red-900/20 border border-red-500/50 rounded-md p-3">
              <p className="text-red-400 text-sm font-medium">{error}</p>
              {(error.includes("invalid") || error.includes("expired")) && (
                <p className="text-red-400/70 text-xs mt-1">
                  <Link href="/forgot-password" className="underline hover:text-red-300">
                    Request a new reset link
                  </Link>
                </p>
              )}
            </div>
          )}

          <Button
            type="submit"
            className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold"
            disabled={loading || !token}
          >
            {loading ? "Updating password..." : "Update password"}
          </Button>
        </form>
      )}

      <div className="text-center mt-6">
        <span className="text-gray-400">Remembered your password? </span>
        <Link href="/" className="text-white hover:underline">
          Return to login
        </Link>
      </div>
    </div>
  )
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: "1s" }} />
      </div>
      <Suspense fallback={<div className="text-gray-400">Loading…</div>}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  )
}
