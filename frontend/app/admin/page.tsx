"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { buildApiUrl } from "@/lib/api"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { toast } from "sonner"

interface Professor {
  id: number
  full_name: string
  email: string
  username: string
  avatar_url: string | null
}

export default function AdminPage() {
  const { user, isLoading } = useAuth()
  const router = useRouter()
  const [professors, setProfessors] = useState<Professor[]>([])
  const [search, setSearch] = useState("")
  const [loadingId, setLoadingId] = useState<number | null>(null)
  const [fetchError, setFetchError] = useState("")

  // Guard: redirect non-super_admin users
  useEffect(() => {
    if (!isLoading && user && user.role !== "super_admin") {
      router.replace(user.role === "student" ? "/student/dashboard" : "/professor/dashboard")
    }
    if (!isLoading && !user) {
      router.replace("/login")
    }
  }, [user, isLoading, router])

  useEffect(() => {
    if (!user || user.role !== "super_admin") return
    fetchProfessors()
  }, [user])

  const fetchProfessors = async () => {
    try {
      const res = await fetch(buildApiUrl("api/admin/professors"), {
        credentials: "include",
      })
      if (!res.ok) throw new Error("Failed to load professors")
      const data = await res.json()
      setProfessors(data)
    } catch {
      setFetchError("Could not load professor accounts.")
    }
  }

  const handleImpersonate = async (prof: Professor) => {
    setLoadingId(prof.id)
    try {
      const res = await fetch(buildApiUrl(`api/admin/impersonate/${prof.id}`), {
        method: "POST",
        credentials: "include",
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || "Impersonation failed")
      }
      const data = await res.json()

      // Store impersonation state in sessionStorage so the banner can read it
      sessionStorage.setItem("isImpersonating", "true")
      sessionStorage.setItem("impersonatedName", data.impersonated_user.full_name)
      sessionStorage.setItem("impersonatedEmail", data.impersonated_user.email)
      sessionStorage.setItem("adminRestoreToken", data.restore_token)

      // Clear cached user and force a full page reload so the new cookie is picked up fresh
      sessionStorage.removeItem("user")
      window.location.href = "/professor/dashboard"
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Impersonation failed")
      setLoadingId(null)
    }
  }

  const filtered = professors.filter(
    (p) =>
      p.full_name.toLowerCase().includes(search.toLowerCase()) ||
      p.email.toLowerCase().includes(search.toLowerCase())
  )

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent" />
      </div>
    )
  }

  if (!user || user.role !== "super_admin") return null

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <h1 className="text-xl font-semibold text-gray-900">Admin — Select a Professor Account</h1>
        <p className="text-sm text-gray-500 mt-0.5">Logged in as {user.email}</p>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Search */}
        <div className="mb-6">
          <Input
            placeholder="Search by name or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-white"
          />
        </div>

        {/* Error */}
        {fetchError && (
          <p className="text-red-600 text-sm mb-4">{fetchError}</p>
        )}

        {/* Professor list */}
        {filtered.length === 0 && !fetchError && (
          <p className="text-gray-500 text-sm text-center py-12">No professors found.</p>
        )}

        <div className="space-y-3">
          {filtered.map((prof) => (
            <div
              key={prof.id}
              className="bg-white rounded-lg border border-gray-200 px-5 py-4 flex items-center justify-between gap-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                <Avatar className="h-10 w-10 shrink-0">
                  {prof.avatar_url && <AvatarImage src={prof.avatar_url} alt={prof.full_name} />}
                  <AvatarFallback className="text-sm font-medium bg-blue-50 text-blue-700">
                    {prof.full_name
                      .split(" ")
                      .map((n) => n[0])
                      .join("")
                      .slice(0, 2)
                      .toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0">
                  <p className="font-medium text-gray-900 truncate">{prof.full_name}</p>
                  <p className="text-sm text-gray-500 truncate">{prof.email}</p>
                </div>
              </div>

              <Button
                size="sm"
                variant="outline"
                onClick={() => handleImpersonate(prof)}
                disabled={loadingId !== null}
                className="shrink-0"
              >
                {loadingId === prof.id ? (
                  <span className="flex items-center gap-2">
                    <span className="animate-spin rounded-full h-3 w-3 border border-gray-600 border-t-transparent" />
                    Entering…
                  </span>
                ) : (
                  `Enter as ${prof.full_name.split(" ")[0]}`
                )}
              </Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
