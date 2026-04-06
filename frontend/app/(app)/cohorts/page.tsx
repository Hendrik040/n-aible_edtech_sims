"use client"

import { useAuth } from "@/lib/auth-context"
import ProfessorCohortsContent from "./ProfessorCohortsContent"
import StudentCohortsContent from "./StudentCohortsContent"

export default function UnifiedCohorts() {
  const { user } = useAuth()
  const isProfessor = user?.role === 'professor' || user?.role === 'admin'

  if (isProfessor) return <ProfessorCohortsContent />
  return <StudentCohortsContent />
}
