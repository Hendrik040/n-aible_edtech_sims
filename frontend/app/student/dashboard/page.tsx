"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Target,
  Users,
  Shield,
  Trophy,
  Clock,
  BookOpen,
  Calendar,
  ArrowRight,
  CheckCircle,
  Zap,
  TrendingUp
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

export default function StudentDashboard() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, isLoading: authLoading } = useAuth()
  
  // Real data from API
  const [activeCohorts, setActiveCohorts] = useState<any[]>([])
  const [recentSimulations, setRecentSimulations] = useState<any[]>([])
  const [allSimulations, setAllSimulations] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  
  // Placeholder achievements (keep for future implementation)
  const [achievements] = useState([
    {
      id: 1,
      title: "Strategic Thinker",
      description: "Scored 90+ on 3 strategy simulations",
      icon: Target,
      earnedDate: "Dec 10",
      color: "bg-yellow-100 text-yellow-800"
    },
    {
      id: 2,
      title: "Speed Runner",
      description: "Complete a simulation in under 30 minutes",
      icon: Zap,
      earnedDate: "Dec 8",
      color: "bg-yellow-100 text-yellow-800"
    },
    {
      id: 3,
      title: "Top Performer",
      description: "Rank #1 in any simulation",
      icon: Trophy,
      earnedDate: "Dec 10",
      color: "bg-yellow-100 text-yellow-800"
    },
    {
      id: 4,
      title: "Consistent Player",
      description: "Complete 10 simulations",
      icon: TrendingUp,
      progress: "7/10",
      color: "bg-yellow-100 text-yellow-800"
    }
  ])
  
  // Load real data from API
  useEffect(() => {
    if (user) {
      loadDashboardData()
    }
  }, [user])

  // Check for refresh parameter and refresh data if present
  useEffect(() => {
    if (user && searchParams?.get('refresh') === 'true') {
      // Refresh data when coming from invite acceptance
      loadDashboardData()
      // Remove the query parameter from URL without page reload
      if (typeof window !== 'undefined') {
        window.history.replaceState({}, '', '/student/dashboard')
      }
    }
  }, [user, searchParams])

  const loadDashboardData = async () => {
    try {
      setLoading(true)
      
      // Ensure loading overlay is visible for at least 300ms to prevent flicker
      const loadStartTime = Date.now()
      const minLoadTime = 300

      // Load cohorts and simulations in parallel
      const [cohortsRes, simulationsRes] = await Promise.allSettled([
        apiClient.getStudentCohorts(),
        apiClient.getStudentSimulationInstances()
      ])
      
      // Ensure minimum display time for loading overlay
      const elapsed = Date.now() - loadStartTime
      if (elapsed < minLoadTime) {
        await new Promise(resolve => setTimeout(resolve, minLoadTime - elapsed))
      }

      // Handle cohorts
      if (cohortsRes.status === 'fulfilled') {
        const cohortsData = cohortsRes.value.cohorts || cohortsRes.value || []
        setActiveCohorts(Array.isArray(cohortsData) ? cohortsData : [])
      } else if (cohortsRes.status === 'rejected') {
        console.error('[Dashboard] Failed to load active cohorts:', cohortsRes.reason)
        // Set empty array to prevent UI from showing stale data
        setActiveCohorts([])
      }

      // Handle simulations
      if (simulationsRes.status === 'fulfilled') {
        const allSims = simulationsRes.value.instances || simulationsRes.value || []
        
        // Store all simulations for statistics
        setAllSimulations(Array.isArray(allSims) ? allSims : [])
        
        // Show both in-progress and completed simulations, sorted by most recent activity
        const recentSims = (Array.isArray(allSims) ? allSims : [])
          .filter((sim: any) => 
            sim.status === 'in_progress' || 
            sim.status === 'completed' || 
            sim.status === 'graded'
          )
          .sort((a: any, b: any) => {
            // Sort by most recent activity (completed_at for completed, started_at for in-progress)
            const dateA = new Date(a.completed_at || a.started_at || 0).getTime()
            const dateB = new Date(b.completed_at || b.started_at || 0).getTime()
            return dateB - dateA
          })
          .slice(0, 5) // Get last 5
        setRecentSimulations(recentSims)
      } else if (simulationsRes.status === 'rejected') {
        console.error('[Dashboard] Failed to load recent simulations:', simulationsRes.reason)
        // Set empty arrays to prevent UI from showing stale data
        setAllSimulations([])
        setRecentSimulations([])
      }

    } catch (error) {
      console.error('[Dashboard] Unexpected error loading dashboard data:', error)
    } finally {
      setLoading(false)
    }
  }

  // Handle redirect when user is not authenticated or not a student
  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/")
    } else if (!authLoading && user && user.role !== 'student' && user.role !== 'admin') {
      // Redirect professors to their dashboard
      router.push("/professor/dashboard")
    }
  }, [user, authLoading, router])

  // Show loading while auth is being checked
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

  // If no user, show redirecting message
  if (!user) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-black">Redirecting...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-atmospheric relative pattern-dots">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/student/dashboard" />

      {/* Loading Overlay - High z-index to ensure visibility */}
      {loading && (
        <div 
          className="fixed inset-0 bg-white/90 backdrop-blur-md z-[9999] flex items-center justify-center animate-fade-in" 
          style={{ marginLeft: '5rem' }}
        >
          <div className="flex flex-col items-center gap-4">
            <div className="relative">
              <div className="w-16 h-16 border-4 border-blue-500/30 rounded-full"></div>
              <div className="absolute top-0 left-0 w-16 h-16 border-4 border-transparent border-t-blue-500 rounded-full animate-spin"></div>
            </div>
            <div className="text-center">
              <p className="text-lg font-semibold text-gray-900">Loading Dashboard</p>
              <p className="text-sm text-gray-600 mt-1">Fetching your cohorts and simulations...</p>
            </div>
          </div>
        </div>
      )}

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 relative">
        {/* Header */}
        <header className="bg-white/80 backdrop-blur-sm border-b border-gray-200/60 px-6 py-4 sticky top-0 z-10 shadow-sm">
          <div className="flex items-center justify-between animate-page-enter">
            <div>
              <h1 className="text-4xl font-bold text-black tracking-tight mb-1">Dashboard</h1>
              <p className="text-sm text-gray-600 font-medium">Welcome back, {user?.full_name || user?.username || 'Student'}</p>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <div className="p-8">

          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8 stagger-3 animate-fade-scale">
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Users className="h-6 w-6 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">Active Cohorts</p>
                    <p className="text-2xl font-bold text-gray-900">{activeCohorts.length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Shield className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Avg. Score</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {(() => {
                        const gradedSims = allSimulations.filter((sim: any) => 
                          (sim.status === 'graded' || sim.status === 'completed') && 
                          (sim.grade !== null && sim.grade !== undefined)
                        )
                        if (gradedSims.length === 0) return 'N/A'
                        const avgScore = Math.round(gradedSims.reduce((sum: number, sim: any) => sum + (sim.grade || sim.final_score || 0), 0) / gradedSims.length)
                        return `${avgScore}%`
                      })()}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Target className="h-6 w-6 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Completed</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {allSimulations.filter((sim: any) => sim.status === 'completed' || sim.status === 'graded').length}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-yellow-100 to-yellow-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Trophy className="h-6 w-6 text-yellow-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Best Score</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {(() => {
                        const gradedSims = allSimulations.filter((sim: any) => 
                          (sim.status === 'graded' || sim.status === 'completed') && 
                          (sim.grade !== null && sim.grade !== undefined)
                        )
                        if (gradedSims.length === 0) return 'N/A'
                        const bestScore = Math.max(...gradedSims.map((sim: any) => sim.grade || sim.final_score || 0))
                        return `${bestScore}%`
                      })()}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Active Cohorts */}
          <div className="mb-8 stagger-5 animate-fade-scale">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-black tracking-tight">My Cohorts</h2>
              <Link href="/student/my-cohorts" className="text-sm text-gray-600 hover:text-black flex items-center">
                View All Cohorts <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </div>
            
            {activeCohorts.length === 0 ? (
              <Card className="bg-white border border-gray-200">
                <CardContent className="p-6 text-center">
                  <Users className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                  <p className="text-gray-600">No active cohorts yet</p>
                  <p className="text-sm text-gray-500 mt-1">Accept an invitation to join your first cohort</p>
                </CardContent>
              </Card>
            ) : (
            <div className="flex gap-4 overflow-x-auto pb-2 -mx-1 px-1">
              {activeCohorts.map((cohort, index) => {
                const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                return (
                <div
                  key={cohort.id}
                  onClick={() => router.push(`/student/my-cohorts?cohortId=${cohort.id}`)}
                  className={`card-elevated w-72 shrink-0 bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md cursor-pointer hover:shadow-lg hover:border-gray-300/60 transition-all duration-200 p-5 ${staggerClass} animate-fade-scale`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="font-bold text-black text-base leading-tight flex-1 mr-2">{cohort.title || 'Cohort'}</h3>
                    <Badge className="bg-green-100 text-green-800 text-xs shrink-0">Active</Badge>
                  </div>
                  <p className="text-sm text-gray-600 mb-1">{cohort.professor?.name || 'Instructor'}</p>
                  {cohort.course_code && (
                    <p className="text-xs text-gray-400 mb-3">{cohort.course_code}{cohort.semester ? ` • ${cohort.semester}` : ''}{cohort.year ? ` ${cohort.year}` : ''}</p>
                  )}
                  <p className="text-sm text-gray-500 line-clamp-2 mb-4">{cohort.description || 'Active cohort for simulation assignments'}</p>
                  <div className="flex items-center text-xs text-gray-400">
                    <Calendar className="h-3 w-3 mr-1" />
                    Joined {cohort.joined_at ? new Date(cohort.joined_at).toLocaleDateString() :
                            cohort.created_at ? new Date(cohort.created_at).toLocaleDateString() :
                            'Recently'}
                  </div>
                </div>
                )
              })}
            </div>
            )}
          </div>

          {/* Recent Simulations */}
          <div className="mb-8 stagger-6 animate-fade-scale">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-black tracking-tight">Recent Activity</h2>
              <Link href="/student/simulations" className="text-sm text-gray-600 hover:text-black flex items-center">
                View All <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </div>
            
            {recentSimulations.length === 0 ? (
              <Card className="bg-white border border-gray-200">
                <CardContent className="p-6 text-center">
                  <BookOpen className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                  <p className="text-gray-600">No completed simulations yet</p>
                  <p className="text-sm text-gray-500 mt-1">Start a simulation to see your progress here</p>
                </CardContent>
              </Card>
            ) : (
            <div className="space-y-5">
                {recentSimulations.map((simulation: any, index: number) => {
                  const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                  return (
                <Card key={simulation.id} className={`card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${staggerClass} animate-fade-scale`}>
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                          <h3 className="font-bold text-gray-900 text-lg mb-2">
                            {simulation.cohort_assignment?.simulation?.title || 'Simulation'}
                          </h3>
                        <div className="flex flex-wrap items-center gap-2 text-sm text-gray-500 mb-3">
                            {simulation.cohort_assignment?.cohort?.title && (
                              <span className="flex items-center">
                                <Users className="h-3 w-3 mr-1" />
                                {simulation.cohort_assignment.cohort.title}
                              </span>
                            )}
                            {simulation.status === 'in_progress' && simulation.started_at && (
                              <span className="flex items-center">
                                <Clock className="h-3 w-3 mr-1" />
                                Started {new Date(simulation.started_at).toLocaleDateString()}
                              </span>
                            )}
                            {simulation.completed_at && (
                              <span className="flex items-center">
                                <CheckCircle className="h-3 w-3 mr-1" />
                                {new Date(simulation.completed_at).toLocaleDateString()}
                              </span>
                            )}
                            {simulation.started_at && simulation.completed_at && (
                              <span className="flex items-center">
                                <Clock className="h-3 w-3 mr-1" />
                                {Math.round((new Date(simulation.completed_at).getTime() - new Date(simulation.started_at).getTime()) / (1000 * 60))} min
                              </span>
                            )}
                            {simulation.cohort_assignment?.due_date && (
                              <span className={simulation.is_overdue ? 'text-red-600 font-semibold' : ''}>
                                {simulation.is_overdue ? '⚠️ ' : '📅 '}
                                Due {new Date(simulation.cohort_assignment.due_date).toLocaleDateString()}
                                {simulation.is_overdue && simulation.days_late ? ` (${simulation.days_late}d late)` : ''}
                              </span>
                            )}
                        </div>
                        <div className="flex items-center space-x-2">
                            {simulation.status === 'in_progress' ? (
                              <Badge className="bg-blue-100 text-blue-800 text-xs">
                                In Progress
                              </Badge>
                            ) : simulation.status === 'graded' ? (
                              <Badge className="bg-green-100 text-green-800 text-xs">
                                Graded
                              </Badge>
                            ) : simulation.status === 'completed' ? (
                              <Badge className="bg-purple-100 text-purple-800 text-xs">
                                Awaiting Grade
                              </Badge>
                            ) : simulation.status === 'submitted' ? (
                              <Badge className="bg-yellow-100 text-yellow-800 text-xs">
                                Submitted
                              </Badge>
                            ) : (
                              <Badge className="bg-gray-100 text-gray-800 text-xs">
                                {simulation.status}
                              </Badge>
                            )}
                            {(simulation.completion_percentage !== null && simulation.completion_percentage !== undefined) && (
                              <span className="text-xs text-gray-500">
                                {simulation.completion_percentage}% Complete
                          </span>
                            )}
                        </div>
                      </div>
                      
                      <div className="text-right">
                          {(simulation.grade !== null && simulation.grade !== undefined) && (
                        <div className="text-sm text-gray-600 mb-2">
                              Score: {simulation.grade}%
                        </div>
                          )}
                          <Link 
                            href={`/student/run-simulation/${simulation.unique_id}`} 
                            className="text-sm text-blue-600 hover:text-blue-800"
                          >
                            {simulation.status === 'in_progress' ? 'Continue' : 'View Results'}
                        </Link>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                  )
                })}
            </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
