"use client"

import { useAuth } from "@/lib/auth-context"
import { ProfilePage } from "@/components/ProfilePage"

export default function UnifiedProfilePage() {
  const { user } = useAuth()

  const role = user?.role === 'admin' ? 'professor' : (user?.role || 'student')

  return <ProfilePage role={role as 'professor' | 'student'} />
}
