"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter, useParams } from "next/navigation"
import { notFound } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { 
  ArrowLeft,
  Copy,
  Users,
  Settings,
  Search,
  Filter,
  CheckCircle,
  BookOpen,
  Clock,
  MoreVertical,
  ChevronDown,
  Plus,
  X,
  Calendar,
  UserPlus
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

export default function CohortDetail() {
  const router = useRouter()
  const params = useParams()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  const [activeTab, setActiveTab] = useState("Students")
  const [cohortData, setCohortData] = useState<any>(null)
  const [students, setStudents] = useState<any[]>([])
  const [simulations, setSimulations] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Simulation assignment modal state
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [availableScenarios, setAvailableScenarios] = useState<any[]>([])
  const [selectedScenario, setSelectedScenario] = useState<any>(null)
  const [dueDate, setDueDate] = useState("")
  const [isRequired, setIsRequired] = useState(true)
  const [assigning, setAssigning] = useState(false)

  // Fetch cohort data on component mount
  useEffect(() => {
    const fetchCohortData = async () => {
      if (!params.id) return
      
      try {
        setLoading(true)
        setError(null)
        
        // Fetch cohort details
        const cohort = await apiClient.getCohort(params.id as string)
        setCohortData(cohort)
        
        // Fetch students and simulations in parallel
        const [studentsData, simulationsData] = await Promise.all([
          apiClient.getCohortStudents(params.id as string).catch((err) => {
            console.warn('Failed to fetch students:', err);
            return [];
          }),
          apiClient.getCohortSimulations(params.id as string).catch((err) => {
            console.warn('Failed to fetch simulations:', err);
            return [];
          })
        ])
        
        setStudents(studentsData)
        setSimulations(simulationsData)
        
      } catch (err) {
        console.error('Error fetching cohort data:', err)
        setError(err instanceof Error ? err.message : 'Failed to load cohort data')
      } finally {
        setLoading(false)
      }
    }
    
    fetchCohortData()
  }, [params.id])

  // Listen for simulation status changes from dashboard
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'simulationStatusChanged' && e.newValue) {
        try {
          const changeData = JSON.parse(e.newValue)
          console.log('Simulation status changed, refreshing cohort data:', changeData)
          
          // Refresh cohort data to get updated simulation statuses
          const refreshCohortData = async () => {
            try {
              // Refresh simulations data
              const simulationsData = await apiClient.getCohortSimulations(params.id as string)
              setSimulations(simulationsData)
            } catch (error) {
              console.warn('Failed to refresh cohort data after simulation status change:', error)
            }
          }
          
          refreshCohortData()
          
          // Clear the notification
          localStorage.removeItem('simulationStatusChanged')
        } catch (error) {
          console.error('Failed to parse simulation status change notification:', error)
        }
      }
    }
    
    window.addEventListener('storage', handleStorageChange)
    
    return () => {
      window.removeEventListener('storage', handleStorageChange)
    }
  }, [params.id])

  const [searchTerm, setSearchTerm] = useState("")
  const [studentFilter, setStudentFilter] = useState("All Students")
  const [showStudentFilterDropdown, setShowStudentFilterDropdown] = useState(false)

  // Fetch available scenarios for assignment
  const fetchAvailableScenarios = async () => {
    try {
      const scenarios = await apiClient.getScenarios()
      setAvailableScenarios(scenarios)
    } catch (error) {
      console.error('Failed to fetch scenarios:', error)
    }
  }

  // Handle simulation assignment
  const handleAssignSimulation = async () => {
    if (!selectedScenario || !cohortData) return
    
    try {
      setAssigning(true)
      
      // Create the assignment data
      const assignmentData = {
        simulation_id: selectedScenario.id,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
        is_required: isRequired
      }
      
      // Call the API to assign simulation to cohort
      await apiClient.assignSimulationToCohort(cohortData.id, assignmentData)
      
      // Refresh simulations data
      const updatedSimulations = await apiClient.getCohortSimulations(params.id as string)
      setSimulations(updatedSimulations)
      
      // Close modal and reset form
      setShowAssignModal(false)
      setSelectedScenario(null)
      setDueDate("")
      setIsRequired(true)
      
    } catch (error) {
      console.error('Failed to assign simulation:', error)
      alert('Failed to assign simulation. Please try again.')
    } finally {
      setAssigning(false)
    }
  }

  // Handle redirect when user is not authenticated
  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/")
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

  // Show loading while fetching cohort data
  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black mx-auto mb-4"></div>
          <p className="text-black">Loading cohort data...</p>
        </div>
      </div>
    )
  }

  // Show error if cohort not found or failed to load
  if (error || !cohortData) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error || 'Cohort not found'}</p>
          <Button onClick={() => router.push('/cohorts')}>
            Back to Cohorts
          </Button>
        </div>
      </div>
    )
  }

  const handleLogout = () => {
    logout()
    router.push("/")
  }

  const handleCopyInviteLink = async () => {
    try {
      // Get base URL from environment variable or use current origin as fallback
      const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || window.location.origin
      const inviteUrl = `${baseUrl}/cohorts/${cohortData.id}/join`
      
      await navigator.clipboard.writeText(inviteUrl)
      
      // Show success feedback (you could use a toast library here)
      console.log('Invite link copied to clipboard!')
    } catch (error) {
      console.error('Failed to copy invite link:', error)
      // Fallback for browsers that don't support clipboard API
      const textArea = document.createElement('textarea')
      textArea.value = `${process.env.NEXT_PUBLIC_BASE_URL || window.location.origin}/cohorts/${cohortData.id}/join`
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    }
  }

  const filteredStudents = students.filter(student => {
    const matchesSearch = student.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         student.email.toLowerCase().includes(searchTerm.toLowerCase())
    
    if (studentFilter === "All Students") {
      return matchesSearch
    } else if (studentFilter === "Active") {
      return student.status === "Active" && matchesSearch
    } else if (studentFilter === "Pending") {
      return student.status === "Pending" && matchesSearch
    }
    return matchesSearch
  })

  return (
    <div className="min-h-screen bg-white">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/professor/cohorts" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 bg-white">
        {/* Main Content Area */}
        <div className="p-6">
          {/* Back Navigation */}
          <div className="mb-6">
            <Link 
              href="/professor/cohorts" 
              className="inline-flex items-center text-sm text-gray-600 hover:text-black transition-colors"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Cohorts
            </Link>
          </div>

          {/* Cohort Header */}
          <div className="mb-8">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h2 className="text-2xl font-bold text-black mb-2">{cohortData?.title || 'Loading...'}</h2>
                <p className="text-gray-600 mb-4">{cohortData?.description || 'No description provided'}</p>
                
                <div className="flex items-center space-x-4">
                  <Badge className="bg-gray-100 text-gray-700 text-xs px-2 py-1 hover:bg-black hover:text-white transition-colors duration-200 cursor-pointer">
                    ID: {cohortData?.unique_id || cohortData?.id || 'Loading...'}
                  </Badge>
                  <Badge className={`text-xs px-2 py-1 transition-colors duration-200 ${
                    cohortData?.is_active 
                      ? 'bg-green-100 text-green-700 hover:bg-black hover:text-white' 
                      : 'bg-gray-100 text-gray-600 hover:bg-black hover:text-white'
                  }`}>
                    {cohortData?.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                  <span className="text-sm text-gray-600">
                    Created {cohortData?.created_at ? new Date(cohortData.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'Loading...'}
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center space-x-3">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => {
                    const inviteLink = `${window.location.origin}/cohorts/${cohortData?.id}/join`;
                    navigator.clipboard.writeText(inviteLink);
                    // You could add a toast notification here
                  }}
                  className="border-gray-300 text-gray-700 hover:bg-gray-50"
                >
                  <Copy className="h-4 w-4 mr-2" />
                  Copy Invite Link
                </Button>
                <Button 
                  size="sm"
                  className="bg-black text-white hover:bg-gray-800"
                >
                  <Users className="h-4 w-4 mr-2" />
                  Invite Students
                </Button>
                <Button 
                  variant="ghost" 
                  size="sm"
                  className="text-gray-600 hover:text-black"
                >
                  <Settings className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>

          {/* Metrics Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            {/* Total Students */}
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <div className="flex items-center">
                <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mr-4">
                  <Users className="h-6 w-6 text-blue-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-1">Total Students</p>
                  <p className="text-2xl font-bold text-gray-900">{students?.length || 0}</p>
                </div>
              </div>
            </div>

            {/* Active Students */}
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <div className="flex items-center">
                <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mr-4">
                  <CheckCircle className="h-6 w-6 text-green-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-1">Active Students</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {students?.filter(student => student.status === 'approved').length || 0}
                  </p>
                </div>
              </div>
            </div>

            {/* Simulations */}
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <div className="flex items-center">
                <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mr-4">
                  <BookOpen className="h-6 w-6 text-purple-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-1">Simulations</p>
                  <p className="text-2xl font-bold text-gray-900">{simulations?.length || 0}</p>
                </div>
              </div>
            </div>

            {/* Avg. Completion */}
            <div className="bg-white border border-gray-200 rounded-lg p-6">
              <div className="flex items-center">
                <div className="w-12 h-12 bg-orange-100 rounded-lg flex items-center justify-center mr-4">
                  <Clock className="h-6 w-6 text-orange-600" />
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-1">Avg. Completion</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {students?.length > 0 
                      ? Math.round((students.filter(student => student.status === 'approved').length / students.length) * 100) 
                      : 0}%
                  </p>
                </div>
              </div>
            </div>
          </div>


          {/* Tabs */}
          <div className="mb-6">
            <div className="flex space-x-2 border-b border-gray-200">
              {["Students", "Simulations", "Analytics", "Settings"].map((tab) => (
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

          {/* Tab Content */}
          {activeTab === "Students" && (
            <div>
              {/* Search and Filter */}
              <div className="flex items-center space-x-4 mb-6">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search students..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent"
                  />
                </div>
                
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setShowStudentFilterDropdown(!showStudentFilterDropdown)}
                    className="px-3 py-2 pr-4 border border-gray-200 rounded-lg bg-gray-50 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent cursor-pointer transition-colors whitespace-nowrap flex items-center justify-between"
                  >
                    <span className="text-gray-700">{studentFilter}</span>
                    <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${showStudentFilterDropdown ? 'rotate-180' : ''}`} />
                  </button>
                  
                  {showStudentFilterDropdown && (
                    <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-32 overflow-y-auto">
                      {["All Students", "Active", "Pending"].map((filter) => (
                        <button
                          key={filter}
                          type="button"
                          onClick={() => {
                            setStudentFilter(filter)
                            setShowStudentFilterDropdown(false)
                          }}
                          className="w-full px-3 py-2 text-left hover:bg-gray-50 focus:bg-gray-50 focus:outline-none text-sm text-gray-700"
                        >
                          {filter}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Students List */}
              <div className="space-y-4">
                {filteredStudents.map((student) => (
                  <Card key={student.id} className="bg-white border border-gray-200">
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-4">
                          <div className="w-12 h-12 bg-gray-200 rounded-full flex items-center justify-center">
                            <span className="text-sm font-medium text-gray-700">{student.initials}</span>
                          </div>
                          <div>
                            <h3 className="font-semibold text-gray-900">{student.name}</h3>
                            <p className="text-sm text-gray-600">{student.email}</p>
                          </div>
                        </div>
                        
                        <div className="flex items-center space-x-4">
                          <div className="text-sm text-gray-700">
                            <div>Completed: {student.completed}</div>
                            <div>Pending: {student.pending}</div>
                          </div>
                          
                          <Badge className={`text-xs ${student.statusColor}`}>
                            {student.status}
                          </Badge>
                          
                          <span className="text-sm text-gray-700">
                            Joined {student.joinedDate}
                          </span>
                          
                          <Button variant="ghost" size="sm" className="text-gray-400 hover:text-gray-600 p-1">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {activeTab === "Simulations" && (
            <div>
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-bold text-black">Assigned Simulations</h3>
                <Button 
                  onClick={() => {
                    fetchAvailableScenarios()
                    setShowAssignModal(true)
                  }}
                  className="bg-black text-white hover:bg-gray-800 text-sm"
                >
                  <BookOpen className="h-4 w-4 mr-2" />
                  Assign Simulation
                </Button>
              </div>

              {/* Simulations List */}
              <div className="space-y-4">
                {simulations.length === 0 ? (
                  <div className="text-center py-8">
                    <BookOpen className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <p className="text-gray-500 mb-4">No simulations assigned yet</p>
                    <Button 
                      onClick={() => {
                        fetchAvailableScenarios()
                        setShowAssignModal(true)
                      }}
                      className="bg-black text-white hover:bg-gray-800"
                    >
                      <BookOpen className="h-4 w-4 mr-2" />
                      Assign First Simulation
                    </Button>
                  </div>
                ) : (
                  simulations.map((simulation) => {
                    // Calculate completion data (mock data for now - would come from API)
                    const totalStudents = students.filter(s => s.status === 'approved').length
                    const completedStudents = Math.floor(Math.random() * totalStudents) // Mock completion
                    const completionPercentage = totalStudents > 0 ? (completedStudents / totalStudents) * 100 : 0
                    
                    return (
                      <Card key={simulation.id} className="bg-white border border-gray-200 rounded-lg shadow-sm">
                        <CardContent className="p-6">
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <h4 className="font-bold text-gray-900 text-lg mb-2">
                                {simulation.simulation?.title || `Simulation ${simulation.simulation_id}`}
                              </h4>
                              <div className="flex items-center space-x-4 text-sm text-gray-500 mb-3">
                                <span>
                                  Assigned {new Date(simulation.assigned_at).toLocaleDateString('en-US', { 
                                    month: 'short', 
                                    day: 'numeric' 
                                  })}
                                </span>
                                {simulation.due_date && (
                                  <span>
                                    Due {new Date(simulation.due_date).toLocaleDateString('en-US', { 
                                      month: 'short', 
                                      day: 'numeric' 
                                    })}
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center space-x-2">
                                {simulation.simulation?.is_draft ? (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                                    Draft
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                    Active
                                  </span>
                                )}
                              </div>
                            </div>
                            
                            <div className="text-right">
                              <div className="text-sm text-gray-600 mb-2">
                                {completedStudents}/{totalStudents} completed
                              </div>
                              <div className="w-32 bg-gray-200 rounded-full h-2">
                                <div 
                                  className="bg-gray-800 h-2 rounded-full transition-all duration-300"
                                  style={{ width: `${completionPercentage}%` }}
                                ></div>
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    )
                  })
                )}
              </div>
            </div>
          )}

          {activeTab === "Analytics" && (
            <div className="text-center py-8">
              <p className="text-gray-500">Analytics content will be displayed here</p>
            </div>
          )}

          {activeTab === "Settings" && (
            <div className="text-center py-8">
              <p className="text-gray-500">Settings content will be displayed here</p>
            </div>
          )}
        </div>
      </div>

      {/* Assign Simulation Modal */}
      {showAssignModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Assign Simulation</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowAssignModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-4">
              {/* Scenario Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Select Simulation
                </label>
                <select
                  value={selectedScenario?.id || ""}
                  onChange={(e) => {
                    const scenario = availableScenarios.find(s => s.id === parseInt(e.target.value))
                    setSelectedScenario(scenario)
                  }}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent"
                >
                  <option value="">Choose a simulation...</option>
                  {availableScenarios.filter(scenario => !scenario.is_draft && scenario.status !== 'Draft').map((scenario) => (
                    <option key={scenario.id} value={scenario.id}>
                      {scenario.title}
                    </option>
                  ))}
                </select>
              </div>

              {/* Due Date */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Due Date (Optional)
                </label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent"
                />
              </div>

              {/* Required Checkbox */}
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="isRequired"
                  checked={isRequired}
                  onChange={(e) => setIsRequired(e.target.checked)}
                  className="h-4 w-4 text-black focus:ring-gray-200 border-gray-300 rounded"
                />
                <label htmlFor="isRequired" className="ml-2 text-sm text-gray-700">
                  Required assignment
                </label>
              </div>
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <Button
                variant="outline"
                onClick={() => setShowAssignModal(false)}
                disabled={assigning}
              >
                Cancel
              </Button>
              <Button
                onClick={handleAssignSimulation}
                disabled={!selectedScenario || assigning}
                className="bg-black text-white hover:bg-gray-800"
              >
                {assigning ? "Assigning..." : "Assign Simulation"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
