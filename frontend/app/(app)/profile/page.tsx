"use client"

import { useAuth } from "@/lib/auth-context"
import { ProfilePage } from "@/components/ProfilePage"

export default function UnifiedProfilePage() {
  const { user } = useAuth()
  const role = (user?.role === 'professor' || user?.role === 'admin') ? 'professor' : 'student'

  return <ProfilePage role={role} embedded />
}
