"use client"

import { useState, useEffect, useMemo } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { 
  Search,
  Filter,
  BookOpen,
  Trophy,
  Star,
  Clock,
  Users,
  TrendingUp,
  Calendar,
  ArrowRight,
  Play,
  Eye,
  MessageCircle,
  UserPlus,
  Crown,
  Shield,
  Target,
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
      // Remove the query parameter from URL without page reload
      if (typeof window !== 'undefined') {
        window.history.replaceState({}, '', '/student/my-cohorts')
      }
    }
  }, [user, searchParams, fetchCohorts])
  
  // Transform API data to match UI expectations
  const transformedCohorts = useMemo(() => cohorts.map(cohort => {
    // Transform simulations data with real status
    const transformedSimulations = (cohort.simulations || []).map((sim: any) => {
      // Map status to display-friendly format
      let displayStatus = sim.status || 'not_started'
      if (displayStatus === 'not_started') displayStatus = 'available'
      
      // Get progress text based on status
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
        unique_id: sim.unique_id, // Important for navigation!
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
    
    // Calculate progress from simulations
    const totalSimulations = transformedSimulations.length
    const completedSimulations = transformedSimulations.filter((s: any) => 
      s.status === 'completed' || s.status === 'graded'
    ).length
    const progressPercentage = totalSimulations > 0 ? (completedSimulations / totalSimulations) * 100 : 0
    
    // Find next simulation (first non-completed, non-graded)
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
      xpEarned: "0",
      joinedDate: cohort.enrollment_date
        ? new Date(cohort.enrollment_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
        : 'N/A',
      nextSimulation: nextSim ? nextSim.title : "No simulations assigned",
      totalStudents: cohort.student_count,
      simulations: transformedSimulations
    }
  }), [cohorts])
  
  // Mock data - fallback when no real data
  const mockCohorts = [
    {
      id: 1,
      title: "Financial Management 401",
      instructor: "Dr. Michael Chen",
      description: "Master corporate finance through realistic AI-powered business simulations and case studies.",
      status: "active",
      progress: "3/4 completed",
      progressPercentage: 75,
      currentRank: "#2",
      bestRank: "#1",
      avgScore: "88%",
      xpEarned: "1250",
      joinedDate: "Nov 28",
      nextSimulation: "Investment Portfolio Challenge",
      totalStudents: 18,
      simulations: [
        {
          id: 1,
          title: "Investment Portfolio Challenge",
          status: "available",
          progress: "Ready to start",
          progressPercentage: 0,
          ranking: "Not started",
          dueDate: "Dec 15",
          xpReward: "+400 XP"
        },
        {
          id: 2,
          title: "Risk Assessment Simulation",
          status: "in_progress",
          progress: "Scene 2 of 5",
          progressPercentage: 40,
          ranking: "Rank #3/15",
          dueDate: "Dec 20",
          xpReward: "+350 XP"
        },
        {
          id: 3,
          title: "Corporate Valuation",
          status: "completed",
          progress: "Completed",
          progressPercentage: 100,
          ranking: "Rank #1/18",
          completedDate: "Dec 10",
          score: "95%",
          xpEarned: "+380 XP"
        }
      ]
    },
    {
      id: 2,
      title: "Business Strategy Fall 2024",
      instructor: "Dr. Sarah Wilson",
      description: "Experience Harvard Business School case simulations with AI-powered scenarios.",
      status: "active",
      progress: "1/3 completed",
      progressPercentage: 33,
      currentRank: "#5",
      bestRank: "#1",
      avgScore: "92%",
      xpEarned: "750",
      joinedDate: "Dec 1",
      nextSimulation: "Amazon Supply Chain Optimization",
      totalStudents: 24,
      simulations: [
        {
          id: 4,
          title: "Tesla Strategic Analysis",
          status: "completed",
          progress: "Completed",
          progressPercentage: 100,
          ranking: "Rank #1/24",
          completedDate: "Dec 10",
          score: "95%",
          xpEarned: "+350 XP"
        },
        {
          id: 5,
          title: "Amazon Supply Chain Optimization",
          status: "in_progress",
          progress: "Scene 2 of 4",
          progressPercentage: 50,
          ranking: "Rank #5/22",
          dueDate: "Dec 18",
          xpReward: "+300 XP"
        }
      ]
    },
  ]; // Added semicolon here

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

  const handleLogout = () => {
    logout()
    router.push("/")
  }

  // Filter cohorts based on search and filters
  const filteredCohorts = transformedCohorts.filter(cohort => {
    const matchesSearch = cohort.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         cohort.instructor.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         cohort.description.toLowerCase().includes(searchTerm.toLowerCase())
    
    const matchesStatus = statusFilter === "All Status" || 
                         cohort.status === statusFilter.toLowerCase()
    
    return matchesSearch && matchesStatus
  })

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
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/student/my-cohorts" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 relative">
        {/* Main Content Area */}
        <div className="p-8 animate-page-enter">
          {/* Header */}
          <div className="mb-10 stagger-1 animate-fade-scale">
            <h1 className="text-4xl font-bold text-black mb-3 tracking-tight">My Cohorts</h1>
            <p className="text-gray-600 text-lg">View your enrolled cohorts, track progress, and access simulations.</p>
          </div>

          {/* Search and Filters */}
          <div className="flex items-center space-x-4 mb-8 stagger-2 animate-fade-scale">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search cohorts..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-12 pr-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md"
              />
            </div>
            
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md cursor-pointer"
              >
                <option value="All Status">All Status</option>
                <option value="Active">Active</option>
                <option value="Completed">Completed</option>
                <option value="Archived">Archived</option>
              </select>
            </div>
          </div>

          {/* Summary Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10 stagger-3 animate-fade-scale">
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <BookOpen className="h-6 w-6 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Total Cohorts</p>
                    <p className="text-2xl font-bold text-gray-900">{transformedCohorts.length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Target className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Active Cohorts</p>
                    <p className="text-2xl font-bold text-gray-900">{transformedCohorts.filter(c => c.status === 'active').length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Trophy className="h-6 w-6 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Best Rank</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {(() => {
                        // Calculate best rank from all cohorts
                        const allRanks = transformedCohorts
                          .map(c => {
                            // Extract numeric rank from strings like "#1" or "#-"
                            const rankMatch = c.bestRank?.match(/#(\d+)/)
                            return rankMatch ? parseInt(rankMatch[1]) : null
                          })
                          .filter(r => r !== null) as number[]
                        
                        if (allRanks.length === 0) return '#-'
                        const bestRank = Math.min(...allRanks)
                        return `#${bestRank}`
                      })()}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Cohorts List */}
          <div className="mb-6 stagger-4 animate-fade-scale">
            <h2 className="text-xl font-bold text-black mb-6">Enrolled Cohorts ({filteredCohorts.length})</h2>
            
            {loadingCohorts ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-black mx-auto mb-4"></div>
                <p className="text-gray-600">Loading cohorts...</p>
              </div>
            ) : filteredCohorts.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <BookOpen className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                <p className="text-lg font-medium mb-2">No cohorts found</p>
                <p className="text-sm">You haven't joined any cohorts yet.</p>
              </div>
            ) : (
              <div className="space-y-6">
                {filteredCohorts.map((cohort, index) => {
                  const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                  return (
                <Card key={cohort.id} className={`card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md overflow-hidden ${staggerClass} animate-fade-scale`}>
                  <CardHeader className="pb-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-3 mb-2">
                          <CardTitle className="text-xl font-bold text-black">{cohort.title}</CardTitle>
                          {getStatusBadge(cohort.status)}
                        </div>
                        <p className="text-sm text-gray-600 mb-2">Instructor: {cohort.instructor}</p>
                        <p className="text-sm text-gray-600">{cohort.description}</p>
                      </div>
                      <div className="flex items-center space-x-2">
                        <div className="flex items-center space-x-1 text-sm text-gray-600">
                          <Users className="h-4 w-4" />
                          <span>{cohort.totalStudents} students</span>
                        </div>
                      </div>
                    </div>
                  </CardHeader>
                  
                  <CardContent>
                    {/* Progress Bar */}
                    <div className="mb-4">
                      <div className="flex justify-between text-sm text-gray-600 mb-2">
                        <span>Overall Progress</span>
                        <span>{cohort.progress}</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${cohort.progressPercentage}%` }}
                        ></div>
                      </div>
                    </div>
                    
                    {/* Performance Metrics */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                      <div className="text-center">
                        <div className="flex items-center justify-center space-x-1 mb-1">
                          <Trophy className="h-4 w-4 text-gray-600" />
                          <span className="text-lg font-bold text-gray-900">{cohort.currentRank}</span>
                        </div>
                        <p className="text-xs text-gray-600">Current Rank</p>
                      </div>
                      
                      <div className="text-center">
                        <div className="flex items-center justify-center space-x-1 mb-1">
                          <Crown className="h-4 w-4 text-gray-600" />
                          <span className="text-lg font-bold text-gray-900">{cohort.bestRank}</span>
                        </div>
                        <p className="text-xs text-gray-600">Best Rank</p>
                      </div>
                      
                      <div className="text-center">
                        <div className="flex items-center justify-center space-x-1 mb-1">
                          <Shield className="h-4 w-4 text-gray-600" />
                          <span className="text-lg font-bold text-gray-900">{cohort.avgScore}</span>
                        </div>
                        <p className="text-xs text-gray-600">Avg. Score</p>
                      </div>
                      
                      <div className="text-center">
                        <div className="flex items-center justify-center space-x-1 mb-1">
                          <Calendar className="h-4 w-4 text-gray-600" />
                          <span className="text-lg font-bold text-gray-900">{cohort.joinedDate}</span>
                        </div>
                        <p className="text-xs text-gray-600">Joined</p>
                      </div>
                    </div>
                    
                    {/* Next Simulation */}
                    {cohort.nextSimulation && cohort.nextSimulation !== "No simulations assigned" && (
                      <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg mb-6">
                        <div>
                          <p className="text-sm font-medium text-gray-900">Next Simulation</p>
                          <p className="text-sm text-gray-600">{cohort.nextSimulation}</p>
                        </div>
                        <Button 
                          size="sm" 
                          className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                          onClick={() => {
                            const nextSim = cohort.simulations.find((s: any) => s.status !== 'completed' && s.status !== 'graded')
                            if (nextSim?.is_draft) {
                              alert('This simulation is not available yet. Please contact your instructor.')
                              return
                            }
                            if (nextSim?.unique_id) {
                              router.push(`/student/run-simulation/${nextSim.unique_id}`)
                            } else {
                              alert('Unable to start simulation. Please refresh and try again.')
                            }
                          }}
                          disabled={cohort.simulations.find((s: any) => s.status !== 'completed' && s.status !== 'graded')?.is_draft}
                        >
                          <BookOpen className="h-4 w-4 mr-2" />
                          Start Now
                        </Button>
                      </div>
                    )}
                    
                    {/* Simulations */}
                    <div className="mb-6">
                      <h3 className="text-lg font-semibold text-black mb-4">Assigned Simulations ({cohort.simulations?.length || 0})</h3>
                      <div className="space-y-4">
                        {cohort.simulations && cohort.simulations.length > 0 ? (
                          cohort.simulations.map((simulation: any) => (
                          <div key={simulation.id} className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md p-5">
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center space-x-2 mb-2">
                                  <h4 className="font-bold text-gray-900 text-lg">{simulation.title}</h4>
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
                                <div className="flex items-center space-x-4 text-sm text-gray-500 mb-3">
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
                                <div className="flex items-center space-x-2">
                                  {getSimulationStatusBadge(simulation.status)}
                                  <span className="text-xs text-gray-500">{simulation.progress}</span>
                                </div>
                              </div>
                              
                              <div className="flex flex-col items-end space-y-2">
                                <Button 
                                  size="sm" 
                                  className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                                  onClick={() => {
                                    // Don't allow starting draft simulations
                                    if (simulation.is_draft) {
                                      alert('This simulation is not available yet. Please contact your instructor.')
                                      return
                                    }
                                    
                                    // Navigate to run-simulation page using instance unique_id
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
                          <div className="text-center py-8 text-gray-500">
                            <BookOpen className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                            <p className="text-lg font-medium mb-2">No simulations assigned yet</p>
                            <p className="text-sm">Your instructor will assign simulations to this cohort soon.</p>
                          </div>
                        )}
                      </div>
                    </div>
                    
                    {/* Action Buttons */}
                    <div className="flex space-x-2 mt-4">
                      <Button variant="outline" size="sm" className="flex-1 border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all">
                        <Trophy className="h-4 w-4 mr-2" />
                        Leaderboard
                      </Button>
                      <Button variant="outline" size="sm" className="flex-1 border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all">
                        <BookOpen className="h-4 w-4 mr-2" />
                        All Simulations
                      </Button>
                      <Button variant="outline" size="sm" className="flex-1 border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all">
                        <MessageCircle className="h-4 w-4 mr-2" />
                        Discussion
                      </Button>
                      <Button variant="outline" size="sm" className="flex-1 border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all">
                        <UserPlus className="h-4 w-4 mr-2" />
                        Classmates
                      </Button>
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
