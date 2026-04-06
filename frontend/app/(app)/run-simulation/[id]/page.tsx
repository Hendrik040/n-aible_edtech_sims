"use client"

import { useAuth } from "@/lib/auth-context"
import StudentRunSimulationContent from "./StudentRunSimulationContent"

export default function UnifiedRunSimulation() {
  // For now, only students use this route. Professors test via /simulations
  return <StudentRunSimulationContent />
}
