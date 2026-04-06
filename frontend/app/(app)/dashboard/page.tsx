"use client"

import { useAuth } from "@/lib/auth-context"
import ProfessorDashboardContent from "./ProfessorDashboardContent"
import StudentDashboardContent from "./StudentDashboardContent"

export default function UnifiedDashboard() {
  const { user } = useAuth()
  const isProfessor = user?.role === 'professor' || user?.role === 'admin'

  if (isProfessor) return <ProfessorDashboardContent />
  return <StudentDashboardContent />
}
