"use client"

import { useState, useEffect, useRef } from "react"
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
  RefreshCw,
  CirclePlay,
  ChartColumn,
  CircleCheckBig,
  Clock,
  Activity,
  TrendingUp
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
  const [dashboardStats, setDashboardStats] = useState<any>(null)
  const [recentActivity, setRecentActivity] = useState<any[]>([])
  const [simulationsLoading, setSimulationsLoading] = useState(true)
  const [cohortsLoading, setCohortsLoading] = useState(true)
  const [statsLoading, setStatsLoading] = useState(true)
  const [activityLoading, setActivityLoading] = useState(true)
  const [simulationsError, setSimulationsError] = useState<string | null>(null)
  const [cohortsError, setCohortsError] = useState<string | null>(null)
  const [statsError, setStatsError] = useState<string | null>(null)
  const [activityError, setActivityError] = useState<string | null>(null)
  
  const [activeFilter, setActiveFilter] = useState("All")
  const [showWhatsNew, setShowWhatsNew] = useState(true)
  const [editingStatus, setEditingStatus] = useState<number | null>(null)
  const [statusUpdating, setStatusUpdating] = useState<number | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  
  // State for deletion
  const [deletingScenario, setDeletingScenario] = useState<number | null>(null)
  
  // State for playing simulation
  const [playingSimulation, setPlayingSimulation] = useState<number | null>(null)
  
  // Request deduplication - prevent multiple simultaneous API calls
  const [pendingRequests, setPendingRequests] = useState<Set<string>>(new Set())
  
  // WebSocket connection for real-time updates
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const simulationsRef = useRef<any[]>([])
  const creatingRef = useRef(false)
  const connectWebSocketRef = useRef<(() => Promise<void>) | null>(null)
  const lastActivityRef = useRef<number>(Date.now())
  const lastSimulationFinishRef = useRef<number | null>(null)
  const disconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  
  // OPTIMIZATION: Prevent duplicate fetches (React StrictMode protection)
  const fetchInitiatedRef = useRef(false)

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

  // Fetch data from API
  // OPTIMIZATION: Uses ref to prevent duplicate fetches in React StrictMode
  useEffect(() => {
    // Prevent duplicate fetches (StrictMode protection)
    if (fetchInitiatedRef.current) {
      return
    }

    const fetchData = async () => {
      fetchInitiatedRef.current = true  // Mark as initiated before async calls
      
      try {
        // Fetch simulations
        setSimulationsLoading(true)
        setSimulationsError(null)
        const simulationsData = await apiClient.getSimulations()
        console.log('[DASHBOARD] Fetched simulations from API:', simulationsData.length, simulationsData)
        if (simulationsData.length === 0) {
          console.warn('[DASHBOARD] WARNING: API returned 0 simulations!')
        }
        // Normalize simulations to ensure is_draft is set correctly
        const normalizedSimulations = simulationsData.map(normalizeSimulation)
        console.log('[DASHBOARD] Normalized simulations:', normalizedSimulations.length, normalizedSimulations.map(s => ({ id: s.id, title: s.title, status: s.status, is_draft: s.is_draft })))
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

      try {
        // Fetch dashboard stats
        setStatsLoading(true)
        setStatsError(null)
        const statsData = await apiClient.getDashboardStats()
        setDashboardStats(statsData)
      } catch (error) {
        console.error('Failed to fetch dashboard stats:', error)
        setStatsError('Failed to load dashboard stats')
        // Don't set to null, keep previous stats if available
      } finally {
        setStatsLoading(false)
      }

      try {
        // Fetch recent activity
        setActivityLoading(true)
        setActivityError(null)
        const activityData = await apiClient.getRecentActivity(10)
        setRecentActivity(activityData.activities || [])
      } catch (error) {
        console.error('Failed to fetch recent activity:', error)
        setActivityError('Failed to load recent activity')
        setRecentActivity([])
      } finally {
        setActivityLoading(false)
      }
    }

    if (user && !authLoading) {
      fetchData()
    }
  }, [user?.id, authLoading])  // Use user.id for stable reference

  // WebSocket connection for real-time simulation updates
  // Only connect when there are simulations with status "creating"
  const hasCreatingSimulations = (list: any[]) => {
    return list.some(sim => {
      const statusLower = sim.status?.toLowerCase() || ''
      const originalStatusLower = (sim as any).original_status?.toLowerCase() || ''
      return statusLower === 'creating' || originalStatusLower === 'creating'
    })
  }
  
  useEffect(() => {
    if (!user || authLoading) return

    const connectWebSocket = async () => {
      // Connect if: creating simulations exist OR user is on dashboard (always connect while active)
      // Don't connect if already connected
      if (wsRef.current) return
      try {
        const tokenResponse = await fetch('/api/websocket-token')
        if (!tokenResponse.ok) {
          console.warn('Failed to get WebSocket token, skipping connection')
          return
        }
        
        const { token } = await tokenResponse.json()
        if (!token) {
          console.warn('No token received, skipping WebSocket connection')
          return
        }

        let apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim()
        apiUrl = apiUrl.replace(/\/+$/, '')
        
        if (!apiUrl) {
          console.error('NEXT_PUBLIC_API_URL is empty or invalid')
          return
        }
        
        const wsProtocol = apiUrl.startsWith('https') ? 'wss' : 'ws'
        const wsHost = apiUrl.replace(/^https?:\/\//, '').replace(/\/+$/, '')
        
        if (!wsHost) {
          console.error('WebSocket host is empty after processing:', { apiUrl, wsHost })
          return
        }
        
        const wsUrl = `${wsProtocol}://${wsHost}/api/publishing/simulations/ws/${user.id}?token=${token}`
        
        console.log('Connecting to WebSocket for simulation updates:', { apiUrl, wsHost, wsUrl })
        
        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          console.log('WebSocket connected for simulation updates')
          setWsConnected(true)
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            console.log('WebSocket message received:', data)
            
            if (data.type === 'simulation_ready') {
              console.log(`Simulation ${data.simulation_id} update received! Status: ${data.status}, Title: ${data.title}, TitleOnly: ${data.title_only}`)
              // Update last activity time on any WebSocket message
              lastActivityRef.current = Date.now()
              
              // Handle title-only updates (just update title, don't change status)
              if (data.title_only) {
                console.log(`[DASHBOARD] Title-only update for simulation ${data.simulation_id}, new title: ${data.title}`)
                setSimulations(prevSimulations => {
                  const simulationExists = prevSimulations.some(sim => sim.id === data.simulation_id)
                  
                  // If simulation doesn't exist, add it with creating status
                  if (!simulationExists) {
                    console.log(`[DASHBOARD] Simulation ${data.simulation_id} not in list, adding it with title-only update`)
                    const newSimulation = {
                      id: data.simulation_id,
                      title: data.title || "New Simulation",
                      description: "",
                      status: 'Creating...',
                      date: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                      students: 0,
                      created_at: new Date().toISOString(),
                      is_draft: true,
                      published_version_id: null,
                      unique_id: `SC-${data.simulation_id}`,
                      original_status: 'creating'
                    }
                    return [newSimulation, ...prevSimulations]
                  }
                  
                  // Update existing simulation's title only
                  return prevSimulations.map(sim => {
                    if (sim.id === data.simulation_id) {
                      // Only update title if we have a valid title, otherwise keep existing
                      const newTitle = data.title && data.title.trim() ? data.title.trim() : sim.title
                      console.log(`[DASHBOARD] Updating title from "${sim.title}" to "${newTitle}"`)
                      return {
                        ...sim,
                        title: newTitle
                      }
                    }
                    return sim
                  })
                })
                return // Don't process further, just title update
              }
              
              // If simulation finished (status changed to draft), refresh the full list from API
              // This ensures we get all simulations, not just the one being updated
              if (data.status === 'draft') {
                console.log('Simulation finished, refreshing simulations list from API...')
                // Track when simulation finished for connection management
                lastSimulationFinishRef.current = Date.now()
                lastActivityRef.current = Date.now()
                
                // Keep simulation in "Creating..." state until API refresh completes
                // This ensures the loading state persists while polling/queuing
                setSimulations(prevSimulations => {
                  const simulationExists = prevSimulations.some(sim => sim.id === data.simulation_id)
                  
                  if (!simulationExists) {
                    console.log(`Simulation ${data.simulation_id} not in list, adding it with Creating status...`)
                    // Add the simulation to the list if it doesn't exist, but keep it as "Creating..." until API loads
                    const newSimulation = {
                      id: data.simulation_id,
                      title: data.title || "New Simulation",
                      description: "",
                      status: 'Creating...', // Keep as Creating until API refresh completes
                      date: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                      students: 0,
                      created_at: new Date().toISOString(),
                      is_draft: true,
                      published_version_id: null,
                      unique_id: `SC-${data.simulation_id}`,
                      original_status: 'creating' // Keep as creating until API refresh
                    }
                    return [newSimulation, ...prevSimulations]
                  }
                  
                  // Update existing simulation - keep it as "Creating..." until API refresh completes
                  return prevSimulations.map(sim => {
                    if (sim.id === data.simulation_id) {
                      // Preserve title with better fallback chain - always have a title
                      const preservedTitle = (data.title && data.title.trim()) 
                        ? data.title.trim() 
                        : (sim.title && sim.title.trim()) 
                          ? sim.title 
                          : "New Simulation"
                      
                      return {
                        ...sim,
                        // Keep status as "Creating..." - don't change to Draft yet
                        title: preservedTitle, // Always have a title
                        // Status stays as "Creating..." until API refresh completes
                        original_status: 'creating'
                      }
                    }
                    return sim
                  })
                })
                
                // Then refresh from API immediately (no delay needed since commit happens before notification)
                // Also retry a few times to ensure we get the simulation
                // Only after successful API refresh will we update status to 'Draft'
                const refreshSimulations = (attempt = 1, maxAttempts = 3) => {
                  apiClient.getSimulations()
                    .then(simulationsData => {
                      console.log(`[DASHBOARD] API returned simulations (attempt ${attempt}):`, simulationsData.length, simulationsData)
                      const normalizedSimulations = simulationsData.map(normalizeSimulation)
                      const hasNewSimulation = normalizedSimulations.some(s => s.id === data.simulation_id)
                      
                      if (!hasNewSimulation && attempt < maxAttempts) {
                        console.log(`[DASHBOARD] Simulation ${data.simulation_id} not found, retrying in 1 second... (attempt ${attempt + 1}/${maxAttempts})`)
                        setTimeout(() => refreshSimulations(attempt + 1, maxAttempts), 1000)
                        return
                      }
                      
                      // Only update to Draft status after successful API refresh
                      console.log('[DASHBOARD] Refreshed simulations list:', normalizedSimulations.length, normalizedSimulations.map(s => ({ id: s.id, title: s.title, status: s.status, is_draft: s.is_draft })))
                      if (normalizedSimulations.length === 0) {
                        console.warn('[DASHBOARD] WARNING: API returned 0 simulations, but simulation should exist!')
                      }
                      
                      // If simulation found in API, use that data
                      if (hasNewSimulation) {
                        // Now update with full data from API - this will show the simulation as 'Draft'
                        setSimulations(normalizedSimulations)
                      } else {
                        // Simulation not found in API after max attempts, but we know it finished
                        // Update it to Draft status manually as fallback
                        console.warn(`[DASHBOARD] Simulation ${data.simulation_id} not found in API after ${maxAttempts} attempts, updating to Draft manually`)
                        setSimulations(prevSimulations => {
                          return prevSimulations.map(sim => {
                            if (sim.id === data.simulation_id) {
                              // Preserve title with fallback chain
                              const preservedTitle = (data.title && data.title.trim()) 
                                ? data.title.trim() 
                                : (sim.title && sim.title.trim()) 
                                  ? sim.title 
                                  : "New Simulation"
                              
                              return {
                                ...sim,
                                status: 'Draft',
                                is_draft: true,
                                title: preservedTitle, // Always have a title
                                original_status: 'draft'
                              }
                            }
                            return sim
                          })
                        })
                      }
                    })
                    .catch(error => {
                      console.error(`[DASHBOARD] Failed to refresh simulations (attempt ${attempt}):`, error)
                      if (attempt < maxAttempts) {
                        setTimeout(() => refreshSimulations(attempt + 1, maxAttempts), 2000)
                      } else {
                        // After max attempts, we know the simulation finished (got the notification)
                        // So update it to Draft status even if API refresh failed
                        console.warn(`[DASHBOARD] Max retry attempts reached, updating simulation ${data.simulation_id} to Draft status as fallback`)
                        setSimulations(prevSimulations => {
                          return prevSimulations.map(sim => {
                            if (sim.id === data.simulation_id) {
                              // Preserve title with fallback chain
                              const preservedTitle = (data.title && data.title.trim()) 
                                ? data.title.trim() 
                                : (sim.title && sim.title.trim()) 
                                  ? sim.title 
                                  : "New Simulation"
                              
                              return {
                                ...sim,
                                status: 'Draft',
                                is_draft: true,
                                title: preservedTitle, // Always have a title
                                original_status: 'draft'
                              }
                            }
                            return sim
                          })
                        })
                      }
                    })
                }
                
                refreshSimulations()
              } else {
                // For "creating" status or title-only updates, update the existing simulation in the list
                // BUT: Don't downgrade from 'draft' to 'creating' (title updates can come after completion)
                setSimulations(prevSimulations => {
                  const simulationExists = prevSimulations.some(sim => sim.id === data.simulation_id)
                  
                  if (!simulationExists) {
                    console.log(`Simulation ${data.simulation_id} not in list, adding it...`)
                    // Add the simulation to the list if it doesn't exist
                    const newSimulation = {
                      id: data.simulation_id,
                      title: data.title || "New Simulation",
                      description: "",
                      status: 'Creating...',
                      date: new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
                      students: 0,
                      created_at: new Date().toISOString(),
                      is_draft: true,
                      published_version_id: null,
                      unique_id: `SC-${data.simulation_id}`,
                      original_status: 'creating'
                    }
                    return [newSimulation, ...prevSimulations]
                  }
                  
                  return prevSimulations.map(sim => {
                    if (sim.id === data.simulation_id) {
                      // Check if simulation is already in 'draft' status - don't downgrade to 'creating'
                      const currentStatus = sim.status?.toLowerCase() || ''
                      const currentOriginalStatus = (sim as any).original_status?.toLowerCase() || ''
                      const isAlreadyDraft = currentStatus === 'draft' || currentOriginalStatus === 'draft'
                      
                      // If it's already draft, only update the title, don't change status
                      if (isAlreadyDraft) {
                        console.log(`[DASHBOARD] Simulation ${data.simulation_id} is already draft, only updating title`)
                        return {
                          ...sim,
                          title: data.title || sim.title
                        }
                      }
                      
                      // Otherwise, update status and title
                      // IMPORTANT: Preserve existing title if notification doesn't have one or has empty title
                      const newTitle = data.title && data.title.trim() ? data.title.trim() : sim.title
                      const updated = {
                        ...sim,
                        status: 'Creating...',
                        is_draft: true,
                        title: newTitle, // Always preserve existing title if new one is missing/empty
                        original_status: 'creating'
                      }
                      console.log(`[DASHBOARD] Updated simulation ${data.simulation_id} status to creating, title: "${newTitle}"`)
                      return updated
                    }
                    return sim
                  })
                })
              }
            }
          } catch (error) {
            console.error('Error parsing WebSocket message:', error, event.data)
          }
        }

        ws.onerror = (error) => {
          console.error('WebSocket error:', error)
          setWsConnected(false)
        }

        ws.onclose = (event) => {
          console.log('WebSocket disconnected', { code: event.code, reason: event.reason, wasClean: event.wasClean })
          setWsConnected(false)
          wsRef.current = null
          
          if (event.code !== 1000 && event.code !== 1008) {
            if (creatingRef.current) {
              setTimeout(() => {
                if (user && !authLoading && !wsRef.current && creatingRef.current && connectWebSocketRef.current) {
                  connectWebSocketRef.current()
                }
              }, 5000)
            }
          }
        }
      } catch (error) {
        console.error('Error connecting WebSocket:', error)
      }
    }

    connectWebSocketRef.current = connectWebSocket
    // Always connect when user is on dashboard (hybrid approach)
    // The connection management logic will handle disconnecting when inactive
    connectWebSocket()

    return () => {
      connectWebSocketRef.current = null
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [user, authLoading])

  // Track user activity (mouse movements, clicks, etc.)
  useEffect(() => {
    const updateActivity = () => {
      lastActivityRef.current = Date.now()
    }

    const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click']
    events.forEach(event => {
      window.addEventListener(event, updateActivity, { passive: true })
    })

    return () => {
      events.forEach(event => {
        window.removeEventListener(event, updateActivity)
      })
    }
  }, [])

  // Track page visibility
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        lastActivityRef.current = Date.now()
        // Reconnect if disconnected and should be connected
        if (!wsRef.current && connectWebSocketRef.current && user && !authLoading) {
          connectWebSocketRef.current()
        }
        // Refresh simulations when user returns to tab (in case they missed updates)
        if (user && !authLoading) {
          console.log('[DASHBOARD] Page became visible, refreshing simulations...')
          apiClient.getSimulations()
            .then(simulationsData => {
              const normalizedSimulations = simulationsData.map(normalizeSimulation)
              console.log('[DASHBOARD] Refreshed on visibility change:', normalizedSimulations.length, 'simulations')
              setSimulations(normalizedSimulations)
            })
            .catch(error => {
              console.error('[DASHBOARD] Failed to refresh on visibility change:', error)
            })
        }
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [user, authLoading])

  // Hybrid WebSocket connection management
  useEffect(() => {
    simulationsRef.current = simulations
    creatingRef.current = hasCreatingSimulations(simulations)

    // Clear any existing disconnect timeout
    if (disconnectTimeoutRef.current) {
      clearTimeout(disconnectTimeoutRef.current)
      disconnectTimeoutRef.current = null
    }

    // Determine if we should stay connected
    const now = Date.now()
    const hasCreating = hasCreatingSimulations(simulations)
    const recentActivity = (now - lastActivityRef.current) < 300000 // 5 minutes
    const recentSimulationFinish = lastSimulationFinishRef.current && 
                                   (now - lastSimulationFinishRef.current) < 120000 // 2 minutes
    const isPageVisible = document.visibilityState === 'visible'
    
    const shouldStayConnected = hasCreating || 
                                (recentActivity && isPageVisible) || 
                                (recentSimulationFinish && isPageVisible)

    if (shouldStayConnected) {
      // Should be connected - connect if not already
      if (!wsRef.current && connectWebSocketRef.current && user && !authLoading) {
        console.log('Connecting WebSocket (creating sims or active user)...')
        connectWebSocketRef.current()
      }
    } else {
      // Should disconnect - but give grace period
      if (wsRef.current) {
        console.log('Scheduling WebSocket disconnect after 1 minute grace period...')
        disconnectTimeoutRef.current = setTimeout(() => {
          // Re-check conditions before disconnecting
          const stillShouldDisconnect = !hasCreatingSimulations(simulationsRef.current) &&
                                       (Date.now() - lastActivityRef.current) >= 300000 &&
                                       (!lastSimulationFinishRef.current || 
                                        (Date.now() - (lastSimulationFinishRef.current || 0)) >= 120000)
          
          if (stillShouldDisconnect && wsRef.current) {
            console.log('Disconnecting WebSocket (inactive user)')
            wsRef.current.close()
            wsRef.current = null
            setWsConnected(false)
          }
        }, 60000) // 1 minute grace period
      }
    }

    return () => {
      if (disconnectTimeoutRef.current) {
        clearTimeout(disconnectTimeoutRef.current)
      }
    }
  }, [simulations, user, authLoading])

  // Refresh function
  const refreshData = async () => {
    try {
      setIsRefreshing(true)
      setSimulationsError(null)
      setCohortsError(null)
      setStatsError(null)

      const simulationsData = await apiClient.getSimulations()
      // Normalize simulations to ensure is_draft is set correctly
      const normalizedSimulations = simulationsData.map(normalizeSimulation)
      setSimulations(normalizedSimulations)

      const cohortsData = await apiClient.getCohorts()
      setCohorts(cohortsData)

      const statsData = await apiClient.getDashboardStats()
      setDashboardStats(statsData)

      const activityData = await apiClient.getRecentActivity(10)
      setRecentActivity(activityData.activities || [])
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
      setStatsError('Failed to refresh dashboard stats')
      setActivityError('Failed to refresh recent activity')
    } finally {
      setIsRefreshing(false)
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
    
    // Store simulation data for chat-box
    const chatboxData = {
      simulation_id: simulation.id,
      title: simulation.title
    }
    
    localStorage.setItem("chatboxSimulation", JSON.stringify(chatboxData))
    
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

  // Use dashboard stats from API if available, otherwise calculate from local data
  const totalSimulations = dashboardStats?.total_simulations ?? simulations.length
  const activeStudents = dashboardStats?.active_students ?? cohorts.reduce((sum, cohort) => {
    return sum + (cohort.students?.length || 0)
  }, 0)
  const avgCompletionRate = dashboardStats?.avg_completion_rate ?? 0
  const avgTimePerSimulation = dashboardStats?.avg_time_per_simulation ?? null
  const simulationsThisMonth = dashboardStats?.simulations_this_month ?? 0
  const studentsGrowthPercent = dashboardStats?.students_growth_percent ?? null
  const completionImprovementPercent = dashboardStats?.completion_improvement_percent ?? null
  const typicalTimeRange = dashboardStats?.typical_time_range ?? null
  
  // Get creating simulations (for WebSocket connection)
  const creatingSimulations = simulations.filter(sim => {
    const statusLower = sim.status?.toLowerCase() || ''
    const originalStatusLower = (sim as any).original_status?.toLowerCase() || ''
    return statusLower === 'creating' || originalStatusLower === 'creating'
  })
  
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
        .map((part: string) => part.charAt(0).toUpperCase())
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
    <div className="min-h-screen bg-gray-50">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/professor/dashboard" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 relative">
        {/* Main Content Area */}
        <div className="p-8">
          {/* Header */}
          <div className="flex justify-between items-center mb-8">
            <div>
              <h1 className="text-2xl font-bold">Dashboard</h1>
              <p className="text-gray-600 mt-1">Welcome back! Here's an overview of your simulations</p>
            </div>
            <div className="flex items-center gap-3">
              <Link href="/professor/simulation-builder">
                <button className="bg-black text-white rounded-md px-4 py-2 flex items-center gap-2 hover:bg-gray-800">
                  <Plus className="w-4 h-4" />
                  <span>New Simulation</span>
                </button>
              </Link>
              <button 
                onClick={handleLogout}
                className="bg-gray-200 text-gray-700 rounded-md px-4 py-2 flex items-center gap-2 hover:bg-gray-300"
              >
                <LogOut className="w-4 h-4" />
                <span>Logout</span>
              </button>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid gap-6 mb-8 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
            {/* Welcome Banner */}
            {showWhatsNew && (
              <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg p-6 text-white relative overflow-hidden lg:col-span-2">
                <button 
                  className="absolute top-4 right-4 text-white hover:bg-white hover:bg-opacity-20 rounded-full p-1 transition-colors"
                  onClick={() => setShowWhatsNew(false)}
                >
                  <X className="w-5 h-5" />
                </button>
                <div className="relative z-10">
                  <div className="flex items-center gap-2 mb-3">
                    <CirclePlay className="w-6 h-6" />
                    <span className="text-sm font-medium bg-white bg-opacity-20 px-2 py-1 rounded">New</span>
                  </div>
                  <h3 className="text-xl font-bold mb-2">Welcome to Your Simulation Platform</h3>
                  <p className="text-blue-100 mb-4 text-sm">Watch this 2-minute video to learn how to create engaging simulations for your students and track their progress effectively.</p>
                  <button className="bg-white text-blue-600 px-4 py-2 rounded-md font-medium hover:bg-blue-50 transition-colors flex items-center gap-2">
                    <Play className="w-4 h-4" />
                    Watch Tutorial
                  </button>
                </div>
                <div className="absolute -bottom-6 -right-6 w-32 h-32 bg-white opacity-10 rounded-full"></div>
                <div className="absolute top-1/2 -right-4 w-24 h-24 bg-white opacity-10 rounded-full"></div>
              </div>
            )}

            {/* Total Simulations Card */}
            <div className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-lg flex items-center justify-center bg-blue-50 text-blue-600">
                  <ChartColumn className="w-6 h-6" />
                </div>
              </div>
              <div>
                <p className="text-gray-600 text-sm mb-1">Total Simulations</p>
                <p className="text-3xl font-bold mb-2">{statsLoading ? '...' : totalSimulations}</p>
                <div className="flex items-center gap-1 text-sm text-gray-500">
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span>+{simulationsThisMonth} this month</span>
                </div>
              </div>
            </div>

            {/* Active Students Card */}
            <div className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-lg flex items-center justify-center bg-green-50 text-green-600">
                  <Users className="w-6 h-6" />
                </div>
              </div>
              <div>
                <p className="text-gray-600 text-sm mb-1">Active Students</p>
                <p className="text-3xl font-bold mb-2">{statsLoading ? '...' : activeStudents}</p>
                <div className="flex items-center gap-1 text-sm text-gray-500">
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span>{studentsGrowthPercent !== null ? `+${studentsGrowthPercent.toFixed(0)}% from last month` : 'No previous data'}</span>
                </div>
              </div>
            </div>

            {/* Avg Completion Rate Card */}
            <div className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-lg flex items-center justify-center bg-purple-50 text-purple-600">
                  <CircleCheckBig className="w-6 h-6" />
                </div>
              </div>
              <div>
                <p className="text-gray-600 text-sm mb-1">Avg Completion Rate</p>
                <p className="text-3xl font-bold mb-2">{statsLoading ? '...' : `${avgCompletionRate.toFixed(0)}%`}</p>
                <div className="flex items-center gap-1 text-sm text-gray-500">
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span>{completionImprovementPercent !== null ? `+${completionImprovementPercent.toFixed(1)}% improvement` : 'No previous data'}</span>
                </div>
              </div>
            </div>

            {/* Avg Time per Simulation Card */}
            <div className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-lg flex items-center justify-center bg-orange-50 text-orange-600">
                  <Clock className="w-6 h-6" />
                </div>
              </div>
              <div>
                <p className="text-gray-600 text-sm mb-1">Avg Time per Simulation</p>
                <p className="text-3xl font-bold mb-2">{statsLoading ? '...' : (avgTimePerSimulation || 'N/A')}</p>
                <div className="flex items-center gap-1 text-sm text-gray-500">
                  <TrendingUp className="w-4 h-4 text-green-500" />
                  <span>{typicalTimeRange ? `Typical range: ${typicalTimeRange}` : 'No data available'}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Recent Activity Section */}
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">Recent Activity</h2>
              <button className="text-sm text-blue-600 hover:text-blue-700 font-medium">View All</button>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg divide-y divide-gray-200 max-h-[210px] overflow-y-auto">
              {activityLoading ? (
                <div className="p-8 text-center text-gray-500">Loading activity...</div>
              ) : recentActivity.length === 0 ? (
                <div className="p-8 text-center text-gray-500">No recent activity</div>
              ) : (
                recentActivity.map((activity, index) => {
                  const getIcon = () => {
                    if (activity.type === 'completion') {
                      return <CircleCheckBig className="w-5 h-5 text-green-600" />
                    } else if (activity.type === 'enrollment') {
                      return <Users className="w-5 h-5 text-purple-600" />
                    } else {
                      return <Activity className="w-5 h-5 text-blue-600" />
                    }
                  }
                  
                  const getBgColor = () => {
                    if (activity.type === 'completion') return 'bg-green-50'
                    if (activity.type === 'enrollment') return 'bg-purple-50'
                    return 'bg-blue-50'
                  }
                  
                  const formatTimeAgo = (timestamp: string) => {
                    const date = new Date(timestamp)
                    const now = new Date()
                    const diffMs = now.getTime() - date.getTime()
                    const diffMins = Math.floor(diffMs / 60000)
                    const diffHours = Math.floor(diffMs / 3600000)
                    const diffDays = Math.floor(diffHours / 24)
                    
                    if (diffMins < 1) return 'Just now'
                    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`
                    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
                    if (diffDays === 1) return 'Yesterday'
                    if (diffDays < 7) return `${diffDays} days ago`
                    return date.toLocaleDateString()
                  }
                  
                  return (
                    <div key={index} className="p-4 flex items-center gap-4">
                      <div className={`w-10 h-10 ${getBgColor()} rounded-full flex items-center justify-center`}>
                        {getIcon()}
                      </div>
                      <div className="flex-1">
                        <p className="font-medium">{activity.title}</p>
                        <p className="text-sm text-gray-500">{formatTimeAgo(activity.timestamp)}</p>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* My Simulations Section */}
          <div>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">My Simulations</h2>
              <div className="flex gap-2 items-center">
                <Button 
                  onClick={async () => {
                    try {
                      setSimulationsLoading(true)
                      const simulationsData = await apiClient.getSimulations()
                      const normalizedSimulations = simulationsData.map(normalizeSimulation)
                      setSimulations(normalizedSimulations)
                      console.log('[DASHBOARD] Manually refreshed simulations:', normalizedSimulations.length)
                    } catch (error) {
                      console.error('Failed to refresh simulations:', error)
                    } finally {
                      setSimulationsLoading(false)
                    }
                  }}
                  variant="outline"
                  size="sm"
                  className="mr-2"
                >
                  <RefreshCw className="w-4 h-4 mr-1" />
                  Refresh
                </Button>
                {["All", "Draft", "Active"].map((filter) => (
                  <button
                    key={filter}
                    onClick={() => setActiveFilter(filter)}
                    className={`px-4 py-2 rounded-full text-sm font-medium ${
                      activeFilter === filter
                        ? "bg-gray-100"
                        : "hover:bg-gray-100"
                    }`}
                  >
                    {filter}
                  </button>
                ))}
              </div>
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
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {simulations
                  .filter(sim => {
                    if (activeFilter === "All") return true
                    if (activeFilter === "Draft") {
                      const statusLower = sim.status?.toLowerCase() || ''
                      const originalStatusLower = (sim as any).original_status?.toLowerCase() || ''
                      return statusLower === 'draft' || statusLower === 'creating' || 
                             originalStatusLower === 'draft' || originalStatusLower === 'creating' ||
                             sim.is_draft
                    }
                    return sim.status?.toLowerCase() === activeFilter.toLowerCase()
                  })
                  .map((simulation) => {
                    const isDraft = simulation.is_draft || simulation.status?.toLowerCase() === 'draft'
                    const isCreating = simulation.status?.toLowerCase() === 'creating' || (simulation as any).original_status?.toLowerCase() === 'creating'
                    const statusDisplay = isDraft ? 'Draft' : (isCreating ? 'Creating...' : 'Active')
                    const statusColor = isDraft ? 'bg-yellow-50 text-yellow-700' : (isCreating ? 'bg-blue-50 text-blue-700' : 'bg-green-50 text-green-700')
                    
                    return (
                      <div key={simulation.id} className={`border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow ${isCreating ? 'relative overflow-hidden border-blue-200' : ''}`}>
                        {isCreating && (
                          <>
                            <div className="absolute inset-0 bg-gradient-to-r from-blue-50/30 via-blue-100/50 to-blue-50/30"></div>
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer" style={{
                              backgroundSize: '200% 100%'
                            }}></div>
                          </>
                        )}
                        {isCreating && (
                          <div className="absolute top-2 right-2 flex items-center gap-2 bg-blue-100 text-blue-700 px-2 py-1 rounded-md text-xs font-medium shadow-sm z-20">
                            <div className="flex gap-1">
                              <div className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                              <div className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                              <div className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                            </div>
                            <span>Creating...</span>
                          </div>
                        )}
                        <div className="flex justify-between items-start mb-4 relative z-10">
                          <h3 className="text-base font-medium">
                            {simulation.title && simulation.title.trim() 
                              ? (simulation.title.length > 40 ? `${simulation.title.substring(0, 40)}...` : simulation.title)
                              : isCreating 
                                ? "New Simulation" 
                                : "Untitled Simulation"}
                          </h3>
                          <button
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              if (isCreating) {
                                alert('Cannot change status while simulation is being created.')
                                return
                              }
                              // Toggle between active and draft
                              const currentStatus = isDraft ? 'draft' : 'active'
                              const newStatus = currentStatus === 'draft' ? 'active' : 'draft'
                              updateSimulationStatus(simulation.id, newStatus)
                            }}
                            disabled={isCreating || statusUpdating === simulation.id}
                            className={`text-xs px-2 py-1 ${statusColor} rounded-md cursor-pointer hover:opacity-80 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed ${isCreating ? 'relative z-10' : ''}`}
                            title={isCreating ? 'Cannot change status while creating' : `Click to change to ${isDraft ? 'Active' : 'Draft'}`}
                          >
                            {statusUpdating === simulation.id ? (
                              <span className="flex items-center gap-1">
                                <RefreshCw className="w-3 h-3 animate-spin" />
                                Updating...
                              </span>
                            ) : (
                              statusDisplay
                            )}
                          </button>
                        </div>
                        <div className={`flex items-center text-sm text-gray-500 gap-4 mb-4 ${isCreating ? 'relative z-10' : ''}`}>
                          <div className="flex items-center gap-1">
                            <Calendar className="w-4 h-4" />
                            <span>{simulation.date}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <Users className="w-4 h-4" />
                            <span>{simulation.students} students</span>
                          </div>
                        </div>
                        <div className={`flex gap-2 ${isCreating ? 'relative z-10' : ''}`}>
                          {isDraft && !isCreating && (
                            <>
                              <button 
                                onClick={(e) => {
                                  e.preventDefault()
                                  e.stopPropagation()
                                  deleteDraftSimulation(simulation.id)
                                }}
                                disabled={deletingScenario === simulation.id}
                                className="rounded-md py-2 px-3 flex items-center justify-center gap-2 bg-red-500 text-white hover:bg-red-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                title="Delete draft simulation"
                              >
                                {deletingScenario === simulation.id ? (
                                  <RefreshCw className="w-4 h-4 animate-spin" />
                                ) : (
                                  <Trash2 className="w-4 h-4" />
                                )}
                              </button>
                              <button 
                                onClick={(e) => {
                                  e.preventDefault()
                                  e.stopPropagation()
                                  editDraftSimulation(simulation)
                                }}
                                className="flex-1 rounded-md py-2 flex items-center justify-center gap-2 bg-gray-600 text-white hover:bg-gray-700 transition-colors"
                              >
                                <Edit className="w-4 h-4" />
                                <span>Edit</span>
                              </button>
                            </>
                          )}
                          <button 
                            onClick={(e) => {
                              e.preventDefault()
                              if (isDraft || isCreating) {
                                if (isDraft) {
                                  alert('Cannot play draft simulations. Please publish the simulation first.')
                                }
                                return
                              }
                              playSimulation(simulation)
                            }}
                            className={`${isDraft && !isCreating ? 'flex-1' : 'w-full'} rounded-md py-2 flex items-center justify-center gap-2 ${
                              isDraft || isCreating
                                ? 'bg-gray-300 text-gray-600 cursor-not-allowed'
                                : 'bg-blue-500 text-white hover:bg-blue-600'
                            }`}
                            disabled={isDraft || isCreating || playingSimulation === simulation.id}
                          >
                            {playingSimulation === simulation.id ? (
                              <>
                                <RefreshCw className="w-4 h-4 animate-spin" />
                                <span>Loading...</span>
                              </>
                            ) : (
                              <>
                                <Play className="w-4 h-4" />
                                <span>Play</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    )
                  })}
                
                {/* Show message if no simulations match filter */}
                {simulations.filter(sim => {
                  if (activeFilter === "All") return true
                  if (activeFilter === "Draft") {
                    const statusLower = sim.status?.toLowerCase() || ''
                    const originalStatusLower = (sim as any).original_status?.toLowerCase() || ''
                    return statusLower === 'draft' || statusLower === 'creating' || 
                           originalStatusLower === 'draft' || originalStatusLower === 'creating' ||
                           sim.is_draft
                  }
                  return sim.status?.toLowerCase() === activeFilter.toLowerCase()
                }).length === 0 && (
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