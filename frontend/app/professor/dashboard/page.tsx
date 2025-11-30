"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { 
  FileText, 
  BookOpen, 
  Upload,
  LogOut,
  Package,
  Plus,
  Calendar,
  Users,
  Lightbulb,
  X,
  ChevronDown,
  Check,
  Play,
  Trash2,
  Edit,
  RefreshCw
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient, Agent, Scenario } from "@/lib/api"

export default function Dashboard() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  // Real data from API
  const [simulations, setSimulations] = useState<any[]>([])
  const [cohorts, setCohorts] = useState<any[]>([])
  const [simulationsLoading, setSimulationsLoading] = useState(true)
  const [cohortsLoading, setCohortsLoading] = useState(true)
  const [simulationsError, setSimulationsError] = useState<string | null>(null)
  const [cohortsError, setCohortsError] = useState<string | null>(null)
  
  const [activeFilter, setActiveFilter] = useState("All")
  const [showWhatsNew, setShowWhatsNew] = useState(true)
  const [editingStatus, setEditingStatus] = useState<number | null>(null)
  const [statusUpdating, setStatusUpdating] = useState<number | null>(null)
  
  // State for deletion
  const [deletingScenario, setDeletingScenario] = useState<number | null>(null)
  
  // State for playing simulation
  const [playingSimulation, setPlayingSimulation] = useState<number | null>(null)
  
  // Request deduplication - prevent multiple simultaneous API calls
  const [pendingRequests, setPendingRequests] = useState<Set<string>>(new Set())

  // Normalize simulation data to ensure is_draft is always set correctly
  const normalizeSimulation = (sim: any) => {
    const isDraft = sim.status?.toLowerCase() === 'draft' || sim.is_draft === true
    return {
      ...sim,
      is_draft: isDraft,
      status: sim.status || (isDraft ? 'Draft' : 'Active')
    }
  }

  // Close status editor when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (editingStatus !== null) {
        const target = event.target as HTMLElement
        if (!target.closest('.status-editor')) {
          setEditingStatus(null)
        }
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [editingStatus])

  // Auto-refresh for creating scenarios - only update status, don't replace entire list
  useEffect(() => {
    const hasCreatingScenarios = simulations.some(sim => {
      const statusLower = sim.status?.toLowerCase() || ''
      const originalStatusLower = (sim as any).original_status?.toLowerCase() || ''
      return statusLower === 'creating' || originalStatusLower === 'creating'
    })
    if (!hasCreatingScenarios) return
    
    const interval = setInterval(async () => {
      try {
        // Only fetch draft scenarios (which includes creating ones)
        const simulationsData = await apiClient.getSimulations()
        const normalizedSimulations = simulationsData.map(normalizeSimulation)
        
        // Smart update: merge with existing simulations to preserve card state and order
        setSimulations(prevSimulations => {
          const updatedMap = new Map(normalizedSimulations.map(sim => [sim.id, sim]))
          
          // Update existing simulations in place, preserving order
          const updated = prevSimulations.map(sim => {
            const updatedSim = updatedMap.get(sim.id)
            return updatedSim || sim // Use updated version if available, otherwise keep existing
          })
          
          // Add any new simulations that weren't in the previous list
          const newSims = normalizedSimulations.filter(sim => !prevSimulations.some(prev => prev.id === sim.id))
          
          return [...updated, ...newSims]
        })
      } catch (error) {
        console.error('Failed to refresh creating scenarios:', error)
      }
    }, 5000) // Refresh every 5 seconds if there are creating scenarios
    
    return () => clearInterval(interval)
  }, [simulations])

  // Fetch data from API
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch simulations
        setSimulationsLoading(true)
        setSimulationsError(null)
        const simulationsData = await apiClient.getSimulations()
        // Normalize simulations to ensure is_draft is set correctly
        const normalizedSimulations = simulationsData.map(normalizeSimulation)
        setSimulations(normalizedSimulations)
      } catch (error) {
        console.error('Failed to fetch simulations:', error)
        // Check if it's an authentication error
        if (error instanceof Error && error.message.includes('Authentication failed')) {
          // Logout and redirect to login
          logout()
          router.push('/')
          return
        }
        setSimulationsError('Failed to load simulations')
        // Fallback to empty array
        setSimulations([])
      } finally {
        setSimulationsLoading(false)
      }

      try {
        // Fetch cohorts
        setCohortsLoading(true)
        setCohortsError(null)
        const cohortsData = await apiClient.getCohorts()
        setCohorts(cohortsData)
      } catch (error) {
        console.error('Failed to fetch cohorts:', error)
        setCohortsError('Failed to load cohorts')
        setCohorts([])
      } finally {
        setCohortsLoading(false)
      }
    }

    if (user && !authLoading) {
      fetchData()
    }
  }, [user, authLoading])

  // Refresh function
  const refreshData = async () => {
    try {
      setSimulationsLoading(true)
      setCohortsLoading(true)
      setSimulationsError(null)
      setCohortsError(null)
      
      const simulationsData = await apiClient.getSimulations()
      // Normalize simulations to ensure is_draft is set correctly
      const normalizedSimulations = simulationsData.map(normalizeSimulation)
      setSimulations(normalizedSimulations)
      
      const cohortsData = await apiClient.getCohorts()
      setCohorts(cohortsData)
    } catch (error) {
      console.error('Failed to refresh data:', error)
      // Check if it's an authentication error
      if (error instanceof Error && error.message.includes('Authentication failed')) {
        // Logout and redirect to login
        logout()
        router.push('/')
        return
      }
      setSimulationsError('Failed to refresh data')
      setCohortsError('Failed to refresh data')
    } finally {
      setSimulationsLoading(false)
      setCohortsLoading(false)
    }
  }

  // Update simulation status
  const updateSimulationStatus = async (simulationId: number, newStatus: string) => {
    try {
      setStatusUpdating(simulationId)
      
      // Call the API and get the updated scenario directly
      const updatedScenario = await apiClient.updateScenarioStatus(simulationId, newStatus)
      
      // Map backend status to frontend display format
      const getDisplayStatus = (backendStatus: string, isDraft: boolean) => {
        if (backendStatus === 'draft') return 'Draft'
        if (backendStatus === 'active') return 'Active'
        if (backendStatus === 'archived') return 'Archived'
        // Fallback to is_draft for backwards compatibility
        return isDraft ? 'Draft' : 'Active'
      }
      
      // Transform the backend response to match frontend format
      // Explicitly set is_draft based on status to ensure consistency
      const isDraftStatus = updatedScenario.status === 'draft' || updatedScenario.is_draft === true
      
      const mappedScenario = {
        id: updatedScenario.id,
        title: updatedScenario.title,
        description: updatedScenario.description,
        status: getDisplayStatus(updatedScenario.status, isDraftStatus),
        date: new Date(updatedScenario.created_at).toLocaleDateString('en-US', { 
          month: 'short', 
          day: 'numeric' 
        }),
        students: updatedScenario.personas?.length || 0,
        created_at: updatedScenario.created_at,
        is_draft: isDraftStatus,
        published_version_id: updatedScenario.published_version_id,
        unique_id: updatedScenario.unique_id
      }
      
      // Update the simulation in local state with the transformed response
      setSimulations(prevSimulations => 
        prevSimulations.map(sim => 
          sim.id === simulationId ? mappedScenario : sim
        )
      )
      
      // If simulation was published (draft -> active), refresh cohorts data
      // This ensures any cohorts with this simulation will show the updated status
      if (newStatus === 'active') {
        try {
          const cohortsData = await apiClient.getCohorts()
          setCohorts(cohortsData)
          
          // Notify cohorts page to refresh simulation data
          localStorage.setItem('simulationStatusChanged', JSON.stringify({
            simulationId,
            newStatus,
            timestamp: Date.now()
          }))
        } catch (error) {
          console.error('Failed to refresh cohorts data:', error)
        }
      }
      
      setEditingStatus(null)
    } catch (error) {
      console.error('Failed to update status:', error)
      
      // If scenario not found, refresh the data to get current state
      if (error instanceof Error && error.message.includes('Scenario not found')) {
        await refreshData()
        alert('Scenario not found. Data has been refreshed.')
      } else {
        alert('Failed to update simulation status. Please try again.')
      }
    } finally {
      setStatusUpdating(null)
    }
  }

  // Play simulation - navigate to chat-box with scenario data
  const playSimulation = (simulation: any) => {
    // Check if simulation is draft (case-insensitive)
    const isDraft = simulation.is_draft || simulation.status?.toLowerCase() === 'draft'
    if (isDraft) {
      alert('Cannot play draft simulations. Please publish the simulation first.')
      return
    }
    
    setPlayingSimulation(simulation.id)
    
    // Store scenario data for chat-box
    const chatboxData = {
      scenario_id: simulation.id,
      title: simulation.title
    }
    
    localStorage.setItem("chatboxScenario", JSON.stringify(chatboxData))
    
    // Navigate to test-simulations
    router.push("/professor/test-simulations")
  }

  // Delete draft simulation
  const deleteDraftSimulation = async (simulationId: number) => {
    if (!confirm('Are you sure you want to delete this draft simulation? This action cannot be undone.')) {
      return
    }
    
    try {
      setDeletingScenario(simulationId)
      await apiClient.deleteDraftScenario(simulationId)
      
      // Remove from local state
      setSimulations(prev => prev.filter(sim => sim.id !== simulationId))
      
    } catch (error) {
      console.error('Failed to delete simulation:', error)
      alert('Failed to delete simulation. Please try again.')
    } finally {
      setDeletingScenario(null)
    }
  }

  // Edit draft simulation - navigate to simulation builder with draft ID
  const editDraftSimulation = async (simulation: any) => {
    const requestKey = `edit-${simulation.id}`
    
    // Prevent duplicate requests
    if (pendingRequests.has(requestKey)) {
      return
    }
    
    try {
      setPendingRequests(prev => new Set(prev).add(requestKey))
      
      // Check if this is a draft using both is_draft flag and status field
      const isDraft = simulation.is_draft || simulation.status?.toLowerCase() === 'draft'
      
      // If this is a published simulation (not a draft), we need to find its draft
      if (!isDraft) {
        // Find the draft scenario that has this published scenario as its published_version_id
        const draftSimulation = simulations.find(s => s.published_version_id === simulation.id && s.is_draft)
        if (draftSimulation) {
          router.push(`/professor/simulation-builder?edit=${draftSimulation.id}`)
          return
        } else {
          alert("No draft found for this published simulation")
          return
        }
      }
      
      // Navigate directly with the draft ID as a URL parameter
      router.push(`/professor/simulation-builder?edit=${simulation.id}`)
      
    } catch (error) {
      console.error('Failed to navigate to draft editing:', error)
      const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred'
      alert(`Failed to open draft for editing: ${errorMessage}`)
    } finally {
      setPendingRequests(prev => {
        const newSet = new Set(prev)
        newSet.delete(requestKey)
        return newSet
      })
    }
  }

  // Calculate stats from actual data
  const activeCohorts = cohorts.filter(cohort => cohort.is_active === true).length
  const activeSimulations = simulations.filter(sim => sim.status?.toLowerCase() === "active").length
  
  // Normalize status display (capitalize first letter)
  const normalizeStatus = (status: string) => {
    if (!status) return 'Draft'
    const lower = status.toLowerCase()
    if (lower === 'creating') return 'Creating...'
    return lower.charAt(0).toUpperCase() + lower.slice(1)
  }
  
  // Compute status colors for each simulation
  const getStatusColor = (status: string) => {
    const normalizedStatus = status?.toLowerCase() || 'draft'
    if (normalizedStatus === 'active') {
      return 'bg-green-100 text-green-800 hover:bg-green-200'
    } else if (normalizedStatus === 'draft') {
      return 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200'
    } else if (normalizedStatus === 'creating') {
      return 'bg-blue-100 text-blue-800 hover:bg-blue-200'
    }
    return 'bg-gray-100 text-gray-800 hover:bg-gray-200'
  }

  const avatarFallback = user?.full_name
    ? user.full_name
        .split(" ")
        .map((part) => part.charAt(0).toUpperCase())
        .slice(0, 2)
        .join("") || "P"
    : user?.email
    ? user.email.charAt(0).toUpperCase()
    : "P"
  
  // Handle redirect when user is not authenticated
  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/")
    }
  }, [user?.id, authLoading, router]) // More specific dependency
  
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

  // If no user, show redirecting message (navigation handled in useEffect)
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

  return (
    <div className="min-h-screen bg-atmospheric relative pattern-dots">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/professor/dashboard" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 relative">
        {/* Header */}
        <header className="bg-white/80 backdrop-blur-sm border-b border-gray-200/60 px-6 py-4 sticky top-0 z-10 shadow-sm">
          <div className="flex items-center justify-between animate-page-enter">
            <div>
              <h1 className="text-4xl font-bold text-black tracking-tight mb-1">Dashboard</h1>
              <p className="text-sm text-gray-600 font-medium">Welcome back, {user?.full_name || user?.username || 'User'}</p>
            </div>
            <div className="flex items-center space-x-4">
              <Link
                href="/professor/profile"
                title="View profile"
                className="transition-transform hover:scale-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black rounded-full"
              >
                <Avatar className="h-10 w-10 border border-gray-200 shadow-sm">
                  {user?.avatar_url ? (
                    <AvatarImage src={user.avatar_url} alt={user?.full_name || 'Professor profile'} />
                  ) : null}
                  <AvatarFallback className="bg-gradient-to-br from-blue-600 to-blue-500 text-white text-sm font-semibold">
                    {avatarFallback}
                  </AvatarFallback>
                </Avatar>
              </Link>
              <Button variant="ghost" size="sm" onClick={handleLogout} className="text-gray-600 hover:text-black">
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </header>

        {/* Main Content Area */}
        <div className="p-8 pb-40">
          {/* Stats Section */}
          <div className="mb-10 stagger-1 animate-fade-scale">
            <div className="flex items-center space-x-6 text-sm text-gray-600 font-medium">
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                <span>{activeCohorts} cohorts active</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                <span>{activeSimulations} simulations active</span>
              </div>
            </div>
          </div>

          {/* What's New Notification */}
          {showWhatsNew && (
            <div className="mb-12 stagger-2 animate-fade-scale">
              <Card className="card-elevated bg-gradient-to-r from-blue-50 to-blue-100/50 border-l-4 border-l-blue-500 shadow-md backdrop-blur-sm">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-3">
                      <Lightbulb className="h-5 w-5 text-blue-500 mt-0.5" />
                      <div className="flex-1">
                        <h3 className="font-semibold text-blue-900 mb-2">What's New</h3>
                        <p className="text-blue-900 text-sm leading-relaxed mb-3">
                          New feature: Real-time collaboration! Students can now work together on simulations with live updates and shared decision-making tools.
                        </p>
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="border-blue-300 text-blue-700 hover:bg-blue-50"
                        >
                          Learn More
                        </Button>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowWhatsNew(false)}
                      className="text-gray-400 hover:text-gray-600 p-1"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Getting Started Section */}
          <div className="mb-12 stagger-3 animate-fade-scale">
            <h2 className="text-3xl font-bold text-black mb-8 tracking-tight">Getting started</h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {/* Create a simulation */}
              <Link href="/professor/simulation-builder">
                <Card className="card-elevated bg-white/90 backdrop-blur-sm border-gray-200/60 cursor-pointer overflow-hidden h-full hover:shadow-lg transition-shadow">
                  <div className="w-full h-30 overflow-hidden rounded-t-lg">
                    <img src="/createsim.png" alt="Create simulation" className="h-full w-full object-cover" />
                  </div>
                  <CardHeader className="pb-3 pt-3">
                    <CardTitle className="text-base text-gray-800">Create simulation</CardTitle>
                    <p className="text-sm text-gray-700 font-medium mt-1">Create a simulation</p>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-600">Upload a case study, configure parameters and publish</p>
                  </CardContent>
                </Card>
              </Link>

              {/* Set up a cohort */}
              <Link href="/professor/cohorts">
                <Card className="card-elevated bg-white/90 backdrop-blur-sm border-gray-200/60 cursor-pointer overflow-hidden h-full hover:shadow-lg transition-shadow">
                  <div className="w-full h-30 overflow-hidden rounded-t-lg">
                    <img src="/cohort.png" alt="Set up cohort" className="h-full w-full object-cover" />
                  </div>
                  <CardHeader className="pb-3 pt-3">
                    <CardTitle className="text-base text-gray-800 font-semibold">Set up cohort</CardTitle>
                    <p className="text-sm text-gray-700 font-medium mt-1">Set up a cohort</p>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-600">Create a group of students and give them certain simulations</p>
                  </CardContent>
                </Card>
              </Link>

              {/* Read our documentation */}
              <Card className="card-elevated bg-white/90 backdrop-blur-sm border-gray-200/60 cursor-pointer overflow-hidden h-full hover:shadow-lg transition-shadow">
                <div className="w-full h-30 overflow-hidden rounded-t-lg">
                  <img src="/createsim.png" alt="Read documentation" className="h-full w-full object-cover" />
                </div>
                <CardHeader className="pb-3 pt-3">
                  <CardTitle className="text-base text-gray-800">Read documentation</CardTitle>
                  <p className="text-sm text-gray-700 font-medium mt-1">Read our documentation</p>
                </CardHeader>
                <CardContent>
                  <p className="text-xs text-gray-600">Get guides, and further understand the platform</p>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* My Simulations Section */}
          <div className="mt-12 stagger-4 animate-fade-scale">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-3xl font-bold text-black tracking-tight">My simulations</h2>
              <Link href="/professor/simulation-builder">
                <Button className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all text-sm font-semibold">
                  <Plus className="h-4 w-4 mr-2" />
                  New Simulation
                </Button>
              </Link>
            </div>
            
            {/* Filter Bar */}
            <div className="flex space-x-3 mb-8">
              {["All", "Draft", "Active"].map((filter) => (
                <button
                  key={filter}
                  onClick={() => setActiveFilter(filter)}
                  className={`px-6 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                    activeFilter === filter
                      ? "bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-md"
                      : "bg-white/80 backdrop-blur-sm text-gray-600 hover:bg-white border border-gray-200/60 shadow-sm hover:shadow-md"
                  }`}
                >
                  {filter}
                </button>
              ))}
            </div>
            
            {/* Loading State */}
            {simulationsLoading && (
              <div className="text-center py-8">
                <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-600"></div>
                </div>
                <p className="text-gray-500 text-base">Loading simulations...</p>
              </div>
            )}

            {/* Error State */}
            {simulationsError && !simulationsLoading && (
              <div className="text-center py-8">
                <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-3">
                  <X className="h-8 w-8 text-red-500" />
                </div>
                <p className="text-red-500 text-base mb-2">Failed to load simulations</p>
                <p className="text-gray-400 text-sm mb-4">{simulationsError}</p>
                <Button onClick={refreshData} variant="outline" size="sm">
                  Try Again
                </Button>
              </div>
            )}

            {/* Simulations Grid */}
            {!simulationsLoading && !simulationsError && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-8">
                {simulations
                  .filter(sim => {
                    if (activeFilter === "All") return true
                    if (activeFilter === "Draft") {
                      // Include both draft and creating scenarios in Draft filter
                      // Check both mapped status and original_status
                      const statusLower = sim.status?.toLowerCase() || ''
                      const originalStatusLower = (sim as any).original_status?.toLowerCase() || ''
                      return statusLower === 'draft' || statusLower === 'creating' || 
                             originalStatusLower === 'draft' || originalStatusLower === 'creating' ||
                             sim.is_draft
                    }
                    return sim.status?.toLowerCase() === activeFilter.toLowerCase()
                  })
                  .map((simulation, index) => {
                    const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                    return (
                  <Card key={simulation.id} className={`card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${staggerClass} animate-fade-scale`}>
                    <CardHeader className="pb-4 px-4 sm:px-6 pt-4 sm:pt-6">
                      {/* Header Container - Title and Status */}
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                        <CardTitle className="text-base sm:text-lg font-semibold text-gray-900 leading-tight cursor-pointer hover:text-blue-600 transition-colors flex-1 min-w-0"
                          onClick={() => playSimulation(simulation)}
                        >
                          <span className="block truncate">{simulation.title}</span>
                          {simulation.unique_id && (
                            <span className="text-xs text-gray-500 font-mono mt-1 block">ID: {simulation.unique_id}</span>
                          )}
                        </CardTitle>
                        <div className="relative status-editor flex-shrink-0">
                          {editingStatus === simulation.id ? (
                            <div className="flex items-center space-x-2">
                              <select
                                value={simulation.status === 'Active' ? 'active' : 'draft'}
                                onChange={(e) => updateSimulationStatus(simulation.id, e.target.value)}
                                className="text-xs px-2 py-1 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                                disabled={statusUpdating === simulation.id}
                              >
                                <option value="draft">Draft</option>
                                <option value="active">Active</option>
                              </select>
                              {statusUpdating === simulation.id && (
                                <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin"></div>
                              )}
                            </div>
                          ) : (
                            <div className="flex items-center space-x-2">
                              {(simulation.status?.toLowerCase() === 'creating' || (simulation as any).original_status?.toLowerCase() === 'creating') ? (
                                <Badge className="text-xs px-3 py-1 bg-gradient-to-r from-blue-50 to-blue-100 text-blue-700 border border-blue-200/50 hover:from-blue-100 hover:to-blue-200 transition-all shadow-sm">
                                  <div className="flex items-center space-x-2">
                                    <RefreshCw className="h-3.5 w-3.5 animate-spin text-blue-600" />
                                    <span className="font-medium">Creating simulation...</span>
                                  </div>
                                </Badge>
                              ) : (
                                <>
                                  <Badge 
                                    className={`text-xs ${getStatusColor(simulation.status)} cursor-pointer`}
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setEditingStatus(simulation.id)
                                    }}
                                  >
                                    {normalizeStatus(simulation.status)}
                                  </Badge>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setEditingStatus(simulation.id)
                                    }}
                                    className="text-gray-400 hover:text-gray-600 transition-colors"
                                  >
                                    <ChevronDown className="h-3 w-3" />
                                  </button>
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="pt-0 px-4 sm:px-6 pb-4 sm:pb-6">
                      {/* Content Container - Metadata and Actions */}
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-4 sm:gap-6 text-sm text-gray-600">
                          <div className="flex items-center">
                            <Calendar className="h-4 w-4 mr-2 flex-shrink-0" />
                            <span>{simulation.date}</span>
                          </div>
                          <div className="flex items-center">
                            <Users className="h-4 w-4 mr-2 flex-shrink-0" />
                            <span>{simulation.students} students</span>
                          </div>
                        </div>
                        <div className="flex items-center justify-end sm:justify-start gap-2 flex-wrap">
                          {(() => {
                            const isDraft = simulation.is_draft || simulation.status?.toLowerCase() === 'draft'
                            const isCreating = simulation.status?.toLowerCase() === 'creating' || (simulation as any).original_status?.toLowerCase() === 'creating'
                            
                            // Hide buttons for creating scenarios - status badge shows loading state
                            if (isCreating) {
                              return null
                            }
                            
                            return (
                              <>
                                <Button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    playSimulation(simulation)
                                  }}
                                  disabled={isDraft || playingSimulation === simulation.id}
                                  className={`text-sm px-3 sm:px-4 py-2 h-8 flex-shrink-0 transition-all ${
                                    isDraft
                                      ? 'bg-gray-400 text-gray-600 cursor-not-allowed' 
                                      : 'btn-gradient text-white border-0 shadow-md hover:shadow-lg'
                                  }`}
                                >
                                  {playingSimulation === simulation.id ? (
                                    <>
                                      <RefreshCw className="h-4 w-4 mr-1 flex-shrink-0 sim-loading-spinner" />
                                      <span>Loading...</span>
                                    </>
                                  ) : (
                                    <>
                                      <Play className="h-4 w-4 mr-1 flex-shrink-0" />
                                      <span className="hidden sm:inline">{isDraft ? 'Draft' : 'Play'}</span>
                                      <span className="sm:hidden">{isDraft ? 'Draft' : 'Play'}</span>
                                    </>
                                  )}
                                </Button>
                                
                                {/* Edit and Delete buttons for draft simulations */}
                                {isDraft && (
                                  <>
                                    <Button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        editDraftSimulation(simulation)
                                      }}
                                      variant="outline"
                                      size="sm"
                                      className="h-8 px-3 flex-shrink-0"
                                    >
                                      <Edit className="h-4 w-4" />
                                    </Button>
                                    <Button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        deleteDraftSimulation(simulation.id)
                                      }}
                                      disabled={deletingScenario === simulation.id}
                                      variant="destructive"
                                      size="sm"
                                      className="h-8 px-3 flex-shrink-0"
                                    >
                                      {deletingScenario === simulation.id ? (
                                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                      ) : (
                                        <Trash2 className="h-4 w-4" />
                                      )}
                                    </Button>
                                  </>
                                )}
                              </>
                            )
                          })()}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                    )
                  })}
                
                {/* Show message if no simulations match filter */}
                {simulations.filter(sim => activeFilter === "All" || sim.status?.toLowerCase() === activeFilter.toLowerCase()).length === 0 && (
                  <div className="text-center py-8 col-span-full">
                    <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-3">
                      <Package className="h-8 w-8 text-gray-400" />
                    </div>
                    <p className="text-gray-500 text-base mb-2">No {activeFilter.toLowerCase()} simulations</p>
                    <p className="text-gray-400 text-sm mb-4">
                      {activeFilter === "All" 
                        ? "Create your first simulation to get started" 
                        : `No simulations with status "${activeFilter}" found`}
                    </p>
                    <Link href="/professor/simulation-builder">
                      <Button className="bg-black text-white hover:bg-gray-800 text-sm">
                        <Plus className="h-4 w-4 mr-2" />
                        Create Simulation
                      </Button>
                    </Link>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}