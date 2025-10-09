"use client"

import React, { useState, useRef, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import { 
  Send, 
  Users, 
  Target, 
  Clock, 
  CheckCircle, 
  AlertCircle,
  HelpCircle,
  RefreshCw,
  ArrowLeft,
  BookOpen,
  User
} from "lucide-react"
import { buildApiUrl, apiClient } from "@/lib/api"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"

// Types aligned with backend database schema
interface Scenario {
  id: number
  title: string
  description: string
  challenge: string
  industry?: string
  learning_objectives: string[]
  student_role?: string
  total_scenes: number
}

interface Persona {
  id: number
  name: string
  role: string
  background: string
  correlation: string
  primary_goals: string[]
  personality_traits: Record<string, number>
}

interface Scene {
  id: number
  title: string
  description: string
  user_goal?: string
  scene_order: number
  estimated_duration?: number
  image_url?: string
  personas: Persona[]
  personas_involved?: string[]
  timeout_turns?: number
}

interface SimulationData {
  user_progress_id: number
  scenario: Scenario
  current_scene: Scene
  simulation_status: string
  instance_id: number
}

interface Message {
  id: number | string
  sender: string
  text: string
  timestamp: Date
  type: 'user' | 'ai_persona' | 'system' | 'orchestrator'
  persona_id?: number
  persona_name?: string
  scene_completed?: boolean
  next_scene_id?: number
  showSubmitForGrading?: boolean
  showViewGrading?: boolean
  gradingInProgress?: boolean
}

// Scene Progress Component
const SceneProgress = ({ 
  currentScene, 
  totalScenes, 
  completedScenes 
}: { 
  currentScene: number
  totalScenes: number
  completedScenes: number[]
}) => {
  const progress = (completedScenes.length / totalScenes) * 100

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-semibold text-sm">Simulation Progress</h3>
          <span className="text-xs text-gray-500">
            Scene {currentScene} of {totalScenes}
          </span>
        </div>
        <Progress value={progress} className="mb-2" />
        <div className="flex justify-between text-xs text-gray-500">
          <span>{completedScenes.length} completed</span>
          <span>{Math.round(progress)}%</span>
        </div>
      </CardContent>
    </Card>
  )
}

// Current Scene Info
const CurrentSceneInfo = ({ scene, turnCount }: { scene: Scene, turnCount: number }) => {
  return (
    <Card className="mb-4">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Target className="w-4 h-4 text-blue-500" />
          Current Scene
        </CardTitle>
      </CardHeader>
      <CardContent>
        <h3 className="font-semibold mb-2">{scene.title}</h3>
        
        {scene.image_url && (
          <div className="mb-3">
            <img 
              src={scene.image_url} 
              alt={scene.title}
              className="w-full h-32 object-cover rounded-lg border"
              onError={(e) => {
                const target = e.target as HTMLImageElement
                target.style.display = 'none'
              }}
            />
          </div>
        )}
        
        <p className="text-sm text-gray-600 mb-3">{scene.description}</p>
        
        {scene.user_goal && (
          <div className="bg-blue-50 border border-blue-200 rounded p-3 mb-3">
            <p className="text-sm font-medium text-blue-800">Your Goal:</p>
            <p className="text-sm text-blue-700">{scene.user_goal}</p>
          </div>
        )}
        
        <div className="bg-yellow-50 border border-yellow-200 rounded p-3 mb-3">
          <p className="text-sm font-medium text-yellow-800">Timeout Turns:</p>
          <p className="text-sm text-yellow-700">
            {typeof scene.timeout_turns === 'number' ? `${Math.min(turnCount, scene.timeout_turns)} / ${scene.timeout_turns}` : 'Not set'}
          </p>
        </div>
        
        {scene.personas && scene.personas.length > 0 && (
          <div>
            <p className="text-xs font-medium text-gray-700 mb-2">Available Personas:</p>
            <div className="flex flex-wrap gap-1">
              {scene.personas.map((persona) => (
                <Badge key={persona.id} variant="secondary" className="text-xs">
                  {persona.name}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Typing Indicator
const TypingIndicator = ({ personaName }: { personaName: string }) => (
  <div className="flex justify-start mb-4">
    <div className="bg-gray-100 rounded-lg px-4 py-2 border">
      <div className="flex items-center gap-2">
        <div className="flex space-x-1">
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
        </div>
        <span className="text-xs text-gray-600">{personaName} is typing...</span>
      </div>
    </div>
  </div>
)

export default function StudentSimulationChat() {
  const router = useRouter()
  const params = useParams()
  const instanceId = params?.instanceId as string
  const { user, logout, isLoading: authLoading } = useAuth()
  
  // Core simulation state
  const [simulationData, setSimulationData] = useState<SimulationData | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [typingPersona, setTypingPersona] = useState("")
  const [completedScenes, setCompletedScenes] = useState<number[]>([])
  const [turnCount, setTurnCount] = useState(0)
  const [inputBlocked, setInputBlocked] = useState(false)
  const [allScenes, setAllScenes] = useState<Scene[]>([])
  const [sceneIntroShown, setSceneIntroShown] = useState<Set<number>>(new Set())
  const [gradingData, setGradingData] = useState<any>(null)
  const [showGrading, setShowGrading] = useState(false)
  const [canSubmitForGrading, setCanSubmitForGrading] = useState(false)
  const [hasSubmittedForGrading, setHasSubmittedForGrading] = useState(false)
  const [gradingHasBeenShown, setGradingHasBeenShown] = useState(false)
  const [simulationComplete, setSimulationComplete] = useState(false)
  const [gradingInProgress, setGradingInProgress] = useState(false)
  const [loadingSimulation, setLoadingSimulation] = useState(true)
  
  const simulationHasBegun = simulationData?.simulation_status === "in_progress"
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  // Block input after grading is shown
  useEffect(() => {
    if (gradingData && showGrading) {
      setInputBlocked(true)
    }
  }, [gradingData, showGrading])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Authentication logic
  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/")
    } else if (!authLoading && user && user.role !== 'student' && user.role !== 'admin') {
      router.push("/professor/dashboard")
    }
  }, [user, authLoading, router])

  // Load simulation on mount
  useEffect(() => {
    if (user && instanceId) {
      loadSimulation()
    }
  }, [user, instanceId])
  
  // Helper to add a scene to allScenes if not already present
  const addSceneIfMissing = (scene: Scene) => {
    setAllScenes(prev => {
      if (!scene || !scene.id) return prev
      const exists = prev.some(s => s.id === scene.id)
      if (!exists) {
        return [...prev, scene]
      }
      return prev
    })
  }

  // Helper to check if scene introduction should be shown
  const shouldShowSceneIntro = (scene: Scene) => {
    if (!scene || !scene.id) return false
    return !sceneIntroShown.has(scene.id)
  }

  // Helper to mark scene introduction as shown
  const markSceneIntroShown = (scene: Scene) => {
    if (!scene || !scene.id) return
    setSceneIntroShown(prev => new Set(prev).add(scene.id))
  }
  
  // Helper to generate scene introduction text
  const generateSceneIntroduction = (scene: Scene) => {
    const availablePersonas = scene.personas || []
    
    return `**Scene ${scene.scene_order} — ${scene.title}**

*${scene.description}*

**Objective:** ${scene.user_goal || 'Complete the interaction'}

**Active Participants:**
${availablePersonas.map(persona => `• @${persona.name.toLowerCase().replace(/\s+/g, '_')}: ${persona.name} (${persona.role})`).join('\n')}

*You have ${scene.timeout_turns || 15} turns to achieve the objective.*`
  }
  
  // Show loading while auth is being checked
  if (authLoading || !user) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black mx-auto mb-4"></div>
          <p className="text-black">Loading...</p>
        </div>
      </div>
    )
  }

  const loadSimulation = async () => {
    setLoadingSimulation(true)
    setSimulationComplete(false)
    setCanSubmitForGrading(false)
    setHasSubmittedForGrading(false)
    setSceneIntroShown(new Set())
    
    try {
      const response = await apiClient.apiRequest(
        `/student-simulation-instances/${instanceId}/start-simulation`,
        {
          method: "POST"
        }
      )

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data: SimulationData = await response.json()
      setSimulationData(data)
      setAllScenes([data.current_scene])
      
      // Add welcome message
      setMessages([{
        id: Date.now(),
        sender: "System",
        text: `🎯 **${data.scenario.title}**\n\n${data.scenario.description}\n\n**Your Role:** ${data.scenario.student_role}\n\n**Current Scene:** ${data.current_scene.title}\n\n**Instructions:**\n• Type **"begin"** to start the simulation\n• Type **"help"** for available commands\n• Use natural conversation to interact with personas`,
        timestamp: new Date(),
        type: 'system'
      }])

    } catch (error) {
      console.error("Failed to load simulation:", error)
      alert(`Failed to load simulation: ${error}`)
      router.push("/student/simulations")
    } finally {
      setLoadingSimulation(false)
    }
  }

  const sendMessage = async () => {
    if (inputBlocked) return
    if (!simulationData || !input.trim() || isLoading) return

    // Restrict @mentions to only personas in the current scene
    const trimmedInput = input.trim()
    const mentionMatch = trimmedInput.match(/@(\w+)/)
    if (mentionMatch) {
      const mentionId = mentionMatch[1].toLowerCase()
      const validPersonaMentions = simulationData.current_scene.personas.map(
        p => p.name.toLowerCase().replace(/\s+/g, '_')
      )
      if (!validPersonaMentions.includes(mentionId)) {
        alert('You can only @mention personas involved in this scene.')
        return
      }
    }

    const userMessage: Message = {
      id: Date.now(),
      sender: "You",
      text: input.trim(),
      timestamp: new Date(),
      type: 'user'
    }

    setMessages(prev => [...prev, userMessage])
    setInput("")
    setIsLoading(true)
    setIsTyping(true)
    setTypingPersona("ChatOrchestrator")

    // Only increment turn count for non-command messages
    if (trimmedInput !== 'begin' && trimmedInput !== 'help') {
      setTurnCount(prev => prev + 1)
      setHasSubmittedForGrading(false)
      setCanSubmitForGrading(false)
    }

    try {
      const response = await apiClient.apiRequest("/api/simulation/linear-chat", {
        method: "POST",
        body: JSON.stringify({
          scenario_id: simulationData.scenario.id,
          user_id: 1,
          scene_id: simulationData.current_scene.id,
          message: userMessage.text,
          user_progress_id: simulationData.user_progress_id
        })
      })

      if (!response.ok) {
        throw new Error(`Chat failed: ${response.status}`)
      }

      const chatData = await response.json()
      
      // Simulate typing delay for better UX
      setTimeout(() => {
        setIsTyping(false)
        
        // Add orchestrator response with persona information
        const aiMessage: Message = {
          id: Date.now() + 1,
          sender: chatData.persona_name || "ChatOrchestrator",
          text: chatData.message,
          timestamp: new Date(),
          type: chatData.persona_name && chatData.persona_name !== "ChatOrchestrator" ? 'ai_persona' : 'orchestrator',
          persona_name: chatData.persona_name,
          persona_id: chatData.persona_id,
          scene_completed: chatData.scene_completed,
          next_scene_id: chatData.next_scene_id
        }
        setMessages(prev => [...prev, aiMessage])
        
        // If this is the first "begin" response, add scene introduction
        if (trimmedInput === 'begin') {
          setSimulationData(prev => prev ? {
            ...prev,
            simulation_status: "in_progress"
          } : null)
          
          const currentScene = simulationData.current_scene
          if (shouldShowSceneIntro(currentScene)) {
            const sceneIntro = generateSceneIntroduction(currentScene)
            const sceneMessage: Message = {
              id: Date.now() + 2,
              sender: "System",
              text: sceneIntro,
              timestamp: new Date(),
              type: 'system'
            }
            setMessages(prev => [...prev, sceneMessage])
            markSceneIntroShown(currentScene)
          }
        }
        
        setCanSubmitForGrading(true)

        if (typeof chatData.turn_count === 'number') {
          setTurnCount(chatData.turn_count)
        }
        
        const isLastScene =
          allScenes.length > 0 &&
          simulationData.current_scene &&
          simulationData.current_scene.id === allScenes[allScenes.length - 1].id
          
        if (chatData.scene_completed) {
          setCompletedScenes(prev => {
            if (!prev.includes(simulationData.current_scene.id)) {
              return [...prev, simulationData.current_scene.id]
            }
            return prev
          })
          addSceneIfMissing(simulationData.current_scene)

          if (chatData.next_scene_id) {
            setInputBlocked(true)
            fetch(buildApiUrl(`/api/simulation/scenes/${chatData.next_scene_id}`), {
              credentials: 'include'
            })
              .then(response => {
                if (response.ok) {
                  return response.json()
                }
                throw new Error('Failed to fetch next scene')
              })
              .then(nextSceneData => {
                setSimulationData(prev => prev ? {
                  ...prev,
                  current_scene: nextSceneData,
                  simulation_status: "in_progress"
                } : null)
                setTurnCount(0)
                setInputBlocked(false)
                setCanSubmitForGrading(true)
                addSceneIfMissing(nextSceneData)
                
                setMessages(prev => {
                  const filteredMessages = prev.filter(msg => 
                    !(msg.sender === "System" && msg.text.includes("Scene") && msg.text.includes("—"))
                  )
                  
                  return [
                    ...filteredMessages,
                    {
                      id: Date.now() + 2,
                      sender: "System",
                      text: generateSceneIntroduction(nextSceneData),
                      timestamp: new Date(),
                      type: 'system'
                    }
                  ]
                })
                markSceneIntroShown(nextSceneData)
              })
              .catch(error => {
                console.error("Failed to fetch next scene:", error)
                setInputBlocked(false)
                const completionMessage: Message = {
                  id: Date.now() + 2,
                  sender: "System",
                  text: "🎉 Scene completed! Moving to the next scene...",
                  timestamp: new Date(),
                  type: 'system'
                }
                setMessages(prev => [...prev, completionMessage])
              })
            return
          } else if (isLastScene && !chatData.next_scene_id) {
            setInputBlocked(false)
            setMessages(prev => [
              ...prev,
              {
                id: Date.now() + 3,
                sender: "System",
                text: "🎉 Simulation complete! You have finished all scenes. View your grading and feedback.",
                timestamp: new Date(),
                type: 'system'
              }
            ])
            
            // Update instance to completed status before grading
            apiClient.apiRequest(`/student-simulation-instances/${instanceId}`, {
              method: 'PUT',
              body: JSON.stringify({
                status: 'completed',
                completion_percentage: 100
              })
            }).catch(err => console.error('Failed to update instance status:', err))
            
            setGradingInProgress(true)
            setSimulationComplete(true)
            fetchGradingData().then(() => setGradingInProgress(false))
            return
          }
          
          if (!chatData.next_scene_id) {
            setInputBlocked(false)
            setMessages(prev => [
              ...prev,
              {
                id: Date.now() + 4,
                sender: "System",
                text: "🎉 Scene completed! Moving to the next scene...",
                timestamp: new Date(),
                type: 'system'
              }
            ])
          }
          return
        }
        
      }, 1500)

    } catch (error) {
      console.error("Failed to send message:", error)
      setIsTyping(false)
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        sender: "System",
        text: `❌ Error: ${error}. Please try again or restart the simulation.`,
        timestamp: new Date(),
        type: 'system'
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const fetchGradingData = async () => {
    if (!simulationData) return
    
    try {
      // Fetch the grading from the AI
      const res = await apiClient.apiRequest(`/api/simulation/grade?user_progress_id=${simulationData.user_progress_id}`)
      if (!res.ok) {
        throw new Error('Failed to fetch grading')
      }
      
      const data = await res.json()
      setGradingData(data)
      setShowGrading(true)
      
      // Save the grade to the StudentSimulationInstance
      try {
        // instanceId can be either integer or unique_id string - pass as-is
        await apiClient.apiRequest(`/student-simulation-instances/${instanceId}`, {
          method: 'PUT',
          body: JSON.stringify({
            status: 'completed',
            completion_percentage: 100,
            grade: data.overall_score,
            feedback: data.overall_feedback
          })
        })
        console.log('[DEBUG] Grade saved to instance:', data.overall_score)
      } catch (saveError) {
        console.error('[ERROR] Failed to save grade to instance:', saveError)
        // Don't fail the whole grading if save fails - student still sees their grade
      }
    } catch (error) {
      console.error('[ERROR] Failed to fetch grading data:', error)
    }
  }

  const handleSubmitForGrading = async () => {
    setHasSubmittedForGrading(true)
    setInputBlocked(true)
    
    const specialMessage = "SUBMIT_FOR_GRADING"
    
    try {
      const response = await apiClient.apiRequest("/api/simulation/linear-chat", {
        method: "POST",
        body: JSON.stringify({
          user_progress_id: simulationData!.user_progress_id,
          scene_id: simulationData!.current_scene.id,
          message: specialMessage,
          user_id: 1,
          scenario_id: simulationData!.scenario.id
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      
      if (data.scene_completed) {
        if (data.next_scene_id) {
          setCompletedScenes(prev => {
            const currentSceneId = simulationData!.current_scene.id
            if (!prev.includes(currentSceneId)) {
              return [...prev, currentSceneId]
            }
            return prev
          })
          
          if (data.next_scene) {
            setSimulationData(prev => prev ? {
              ...prev,
              current_scene: data.next_scene,
              simulation_status: "in_progress"
            } : null)
            
            setTurnCount(0)
            setCanSubmitForGrading(true)
            setHasSubmittedForGrading(false)
            addSceneIfMissing(data.next_scene)
            
            setMessages(prev => {
              const filteredMessages = prev.filter(msg => 
                !(msg.sender === "System" && msg.text.includes("Scene") && msg.text.includes("—"))
              )
              
              return [
                ...filteredMessages,
                {
                  id: Date.now() + 2,
                  sender: "System",
                  text: generateSceneIntroduction(data.next_scene),
                  timestamp: new Date(),
                  type: 'system'
                }
              ]
            })
            markSceneIntroShown(data.next_scene)
          }
          
          apiClient.apiRequest(`/api/simulation/progress/${simulationData!.user_progress_id}`)
            .then(res => res.json())
            .then(progress => {
              if (progress.current_scene_id === data.next_scene_id) {
                setInputBlocked(false)
                setCanSubmitForGrading(true)
              } else {
                setTimeout(() => {
                  setInputBlocked(false)
                  setCanSubmitForGrading(true)
                }, 300)
              }
            })
            .catch(() => {
              setTimeout(() => {
                setInputBlocked(false)
                setCanSubmitForGrading(true)
              }, 300)
            })
          } else {
            setSimulationComplete(true)
            setCompletedScenes(prev => {
              const currentSceneId = simulationData!.current_scene.id
              if (!prev.includes(currentSceneId)) {
                return [...prev, currentSceneId]
              }
              return prev
            })
            
            setMessages(prev => [
              ...prev,
              {
                id: Date.now() + 3,
                sender: "System",
                text: "🎉 Simulation complete! You have finished all scenes. View your grading and feedback.",
                timestamp: new Date(),
                type: 'system',
                showViewGrading: false
              }
            ])
            
            // Update instance to completed status before grading
            apiClient.apiRequest(`/student-simulation-instances/${instanceId}`, {
              method: 'PUT',
              body: JSON.stringify({
                status: 'completed',
                completion_percentage: 100
              })
            }).catch(err => console.error('Failed to update instance status:', err))
            
            setGradingInProgress(true)
            setSimulationComplete(true)
            fetchGradingData().then(() => setGradingInProgress(false))
          }
      } else {
        setInputBlocked(false)
        setCanSubmitForGrading(false)
        setHasSubmittedForGrading(false)
      }
    } catch (error) {
      console.error("[ERROR] Submit for grading failed:", error)
      setInputBlocked(false)
      setCanSubmitForGrading(false)
      setHasSubmittedForGrading(false)
      alert('Failed to submit for grading.')
    }
  }

  if (loadingSimulation) {
    return (
      <div className="min-h-screen bg-gray-50 flex">
        <RoleBasedSidebar currentPath={`/student/run-simulation/${instanceId}`} />
        <div className="flex-1 ml-20 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black mx-auto mb-4"></div>
            <p className="text-black">Loading simulation...</p>
          </div>
        </div>
      </div>
    )
  }

  if (!simulationData) {
    return (
      <div className="min-h-screen bg-gray-50 flex">
        <RoleBasedSidebar currentPath={`/student/run-simulation/${instanceId}`} />
        <div className="flex-1 ml-20 flex items-center justify-center">
          <div className="text-center">
            <AlertCircle className="h-12 w-12 text-red-500 mx-auto mb-4" />
            <p className="text-black mb-4">Failed to load simulation</p>
            <Button onClick={() => router.push("/student/simulations")}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Simulations
            </Button>
          </div>
        </div>
      </div>
    )
  }

  const totalScenes = simulationData.scenario.total_scenes
  const isLastScene = simulationData && simulationData.current_scene.scene_order >= totalScenes
  const timeoutTurns = simulationData?.current_scene?.timeout_turns ?? 15
  const hasTurnsRemaining = turnCount < timeoutTurns
  const shouldShowSubmitSystemMessage = canSubmitForGrading && !hasSubmittedForGrading && !inputBlocked && !simulationComplete && hasTurnsRemaining

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <RoleBasedSidebar currentPath={`/student/run-simulation/${instanceId}`} />
      <div className="flex-1 ml-20 p-4">
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-4 gap-6">
          
          {/* Left Sidebar - Progress & Scene Info */}
          <div className="lg:col-span-1">
            <SceneProgress
              currentScene={simulationData.current_scene.scene_order}
              totalScenes={totalScenes}
              completedScenes={completedScenes}
            />
            
            <CurrentSceneInfo scene={simulationData.current_scene} turnCount={turnCount} />
            
            <Card>
              <CardContent className="p-4">
                <div className="text-center">
                  <Badge variant="outline" className="text-xs mb-2">
                    Instance #{instanceId}
                  </Badge>
                  <p className="text-xs text-gray-500">
                    {simulationData.scenario.industry}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Main Chat Area */}
          <div className="lg:col-span-3">
            <Card className="h-[85vh] flex flex-col">
              <CardHeader className="border-b">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">
                    {simulationData.scenario.title}
                  </CardTitle>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">
                      {simulationData.current_scene.title}
                    </Badge>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => router.push("/student/simulations")}
                    >
                      <ArrowLeft className="w-4 h-4 mr-2" />
                      Exit
                    </Button>
                  </div>
                </div>
              </CardHeader>

              {/* Messages Area */}
              <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
                {[...messages,
                  ...(gradingInProgress ? [{
                    id: 'grading-in-progress',
                    sender: 'System',
                    text: 'Grading in progress... ',
                    type: 'system' as const,
                    timestamp: new Date(),
                    showSubmitForGrading: false,
                    showViewGrading: false,
                    gradingInProgress: true
                  }] : []),
                  ...(shouldShowSubmitSystemMessage ? [{
                    id: 'submit-for-grading',
                    sender: 'System',
                    text: '',
                    type: 'system' as const,
                    timestamp: new Date(),
                    showSubmitForGrading: true,
                    showViewGrading: false
                  }] : [])].map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`max-w-xs lg:max-w-md px-4 py-3 rounded-lg ${
                      message.type === 'user'
                        ? 'bg-blue-500 text-white'
                        : message.type === 'system'
                        ? 'bg-gray-100 text-gray-800 border'
                        : message.type === 'ai_persona'
                        ? 'bg-green-50 text-gray-800 border border-green-200'
                        : message.type === 'orchestrator'
                        ? 'bg-white text-gray-800 border border-purple-200'
                        : 'bg-white text-gray-800 border'
                    }`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-semibold opacity-75">
                          {message.sender}
                        </span>
                        {message.type === 'ai_persona' && message.persona_name && (
                          <Badge variant="secondary" className="text-xs bg-green-100 text-green-800">
                            {message.persona_name}
                          </Badge>
                        )}
                        {message.type === 'orchestrator' && message.persona_name && (
                          <Badge variant="secondary" className="text-xs">
                            AI
                          </Badge>
                        )}
                      </div>
                      <div className="text-sm whitespace-pre-wrap">
                        {message.text.split('\n').map((line, index) => {
                          const boldFormatted = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                          return (
                            <div key={index} dangerouslySetInnerHTML={{ __html: boldFormatted }} />
                          )
                        })}
                        {message.showSubmitForGrading && (
                          <div className="flex flex-col items-center">
                            <div className="mb-2 text-sm text-gray-700">Ready to submit your response for this scene?</div>
                            <Button
                              variant="default"
                              onClick={handleSubmitForGrading}
                              disabled={inputBlocked}
                            >
                              Submit for Grading
                            </Button>
                          </div>
                        )}
                        {message.showViewGrading && (
                          <div className="flex flex-col items-center">
                            <Button
                              variant="default"
                              onClick={() => {
                                if (gradingData) {
                                  setShowGrading(true)
                                } else {
                                  setGradingInProgress(true)
                                  fetchGradingData().then(() => setGradingInProgress(false))
                                }
                              }}
                              className="mt-2"
                            >
                              View Grading & Feedback
                            </Button>
                          </div>
                        )}
                        {message.gradingInProgress && (
                          <div className="w-full mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                            <div className="h-2 bg-blue-400 animate-pulse w-3/4 transition-all duration-1000"></div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {isTyping && (
                  <TypingIndicator personaName={typingPersona} />
                )}

                <div ref={messagesEndRef} />
              </CardContent>

              {/* Input Area */}
              <div className="border-t p-4">
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <Input
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyPress={handleKeyPress}
                      placeholder="Type your message or command..."
                      disabled={inputBlocked || isLoading || isTyping || simulationComplete || gradingInProgress}
                      className="flex-1"
                    />
                    <Button
                      onClick={sendMessage}
                      disabled={inputBlocked || isLoading || isTyping || !input.trim()}
                    >
                      {isLoading ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                  
                  {/* Quick command buttons */}
                  <div className="flex gap-2 flex-wrap">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setInput("begin")}
                      disabled={inputBlocked || isLoading || isTyping}
                    >
                      Begin
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setInput("help")}
                      disabled={inputBlocked || isLoading || isTyping}
                    >
                      Help
                    </Button>
                    {simulationHasBegun && simulationData.current_scene.personas && simulationData.current_scene.personas.length > 0 && 
                      simulationData.current_scene.personas.map((persona, index) => (
                        <Button
                          key={persona.id || index}
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_')
                            setInput(`@${mentionId} `)
                          }}
                          disabled={inputBlocked || isLoading || isTyping}
                        >
                          @{persona.name?.split(' ')[0] || 'Persona'}
                        </Button>
                      ))
                    }
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </div>
      </div>
      
      {/* Grading/Feedback Modal */}
      {showGrading && gradingData && (
        <div className="fixed inset-0 bg-black bg-opacity-60 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg p-8 max-w-6xl w-full overflow-y-auto max-h-[90vh]">
            <h2 className="text-3xl font-bold mb-6 text-center text-gray-800">Business Simulation Assessment</h2>
            
            {/* Overall Performance Section */}
            <div className="mb-8 bg-gradient-to-r from-blue-50 to-indigo-50 p-6 rounded-lg border border-blue-200">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-semibold text-blue-800">Overall Performance</h3>
                <div className="text-3xl font-bold text-blue-600">{gradingData.overall_score}/100</div>
              </div>
              <div className="text-gray-700 text-base leading-relaxed">{gradingData.overall_feedback}</div>
              
              {gradingData.key_strengths && (
                <div className="mt-4">
                  <h4 className="font-semibold text-green-700 mb-2">Key Strengths:</h4>
                  <ul className="list-disc list-inside text-gray-700 space-y-1">
                    {gradingData.key_strengths.map((strength: string, idx: number) => (
                      <li key={idx}>{strength}</li>
                    ))}
                  </ul>
                </div>
              )}
              
              {gradingData.development_areas && (
                <div className="mt-4">
                  <h4 className="font-semibold text-orange-700 mb-2">Areas for Development:</h4>
                  <ul className="list-disc list-inside text-gray-700 space-y-1">
                    {gradingData.development_areas.map((area: string, idx: number) => (
                      <li key={idx}>{area}</li>
                    ))}
                  </ul>
                </div>
              )}
              
              {gradingData.business_acumen_assessment && (
                <div className="mt-4 p-4 bg-white rounded border border-gray-200">
                  <h4 className="font-semibold text-purple-700 mb-2">Business Acumen Assessment:</h4>
                  <p className="text-gray-700">{gradingData.business_acumen_assessment}</p>
                </div>
              )}
              
              {gradingData.recommendations && (
                <div className="mt-4">
                  <h4 className="font-semibold text-indigo-700 mb-2">Recommendations for Continued Learning:</h4>
                  <ul className="list-disc list-inside text-gray-700 space-y-1">
                    {gradingData.recommendations.map((rec: string, idx: number) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Scene-by-Scene Analysis */}
            <div className="mb-6">
              <h3 className="text-xl font-semibold text-gray-800 mb-4">Scene-by-Scene Analysis</h3>
              {gradingData.scenes && gradingData.scenes.map((scene: any) => (
                <div key={scene.id} className="mb-6 border border-gray-200 rounded-lg p-6 bg-gray-50">
                  <div className="flex items-center justify-between mb-3">
                    <div className="font-semibold text-blue-700 text-lg">{scene.title}</div>
                    <div className="text-lg font-bold text-green-600">{scene.score}/100</div>
                  </div>
                  <div className="text-sm text-gray-600 mb-3">{scene.objective}</div>
                  
                  <div className="mb-4">
                    <span className="font-medium text-gray-700">Your Responses:</span>
                    <div className="mt-2 p-3 bg-white rounded border border-gray-200 max-h-32 overflow-y-auto">
                      {scene.user_responses && scene.user_responses.length > 0
                        ? scene.user_responses.map((msg: any, msgIdx: number) => (
                            <div key={msgIdx} className="mb-2 text-sm text-gray-700">
                              <span className="font-medium">{msgIdx + 1}.</span> {msg.content}
                            </div>
                          ))
                        : <span className="text-gray-400 italic">No responses recorded.</span>}
                    </div>
                  </div>
                  
                  <div className="text-gray-700 leading-relaxed">{scene.feedback}</div>
                  
                  {scene.strengths && (
                    <div className="mt-3">
                      <h5 className="font-semibold text-green-600 mb-1">Strengths:</h5>
                      <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                        {scene.strengths.map((strength: string, strengthIdx: number) => (
                          <li key={strengthIdx}>{strength}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {scene.improvements && (
                    <div className="mt-3">
                      <h5 className="font-semibold text-orange-600 mb-1">Areas for Improvement:</h5>
                      <ul className="list-disc list-inside text-sm text-gray-600 space-y-1">
                        {scene.improvements.map((improvement: string, impIdx: number) => (
                          <li key={impIdx}>{improvement}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {scene.business_insights && (
                    <div className="mt-3 p-3 bg-blue-50 rounded border border-blue-200">
                      <h5 className="font-semibold text-blue-700 mb-1">Business Insights:</h5>
                      <p className="text-sm text-gray-700">{scene.business_insights}</p>
                    </div>
                  )}
                  
                  {scene.teaching_notes && (
                    <div className="mt-3 text-xs text-gray-500 italic bg-yellow-50 p-2 rounded border border-yellow-200">
                      <strong>Teaching Notes:</strong> {scene.teaching_notes}
                    </div>
                  )}
                </div>
              ))}
            </div>
            
            <div className="flex justify-center mt-6">
              <button 
                className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-8 rounded-lg transition-colors duration-200" 
                onClick={() => {
                  setShowGrading(false)
                  setGradingHasBeenShown(true)
                  setInputBlocked(false)
                  setCanSubmitForGrading(false)
                  setHasSubmittedForGrading(false)
                  
                  setMessages(prev => prev.map(msg => {
                    if (msg.text.includes("🎉 Simulation complete!") && msg.type === 'system') {
                      return { ...msg, showViewGrading: true }
                    }
                    return msg
                  }))
                }}
              >
                Close Assessment
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
