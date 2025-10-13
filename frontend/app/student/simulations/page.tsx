"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
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
  Play,
  Eye,
  CheckCircle,
  AlertCircle,
  TrendingUp
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

export default function StudentSimulations() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  const [activeTab, setActiveTab] = useState("All Simulations")
  const [searchTerm, setSearchTerm] = useState("")
  const [cohortFilter, setCohortFilter] = useState("All Cohorts")
  const [statusFilter, setStatusFilter] = useState("All Status")
  const [simulations, setSimulations] = useState<any[]>([])
  const [loadingSimulations, setLoadingSimulations] = useState(true)
  const [expandedDescriptions, setExpandedDescriptions] = useState<Set<string>>(new Set())
  
  // Fetch student simulation instances from API
  useEffect(() => {
    const fetchSimulations = async () => {
      if (!user) return
      
      try {
        setLoadingSimulations(true)
        // Get student simulation instances
        const instancesResponse = await apiClient.getStudentSimulationInstances()
        const instances = instancesResponse || []
        
        // Transform instances to match UI expectations
        const transformedSimulations = instances.map((instance: any) => {
          const cohortAssignment = instance.cohort_assignment
          const simulation = cohortAssignment?.simulation || {}
          
          // Check if simulation is draft (safety measure - students should never get draft simulations)
          const isDraft = simulation.is_draft || simulation.status === 'draft'
          
          return {
            id: instance.id,
            unique_id: instance.unique_id,
            title: simulation.title || 'Unknown Simulation',
            description: simulation.description || 'No description available',
            status: instance.status,
            cohort_title: cohortAssignment?.cohort?.title || 'Unknown Cohort',
            cohort_id: cohortAssignment?.cohort_id,
            instructor: cohortAssignment?.cohort?.professor?.name || 'Unknown',
            course: cohortAssignment?.cohort?.title || 'Unknown Course',
            duration: '30-60 min', // Default duration
            tags: ['Assigned'],
            actions: isDraft ? ['Draft - Not Available'] : getActionsForStatus(instance.status),
            is_draft: isDraft,
            // Instance-specific data
            completion_percentage: instance.completion_percentage,
            total_time_spent: instance.total_time_spent,
            attempts_count: instance.attempts_count,
            grade: instance.grade,
            feedback: instance.feedback,
            due_date: cohortAssignment?.due_date,
            is_overdue: instance.is_overdue,
            days_late: instance.days_late,
            started_at: instance.started_at,
            completed_at: instance.completed_at
          }
        })
        
        setSimulations(transformedSimulations)
      } catch (error) {
        setSimulations([])
      } finally {
        setLoadingSimulations(false)
      }
    }

    fetchSimulations()
  }, [user])
  
  // Helper function to get actions based on status
  const getActionsForStatus = (status: string) => {
    switch (status) {
      case 'not_started':
        return ['Start Simulation']
      case 'in_progress':
        return ['Continue Simulation']
      case 'completed':
        return ['View Results']
      case 'submitted':
        return ['View Grade']
      case 'graded':
        return ['View Grade', 'View Feedback']
      default:
        return ['View Details']
    }
  }

  // Handle starting a simulation
  const handleStartSimulation = async (simulation: any) => {
    // Safety check: prevent access to draft simulations
    if (simulation.is_draft) {
      alert('This simulation is not available yet. Please contact your instructor.')
      return
    }
    
    try {
      // Redirect to the run-simulation page using unique_id
      // The page will call the start-simulation endpoint automatically
      router.push(`/student/run-simulation/${simulation.unique_id || simulation.id}`)
    } catch (error) {
      alert('Failed to start simulation. Please try again.')
    }
  }
  
  // Mock data - fallback when no real data
  const mockSimulations = [
    {
      id: 1,
      title: "Tesla Strategic Analysis",
      status: "completed",
      tags: ["Advanced", "Strategy Case"],
      course: "Business Strategy Fall 2024",
      instructor: "Dr. Sarah Wilson",
      duration: "45-60 min",
      description: "Analyze Tesla's market position and develop strategic recommendations for expansion into emerging markets.",
      rank: "#1/24",
      score: "95%",
      xp: "+350 XP",
      feedback: "Outstanding strategic analysis with excellent market insights.",
      completedDate: "Completed Dec 10",
      actions: ["View Results", "View Details"]
    },
    {
      id: 2,
      title: "Netflix Market Entry Simulation",
      status: "completed",
      tags: ["Intermediate", "Market Analysis"],
      course: "Financial Management 401",
      instructor: "Dr. Michael Chen",
      duration: "30-45 min",
      description: "Navigate Netflix's entry into the Indian market, managing content strategy, pricing, and competitive dynamics.",
      rank: "#3/18",
      score: "87%",
      xp: "+280 XP",
      feedback: "Good analysis, consider more local market factors.",
      completedDate: "Completed Dec 8",
      actions: ["View Results", "View Details"]
    },
    {
      id: 3,
      title: "Investment Portfolio Challenge",
      status: "available",
      tags: ["Advanced", "Financial Simulation"],
      course: "Financial Management 401",
      instructor: "Dr. Michael Chen",
      duration: "60-75 min",
      description: "Build and optimize a diversified investment portfolio using modern portfolio theory and risk management principles.",
      reward: "Ready to start",
      xp: "+400 XP reward",
      availableDate: "Available since Dec 8",
      actions: ["Start Simulation", "View Details"]
    },
    {
      id: 4,
      title: "Amazon Supply Chain Optimization",
      status: "in_progress",
      tags: ["Intermediate", "Operations"],
      course: "Business Strategy Fall 2024",
      instructor: "Dr. Sarah Wilson",
      duration: "40-55 min",
      description: "Optimize Amazon's supply chain for faster delivery while reducing costs and environmental impact.",
      progress: 60,
      timeSpent: "25 min",
      lastAccessed: "Dec 11",
      actions: ["Continue", "View Details"]
    }
  ];

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

  // Filter simulations based on search and filters
  const filteredSimulations = simulations.filter(simulation => {
    const matchesSearch = simulation.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         simulation.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         simulation.course.toLowerCase().includes(searchTerm.toLowerCase())
    
    const matchesStatus = statusFilter === "All Status" || 
                         simulation.status === statusFilter.toLowerCase().replace(" ", "_")
    
    const matchesCohort = cohortFilter === "All Cohorts" || 
                         simulation.course === cohortFilter
    
    return matchesSearch && matchesStatus && matchesCohort
  })

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "completed":
        return <Badge className="bg-green-100 text-green-800 text-xs">Completed</Badge>
      case "not_started":
        return <Badge className="bg-purple-100 text-purple-800 text-xs">Not Started</Badge>
      case "in_progress":
        return <Badge className="bg-blue-100 text-blue-800 text-xs">In Progress</Badge>
      case "submitted":
        return <Badge className="bg-yellow-100 text-yellow-800 text-xs">Submitted</Badge>
      case "graded":
        return <Badge className="bg-green-100 text-green-800 text-xs">Graded</Badge>
      default:
        return <Badge className="bg-gray-100 text-gray-800 text-xs">{status}</Badge>
    }
  }

  const getTagBadge = (tag: string) => {
    if (tag === "Advanced") {
      return <Badge className="bg-red-100 text-red-800 text-xs">{tag}</Badge>
    } else if (tag === "Intermediate") {
      return <Badge className="bg-yellow-100 text-yellow-800 text-xs">{tag}</Badge>
    } else {
      return <Badge className="bg-blue-100 text-blue-800 text-xs">{tag}</Badge>
    }
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/student/simulations" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 bg-white">
        {/* Main Content Area */}
        <div className="p-6">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-black mb-2">Simulations</h1>
            <p className="text-gray-600">Dive into realistic business scenarios and compete with your classmates on the leaderboards.</p>
          </div>

          {/* Tabs */}
          <div className="mb-6">
            <div className="flex space-x-2 border-b border-gray-200">
              {["All Simulations", "Leaderboard"].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                    activeTab === tab
                      ? "border-black text-black"
                      : "border-transparent text-gray-600 hover:text-black"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>

          {/* Search and Filters */}
          <div className="flex items-center space-x-4 mb-6">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search simulations..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent"
              />
            </div>
            
            <div className="relative">
              <select
                value={cohortFilter}
                onChange={(e) => setCohortFilter(e.target.value)}
                className="px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent"
              >
                <option value="All Cohorts">All Cohorts</option>
                <option value="Business Strategy Fall 2024">Business Strategy Fall 2024</option>
                <option value="Financial Management 401">Financial Management 401</option>
              </select>
            </div>
            
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent"
              >
                <option value="All Status">All Status</option>
                <option value="Not Started">Not Started</option>
                <option value="In Progress">In Progress</option>
                <option value="Completed">Completed</option>
                <option value="Submitted">Submitted</option>
                <option value="Graded">Graded</option>
              </select>
            </div>
          </div>

          {/* Summary Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <Card className="bg-white border border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mr-4">
                    <BookOpen className="h-6 w-6 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">Total</p>
                    <p className="text-2xl font-bold text-gray-900">4</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-white border border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mr-4">
                    <CheckCircle className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">Completed</p>
                    <p className="text-2xl font-bold text-gray-900">2</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-white border border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mr-4">
                    <Trophy className="h-6 w-6 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">Avg. Score</p>
                    <p className="text-2xl font-bold text-gray-900">91%</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-white border border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-yellow-100 rounded-lg flex items-center justify-center mr-4">
                    <Star className="h-6 w-6 text-yellow-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">Total XP</p>
                    <p className="text-2xl font-bold text-gray-900">630</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Simulations List */}
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-black mb-4">Simulations ({filteredSimulations.length})</h2>
            
            {loadingSimulations ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-black mx-auto mb-4"></div>
                <p className="text-gray-600">Loading simulations...</p>
              </div>
            ) : filteredSimulations.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <Play className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                <p className="text-lg font-medium mb-2">No simulations found</p>
                <p className="text-sm">You don't have any assigned simulations yet.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {filteredSimulations.map((simulation) => (
                <Card key={simulation.id} className="bg-white border border-gray-200 rounded-lg shadow-sm">
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-bold text-gray-900 text-lg mb-2">{simulation.title}</h3>
                        <div className="flex items-center space-x-4 text-sm text-gray-500 mb-3">
                          <span>{simulation.course}</span>
                          <span>{simulation.instructor}</span>
                          <span>{simulation.duration}</span>
                        </div>
                        <div className="flex items-center space-x-2 mb-3">
                          {getStatusBadge(simulation.status)}
                          {simulation.tags.map((tag: string, index: number) => (
                            <span key={index}>
                              {getTagBadge(tag)}
                            </span>
                          ))}
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
                      </div>
                      
                      <div className="text-right">
                        <div className="text-sm text-gray-600 mb-2">
                          {simulation.completion_percentage || 0}% completed
                        </div>
                        <div className="w-32 bg-gray-200 rounded-full h-2">
                          <div 
                            className="bg-gray-800 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${simulation.completion_percentage || 0}%` }}
                          ></div>
                        </div>
                      </div>
                    </div>
                    
                    {/* Status-specific content */}
                    {(simulation.status === "completed" || simulation.status === "graded") && (
                      <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-4">
                            <div className="flex items-center space-x-4">
                              {(simulation.grade !== null && simulation.grade !== undefined) && (
                                <div>
                                  <p className="font-semibold text-green-800">{simulation.grade}%</p>
                                  <p className="text-sm text-green-600">Grade</p>
                                </div>
                              )}
                            </div>
                            <div>
                              <p className="font-semibold text-green-800">{simulation.completion_percentage}%</p>
                              <p className="text-sm text-green-600">Completed</p>
                            </div>
                          </div>
                          <div className="text-right">
                            {simulation.completed_at && (
                              <p className="text-sm text-green-600 font-medium">
                                Completed {new Date(simulation.completed_at).toLocaleDateString()}
                              </p>
                            )}
                          </div>
                        </div>
                        {simulation.feedback && (() => {
                          // Parse feedback if it's JSON, otherwise display as-is
                          try {
                            const parsedFeedback = JSON.parse(simulation.feedback)
                            if (parsedFeedback.overall_feedback) {
                              return <p className="text-sm text-green-700 mt-2 italic">"{parsedFeedback.overall_feedback}"</p>
                            }
                            // Valid JSON but no overall_feedback field - display as plain text
                            return <p className="text-sm text-green-700 mt-2 italic">"{simulation.feedback}"</p>
                          } catch {
                            // Not JSON, display as plain text
                            return <p className="text-sm text-green-700 mt-2 italic">"{simulation.feedback}"</p>
                          }
                        })()}
                      </div>
                    )}
                    
                    {simulation.status === "not_started" && simulation.due_date && (
                      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 mb-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-semibold text-purple-800">Ready to start</p>
                            <p className="text-sm text-purple-600">Click below to begin</p>
                          </div>
                          <div className="text-right">
                            <p className="text-sm text-purple-600 font-medium">
                              Due {new Date(simulation.due_date).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                      </div>
                    )}
                    
                    {simulation.status === "submitted" && (
                      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-semibold text-yellow-800">Awaiting Grade</p>
                            <p className="text-sm text-yellow-600">Your submission is being reviewed</p>
                          </div>
                          <div className="text-right">
                            {simulation.submitted_at && (
                              <p className="text-sm text-yellow-600 font-medium">
                                Submitted {new Date(simulation.submitted_at).toLocaleDateString()}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                    
                    {simulation.status === "in_progress" && (
                      <div className="mb-4">
                        <div className="flex justify-between text-sm text-gray-600 mb-2">
                          <span>Progress</span>
                          <span>{simulation.completion_percentage || 0}%</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div 
                            className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${simulation.completion_percentage || 0}%` }}
                          ></div>
                        </div>
                        <div className="flex justify-between text-sm text-gray-500 mt-2">
                          <span>Time spent: {Math.floor((simulation.total_time_spent || 0) / 60)} min</span>
                          {simulation.started_at && (
                            <span>Started: {new Date(simulation.started_at).toLocaleDateString()}</span>
                          )}
                        </div>
                      </div>
                    )}
                    
                    {/* Action Buttons */}
                    <div className="flex space-x-3">
                      {simulation.actions.map((action: string, index: number) => {
                        const isPrimary = action === "Start Simulation" || action === "Continue"
                        return (
                          <Button
                            key={index}
                            size="sm"
                            variant={isPrimary ? "default" : "outline"}
                            disabled={simulation.is_draft || action === "Draft - Not Available"}
                            className={simulation.is_draft || action === "Draft - Not Available" 
                              ? "bg-gray-400 text-gray-600 cursor-not-allowed" 
                              : isPrimary ? "bg-black text-white hover:bg-gray-800" : "border-gray-300 text-gray-700 hover:bg-gray-50"}
                            onClick={() => {
                              if (action === "Start Simulation" || action === "Continue Simulation") {
                                handleStartSimulation(simulation)
                              } else if (action === "View Details") {
                                // Handle view details - placeholder for future feature
                              } else if (action === "View Results") {
                                // Navigate to run-simulation page to review results
                                const runId = simulation.unique_id ?? simulation.id
                                router.push(`/student/run-simulation/${runId}`)
                              } else if (action === "View Grade") {
                                // Navigate to run-simulation page to review graded simulation
                                const runId = simulation.unique_id ?? simulation.id
                                router.push(`/student/run-simulation/${runId}`)
                              }
                            }}
                          >
                            {action === "Start Simulation" && <Play className="h-4 w-4 mr-2" />}
                            {action === "Continue" && <Play className="h-4 w-4 mr-2" />}
                            {action === "View Details" && <Eye className="h-4 w-4 mr-2" />}
                            {action === "View Results" && <Trophy className="h-4 w-4 mr-2" />}
                            {action}
                          </Button>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
