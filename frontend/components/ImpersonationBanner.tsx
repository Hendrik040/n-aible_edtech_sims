"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { buildApiUrl } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { toast } from "sonner"

export default function ImpersonationBanner() {
  const router = useRouter()
  const { refreshUser } = useAuth()
  const [impersonating, setImpersonating] = useState(false)
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [exiting, setExiting] = useState(false)

  useEffect(() => {
    const check = () => {
      const active = sessionStorage.getItem("isImpersonating") === "true"
      setImpersonating(active)
      if (active) {
        setName(sessionStorage.getItem("impersonatedName") || "")
        setEmail(sessionStorage.getItem("impersonatedEmail") || "")
      }
    }
    check()
    // Re-check on storage events (e.g. another tab clears impersonation)
    window.addEventListener("storage", check)
    return () => window.removeEventListener("storage", check)
  }, [])

  if (!impersonating) return null

  const handleExit = async () => {
    setExiting(true)
    const restoreToken = sessionStorage.getItem("adminRestoreToken")
    if (!restoreToken) {
      toast.error("Restore token missing — please log in again.")
      sessionStorage.clear()
      router.push("/login")
      return
    }
    try {
      const res = await fetch(buildApiUrl("api/admin/restore"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ restore_token: restoreToken }),
      })
      if (!res.ok) throw new Error("Failed to restore admin session")

      // Clear impersonation flags
      sessionStorage.removeItem("isImpersonating")
      sessionStorage.removeItem("impersonatedName")
      sessionStorage.removeItem("impersonatedEmail")
      sessionStorage.removeItem("adminRestoreToken")
      sessionStorage.removeItem("user")

      setImpersonating(false)
      await refreshUser()
      router.push("/admin")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to exit impersonation")
      setExiting(false)
    }
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-[9999] bg-orange-500 text-white px-4 py-2 flex items-center justify-between gap-4 shadow-md">
      <div className="flex items-center gap-2 text-sm font-medium min-w-0">
        <span className="shrink-0">⚠️</span>
        <span className="truncate">
          Viewing as <strong>{name}</strong>
          {email && <span className="font-normal opacity-80"> ({email})</span>}
        </span>
      </div>
      <button
        onClick={handleExit}
        disabled={exiting}
        className="shrink-0 text-sm font-semibold bg-white/20 hover:bg-white/30 transition-colors rounded px-3 py-1 disabled:opacity-60"
      >
        {exiting ? "Exiting…" : "Exit Admin View"}
      </button>
    </div>
  )
}
