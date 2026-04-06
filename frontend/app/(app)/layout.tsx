"use client"

import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const { user, isLoading } = useAuth()

  // Auth loading state
  if (isLoading) {
    return (
      <div className="min-h-screen bg-atmospheric relative pattern-dots flex items-center justify-center">
        <div className="text-center animate-fade-scale">
          <div className="w-16 h-16 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center mx-auto mb-4 shadow-sm">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
          </div>
          <p className="text-gray-900 font-semibold text-lg">Loading...</p>
        </div>
      </div>
    )
  }

  // Not authenticated — redirect to login
  if (!user) {
    router.push("/login")
    return null
  }

  return (
    <div className="min-h-screen bg-atmospheric relative pattern-dots">
      <RoleBasedSidebar />
      <main className="ml-20">
        {children}
      </main>
    </div>
  )
}
