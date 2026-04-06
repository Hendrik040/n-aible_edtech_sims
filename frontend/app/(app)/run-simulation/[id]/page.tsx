"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import StudentRunSimulationContent from "./StudentRunSimulationContent"

export default function UnifiedRunSimulation() {
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const isProfessor = user?.role === "professor" || user?.role === "admin"

  useEffect(() => {
    if (!isLoading && isProfessor) {
      router.replace("/simulations")
    }
  }, [isLoading, isProfessor, router])

  if (isLoading || isProfessor) return null
  return <StudentRunSimulationContent />
}
