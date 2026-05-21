"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export default function ForgotPasswordPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [confirmEmail, setConfirmEmail] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)
    setSuccess(null)

    if (!email.trim() || !confirmEmail.trim() || !newPassword.trim()) {
      setError("Please complete all fields.")
      return
    }

    if (email.trim().toLowerCase() !== confirmEmail.trim().toLowerCase()) {
      setError("Emails do not match.")
      return
    }

    if (newPassword.trim().length < 6) {
      setError("New password must be at least 6 characters long.")
      return
    }

    setLoading(true)
    try {
      const response = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          confirm_email: confirmEmail,
          new_password: newPassword,
        }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || data.message || "Failed to reset password.")
      }

      setSuccess("Password updated successfully! You can now log in with your new password.")
      setEmail("")
      setConfirmEmail("")
      setNewPassword("")
      // Redirect back to login after a short delay
      setTimeout(() => router.push("/"), 3000)
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError("Failed to reset password. Please try again.")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: "1s" }} />
      </div>

      <div className="w-full max-w-md relative z-10 animate-fade-scale">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center mb-6 animate-scale-in">
            <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Reset your password</h1>
          <p className="text-gray-400 text-sm">
            Confirm your email and set a new password for your account.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          <div className="space-y-3">
            <Label htmlFor="email" className="text-white font-medium">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
            />
          </div>

          <div className="space-y-3">
            <Label htmlFor="confirmEmail" className="text-white font-medium">Confirm Email</Label>
            <Input
              id="confirmEmail"
              type="email"
              placeholder="Retype your email"
              value={confirmEmail}
              onChange={(event) => setConfirmEmail(event.target.value)}
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
            />
          </div>

          <div className="space-y-3">
            <Label htmlFor="newPassword" className="text-white font-medium">New Password</Label>
            <Input
              id="newPassword"
              type="password"
              placeholder="Create a new password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className="bg-gray-900/50 backdrop-blur-sm border-gray-700 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 transition-all rounded-lg"
            />
          </div>

          {error && (
            <div className="bg-red-900/20 border border-red-500/50 rounded-md p-3">
              <p className="text-red-400 text-sm font-medium">{error}</p>
            </div>
          )}

          {success && (
            <div className="bg-emerald-900/20 border border-emerald-500/50 rounded-md p-3">
              <p className="text-emerald-400 text-sm font-medium">{success}</p>
            </div>
          )}

          <Button
            type="submit"
            className="w-full btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold"
            disabled={loading}
          >
            {loading ? "Updating password..." : "Update password"}
          </Button>
        </form>

        <div className="text-center mt-6">
          <span className="text-gray-400">Remembered your password? </span>
          <Link href="/" className="text-white hover:underline">
            Return to login
          </Link>
        </div>
      </div>
    </div>
  )
}

