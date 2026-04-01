"use client"

import { useState, useEffect, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Search,
  BookOpen,
  Trophy,
  Users,
  Calendar,
  Play,
  Crown,
  Shield,
  Clock,
  RefreshCw
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { useStudentCohorts } from "@/hooks/useStudentCohorts"

export default function StudentMyCohorts() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, logout, isLoading: authLoading } = useAuth()

  const [searchTerm, setSearchTerm] = useState("")
  const [statusFilter, setStatusFilter] = useState("All Status")
  const [expandedDescriptions, setExpandedDescriptions] = useState<Set<string>>(new Set())
  const [startingSimulation, setStartingSimulation] = useState<string | null>(null)
  const [selectedCohortId, setSelectedCohortId] = useState<number | null>(() => {
    const param = searchParams?.get('cohortId')
    if (!param) return null
    const parsed = parseInt(param, 10)
    return Number.isNaN(parsed) ? null : parsed
  })

  // Use custom hook for cohort data fetching
  const { cohorts, loading: loadingCohorts, fetchCohorts } = useStudentCohorts()

  // Fetch cohorts when user is available
  useEffect(() => {
    if (user) {
      fetchCohorts()
    }
  }, [user, fetchCohorts])

  // Handle refresh parameter from invite acceptance
  useEffect(() => {
    if (user && searchParams?.get('refresh') === 'true') {
      fetchCohorts()
      if (typeof window !== 'undefined') {
        window.history.replaceState({}, '', '/student/my-cohorts')
      }
    }
  }, [user, searchParams, fetchCohorts])

  // Transform API data to match UI expectations
  const transformedCohorts = useMemo(() => cohorts.map(cohort => {
    const transformedSimulations = (cohort.simulations || []).map((sim: any) => {
      let displayStatus = sim.status || 'not_started'
      if (displayStatus === 'not_started') displayStatus = 'available'

      let progressText = 'Ready to start'
      if (sim.status === 'completed' || sim.status === 'graded') {
        progressText = 'Completed'
      } else if (sim.status === 'in_progress') {
        progressText = `${Math.round(sim.progress)}% complete`
      } else if (sim.status === 'submitted') {
        progressText = 'Awaiting grade'
      }

      return {
        id: sim.id,
        unique_id: sim.unique_id,
        simulation_id: sim.simulation_id,
        title: sim.title,
        description: sim.description,
        status: displayStatus,
        progress: progressText,
        progressPercentage: sim.progress || 0,
        assignedDate: sim.assigned_at
          ? new Date(sim.assigned_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
          : 'N/A',
        dueDate: sim.due_date
          ? new Date(sim.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
          : null,
        is_required: sim.is_required,
        is_draft: sim.is_draft,
      }
    })

    const totalSimulations = transformedSimulations.length
    const completedSimulations = transformedSimulations.filter((s: any) =>
      s.status === 'completed' || s.status === 'graded'
    ).length
    const progressPercentage = totalSimulations > 0 ? (completedSimulations / totalSimulations) * 100 : 0

    const nextSim = transformedSimulations.find((s: any) =>
      s.status !== 'completed' && s.status !== 'graded'
    )

    return {
      id: cohort.id,
      unique_id: cohort.unique_id,
      title: cohort.title,
      instructor: cohort.professor?.name || 'Unknown',
      description: cohort.description,
      status: cohort.is_active ? 'active' : 'inactive',
      progress: `${completedSimulations}/${totalSimulations} completed`,
      progressPercentage: progressPercentage,
      currentRank: "#-",
      bestRank: "#-",
      avgScore: "0%",
      joinedDate: cohort.enrollment_date
        ? new Date(cohort.enrollment_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        : 'N/A',
      nextSimulation: nextSim ? nextSim.title : null,
      totalStudents: cohort.student_count,
      simulations: transformedSimulations
    }
  }), [cohorts])

  // Handle redirect when user is not authenticated or not a student
  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/")
    } else if (!authLoading && user && user.role !== 'student' && user.role !== 'admin') {
      router.push("/professor/dashboard")
    }
  }, [user, authLoading, router])

  if (authLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black mx-auto mb-4"></div>
          <p className="text-black">Loading...</p>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-black">Redirecting...</p>
        </div>
      </div>
    )
  }

  // Filter cohorts based on search and filters
  const filteredCohorts = transformedCohorts.filter(cohort => {
    const matchesSearch = cohort.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         cohort.instructor.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         (cohort.description || '').toLowerCase().includes(searchTerm.toLowerCase())
    const matchesStatus = statusFilter === "All Status" ||
                         cohort.status === statusFilter.toLowerCase()
    return matchesSearch && matchesStatus
  })

  // Derive selected cohort: prefer explicit selection, fall back to first in list
  const selectedCohort = (() => {
    if (selectedCohortId !== null) {
      const found = filteredCohorts.find(c => c.id === selectedCohortId)
      if (found) return found
    }
    return filteredCohorts[0] ?? null
  })()

  const toggleDescription = (simulationId: string) => {
    setExpandedDescriptions(prev => {
      const newSet = new Set(prev)
      if (newSet.has(simulationId)) {
        newSet.delete(simulationId)
      } else {
        newSet.add(simulationId)
      }
      return newSet
    })
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "active":
        return <Badge className="bg-green-100 text-green-800 text-xs">Active</Badge>
      case "completed":
        return <Badge className="bg-blue-100 text-blue-800 text-xs">Completed</Badge>
      case "archived":
        return <Badge className="bg-gray-100 text-gray-800 text-xs">Archived</Badge>
      default:
        return <Badge className="bg-gray-100 text-gray-800 text-xs">{status}</Badge>
    }
  }

  const getSimulationStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
      case "graded":
        return <Badge className="bg-green-100 text-green-800 text-xs">Completed</Badge>
      case "available":
        return <Badge className="bg-red-100 text-red-800 text-xs">Available</Badge>
      case "in_progress":
        return <Badge className="bg-blue-100 text-blue-800 text-xs">In Progress</Badge>
      case "submitted":
        return <Badge className="bg-yellow-100 text-yellow-800 text-xs">Submitted</Badge>
      default:
        return <Badge className="bg-gray-100 text-gray-800 text-xs">{status}</Badge>
    }
  }

  return (
    <div className="min-h-screen bg-atmospheric relative pattern-dots">
      <RoleBasedSidebar currentPath="/student/my-cohorts" />

      <div className="ml-20 flex h-screen relative">

        {/* Left Column — Cohort List */}
        <div className="w-96 bg-white/95 backdrop-blur-sm border-r border-gray-200/60 flex flex-col shadow-lg relative z-40">
          {/* Header */}
          <div className="p-6 border-b border-gray-200/60">
            <h1 className="text-xl font-bold text-black">My Cohorts</h1>
            <p className="text-sm text-gray-500 mt-1">{filteredCohorts.length} enrolled</p>
          </div>

          {/* Search + Filter */}
          <div className="p-4 space-y-3 border-b border-gray-200/60">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search cohorts..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-200/80 rounded-xl bg-white/80 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all"
              />
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full px-3 py-2.5 border border-gray-200/80 rounded-xl bg-white/80 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all cursor-pointer"
            >
              <option value="All Status">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>

          {/* Cohort Cards */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {loadingCohorts ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-black mx-auto mb-3"></div>
                <p className="text-sm text-gray-500">Loading cohorts...</p>
              </div>
            ) : filteredCohorts.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-300" />
                <p className="text-sm font-medium">No cohorts found</p>
                <p className="text-xs mt-1">You haven't joined any cohorts yet.</p>
              </div>
            ) : (
              filteredCohorts.map(cohort => (
                <div
                  key={cohort.id}
                  onClick={() => setSelectedCohortId(cohort.id)}
                  className={`p-4 rounded-xl border cursor-pointer transition-all duration-200 ${
                    selectedCohort?.id === cohort.id
                      ? 'border-slate-400/60 bg-gradient-to-br from-slate-50 to-blue-50/40 shadow-md'
                      : 'border-gray-200/60 bg-white/90 hover:bg-gray-50/80 hover:border-gray-300/60 hover:shadow-sm'
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="font-semibold text-gray-900 text-sm leading-tight flex-1 mr-2">{cohort.title}</h3>
                    {getStatusBadge(cohort.status)}
                  </div>
                  <p className="text-xs text-gray-500 mb-3">{cohort.instructor}</p>
                  <div className="flex items-center justify-between text-xs text-gray-400">
                    <span>{cohort.progress}</span>
                    <span>Joined {cohort.joinedDate}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Column — Cohort Detail */}
        <div className="flex-1 bg-white/50 backdrop-blur-sm h-full overflow-y-auto">
          {selectedCohort ? (
            <div className="p-8">

              {/* Cohort Header */}
              <div className="mb-8">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    <h2 className="text-3xl font-bold text-black tracking-tight">{selectedCohort.title}</h2>
                    {getStatusBadge(selectedCohort.status)}
                  </div>
                  <div className="flex items-center space-x-2 text-sm text-gray-500">
                    <Users className="h-4 w-4" />
                    <span>{selectedCohort.totalStudents} students</span>
                  </div>
                </div>
                <p className="text-gray-600 mb-1">Instructor: {selectedCohort.instructor}</p>
                {selectedCohort.description && (
                  <p className="text-gray-500 text-sm">{selectedCohort.description}</p>
                )}
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <div className="card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl p-4 text-center shadow-sm">
                  <div className="flex items-center justify-center space-x-1 mb-1">
                    <Trophy className="h-4 w-4 text-gray-500" />
                    <span className="text-xl font-bold text-gray-900">{selectedCohort.currentRank}</span>
                  </div>
                  <p className="text-xs text-gray-500">Current Rank</p>
                </div>
                <div className="card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl p-4 text-center shadow-sm">
                  <div className="flex items-center justify-center space-x-1 mb-1">
                    <Crown className="h-4 w-4 text-gray-500" />
                    <span className="text-xl font-bold text-gray-900">{selectedCohort.bestRank}</span>
                  </div>
                  <p className="text-xs text-gray-500">Best Rank</p>
                </div>
                <div className="card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl p-4 text-center shadow-sm">
                  <div className="flex items-center justify-center space-x-1 mb-1">
                    <Shield className="h-4 w-4 text-gray-500" />
                    <span className="text-xl font-bold text-gray-900">{selectedCohort.avgScore}</span>
                  </div>
                  <p className="text-xs text-gray-500">Avg. Score</p>
                </div>
                <div className="card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl p-4 text-center shadow-sm">
                  <div className="flex items-center justify-center space-x-1 mb-1">
                    <Calendar className="h-4 w-4 text-gray-500" />
                    <span className="text-xl font-bold text-gray-900">{selectedCohort.joinedDate}</span>
                  </div>
                  <p className="text-xs text-gray-500">Joined</p>
                </div>
              </div>

              {/* Simulations List */}
              <div>
                <h3 className="text-lg font-bold text-black mb-4">
                  Assigned Simulations ({selectedCohort.simulations?.length || 0})
                </h3>
                <div className="space-y-4">
                  {selectedCohort.simulations && selectedCohort.simulations.length > 0 ? (
                    selectedCohort.simulations.map((simulation: any) => (
                      <div key={simulation.id} className="card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-sm p-5">
                        <div className="flex flex-col">
                          <div className="flex-1">
                            <div className="flex items-center space-x-2 mb-2">
                              <h4 className="font-bold text-gray-900">{simulation.title}</h4>
                              {simulation.is_required && (
                                <Badge className="bg-red-100 text-red-800 text-xs">Required</Badge>
                              )}
                            </div>
                            {simulation.description && (
                              <div className="mb-3">
                                <p className={`text-sm text-gray-600 ${expandedDescriptions.has(simulation.id.toString()) ? '' : 'line-clamp-2'} transition-all duration-200`}>
                                  {simulation.description}
                                </p>
                                {simulation.description.length > 150 && (
                                  <button
                                    onClick={() => toggleDescription(simulation.id.toString())}
                                    className="text-xs text-blue-600 hover:text-blue-800 font-medium mt-1 focus:outline-none"
                                  >
                                    {expandedDescriptions.has(simulation.id.toString()) ? 'Read less' : 'Read more'}
                                  </button>
                                )}
                              </div>
                            )}
                            <div className="flex items-center space-x-4 text-xs text-gray-500 mb-3">
                              <span className="flex items-center">
                                <Calendar className="h-3 w-3 mr-1" />
                                Assigned {simulation.assignedDate}
                              </span>
                              {simulation.dueDate && (
                                <span className="flex items-center text-orange-600">
                                  <Clock className="h-3 w-3 mr-1" />
                                  Due {simulation.dueDate}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center space-x-2 mb-3">
                              {getSimulationStatusBadge(simulation.status)}
                              <span className="text-xs text-gray-500">{simulation.progress}</span>
                            </div>
                            {simulation.progressPercentage > 0 && (
                              <div className="space-y-1">
                                <div className="flex justify-between text-xs text-gray-400">
                                  <span>Progress</span>
                                  <span>{Math.round(simulation.progressPercentage)}%</span>
                                </div>
                                <div className="w-full bg-gray-100 rounded-full h-1.5">
                                  <div
                                    className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
                                    style={{ width: `${simulation.progressPercentage}%` }}
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          <div className="flex justify-end mt-4">
                          <Button
                            size="sm"
                            className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                            onClick={() => {
                              if (simulation.is_draft) {
                                alert('This simulation is not available yet. Please contact your instructor.')
                                return
                              }
                              if (simulation.unique_id) {
                                setStartingSimulation(simulation.unique_id)
                                router.push(`/student/run-simulation/${simulation.unique_id}`)
                              } else {
                                alert('Unable to start simulation. Please refresh and try again.')
                              }
                            }}
                            disabled={simulation.is_draft || startingSimulation === simulation.unique_id}
                          >
                            {startingSimulation === simulation.unique_id ? (
                              <>
                                <RefreshCw className="h-4 w-4 mr-2 sim-loading-spinner" />
                                Loading...
                              </>
                            ) : (
                              <>
                                <Play className="h-4 w-4 mr-2" />
                                {simulation.status === 'completed' || simulation.status === 'graded'
                                  ? 'Review'
                                  : simulation.status === 'in_progress'
                                  ? 'Continue'
                                  : 'Start'}
                              </>
                            )}
                          </Button>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-10 text-gray-500">
                      <BookOpen className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                      <p className="font-medium mb-1">No simulations assigned yet</p>
                      <p className="text-sm">Your instructor will assign simulations to this cohort soon.</p>
                    </div>
                  )}
                </div>
              </div>

            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400">
              <div className="text-center">
                <BookOpen className="h-16 w-16 mx-auto mb-4 text-gray-200" />
                <p className="text-lg font-medium text-gray-400">Select a cohort to view details</p>
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}