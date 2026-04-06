"use client"

import { useAuth } from "@/lib/auth-context"
import ProfessorSimulationsContent from "./ProfessorSimulationsContent"
import StudentSimulationsContent from "./StudentSimulationsContent"

export default function UnifiedSimulations() {
  const { user } = useAuth()
  const isProfessor = user?.role === 'professor' || user?.role === 'admin'

  if (isProfessor) return <ProfessorSimulationsContent />
  return <StudentSimulationsContent />
}
