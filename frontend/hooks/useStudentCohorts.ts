"use client"

import { useState, useCallback } from "react"
import { apiClient } from "@/lib/api"

interface Cohort {
  id: number
  unique_id: string
  title: string
  description?: string
  professor?: { name: string }
  is_active: boolean
  student_count?: number
  enrollment_date?: string
}

interface SimulationInstance {
  id: number
  unique_id: string
  status: string
  completion_percentage: number
  created_at: string
  cohort_assignment?: {
    simulation_id: number
    due_date?: string
    is_required?: boolean
    simulation?: {
      title: string
      description: string
      is_draft?: boolean
    }
  }
}

interface CohortWithSimulations extends Cohort {
  simulations: any[]
}

export function useStudentCohorts() {
  const [cohorts, setCohorts] = useState<CohortWithSimulations[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchCohorts = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Fetch cohorts and all instances in parallel to eliminate N+1 API pattern
      // Note: We use getStudentSimulationInstances() (all instances) instead of
      // getStudentCohortSimulations() per cohort because:
      // 1. getStudentCohortSimulations returns assignments, not instances
      // 2. We need instance data (unique_id, status, progress) for navigation and display
      // 3. Fetching all instances once eliminates N+1 queries (1 call vs N calls)
      const [cohortsData, allInstances] = await Promise.all([
        apiClient.getStudentCohorts(),
        apiClient.getStudentSimulationInstances() // Single call for all instances
      ])
      
      // Create a map of cohort_id -> instances for efficient lookup
      // Instances include cohort_assignment.cohort.id in the response
      const instancesByCohortId = new Map<number, SimulationInstance[]>()
      for (const instance of allInstances || []) {
        const cohortId = instance.cohort_assignment?.cohort?.id
        if (cohortId) {
          if (!instancesByCohortId.has(cohortId)) {
            instancesByCohortId.set(cohortId, [])
          }
          instancesByCohortId.get(cohortId)!.push(instance)
        }
      }
      
      // Map cohorts with their instances (no additional API calls needed)
      const cohortsWithSimulations = (cohortsData || []).map((cohort: Cohort) => {
        const instances = instancesByCohortId.get(cohort.id) || []
        
        // Transform instances to match expected format
        const simulations = instances.map((instance: SimulationInstance) => ({
          id: instance.id,
          unique_id: instance.unique_id, // Important for navigation!
          simulation_id: instance.cohort_assignment?.simulation_id,
          title: instance.cohort_assignment?.simulation?.title || 'Untitled Simulation',
          description: instance.cohort_assignment?.simulation?.description || '',
          status: instance.status, // not_started, in_progress, completed, submitted, graded
          progress: instance.completion_percentage || 0,
          assigned_at: instance.created_at,
          due_date: instance.cohort_assignment?.due_date,
          is_required: instance.cohort_assignment?.is_required,
          is_draft: instance.cohort_assignment?.simulation?.is_draft
        }))
        
        return { ...cohort, simulations }
      })
      
      setCohorts(cohortsWithSimulations)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch student cohorts'
      console.error('Error fetching student cohorts:', err)
      setError(errorMessage)
      setCohorts([])
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    cohorts,
    loading,
    error,
    fetchCohorts,
    refreshCohorts: fetchCohorts // Alias for clarity
  }
}

