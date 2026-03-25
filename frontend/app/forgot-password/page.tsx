"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import ThemeToggle from "@/components/ThemeToggle"

export default function ForgotPasswordPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [confirmEmail, setConfirmEmail] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const authInputClassName =
    "rounded-lg border-border/60 bg-background/70 text-foreground placeholder:text-muted-foreground shadow-sm backdrop-blur-sm transition-all focus-visible:ring-2 focus-visible:ring-blue-500/30 focus-visible:ring-offset-0"

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
    <div className="auth-shell pattern-grid relative flex min-h-screen items-center justify-center overflow-hidden p-4 text-foreground">
      <ThemeToggle className="fixed right-4 top-4 z-20" />
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="auth-glow-primary absolute top-0 left-0 h-96 w-96 rounded-full blur-3xl animate-pulse" />
        <div className="auth-glow-secondary absolute bottom-0 right-0 h-96 w-96 rounded-full blur-3xl animate-pulse" style={{ animationDelay: "1s" }} />
      </div>

      <div className="relative z-10 w-full max-w-md animate-fade-scale rounded-[32px] border border-border/60 bg-background/70 p-8 shadow-2xl backdrop-blur-xl">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center mb-6 animate-scale-in">
            <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto opacity-95 object-contain" />
          </div>
          <h1 className="mb-2 text-3xl font-bold tracking-tight text-foreground">Reset your password</h1>
          <p className="text-sm text-muted-foreground">
            Confirm your email and set a new password for your account.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          <div className="space-y-3">
            <Label htmlFor="email" className="font-medium text-foreground">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="Enter your email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={authInputClassName}
            />
          </div>

          <div className="space-y-3">
            <Label htmlFor="confirmEmail" className="font-medium text-foreground">Confirm Email</Label>
            <Input
              id="confirmEmail"
              type="email"
              placeholder="Retype your email"
              value={confirmEmail}
              onChange={(event) => setConfirmEmail(event.target.value)}
              className={authInputClassName}
            />
          </div>

          <div className="space-y-3">
            <Label htmlFor="newPassword" className="font-medium text-foreground">New Password</Label>
            <Input
              id="newPassword"
              type="password"
              placeholder="Create a new password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              className={authInputClassName}
            />
          </div>

          {error && (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3">
              <p className="text-sm font-medium text-red-600 dark:text-red-200">{error}</p>
            </div>
          )}

          {success && (
            <div className="rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3">
              <p className="text-sm font-medium text-emerald-700 dark:text-emerald-200">{success}</p>
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
          <span className="text-muted-foreground">Remembered your password? </span>
          <Link href="/" className="text-foreground hover:underline">
            Return to login
          </Link>
        </div>
      </div>
    </div>
  )
}
