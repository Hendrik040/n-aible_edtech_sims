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
  TrendingUp,
  RefreshCw
} from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

// Helper function to extract a clean feedback summary from raw feedback text
const extractFeedbackSummary = (feedback: string): string => {
  if (!feedback) return ""
  
  // Try to parse as JSON first
  try {
    const parsed = JSON.parse(feedback)
    if (parsed.overall_feedback) {
      feedback = parsed.overall_feedback
    } else if (parsed.overall_assessment?.summary) {
      return parsed.overall_assessment.summary
    }
  } catch {
    // Not JSON, use as-is
  }
  
  // If feedback contains markdown/unformatted grading text, extract a summary
  if (feedback.includes('**OVERALL ASSESSMENT:**') || feedback.includes('OVERALL ASSESSMENT:')) {
    // Try to extract the summary section - handle both markdown and plain text formats
    const assessmentMatch = feedback.match(/\*\*OVERALL ASSESSMENT:\*\*([\s\S]*?)(?=\*\*FEEDBACK:\*\*|\*\*SCORE BREAKDOWN:\*\*|$)/i)
    if (assessmentMatch) {
      let assessmentText = assessmentMatch[1]
      // Remove markdown formatting
      assessmentText = assessmentText.replace(/\*\*/g, '').replace(/-\s*\*\*/g, '-')
      
      // Try to find "Summary of Performance"
      const summaryMatch = assessmentText.match(/Summary\s+of\s+Performance[:\-]\s*([^\n]+(?:\n(?!Key\s+Strengths|Main\s+Areas|$))?)/i)
      if (summaryMatch) {
        let summary = summaryMatch[1].trim()
        // Clean up any remaining formatting
        summary = summary.replace(/\*\*/g, '').replace(/^\s*[-•]\s*/, '').trim()
        // Get first sentence or up to 200 chars
        const firstSentence = summary.split(/[.!?]\s+/)[0]
        if (firstSentence.length > 20 && firstSentence.length < 250) {
          return firstSentence + (firstSentence.endsWith('.') ? '' : '.')
        }
        if (summary.length > 250) {
          return summary.substring(0, 250).trim() + '...'
        }
        return summary
      }
      
      // If no explicit summary, get first meaningful paragraph
      const paragraphs = assessmentText.split(/\n\n|\n(?=-|\*\*)/).filter(p => p.trim().length > 30)
      if (paragraphs.length > 0) {
        let firstPara = paragraphs[0].trim().replace(/\*\*/g, '').replace(/^[-•]\s*/, '')
        // Get first sentence
        const firstSentence = firstPara.split(/[.!?]\s+/)[0]
        if (firstSentence.length > 20) {
          return firstSentence + (firstSentence.endsWith('.') ? '' : '.')
        }
        if (firstPara.length > 250) {
          return firstPara.substring(0, 250).trim() + '...'
        }
        return firstPara
      }
    }
  }
  
  // If it's plain text but long, truncate intelligently
  if (feedback.length > 200) {
    // Remove markdown formatting if present
    let cleanFeedback = feedback.replace(/\*\*/g, '').replace(/#{1,6}\s*/g, '')
    const truncated = cleanFeedback.substring(0, 200)
    const lastSentence = truncated.lastIndexOf('.')
    if (lastSentence > 50) {
      return truncated.substring(0, lastSentence + 1)
    }
    return truncated + '...'
  }
  
  // Remove markdown formatting before returning
  return feedback.replace(/\*\*/g, '').replace(/#{1,6}\s*/g, '')
}

export default function StudentSimulationsContent() {
  const router = useRouter()
  const { user } = useAuth()
  
  const [searchTerm, setSearchTerm] = useState("")
  const [cohortFilter, setCohortFilter] = useState("All Cohorts")
  const [statusFilter, setStatusFilter] = useState("All Status")
  const [simulations, setSimulations] = useState<any[]>([])
  const [loadingSimulations, setLoadingSimulations] = useState(true)
  const [expandedDescriptions, setExpandedDescriptions] = useState<Set<string>>(new Set())
  const [startingSimulation, setStartingSimulation] = useState<string | null>(null)
  
  // Fetch student simulation instances from API
  useEffect(() => {
    const fetchSimulations = async () => {
      if (!user) return
      
      try {
        setLoadingSimulations(true)
        // Get student simulation instances
        const instancesResponse = await apiClient.getStudentSimulationInstances()
        const rawInstances = instancesResponse?.instances ?? instancesResponse ?? []
        const instances = Array.isArray(rawInstances) ? rawInstances : []

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
        return ['View Grade']
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
      setStartingSimulation(simulation.unique_id || simulation.id)
      // Redirect to the run-simulation page using unique_id
      // The page will call the start-simulation endpoint automatically
      router.push(`/run-simulation/${simulation.unique_id || simulation.id}`)
    } catch (error) {
      alert('Failed to start simulation. Please try again.')
      setStartingSimulation(null)
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

  // Auth handled by (app)/layout.tsx

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
    <div className="p-8 animate-page-enter">
          {/* Header */}
          <div className="mb-10 stagger-1 animate-fade-scale">
            <h1 className="text-4xl font-bold text-black mb-3 tracking-tight">Simulations</h1>
            <p className="text-gray-600 text-lg">Dive into realistic business scenarios and compete with your classmates on the leaderboards.</p>
          </div>


          {/* Search and Filters */}
          <div className="flex items-center space-x-4 mb-8 stagger-3 animate-fade-scale">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search simulations..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-12 pr-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md"
              />
            </div>
            
            <div className="relative">
              <select
                value={cohortFilter}
                onChange={(e) => setCohortFilter(e.target.value)}
                className="px-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md cursor-pointer"
              >
                <option value="All Cohorts">All Cohorts</option>
                {Array.from(new Set(simulations.map(s => s.course).filter(Boolean))).sort().map(cohortTitle => (
                  <option key={cohortTitle} value={cohortTitle}>{cohortTitle}</option>
                ))}
              </select>
            </div>
            
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md cursor-pointer"
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10 stagger-4 animate-fade-scale">
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                      <BookOpen className="h-6 w-6 text-blue-600" />
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1 font-medium">Total</p>
                      <p className="text-2xl font-bold text-gray-900">{simulations.length}</p>
                    </div>
                  </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <CheckCircle className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Completed</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {simulations.filter(s => s.status === 'completed' || s.status === 'graded').length}
                    </p>
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
                    <p className="text-sm text-gray-600 mb-1 font-medium">Avg. Score</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {(() => {
                        const gradedSims = simulations.filter(s => (s.status === 'graded' || s.status === 'completed') && s.grade !== null && s.grade !== undefined)
                        if (gradedSims.length === 0) return 'N/A'
                        const avgScore = Math.round(gradedSims.reduce((sum, s) => sum + (s.grade || 0), 0) / gradedSims.length)
                        return `${avgScore}%`
                      })()}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Simulations List */}
          <div className="mb-6 stagger-5 animate-fade-scale">
            <h2 className="text-xl font-bold text-black mb-6">Simulations ({filteredSimulations.length})</h2>
            
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
              <div className="space-y-5">
                {filteredSimulations.map((simulation, index) => {
                  const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                  return (
                <Card key={simulation.id} className={`card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md overflow-hidden ${staggerClass} animate-fade-scale`}>
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
                          const feedbackSummary = extractFeedbackSummary(simulation.feedback)
                          return (
                            <p className="text-sm text-green-700 mt-2 italic line-clamp-2">
                              "{feedbackSummary}"
                            </p>
                          )
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
                    <div className="flex space-x-3 mt-4">
                      {simulation.actions.map((action: string, index: number) => {
                        const isPrimary = action === "Start Simulation" || action === "Continue Simulation" || action === "Continue"
                        const isLoading = startingSimulation === (simulation.unique_id || simulation.id) && isPrimary
                        return (
                          <Button
                            key={index}
                            size="sm"
                            variant={isPrimary ? "default" : "outline"}
                            disabled={simulation.is_draft || action === "Draft - Not Available" || isLoading}
                            className={simulation.is_draft || action === "Draft - Not Available" 
                              ? "bg-gray-400 text-gray-600 cursor-not-allowed" 
                              : isPrimary ? "btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all" : "border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all"}
                            onClick={() => {
                              if (action === "Start Simulation" || action === "Continue Simulation") {
                                handleStartSimulation(simulation)
                              } else if (action === "View Details") {
                                // Handle view details - placeholder for future feature
                              } else if (action === "View Results") {
                                // Navigate to run-simulation page to review results
                                if (simulation.unique_id) {
                                  router.push(`/run-simulation/${simulation.unique_id}`)
                                }
                              } else if (action === "View Grade") {
                                // Navigate to run-simulation page to review graded simulation
                                if (simulation.unique_id) {
                                  router.push(`/run-simulation/${simulation.unique_id}`)
                                }
                              }
                            }}
                          >
                            {isLoading ? (
                              <>
                                <RefreshCw className="h-4 w-4 mr-2 sim-loading-spinner" />
                                Starting...
                              </>
                            ) : (
                              <>
                                {action === "Start Simulation" && <Play className="h-4 w-4 mr-2" />}
                                {action === "Continue" && <Play className="h-4 w-4 mr-2" />}
                                {action === "View Details" && <Eye className="h-4 w-4 mr-2" />}
                                {action === "View Results" && <Trophy className="h-4 w-4 mr-2" />}
                                {action}
                              </>
                            )}
                          </Button>
                        )
                      })}
                    </div>
                  </CardContent>
                </Card>
                  )
                })}
              </div>
            )}
          </div>
    </div>
  )
}
