"use client"

import { useState, useEffect, useRef } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
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
  Target,
  Shield,
  Trophy,
  Clock,
  ArrowRight,
  CheckCircle,
  Zap,
  TrendingUp
} from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { apiClient, Agent, Scenario } from "@/lib/api"
import { DOCUMENTATION_URL } from "@/lib/constants"

export default function DashboardPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, logout, isLoading: authLoading } = useAuth()

  const isProfessor = user?.role === "professor" || user?.role === "admin"

  // ── Shared state ──
  const [loading, setLoading] = useState(true)

  // ── Professor state ──
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
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [deletingScenario, setDeletingScenario] = useState<number | null>(null)
  const [playingSimulation, setPlayingSimulation] = useState<number | null>(null)
  const [pendingRequests, setPendingRequests] = useState<Set<string>>(new Set())

  // WebSocket refs (professor)
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const simulationsRef = useRef<any[]>([])
  const creatingRef = useRef(false)
  const connectWebSocketRef = useRef<(() => Promise<void>) | null>(null)
  const fetchInitiatedRef = useRef(false)

  // ── Student state ──
  const [activeCohorts, setActiveCohorts] = useState<any[]>([])
  const [recentSimulations, setRecentSimulations] = useState<any[]>([])
  const [allSimulations, setAllSimulations] = useState<any[]>([])

  // ────────────────────────────────────────────────
  // Professor helpers
  // ────────────────────────────────────────────────

  const normalizeSimulation = (sim: any) => {
    const isDraft = sim.status?.toLowerCase() === "draft" || sim.is_draft === true
    return {
      ...sim,
      is_draft: isDraft,
      status: sim.status || (isDraft ? "Draft" : "Active"),
    }
  }

  const hasCreatingSimulations = (list: any[]) => {
    return list.some((sim) => {
      const statusLower = sim.status?.toLowerCase() || ""
      const originalStatusLower = (sim as any).original_status?.toLowerCase() || ""
      return statusLower === "creating" || originalStatusLower === "creating"
    })
  }

  const normalizeStatus = (status: string) => {
    if (!status) return "Draft"
    const lower = status.toLowerCase()
    if (lower === "creating") return "Creating..."
    return lower.charAt(0).toUpperCase() + lower.slice(1)
  }

  const getStatusColor = (status: string) => {
    const s = status?.toLowerCase() || "draft"
    if (s === "active") return "bg-green-100 text-green-800 hover:bg-green-200"
    if (s === "draft") return "bg-yellow-100 text-yellow-800 hover:bg-yellow-200"
    if (s === "creating") return "bg-blue-100 text-blue-800 hover:bg-blue-200"
    return "bg-gray-100 text-gray-800 hover:bg-gray-200"
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

  // ────────────────────────────────────────────────
  // Close status editor on outside click
  // ────────────────────────────────────────────────

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (editingStatus !== null) {
        const target = event.target as HTMLElement
        if (!target.closest(".status-editor")) {
          setEditingStatus(null)
        }
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [editingStatus])

  // ────────────────────────────────────────────────
  // Refresh param handling
  // ────────────────────────────────────────────────

  useEffect(() => {
    if (user && searchParams?.get("refresh") === "true") {
      if (isProfessor) {
        refreshProfessorData()
      } else {
        loadStudentData()
      }
      if (typeof window !== "undefined") {
        window.history.replaceState({}, "", "/dashboard")
      }
    }
  }, [user, searchParams])

  // ────────────────────────────────────────────────
  // Professor data fetching
  // ────────────────────────────────────────────────

  useEffect(() => {
    if (!user || authLoading || !isProfessor) return
    if (fetchInitiatedRef.current) return

    const fetchData = async () => {
      fetchInitiatedRef.current = true

      try {
        setSimulationsLoading(true)
        setSimulationsError(null)
        const simulationsData = await apiClient.getSimulations()
        const normalizedSimulations = simulationsData.map(normalizeSimulation)
        setSimulations(normalizedSimulations)
      } catch (error) {
        console.error("Failed to fetch simulations:", error)
        if (error instanceof Error && error.message.includes("Authentication failed")) {
          logout()
          router.push("/")
          return
        }
        setSimulationsError("Failed to load simulations")
        setSimulations([])
      } finally {
        setSimulationsLoading(false)
      }

      try {
        setCohortsLoading(true)
        setCohortsError(null)
        const cohortsData = await apiClient.getCohorts()
        setCohorts(cohortsData)
      } catch (error) {
        console.error("Failed to fetch cohorts:", error)
        setCohortsError("Failed to load cohorts")
        setCohorts([])
      } finally {
        setCohortsLoading(false)
      }
    }

    fetchData()
  }, [user?.id, authLoading])

  // ── Professor WebSocket ──

  useEffect(() => {
    if (!user || authLoading || !isProfessor) return

    const connectWebSocket = async () => {
      if (!creatingRef.current || wsRef.current) return
      try {
        const tokenResponse = await fetch("/api/websocket-token")
        if (!tokenResponse.ok) {
          console.warn("Failed to get WebSocket token, skipping connection")
          return
        }

        const { token } = await tokenResponse.json()
        if (!token) {
          console.warn("No token received, skipping WebSocket connection")
          return
        }

        let apiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").trim()
        apiUrl = apiUrl.replace(/\/+$/, "")

        if (!apiUrl) {
          console.error("NEXT_PUBLIC_API_URL is empty or invalid")
          return
        }

        const wsProtocol = apiUrl.startsWith("https") ? "wss" : "ws"
        const wsHost = apiUrl.replace(/^https?:\/\//, "").replace(/\/+$/, "")

        if (!wsHost) {
          console.error("WebSocket host is empty after processing:", { apiUrl, wsHost })
          return
        }

        const wsUrl = `${wsProtocol}://${wsHost}/api/publishing/simulations/ws/${user.id}?token=${token}`

        const ws = new WebSocket(wsUrl)
        wsRef.current = ws

        ws.onopen = () => {
          console.log("WebSocket connected for simulation updates")
          setWsConnected(true)
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            console.log("WebSocket message received:", data)

            if (data.type === "simulation_ready") {
              setSimulations((prevSimulations) => {
                const simulationExists = prevSimulations.some((sim) => sim.id === data.simulation_id)

                if (!simulationExists) {
                  refreshProfessorData()
                  return prevSimulations
                }

                return prevSimulations.map((sim) => {
                  if (sim.id === data.simulation_id) {
                    return {
                      ...sim,
                      status: data.status === "draft" ? "Draft" : data.status === "creating" ? "Creating..." : sim.status,
                      is_draft: data.status === "draft",
                      title: data.title || sim.title,
                      original_status: data.status,
                    }
                  }
                  return sim
                })
              })
            }
          } catch (error) {
            console.error("Error parsing WebSocket message:", error, event.data)
          }
        }

        ws.onerror = (error) => {
          console.error("WebSocket error:", error)
          setWsConnected(false)
        }

        ws.onclose = (event) => {
          console.log("WebSocket disconnected", { code: event.code, reason: event.reason, wasClean: event.wasClean })
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
        console.error("Error connecting WebSocket:", error)
      }
    }

    connectWebSocketRef.current = connectWebSocket
    connectWebSocket()

    return () => {
      connectWebSocketRef.current = null
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [user, authLoading])

  useEffect(() => {
    simulationsRef.current = simulations
    creatingRef.current = hasCreatingSimulations(simulations)

    if (!creatingRef.current && wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
      setWsConnected(false)
    }

    if (creatingRef.current && !wsRef.current && connectWebSocketRef.current && user && !authLoading) {
      connectWebSocketRef.current()
    }
  }, [simulations, user, authLoading])

  // ── Professor refresh ──

  const refreshProfessorData = async () => {
    try {
      setIsRefreshing(true)
      setSimulationsError(null)
      setCohortsError(null)

      const simulationsData = await apiClient.getSimulations()
      const normalizedSimulations = simulationsData.map(normalizeSimulation)
      setSimulations(normalizedSimulations)

      const cohortsData = await apiClient.getCohorts()
      setCohorts(cohortsData)
    } catch (error) {
      console.error("Failed to refresh data:", error)
      if (error instanceof Error && error.message.includes("Authentication failed")) {
        logout()
        router.push("/")
        return
      }
      setSimulationsError("Failed to refresh data")
      setCohortsError("Failed to refresh data")
    } finally {
      setIsRefreshing(false)
    }
  }

  // ── Professor status update ──

  const updateSimulationStatus = async (simulationId: number, newStatus: string) => {
    try {
      setStatusUpdating(simulationId)

      const updatedScenario = await apiClient.updateScenarioStatus(simulationId, newStatus)

      const getDisplayStatus = (backendStatus: string, isDraft: boolean) => {
        if (backendStatus === "draft") return "Draft"
        if (backendStatus === "active") return "Active"
        if (backendStatus === "archived") return "Archived"
        return isDraft ? "Draft" : "Active"
      }

      const isDraftStatus = updatedScenario.status === "draft" || updatedScenario.is_draft === true

      const mappedScenario = {
        id: updatedScenario.id,
        title: updatedScenario.title,
        description: updatedScenario.description,
        status: getDisplayStatus(updatedScenario.status, isDraftStatus),
        date: new Date(updatedScenario.created_at).toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
        }),
        students: updatedScenario.personas?.length || 0,
        created_at: updatedScenario.created_at,
        is_draft: isDraftStatus,
        published_version_id: updatedScenario.published_version_id,
        unique_id: updatedScenario.unique_id,
      }

      setSimulations((prev) => prev.map((sim) => (sim.id === simulationId ? mappedScenario : sim)))

      if (newStatus === "active") {
        try {
          const cohortsData = await apiClient.getCohorts()
          setCohorts(cohortsData)
          localStorage.setItem(
            "simulationStatusChanged",
            JSON.stringify({ simulationId, newStatus, timestamp: Date.now() })
          )
        } catch (error) {
          console.error("Failed to refresh cohorts data:", error)
        }
      }

      setEditingStatus(null)
    } catch (error) {
      console.error("Failed to update status:", error)
      if (error instanceof Error && error.message.includes("Scenario not found")) {
        await refreshProfessorData()
        alert("Scenario not found. Data has been refreshed.")
      } else {
        alert("Failed to update simulation status. Please try again.")
      }
    } finally {
      setStatusUpdating(null)
    }
  }

  // ── Professor play simulation ──

  const playSimulation = (simulation: any) => {
    const isDraft = simulation.is_draft || simulation.status?.toLowerCase() === "draft"
    if (isDraft) {
      alert("Cannot play draft simulations. Please publish the simulation first.")
      return
    }

    setPlayingSimulation(simulation.id)

    const chatboxData = {
      simulation_id: simulation.id,
      title: simulation.title,
    }

    localStorage.setItem("chatboxSimulation", JSON.stringify(chatboxData))
    router.push("/simulations")
  }

  // ── Professor delete simulation ──

  const deleteDraftSimulation = async (simulationId: number) => {
    if (!confirm("Are you sure you want to delete this draft simulation? This action cannot be undone.")) {
      return
    }

    try {
      setDeletingScenario(simulationId)
      await apiClient.deleteDraftScenario(simulationId)
      setSimulations((prev) => prev.filter((sim) => sim.id !== simulationId))
    } catch (error) {
      console.error("Failed to delete simulation:", error)
      alert("Failed to delete simulation. Please try again.")
    } finally {
      setDeletingScenario(null)
    }
  }

  // ── Professor edit simulation ──

  const editDraftSimulation = async (simulation: any) => {
    const requestKey = `edit-${simulation.id}`

    if (pendingRequests.has(requestKey)) return

    try {
      setPendingRequests((prev) => new Set(prev).add(requestKey))

      const isDraft = simulation.is_draft || simulation.status?.toLowerCase() === "draft"

      if (!isDraft) {
        const draftSimulation = simulations.find((s) => s.published_version_id === simulation.id && s.is_draft)
        if (draftSimulation) {
          router.push(`/simulation-builder?edit=${draftSimulation.id}`)
          return
        } else {
          alert("No draft found for this published simulation")
          return
        }
      }

      router.push(`/simulation-builder?edit=${simulation.id}`)
    } catch (error) {
      console.error("Failed to navigate to draft editing:", error)
      const errorMessage = error instanceof Error ? error.message : "Unknown error occurred"
      alert(`Failed to open draft for editing: ${errorMessage}`)
    } finally {
      setPendingRequests((prev) => {
        const newSet = new Set(prev)
        newSet.delete(requestKey)
        return newSet
      })
    }
  }

  // Professor computed values
  const activeCohortsCount = cohorts.filter((cohort) => cohort.is_active === true).length
  const activeSimulationsCount = simulations.filter((sim) => sim.status?.toLowerCase() === "active").length

  // ────────────────────────────────────────────────
  // Student data fetching
  // ────────────────────────────────────────────────

  const loadStudentData = async () => {
    try {
      setLoading(true)

      const loadStartTime = Date.now()
      const minLoadTime = 300

      const [cohortsRes, simulationsRes] = await Promise.allSettled([
        apiClient.getStudentCohorts(),
        apiClient.getStudentSimulationInstances(),
      ])

      const elapsed = Date.now() - loadStartTime
      if (elapsed < minLoadTime) {
        await new Promise((resolve) => setTimeout(resolve, minLoadTime - elapsed))
      }

      if (cohortsRes.status === "fulfilled") {
        const cohortsData = cohortsRes.value.cohorts || cohortsRes.value || []
        setActiveCohorts(Array.isArray(cohortsData) ? cohortsData : [])
      } else {
        console.error("[Dashboard] Failed to load active cohorts:", cohortsRes.reason)
        setActiveCohorts([])
      }

      if (simulationsRes.status === "fulfilled") {
        const allSims = simulationsRes.value.instances || simulationsRes.value || []
        setAllSimulations(Array.isArray(allSims) ? allSims : [])

        const recentSims = (Array.isArray(allSims) ? allSims : [])
          .filter(
            (sim: any) => sim.status === "in_progress" || sim.status === "completed" || sim.status === "graded"
          )
          .sort((a: any, b: any) => {
            const dateA = new Date(a.completed_at || a.started_at || 0).getTime()
            const dateB = new Date(b.completed_at || b.started_at || 0).getTime()
            return dateB - dateA
          })
          .slice(0, 5)
        setRecentSimulations(recentSims)
      } else {
        console.error("[Dashboard] Failed to load recent simulations:", simulationsRes.reason)
        setAllSimulations([])
        setRecentSimulations([])
      }
    } catch (error) {
      console.error("[Dashboard] Unexpected error loading dashboard data:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (user && !isProfessor) {
      loadStudentData()
    }
  }, [user])

  // ────────────────────────────────────────────────
  // Logout
  // ────────────────────────────────────────────────

  const handleLogout = () => {
    logout()
    router.push("/")
  }

  // ────────────────────────────────────────────────
  // Render: Professor Dashboard
  // ────────────────────────────────────────────────

  if (isProfessor) {
    return (
      <div className="relative">
        {/* Header */}
        <header className="bg-white/80 backdrop-blur-sm border-b border-gray-200/60 px-6 py-4 sticky top-0 z-10 shadow-sm">
          <div className="flex items-center justify-between animate-page-enter">
            <div>
              <h1 className="text-4xl font-bold text-black tracking-tight mb-1">Dashboard</h1>
              <p className="text-sm text-gray-600 font-medium">
                Welcome back, {user?.full_name || user?.username || "User"}
              </p>
            </div>
            <div className="flex items-center space-x-4">
              {user?.role === "admin" && (
                <Link href="/admin/dashboard">
                  <Button variant="outline" size="sm" className="text-blue-600 border-blue-200 hover:bg-blue-50">
                    Admin Dashboard
                  </Button>
                </Link>
              )}
              <Link
                href="/profile"
                title="View profile"
                className="transition-transform hover:scale-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black rounded-full"
              >
                <Avatar className="h-10 w-10 border border-gray-200 shadow-sm">
                  {user?.avatar_url ? (
                    <AvatarImage src={user.avatar_url} alt={user?.full_name || "Professor profile"} />
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
                <span>{activeCohortsCount} cohorts active</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                <span>{activeSimulationsCount} simulations active</span>
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
                        <h3 className="font-semibold text-blue-900 mb-2">What&apos;s New</h3>
                        <p className="text-blue-900 text-sm leading-relaxed mb-3">
                          New feature: Real-time collaboration! Students can now work together on simulations with live
                          updates and shared decision-making tools.
                        </p>
                        <Button
                          variant="outline"
                          size="sm"
                          className="border-blue-300 text-blue-700 hover:bg-blue-50"
                          onClick={() => window.open(DOCUMENTATION_URL, '_blank')}
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
              <Link href="/simulation-builder">
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
              <Link href="/cohorts">
                <Card className="card-elevated bg-white/90 backdrop-blur-sm border-gray-200/60 cursor-pointer overflow-hidden h-full hover:shadow-lg transition-shadow">
                  <div className="w-full h-30 overflow-hidden rounded-t-lg">
                    <img src="/cohort.png" alt="Set up cohort" className="h-full w-full object-cover" />
                  </div>
                  <CardHeader className="pb-3 pt-3">
                    <CardTitle className="text-base text-gray-800 font-semibold">Set up cohort</CardTitle>
                    <p className="text-sm text-gray-700 font-medium mt-1">Set up a cohort</p>
                  </CardHeader>
                  <CardContent>
                    <p className="text-xs text-gray-600">
                      Create a group of students and give them certain simulations
                    </p>
                  </CardContent>
                </Card>
              </Link>

              {/* Read our documentation */}
              <a href={DOCUMENTATION_URL} target="_blank" rel="noopener noreferrer" data-testid="read-documentation-link">
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
              </a>
            </div>
          </div>

          {/* My Simulations Section */}
          <div className="mt-12 stagger-4 animate-fade-scale">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-3xl font-bold text-black tracking-tight">My simulations</h2>
              <Link href="/simulation-builder">
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
                <Button onClick={refreshProfessorData} variant="outline" size="sm">
                  Try Again
                </Button>
              </div>
            )}

            {/* Simulations Grid */}
            {!simulationsLoading && !simulationsError && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-8">
                {simulations
                  .filter((sim) => {
                    if (activeFilter === "All") return true
                    if (activeFilter === "Draft") {
                      const statusLower = sim.status?.toLowerCase() || ""
                      const originalStatusLower = (sim as any).original_status?.toLowerCase() || ""
                      return (
                        statusLower === "draft" ||
                        statusLower === "creating" ||
                        originalStatusLower === "draft" ||
                        originalStatusLower === "creating" ||
                        sim.is_draft
                      )
                    }
                    return sim.status?.toLowerCase() === activeFilter.toLowerCase()
                  })
                  .map((simulation, index) => {
                    const staggerClass =
                      index % 6 === 0
                        ? "stagger-1"
                        : index % 6 === 1
                        ? "stagger-2"
                        : index % 6 === 2
                        ? "stagger-3"
                        : index % 6 === 3
                        ? "stagger-4"
                        : index % 6 === 4
                        ? "stagger-5"
                        : "stagger-6"
                    return (
                      <Card
                        key={simulation.id}
                        className={`card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${staggerClass} animate-fade-scale`}
                      >
                        <CardHeader className="pb-4 px-4 sm:px-6 pt-4 sm:pt-6">
                          {/* Header Container - Title and Status */}
                          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                            <CardTitle
                              className="text-base sm:text-lg font-semibold text-gray-900 leading-tight cursor-pointer hover:text-blue-600 transition-colors flex-1 min-w-0"
                              onClick={() => playSimulation(simulation)}
                            >
                              <span className="block truncate">{simulation.title}</span>
                              {simulation.unique_id && (
                                <span className="text-xs text-gray-500 font-mono mt-1 block">
                                  ID: {simulation.unique_id}
                                </span>
                              )}
                            </CardTitle>
                            <div className="relative status-editor flex-shrink-0">
                              {editingStatus === simulation.id ? (
                                <div className="flex items-center space-x-2">
                                  <select
                                    value={simulation.status === "Active" ? "active" : "draft"}
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
                                  {simulation.status?.toLowerCase() === "creating" ||
                                  (simulation as any).original_status?.toLowerCase() === "creating" ? (
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
                                <span>{simulation.students} Personas</span>
                              </div>
                            </div>
                            <div className="flex items-center justify-end sm:justify-start gap-2 flex-wrap">
                              {(() => {
                                const isDraft =
                                  simulation.is_draft || simulation.status?.toLowerCase() === "draft"
                                const isCreating =
                                  simulation.status?.toLowerCase() === "creating" ||
                                  (simulation as any).original_status?.toLowerCase() === "creating"

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
                                          ? "bg-gray-400 text-gray-600 cursor-not-allowed"
                                          : "btn-gradient text-white border-0 shadow-md hover:shadow-lg"
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
                                          <span>{isDraft ? "Draft" : "Play"}</span>
                                        </>
                                      )}
                                    </Button>

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
                {simulations.filter((sim) => {
                  if (activeFilter === "All") return true
                  if (activeFilter === "Draft") {
                    const statusLower = sim.status?.toLowerCase() || ""
                    const originalStatusLower = (sim as any).original_status?.toLowerCase() || ""
                    return (
                      statusLower === "draft" ||
                      statusLower === "creating" ||
                      originalStatusLower === "draft" ||
                      originalStatusLower === "creating" ||
                      sim.is_draft
                    )
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
                    <Link href="/simulation-builder">
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
    )
  }

  // ────────────────────────────────────────────────
  // Render: Student Dashboard
  // ────────────────────────────────────────────────

  return (
    <div className="relative">
      {/* Loading Overlay */}
      {loading && (
        <div
          className="fixed inset-0 bg-white/90 backdrop-blur-md z-[9999] flex items-center justify-center animate-fade-in"
          style={{ marginLeft: "5rem" }}
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

      {/* Header */}
      <header className="bg-white/80 backdrop-blur-sm border-b border-gray-200/60 px-6 py-4 sticky top-0 z-10 shadow-sm">
        <div className="flex items-center justify-between animate-page-enter">
          <div>
            <h1 className="text-4xl font-bold text-black tracking-tight mb-1">Dashboard</h1>
            <p className="text-sm text-gray-600 font-medium">
              Welcome back, {user?.full_name || user?.username || "Student"}
            </p>
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
                      const gradedSims = allSimulations.filter(
                        (sim: any) =>
                          (sim.status === "graded" || sim.status === "completed") &&
                          sim.grade !== null &&
                          sim.grade !== undefined
                      )
                      if (gradedSims.length === 0) return "N/A"
                      const avgScore = Math.round(
                        gradedSims.reduce((sum: number, sim: any) => sum + (sim.grade || sim.final_score || 0), 0) /
                          gradedSims.length
                      )
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
                    {allSimulations.filter((sim: any) => sim.status === "completed" || sim.status === "graded").length}
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
                      const gradedSims = allSimulations.filter(
                        (sim: any) =>
                          (sim.status === "graded" || sim.status === "completed") &&
                          sim.grade !== null &&
                          sim.grade !== undefined
                      )
                      if (gradedSims.length === 0) return "N/A"
                      const bestScore = Math.max(
                        ...gradedSims.map((sim: any) => sim.grade || sim.final_score || 0)
                      )
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
            <Link href="/cohorts" className="text-sm text-gray-600 hover:text-black flex items-center">
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
                const staggerClass =
                  index % 6 === 0
                    ? "stagger-1"
                    : index % 6 === 1
                    ? "stagger-2"
                    : index % 6 === 2
                    ? "stagger-3"
                    : index % 6 === 3
                    ? "stagger-4"
                    : index % 6 === 4
                    ? "stagger-5"
                    : "stagger-6"
                return (
                  <div
                    key={cohort.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => router.push(`/cohorts?cohortId=${cohort.id}`)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        router.push(`/cohorts?cohortId=${cohort.id}`)
                      }
                    }}
                    className={`card-elevated w-72 shrink-0 bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md cursor-pointer hover:shadow-lg hover:border-gray-300/60 transition-all duration-200 p-5 ${staggerClass} animate-fade-scale`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <h3 className="font-bold text-black text-base leading-tight flex-1 mr-2">
                        {cohort.title || "Cohort"}
                      </h3>
                      <Badge className="bg-green-100 text-green-800 text-xs shrink-0">Active</Badge>
                    </div>
                    <p className="text-sm text-gray-600 mb-1">{cohort.professor?.name || "Instructor"}</p>
                    {cohort.course_code && (
                      <p className="text-xs text-gray-400 mb-3">
                        {cohort.course_code}
                        {cohort.semester ? ` \u2022 ${cohort.semester}` : ""}
                        {cohort.year ? ` ${cohort.year}` : ""}
                      </p>
                    )}
                    <p className="text-sm text-gray-500 line-clamp-2 mb-4">
                      {cohort.description || "Active cohort for simulation assignments"}
                    </p>
                    <div className="flex items-center text-xs text-gray-400">
                      <Calendar className="h-3 w-3 mr-1" />
                      Joined{" "}
                      {cohort.joined_at
                        ? new Date(cohort.joined_at).toLocaleDateString()
                        : cohort.created_at
                        ? new Date(cohort.created_at).toLocaleDateString()
                        : "Recently"}
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
                const staggerClass =
                  index % 6 === 0
                    ? "stagger-1"
                    : index % 6 === 1
                    ? "stagger-2"
                    : index % 6 === 2
                    ? "stagger-3"
                    : index % 6 === 3
                    ? "stagger-4"
                    : index % 6 === 4
                    ? "stagger-5"
                    : "stagger-6"
                return (
                  <Card
                    key={simulation.id}
                    className={`card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${staggerClass} animate-fade-scale`}
                  >
                    <CardContent className="p-6">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <h3 className="font-bold text-gray-900 text-lg mb-2">
                            {simulation.cohort_assignment?.simulation?.title || "Simulation"}
                          </h3>
                          <div className="flex flex-wrap items-center gap-2 text-sm text-gray-500 mb-3">
                            {simulation.cohort_assignment?.cohort?.title && (
                              <span className="flex items-center">
                                <Users className="h-3 w-3 mr-1" />
                                {simulation.cohort_assignment.cohort.title}
                              </span>
                            )}
                            {simulation.status === "in_progress" && simulation.started_at && (
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
                                {Math.round(
                                  (new Date(simulation.completed_at).getTime() -
                                    new Date(simulation.started_at).getTime()) /
                                    (1000 * 60)
                                )}{" "}
                                min
                              </span>
                            )}
                            {simulation.cohort_assignment?.due_date && (
                              <span className={simulation.is_overdue ? "text-red-600 font-semibold" : ""}>
                                {simulation.is_overdue ? "!! " : ""}
                                Due {new Date(simulation.cohort_assignment.due_date).toLocaleDateString()}
                                {simulation.is_overdue && simulation.days_late
                                  ? ` (${simulation.days_late}d late)`
                                  : ""}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center space-x-2">
                            {simulation.status === "in_progress" ? (
                              <Badge className="bg-blue-100 text-blue-800 text-xs">In Progress</Badge>
                            ) : simulation.status === "graded" ? (
                              <Badge className="bg-green-100 text-green-800 text-xs">Graded</Badge>
                            ) : simulation.status === "completed" ? (
                              <Badge className="bg-purple-100 text-purple-800 text-xs">Awaiting Grade</Badge>
                            ) : simulation.status === "submitted" ? (
                              <Badge className="bg-yellow-100 text-yellow-800 text-xs">Submitted</Badge>
                            ) : (
                              <Badge className="bg-gray-100 text-gray-800 text-xs">{simulation.status}</Badge>
                            )}
                            {simulation.completion_percentage !== null &&
                              simulation.completion_percentage !== undefined && (
                                <span className="text-xs text-gray-500">
                                  {simulation.completion_percentage}% Complete
                                </span>
                              )}
                          </div>
                        </div>

                        <div className="text-right">
                          {simulation.grade !== null && simulation.grade !== undefined && (
                            <div className="text-sm text-gray-600 mb-2">Score: {simulation.grade}%</div>
                          )}
                          <Link
                            href={`/run-simulation/${simulation.unique_id}`}
                            className="text-sm text-blue-600 hover:text-blue-800"
                          >
                            {simulation.status === "in_progress" ? "Continue" : "View Results"}
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
  )
}
