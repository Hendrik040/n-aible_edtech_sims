"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"

interface RoleBasedRedirectProps {
  children: React.ReactNode
}

// Paths that are part of the unified (app) route group — no redirect needed
const APP_PATHS = ['/dashboard', '/cohorts', '/simulations', '/notifications', '/profile', '/simulation-builder', '/edit-grading', '/run-simulation']

export default function RoleBasedRedirect({ children }: RoleBasedRedirectProps) {
  const { user, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && user) {
      const currentPath = window.location.pathname

      // Don't redirect if already on a unified app path or legacy role-specific path
      if (currentPath.startsWith('/professor/') || currentPath.startsWith('/student/')) {
        return
      }
      if (APP_PATHS.some(path => currentPath.startsWith(path))) {
        return
      }

      // Don't redirect from auth pages, landing page, or other non-dashboard pages
      if (currentPath === '/') {
        return
      }
      const skipRedirectPaths = ['/login', '/signup', '/auth', '/invite', '/admin', '/forgot-password', '/reset-password', '/test']
      if (skipRedirectPaths.some(path => currentPath.startsWith(path))) {
        return
      }

      // Redirect all roles to unified dashboard
      router.push('/dashboard')
    }
  }, [user, isLoading, router])

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

  return <>{children}</>
}
