"use client"

import React, { useState, useRef, useEffect } from "react"
import { flushSync } from "react-dom"
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
  User,
  Eye,
  Trophy,
  X,
  MessageCircle,
  Mic,
  Type,
  ChevronDown
} from "lucide-react"
import { ChatMessages } from '@/components/ChatMessages'
import { ChatInput } from '@/components/ChatInput'
import { buildApiUrl, apiClient } from "@/lib/api"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { getImageUrl } from "@/lib/image-utils"

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
  image_url?: string
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
  conversation_history?: Array<{
    id: number
    sender: string
    text: string
    timestamp: string
    type: string
    persona_id?: number
    scene_id?: number
  }>
  is_resuming?: boolean
  turn_count?: number
  completed_scene_ids?: number[]
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

// New interfaces for enhanced features
interface PersonaDetails {
  id: number
  name: string
  role: string
  bio: string
  personality: string
  background: string
  profile_picture?: string
  image_url?: string
}

interface TimeoutTurnsModal {
  isOpen: boolean
  currentTurns: number
  maxTurns: number
}

// Scene Progress Component
const SceneProgress = ({ 
  currentScene, 
  totalScenes, 
  completedScenes,
  isCompleted = false
}: { 
  currentScene: number
  totalScenes: number
  completedScenes: number[]
  isCompleted?: boolean
}) => {
  // If simulation is completed, force 100% even if last scene not in array
  const progress = isCompleted ? 100 : (completedScenes.length / totalScenes) * 100
  const displayedCompleted = isCompleted ? totalScenes : completedScenes.length

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
          <span>{displayedCompleted} completed</span>
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
              src={getImageUrl(scene.image_url)} 
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

// Enhanced Typing Indicator with focus effect
const TypingIndicator = ({ personaName, isInterfaceGreyed }: { personaName: string, isInterfaceGreyed: boolean }) => (
  <div className={`flex justify-start mb-4 transition-all duration-300 ${isInterfaceGreyed ? 'opacity-100' : 'opacity-75'}`}>
    <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex space-x-1">
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
          <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
        </div>
        <span className="text-sm font-medium text-blue-700">{personaName} is responding...</span>
      </div>
    </div>
  </div>
)

// Persona Details Modal
const PersonaDetailsModal = ({ 
  persona, 
  isOpen, 
  onClose, 
  onMessage 
}: { 
  persona: PersonaDetails | null
  isOpen: boolean
  onClose: () => void
  onMessage: (personaName: string) => void
}) => {
  if (!isOpen || !persona) return null

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
      <div 
        className="bg-gradient-to-b from-white via-white to-gray-50 rounded-2xl shadow-2xl max-w-md w-full mx-4 max-h-[90vh] overflow-hidden border border-gray-200/50 animate-modal-enter"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6 overflow-y-auto max-h-[90vh]">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-semibold text-gray-900" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>Persona Details</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-full hover:bg-gray-100"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          
          <div className="flex items-center gap-4 mb-6 pb-6 border-b border-gray-200">
            <div className="w-20 h-20 bg-gradient-to-br from-gray-300 to-gray-400 rounded-full flex items-center justify-center flex-shrink-0 shadow-lg overflow-hidden">
              {persona.image_url ? (
                <img src={persona.image_url} alt={persona.name} className="object-cover w-full h-full" />
              ) : (
                <User className="w-10 h-10 text-white" />
              )}
            </div>
            <div>
              <h4 className="text-2xl font-semibold text-gray-900 mb-1" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>{persona.name}</h4>
              <p className="text-gray-600 font-medium">{persona.role}</p>
            </div>
          </div>
          
          <div className="space-y-5">
            <div className="bg-gradient-to-br from-gray-50 to-white rounded-xl p-4 border border-gray-200/50 shadow-sm">
              <h5 className="font-semibold text-gray-900 mb-3 text-sm uppercase tracking-wide" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>Background</h5>
              <p className="text-sm text-gray-700 leading-relaxed">{persona.background}</p>
            </div>
          </div>
          
          <div className="mt-6 pt-6 border-t border-gray-200">
            <Button
              onClick={() => {
                onMessage(persona.name)
                onClose()
              }}
              className="w-full bg-gradient-to-r from-gray-900 to-gray-800 hover:from-gray-800 hover:to-gray-700 text-white shadow-lg hover:shadow-xl transition-all duration-200"
              style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}
            >
              <MessageCircle className="w-4 h-4 mr-2" />
              Message @{persona.name}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

// Timeout Turns Modal
const TimeoutTurnsModal = ({ 
  isOpen, 
  onClose, 
  currentTurns, 
  maxTurns 
}: { 
  isOpen: boolean
  onClose: () => void
  currentTurns: number
  maxTurns: number
}) => {
  if (!isOpen) return null

  const turnsRemaining = maxTurns - currentTurns
  const turnsPercent = (currentTurns / maxTurns) * 100

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in p-4">
      <div 
        className="bg-gradient-to-b from-white via-white to-gray-50 rounded-2xl shadow-2xl max-w-md w-full max-h-[90vh] border border-gray-200/50 animate-modal-enter flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-6 pb-4 border-b border-gray-200 flex-shrink-0">
          <h3 className="text-xl font-semibold flex items-center gap-2 text-gray-900" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>
            <Clock className="w-5 h-5" />
            Timeout Turns Explained
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-full hover:bg-gray-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-6 pt-4">
          <div className="space-y-5">
            <div className="bg-gradient-to-br from-amber-50 via-yellow-50 to-amber-50 border border-amber-200/60 rounded-xl p-5 shadow-sm">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center">
                  <AlertCircle className="w-5 h-5 text-amber-700" />
                </div>
                <span className="font-semibold text-amber-900">Current Status</span>
              </div>
              <p className="text-sm text-amber-800 mb-3">
                You have used <span className="font-semibold">{currentTurns}</span> out of <span className="font-semibold">{maxTurns}</span> available turns in this scene.
              </p>
              <div className="mt-3">
                <div className="flex items-center justify-between text-xs text-amber-700 mb-1">
                  <span>Turns Remaining: {turnsRemaining}</span>
                  <span>{Math.round(turnsPercent)}% Used</span>
                </div>
                <div className="w-full h-2 bg-amber-200/50 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-amber-400 to-amber-500 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min(turnsPercent, 100)}%` }}
                  ></div>
                </div>
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-gray-50 to-white rounded-xl p-4 border border-gray-200/50 shadow-sm">
              <h4 className="font-semibold text-gray-900 mb-2 text-sm uppercase tracking-wide" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>What are turns?</h4>
              <p className="text-sm text-gray-700 leading-relaxed">
                Each time you send a message in the conversation, it counts as one 'turn'. 
                This simulates real-world time constraints and encourages efficient communication.
              </p>
            </div>
            
            <div className="bg-gradient-to-br from-gray-50 to-white rounded-xl p-4 border border-gray-200/50 shadow-sm">
              <h4 className="font-semibold text-gray-900 mb-2 text-sm uppercase tracking-wide" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>What happens when turns run out?</h4>
              <p className="text-sm text-gray-700 leading-relaxed">
                When you reach the maximum number of turns for this scene, you'll be automatically 
                moved to the next part of the simulation. Make sure you've accomplished your objective 
                before the turns run out!
              </p>
            </div>
            
            <div className="bg-gradient-to-br from-gray-50 to-white rounded-xl p-4 border border-gray-200/50 shadow-sm">
              <h4 className="font-semibold text-gray-900 mb-2 text-sm uppercase tracking-wide" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>Tips for managing turns:</h4>
              <ul className="text-sm text-gray-700 space-y-2">
                <li className="flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">•</span>
                  <span>Plan your questions carefully before asking</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">•</span>
                  <span>Use @mentions to direct questions to specific personas</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">•</span>
                  <span>Use @all sparingly, as it's best for important questions that everyone needs to answer</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">•</span>
                  <span>Review the case study materials for information before asking</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
        
        <div className="p-6 pt-4 border-t border-gray-200 flex-shrink-0">
          <Button 
            onClick={onClose} 
            className="w-full bg-gradient-to-r from-gray-900 to-gray-800 hover:from-gray-800 hover:to-gray-700 text-white shadow-lg hover:shadow-xl transition-all duration-200"
            style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}
          >
            Got it
          </Button>
        </div>
      </div>
    </div>
  )
}

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
  const [streamingMessageId, setStreamingMessageId] = useState<number | string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [completedScenes, setCompletedScenes] = useState<number[]>([])
  const [turnCount, setTurnCount] = useState(0)
  const [leftPanelWidth, setLeftPanelWidth] = useState(33.33) // Percentage
  const [isDragging, setIsDragging] = useState(false)
  const [inputAreaHeight, setInputAreaHeight] = useState(120) // Height in pixels
  const [isInputDragging, setIsInputDragging] = useState(false)
  const [inputBlocked, setInputBlocked] = useState(false)

  // Drag handler functions
  const dragStartX = useRef<number>(0)
  const dragStartWidth = useRef<number>(0)
  
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    dragStartX.current = e.clientX
    dragStartWidth.current = leftPanelWidth
    setIsDragging(true)
  }

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging) return
    
    const containerWidth = window.innerWidth - 80 // Account for sidebar
    const deltaX = e.clientX - dragStartX.current
    const deltaPercent = (deltaX / containerWidth) * 100
    const newLeftWidth = dragStartWidth.current + deltaPercent
    
    // Constrain between 20% and 70%
    const constrainedWidth = Math.min(Math.max(newLeftWidth, 20), 70)
    setLeftPanelWidth(constrainedWidth)
  }

  const handleMouseUp = () => {
    setIsDragging(false)
  }

  // Input area drag handler functions
  const dragStartY = useRef<number>(0)
  const dragStartHeight = useRef<number>(0)
  
  const handleInputMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    dragStartY.current = e.clientY
    dragStartHeight.current = inputAreaHeight
    setIsInputDragging(true)
  }

  const handleInputMouseMove = (e: MouseEvent) => {
    if (!isInputDragging) return
    
    const containerHeight = window.innerHeight - 80 // Account for top navigation
    const deltaY = dragStartY.current - e.clientY // Invert because we're measuring from bottom
    const newHeight = dragStartHeight.current + deltaY
    
    // Constrain between 60px and 300px
    const constrainedHeight = Math.min(Math.max(newHeight, 60), 300)
    setInputAreaHeight(constrainedHeight)
  }

  const handleInputMouseUp = () => {
    setIsInputDragging(false)
  }

  // Add event listeners for mouse move and up
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    } else if (isInputDragging) {
      document.addEventListener('mousemove', handleInputMouseMove)
      document.addEventListener('mouseup', handleInputMouseUp)
      document.body.style.cursor = 'row-resize'
      document.body.style.userSelect = 'none'
    } else {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.removeEventListener('mousemove', handleInputMouseMove)
      document.removeEventListener('mouseup', handleInputMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.removeEventListener('mousemove', handleInputMouseMove)
      document.removeEventListener('mouseup', handleInputMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isDragging, isInputDragging])
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
  const [isSceneTransitioning, setIsSceneTransitioning] = useState(false)
  // Stable unique ID generator to avoid duplicate React keys
  const messageSequenceRef = useRef(0)
  const nextMessageId = () => {
    messageSequenceRef.current += 1
    return `${Date.now()}-${messageSequenceRef.current}`
  }
  
  // New state for enhanced features
  const [activeTab, setActiveTab] = useState<'conversation' | 'case-study'>('conversation')
  const [selectedPersona, setSelectedPersona] = useState<PersonaDetails | null>(null)
  const [showPersonaModal, setShowPersonaModal] = useState(false)
  const [showTimeoutModal, setShowTimeoutModal] = useState(false)
  const [showMentionDropdown, setShowMentionDropdown] = useState(false)
  const [inputMode, setInputMode] = useState<'text' | 'voice'>('text')
  const [isInterfaceGreyed, setIsInterfaceGreyed] = useState(false)
  // Persona bubble color utilities
  const personaPalette = [
    'bg-rose-50 border-rose-200',
    'bg-amber-50 border-amber-200',
    'bg-emerald-50 border-emerald-200',
    'bg-sky-50 border-sky-200',
    'bg-violet-50 border-violet-200',
    'bg-fuchsia-50 border-fuchsia-200',
    'bg-lime-50 border-lime-200',
    'bg-cyan-50 border-cyan-200'
  ] as const
  const hashPersona = (name: string) => {
    let h = 0
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
    return h
  }
  const getPersonaBubbleClasses = (personaName?: string) => {
    const key = (personaName || '').trim()
    if (!key) return 'bg-green-50 border-green-200'
    const idx = hashPersona(key) % personaPalette.length
    return personaPalette[idx]
  }

  // Lookup a persona's role by name from current scene
  const getPersonaRole = (personaName?: string) => {
    const name = (personaName || '').trim()
    if (!name || !simulationData?.current_scene?.personas) return undefined
    const p = simulationData.current_scene.personas.find(p => p.name === name)
    return p?.role
  }

  // Lookup a persona's image by name from current scene
  const getPersonaImage = (personaName?: string) => {
    const name = (personaName || '').trim()
    if (!name || !simulationData?.current_scene?.personas) return undefined
    const p = simulationData.current_scene.personas.find(p => p.name === name)
    return p?.image_url
  }
  const [currentTypingPersona, setCurrentTypingPersona] = useState<string>('')
  
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

  // Ensure overlay/bubble clears as soon as a new scene becomes active
  useEffect(() => {
    if (simulationData?.current_scene?.id) {
      setIsSceneTransitioning(false)
      setMessages(prev => prev.filter(m => !(m as any).sceneLoading))
    }
  }, [simulationData?.current_scene?.id])

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
      
      // Check if simulation is already completed/graded (review mode)
      const isCompleted = data.simulation_status === 'completed' || 
                          data.simulation_status === 'graded' ||
                          data.simulation_status === 'submitted'
      
      if (isCompleted) {
        try {
          setInputBlocked(true)
          setSimulationComplete(true)
          setHasSubmittedForGrading(true)
          
          // Load conversation history for review
          if (data.conversation_history && data.conversation_history.length > 0) {
            const existingMessages = data.conversation_history.map((msg: any) => ({
              id: msg.id || nextMessageId(),
              sender: msg.sender,
              text: msg.text,
              timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
              type: msg.type || 'system',
              // Add "View Grading" button to completion messages
              showViewGrading: msg.text?.includes("🎉 Simulation complete!") && msg.type === 'system'
            }))
            setMessages(existingMessages)
            
            // Restore turn count and completed scenes
            if (data.turn_count !== undefined) {
              setTurnCount(data.turn_count)
            }
            if (data.completed_scene_ids) {
              setCompletedScenes(data.completed_scene_ids)
            }
          }
          
          // Fetch grading data automatically (loads saved data if available)
          if (data.simulation_status === 'graded' || data.simulation_status === 'completed') {
            // Auto-show for graded simulations only
            const shouldAutoShow = data.simulation_status === 'graded'
            await fetchGradingData(false, shouldAutoShow).catch(err => {
              // Silently handle error
            })
          }
        } catch (error) {
          // Silently handle error
        } finally {
          // Always stop loading, even if there's an error
          setLoadingSimulation(false)
        }
        return
      }
      
      // Check if we're resuming (has conversation history)
      const isResuming = data.is_resuming && data.conversation_history && data.conversation_history.length > 0
      
      if (isResuming && data.conversation_history) {
        
        // Load existing conversation history
        const existingMessages = data.conversation_history.map((msg: any) => ({
          id: msg.id || nextMessageId(),
          sender: msg.sender,
          text: msg.text,
          timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
          type: msg.type || 'system'
        }))
        
        setMessages(existingMessages)
        
        // Restore turn count
        if (data.turn_count !== undefined) {
          setTurnCount(data.turn_count)
        }
        
        // Restore completed scenes
        if (data.completed_scene_ids && data.completed_scene_ids.length > 0) {
          setCompletedScenes(data.completed_scene_ids)
        }
        
        // Mark scenes with messages as having had their intro shown
        const scenesWithMessages = new Set<number>()
        data.conversation_history.forEach(msg => {
          if (msg.scene_id) {
            scenesWithMessages.add(msg.scene_id)
          }
        })
        setSceneIntroShown(scenesWithMessages)
        
        // Enable submit button when resuming ONLY if simulation has begun
        if (data.simulation_status === "in_progress") {
          setCanSubmitForGrading(true)
        }
      } else {
        // Starting fresh - add welcome message and reset state
        setSceneIntroShown(new Set())
        setTurnCount(0)
        setCompletedScenes([])
        
        setMessages([{
          id: nextMessageId(),
          sender: "System",
          text: `🎯 **${data.scenario.title}**\n\n${data.scenario.description}\n\n**Your Role:** ${data.scenario.student_role}\n\n**Current Scene:** ${data.current_scene.title}\n\n**Instructions:**\n• Type **"begin"** to start the simulation\n• Type **"help"** for available commands\n• Use natural conversation to interact with personas`,
          timestamp: new Date(),
          type: 'system'
        }])
      }

    } catch (error) {
      alert(`Failed to load simulation: ${error}`)
      router.push("/student/simulations")
    } finally {
      setLoadingSimulation(false)
    }
  }

  const sendMessage = async () => {
    if (inputBlocked || simulationComplete) return
    if (!simulationData || !input.trim() || isLoading) return

    const trimmedInput = input.trim()
    const mentionMatch = trimmedInput.match(/@(\w+)/)
    
    // Block persona mentions before simulation begins (unless it's the begin command)
    if (!simulationHasBegun && trimmedInput !== 'begin' && trimmedInput !== 'help') {
      if (mentionMatch) {
        alert('Please type "begin" to start the simulation before mentioning personas.')
        return
      }
    }

    // Restrict @mentions to only personas in the current scene (only after simulation begins)
    if (simulationHasBegun && mentionMatch) {
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
      id: nextMessageId() as any,
      sender: "You",
      text: input.trim(),
      timestamp: new Date(),
      type: 'user'
    }

    setMessages(prev => [...prev, userMessage])
    setInput("")
    setIsLoading(true)
    setIsTyping(true)
    
    // Extract mentioned persona name, otherwise default to ChatOrchestrator
    let typingPersonaName = "ChatOrchestrator"
    if (mentionMatch) {
      const mentionId = mentionMatch[1].toLowerCase()
      const mentionedPersona = simulationData.current_scene.personas.find(
        p => p.name.toLowerCase().replace(/\s+/g, '_') === mentionId
      )
      if (mentionedPersona) {
        typingPersonaName = mentionedPersona.name
      }
    }
    setTypingPersona(typingPersonaName)
    setCurrentTypingPersona(typingPersonaName)
    
    // Grey out interface will be controlled by isStreaming state

    // Only increment turn count for non-command messages
    if (trimmedInput !== 'begin' && trimmedInput !== 'help') {
      setTurnCount(prev => prev + 1)
      setHasSubmittedForGrading(false)
      setCanSubmitForGrading(false)
    }

    try {
      // Use dedicated streaming endpoint (bypasses buffered proxy)
      const response = await fetch('/api/stream-chat', {
        method: "POST",
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
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

      // Handle streaming response
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let streamedText = ""
      let chatData: any = {}
      
      // Create a placeholder AI message that will be updated in real-time
      const aiMessageId: any = nextMessageId()
      const isBeginCommand = userMessage.text.trim().toLowerCase() === 'begin'
      const placeholderMessage: any = {
        id: aiMessageId,
        sender: typingPersonaName === "ChatOrchestrator" ? "System" : typingPersonaName,
        text: "",
        timestamp: new Date(),
        type: typingPersonaName !== "ChatOrchestrator" ? 'ai_persona' : 'orchestrator',
        persona_name: typingPersonaName,
        persona_id: undefined,
        showLoadingBar: typingPersonaName === "ChatOrchestrator" && isBeginCommand
      }
      
      setIsTyping(false) // Hide typing indicator when streaming starts
      setIsStreaming(false) // Don't start streaming state yet - wait for first content
      setStreamingMessageId(aiMessageId) // Track the streaming message ID
      // Add placeholder to messages state for streaming display
      setMessages(prev => [...prev, placeholderMessage])
      
      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          
          const chunk = decoder.decode(value, { stream: true })
          const lines = chunk.split('\n')
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.substring(6)
              try {
                const parsed = JSON.parse(data)
                
                if (parsed.error) {
                  throw new Error(parsed.error)
                }
                
                if (parsed.content && !parsed.done) {
                  // Start streaming state when first content arrives
                  if (!isStreaming) {
                    setIsStreaming(true)
                  }
                  if (typingPersonaName !== "ChatOrchestrator" || !isBeginCommand) {
                    // Append streamed content for persona messages and non-begin orchestrator messages
                    streamedText += parsed.content
                    setMessages(prev => prev.map(msg => 
                      msg.id === aiMessageId 
                        ? { ...msg, text: streamedText, sender: (typingPersonaName === "ChatOrchestrator") ? "System" : (parsed.persona_name || msg.sender) }
                        : msg
                    ))
                  }
                }
                
                if (parsed.done) {
                  // Final metadata received - streaming finished
                  chatData = parsed
                  setIsStreaming(false) // Clear streaming state when streaming finishes
                  setStreamingMessageId(null) // Clear streaming message ID
                  if (typingPersonaName === "ChatOrchestrator" && isBeginCommand) {
                    // For 'begin', remove the loading placeholder when finished
                    setMessages(prev => prev.filter(msg => msg.id !== aiMessageId))
                  } else {
                    setMessages(prev => prev.map(msg => 
                      msg.id === aiMessageId 
                        ? { 
                            ...msg, 
                            text: parsed.full_content || streamedText,
                            sender: (typingPersonaName === "ChatOrchestrator") ? "System" : (parsed.persona_name || "System"),
                            persona_name: parsed.persona_name,
                            persona_id: parsed.persona_id,
                            scene_completed: parsed.scene_completed,
                            next_scene_id: parsed.next_scene_id
                          }
                        : msg
                    ))
                  }
                }
              } catch (e) {
                // Silently handle parsing error
              }
            }
          }
        }
      }
      
      
      // Now process the final chatData metadata
      console.log("[DEBUG] FINAL CHATDATA:", chatData)
      // Then add scene introduction message if provided by backend (should come AFTER the AI response)
      if (chatData.scene_intro_message) {
          const sceneMessage: Message = {
            id: nextMessageId() as any,
            sender: "System",
            text: chatData.scene_intro_message,
            timestamp: new Date(),
            type: 'system'
          }
          setMessages(prev => [...prev, sceneMessage])
          
          // Mark the current scene as having shown its intro
          if (simulationData?.current_scene) {
            markSceneIntroShown(simulationData.current_scene)
          }
        }
        
        // Timeout message handling removed - using loading screen approach
        
        // If this is the first "begin" response, update simulation status
        if (trimmedInput === 'begin') {
          setSimulationData(prev => prev ? {
            ...prev,
            simulation_status: "in_progress"
          } : null)
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
            // Show loading screen for scene transition
            setIsSceneTransitioning(true)
            
            // Safety timeout to ensure loading screen doesn't get stuck
            setTimeout(() => {
              setIsSceneTransitioning(false)
            }, 500)
          
          setCompletedScenes(prev => {
            if (!prev.includes(simulationData.current_scene.id)) {
              return [...prev, simulationData.current_scene.id]
            }
            return prev
          })
          addSceneIfMissing(simulationData.current_scene)

          if (chatData.next_scene_id) {
            setInputBlocked(true)
            const sceneLoadingId: any = nextMessageId()
            flushSync(() => {
              setMessages(prev => [...prev, { id: sceneLoadingId, sender: 'System', text: '', timestamp: new Date(), type: 'system' as const, sceneLoading: true } as any])
              setIsSceneTransitioning(true)
            })
            // Force a paint before starting fetch (double rAF)
            requestAnimationFrame(() => requestAnimationFrame(() => fetch(buildApiUrl(`/api/simulation/scenes/${chatData.next_scene_id}`), {
              credentials: 'include'
            })
              .then(response => {
                if (response.ok) {
                  return response.json()
                }
                throw new Error('Failed to fetch next scene')
              })
              .then(nextSceneData => {
                console.log("[DEBUG] Next scene personas data:", nextSceneData.personas);
                nextSceneData.personas?.forEach((p: any, idx: number) => {
                  console.log(`[DEBUG] Persona ${idx + 1}: ${p.name} - image_url: ${p.image_url}`);
                });
                setSimulationData(prev => prev ? {
                  ...prev,
                  current_scene: nextSceneData,
                  simulation_status: "in_progress"
                } : null)
                setTurnCount(0)
                setInputBlocked(false)
                setCanSubmitForGrading(true)
                addSceneIfMissing(nextSceneData)
                
                // Add scene introduction message for the new scene (like professor's page)
                console.log("[DEBUG] Scene transition - adding new scene intro for scene:", nextSceneData.title);
                const sceneIntroMessage = {
                  id: nextMessageId(),
                  sender: "System",
                  text: generateSceneIntroduction(nextSceneData),
                  timestamp: new Date(),
                  type: 'system' as const
                };
                
                setMessages(prev => {
                  console.log("[DEBUG] Scene transition - current messages before adding new scene intro:", prev.length);
                  const newMessages = [...prev, sceneIntroMessage];
                  console.log("[DEBUG] Scene transition - total messages after adding:", newMessages.length);
                  return newMessages;
                });
                
                // Save the scene intro message to the database
                apiClient.apiRequest("/api/simulation/save-message", {
                  method: "POST",
                  body: JSON.stringify({
                    user_progress_id: simulationData.user_progress_id,
                    scene_id: nextSceneData.id,
                    message_content: sceneIntroMessage.text,
                    sender_name: sceneIntroMessage.sender,
                    message_type: sceneIntroMessage.type
                  })
                }).catch(error => {
                  console.error("Failed to save scene intro message:", error);
                });
                
                markSceneIntroShown(nextSceneData);
                // After intro queued, keep loader/overlay briefly, then clear both
                setTimeout(() => {
                  setMessages(prev => prev.filter(m => m.id !== sceneLoadingId))
                  setIsSceneTransitioning(false)
                }, 800)
              })
              .catch(error => {
                setInputBlocked(false)
                setIsSceneTransitioning(false)
                setMessages(prev => prev.filter(m => m.id !== sceneLoadingId))
                const completionMessage: Message = {
                  id: nextMessageId() as any,
                  sender: "System",
                  text: "🎉 Scene completed! Moving to the next scene...",
                  timestamp: new Date(),
                  type: 'system'
                }
                setMessages(prev => [...prev, completionMessage])
              })))
            return
          } else if (isLastScene && !chatData.next_scene_id) {
            // Mark the last scene as completed
            setCompletedScenes(prev => {
              const currentSceneId = simulationData.current_scene.id
              if (!prev.includes(currentSceneId)) {
                return [...prev, currentSceneId]
              }
              return prev
            })
            
            setInputBlocked(false)
            
            // Add completion message to UI
            const completionMessage = {
              id: nextMessageId(),
              sender: "System",
              text: "🎉 Simulation complete! You have finished all scenes. View your grading and feedback.",
              timestamp: new Date(),
              type: 'system' as const
            }
            setMessages(prev => [...prev, completionMessage])
            
            // Save completion message to database so it appears in review mode
            apiClient.apiRequest("/api/simulation/save-message", {
              method: "POST",
              body: JSON.stringify({
                user_progress_id: simulationData.user_progress_id,
                scene_id: simulationData.current_scene.id,
                sender_name: "System",
                message_content: completionMessage.text,
                message_type: "system"
              })
            }).catch(err => {})
            
            // Update instance to completed status before grading
            apiClient.apiRequest(`/student-simulation-instances/${instanceId}`, {
              method: 'PUT',
              body: JSON.stringify({
                status: 'completed',
                completion_percentage: 100
              })
            }).catch(err => {})
            
            setGradingInProgress(true)
            setSimulationComplete(true)
            fetchGradingData(false, true).then(() => setGradingInProgress(false)) // autoShow=true for fresh completions
            return
          }
          
          if (!chatData.next_scene_id) {
            setInputBlocked(false)
            setMessages(prev => [
              ...prev,
              {
                id: nextMessageId(),
                sender: "System",
                text: "🎉 Scene completed! Moving to the next scene...",
                timestamp: new Date(),
                type: 'system'
              }
            ])
          }
          return
        }

    } catch (error) {
      setIsTyping(false)
      setMessages(prev => [...prev, {
        id: nextMessageId(),
        sender: "System",
        text: `❌ Error: ${error}. Please try again or restart the simulation.`,
        timestamp: new Date(),
        type: 'system'
      }])
    } finally {
      setIsLoading(false)
      setCurrentTypingPersona('')
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const fetchGradingData = async (forceRegenerate = false, autoShow = false) => {
    if (!simulationData) return
    
    try {
      // First, check if we already have saved grading data in the instance
      if (!forceRegenerate) {
        try {
          const instanceRes = await apiClient.apiRequest(`/student-simulation-instances/${instanceId}`)
          if (instanceRes.ok) {
            const instanceData = await instanceRes.json()
            
            // If instance has saved grading data, try to parse it
            if (instanceData.grade !== null && instanceData.grade !== undefined && instanceData.feedback) {
              // Try to parse feedback as JSON (full grading data)
              try {
                const parsedFeedback = JSON.parse(instanceData.feedback)
                if (parsedFeedback.overall_score !== undefined) {
                  // Full grading data saved as JSON - use it without regenerating
                  setGradingData(parsedFeedback)
                  if (autoShow) setShowGrading(true)
                  return // Exit early - don't call AI endpoint
                }
              } catch (parseError) {
                // feedback is plain text, not JSON - will regenerate with AI
              }
            }
          }
        } catch (err) {
          // Error checking for saved grading, will regenerate
        }
      }
      
      // No saved grading or force regenerate - call AI grading
      const res = await apiClient.apiRequest(`/api/simulation/grade?user_progress_id=${simulationData.user_progress_id}`)
      if (!res.ok) {
        throw new Error('Failed to fetch grading')
      }
      
      const data = await res.json()
      setGradingData(data)
      if (autoShow) setShowGrading(true)
      
      // Save the grade to the StudentSimulationInstance
      try {
        await apiClient.apiRequest(`/student-simulation-instances/${instanceId}`, {
          method: 'PUT',
          body: JSON.stringify({
            status: 'graded',
            completion_percentage: 100,
            grade: data.overall_score,
            feedback: JSON.stringify(data) // Save full grading data as JSON
          })
        })
      } catch (saveError) {
        // Silently handle error
      }
    } catch (error) {
      // Silently handle error
    }
  }

  const handleSubmitForGrading = async () => {
    // Safety check: prevent submission if simulation hasn't begun
    if (!simulationHasBegun) {
      alert('Please type "begin" to start the simulation first.')
      return
    }
    
    setHasSubmittedForGrading(true)
    setInputBlocked(true)
    // Show loading screen for manual submit for grading
    setIsSceneTransitioning(true)
    
    // Safety timeout to ensure loading screen doesn't get stuck
    setTimeout(() => {
      setIsSceneTransitioning(false)
    }, 500) 
    
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
          
          // show loading bubble for next scene
          const sceneLoadingId: any = nextMessageId()
          flushSync(() => {
            setMessages(prev => [...prev, { id: sceneLoadingId, sender: 'System', text: '', timestamp: new Date(), type: 'system' as const, sceneLoading: true } as any])
            setIsSceneTransitioning(true)
          })

          if (data.next_scene) {
            // Force a paint with the loading bubble before switching scenes
            requestAnimationFrame(() => requestAnimationFrame(() => {
              setSimulationData(prev => prev ? {
                ...prev,
                current_scene: data.next_scene,
                simulation_status: "in_progress"
              } : null)
            }))
            
            setTurnCount(0)
            setCanSubmitForGrading(true)
            setHasSubmittedForGrading(false)
            addSceneIfMissing(data.next_scene)
            
            if (data.scene_intro_message) {
              setMessages(prev => [
                ...prev,
                {
                  id: nextMessageId(),
                  sender: "System",
                  text: data.scene_intro_message,
                  timestamp: new Date(),
                  type: 'system'
                }
              ])
            }
            markSceneIntroShown(data.next_scene)
            // Remove loading bubble after intro is queued
            setTimeout(() => {
              setMessages(prev => prev.filter(m => m.id !== sceneLoadingId))
            }, 200)
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
            
            // Mark the final scene as completed
            setCompletedScenes(prev => {
              const currentSceneId = simulationData!.current_scene.id
              if (!prev.includes(currentSceneId)) {
                return [...prev, currentSceneId]
              }
              return prev
            })
            
            // Add completion message to UI
            const completionMessage = {
              id: nextMessageId(),
              sender: "System",
              text: "🎉 Simulation complete! You have finished all scenes. View your grading and feedback.",
              timestamp: new Date(),
              type: 'system' as const,
              showViewGrading: false
            }
            setMessages(prev => [...prev, completionMessage])
            
            // Save completion message to database for review mode
            apiClient.apiRequest("/api/simulation/save-message", {
              method: "POST",
              body: JSON.stringify({
                user_progress_id: simulationData!.user_progress_id,
                scene_id: simulationData!.current_scene.id,
                sender_name: "System",
                message_content: completionMessage.text,
                message_type: "system"
              })
            }).catch(err => {})
            
            // Update instance to completed status before grading
            apiClient.apiRequest(`/student-simulation-instances/${instanceId}`, {
              method: 'PUT',
              body: JSON.stringify({
                status: 'completed',
                completion_percentage: 100
              })
            }).catch(err => {})
            
            setGradingInProgress(true)
            setSimulationComplete(true)
            fetchGradingData(false, true).then(() => setGradingInProgress(false)) // autoShow=true for fresh completions
          }
      } else {
        setInputBlocked(false)
        setCanSubmitForGrading(false)
        setHasSubmittedForGrading(false)
      }
    } catch (error) {
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
  const shouldShowSubmitSystemMessage = simulationHasBegun && canSubmitForGrading && !hasSubmittedForGrading && !inputBlocked && !simulationComplete

  return (
    <div className="h-screen bg-white flex">
        <RoleBasedSidebar currentPath={`/student/run-simulation/${instanceId}`} />
        
      <div className="flex-1 ml-20 flex flex-col">
        {/* Top Navigation Bar */}
        <div className="bg-white px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push("/student/simulations")}
                className="text-gray-600 hover:text-gray-900"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <h1 className="text-lg font-semibold text-gray-900 truncate">
                {simulationData.scenario.title}
              </h1>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-600">Scene Progress: {simulationData.current_scene.scene_order}/{totalScenes}</span>
              <div className="w-32 bg-gray-200 rounded-full h-2">
                <div 
                  className="bg-green-500 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${(simulationData.current_scene.scene_order / totalScenes) * 100}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>

        {/* Main Split Panel Layout */}
        <div className="flex flex-1 min-h-0">
          {/* Left Panel - Dark Theme Context */}
          <div 
            className="sim-panel-gradient text-white p-6 flex flex-col min-h-0"
            style={{ width: `${leftPanelWidth}%` }}
          >
            {(!simulationHasBegun && !simulationComplete) && (
              <div className="text-center text-gray-400 py-12">
                <p className="text-sm">Start the simulation to see scene content.</p>
              </div>
            )}
            {(simulationHasBegun && !simulationComplete) && (
              <div className="flex flex-col h-full">
                {/* Scene Image - Fixed height */}
                {simulationData.current_scene.image_url && (
                  <div className="mb-4 relative -mx-6 -mt-6 flex-shrink-0 animate-fade-in-up">
                    <img 
                      src={getImageUrl(simulationData.current_scene.image_url)} 
                      alt={simulationData.current_scene.title}
                      className="w-full h-56 object-cover"
                    />
                    <div className="scene-image-overlay absolute inset-0 pointer-events-none"></div>
                    <div className="absolute bottom-3 left-4 bg-black/80 backdrop-blur-sm text-white px-3 py-1.5 rounded text-sm font-medium" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                      {simulationData.current_scene.title}
                    </div>
                  </div>
                )}

                {/* Content area - Flex to fill remaining space */}
                <div className="flex-1 min-h-0 flex flex-col space-y-4 overflow-hidden">
                  {/* Scene Description - Full text display */}
                  <div className="flex-shrink-0 animate-fade-in-up stagger-1" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                    <h3 className="text-base font-semibold mb-2 text-gradient-sim">Scene Description</h3>
                    <p className="text-gray-300 text-xs leading-relaxed">
                      {simulationData.current_scene.description}
                    </p>
                  </div>

                  {/* Objective - Full text display */}
                  <div className="flex-shrink-0 animate-fade-in-up stagger-2">
                    <div className="objective-card rounded-lg p-3 sim-glow-hover">
                      <div className="flex items-center gap-2 mb-1 relative z-10">
                        <Target className="w-4 h-4" />
                        <span className="font-semibold text-sm" style={{ fontFamily: "'Sora', sans-serif" }}>OBJECTIVE</span>
                      </div>
                      <p className="text-xs leading-relaxed relative z-10">
                        {simulationData.current_scene.user_goal || 'Complete the interaction'}
                      </p>
                    </div>
                  </div>

                  {/* Available Personas - Smaller section, only this box scrolls */}
                  <div className="flex-1 min-h-0 flex flex-col animate-fade-in-up stagger-3">
                    <h3 className="text-sm font-semibold mb-2 text-gradient-sim flex-shrink-0" style={{ fontFamily: "'Sora', sans-serif" }}>Available Personas ({simulationData.current_scene.personas?.length || 0})</h3>
                    <div className="bg-gray-800/80 backdrop-blur-sm rounded-lg p-2 flex-1 min-h-0 overflow-y-auto space-y-1.5 scrollbar-thin border border-gray-700/30">
                      {simulationData.current_scene.personas && simulationData.current_scene.personas.length > 0 ? (
                        simulationData.current_scene.personas.map((persona, idx) => (
                          <div
                            key={persona.id}
                            className="persona-card-hover bg-gray-700/90 rounded-lg p-1.5 cursor-pointer flex-shrink-0 animate-slide-in-right"
                            style={{ animationDelay: `${0.25 + idx * 0.05}s` }}
                            onClick={() => {
                              setSelectedPersona({
                                id: persona.id,
                                name: persona.name,
                                role: persona.role,
                                bio: persona.background,
                                personality: persona.correlation,
                                background: persona.background,
                                image_url: persona.image_url
                              });
                              setShowPersonaModal(true);
                            }}
                          >
                            <div className="flex items-center gap-1.5 min-w-0 w-full">
                              <div className="w-5 h-5 bg-gray-600 rounded-full flex items-center justify-center flex-shrink-0 overflow-hidden">
                                {persona.image_url ? (
                                  <img src={persona.image_url} alt={persona.name} className="object-cover w-full h-full" />
                                ) : (
                                  <User className="w-2.5 h-2.5" />
                                )}
                              </div>
                              <div className="min-w-0 flex-1 overflow-hidden">
                                <p className="font-medium text-xs text-white truncate whitespace-nowrap">
                                  {persona.name}{persona.role && <span className="text-gray-400 font-normal"> · {persona.role}</span>}
                                </p>
                              </div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="bg-gray-700 rounded-lg p-2 flex-shrink-0">
                          <p className="text-xs text-gray-400 text-center">No personas available</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Submit for Grading Button - Always visible at bottom */}
                {canSubmitForGrading || (inputBlocked && !simulationComplete) ? (
                  <div className="mt-2 flex-shrink-0 animate-fade-in-up stagger-4">
                    <Button
                      onClick={handleSubmitForGrading}
                      disabled={inputBlocked || hasSubmittedForGrading}
                      className="sim-button-primary w-full text-white text-sm font-medium relative overflow-hidden"
                      style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}
                    >
                      {inputBlocked || hasSubmittedForGrading ? (
                        <>
                          <RefreshCw className="w-4 h-4 mr-2 sim-loading-spinner" />
                          {hasSubmittedForGrading ? 'Submitting for Grading...' : 'Processing Message...'}
                        </>
                      ) : (
                        <>
                          <CheckCircle className="w-4 h-4 mr-2" />
                          Submit for Grading
                        </>
                      )}
                    </Button>
                  </div>
                ) : null}
              </div>
            )}

            {/* Review Mode Info */}
            {simulationComplete && (
              <div className="bg-blue-600 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-2">
                  <Eye className="w-5 h-5" />
                  <span className="font-semibold">Review Mode</span>
                </div>
                <p className="text-sm">
                  This simulation has been completed. You can review the conversation history.
                </p>
                <Button 
                  onClick={async () => {
                    if (gradingData) {
                      setShowGrading(true)
                    } else {
                      setGradingInProgress(true)
                      await fetchGradingData(false, true)
                      setGradingInProgress(false)
                    }
                  }}
                  disabled={gradingInProgress}
                  className="w-full mt-3 bg-blue-700 hover:bg-blue-800"
                >
                  <Trophy className="w-4 h-4 mr-2" />
                  {gradingInProgress ? 'Loading...' : 'View Grade'}
                </Button>
              </div>
            )}
          </div>

          {/* Draggable Border */}
          <div
            className="w-1 bg-gray-200 hover:bg-gray-300 cursor-col-resize flex-shrink-0 transition-colors"
            onMouseDown={handleMouseDown}
          >
            <div className="w-full h-full flex items-center justify-center">
              <div className="w-0.5 h-8 bg-gray-400 rounded-full opacity-60"></div>
            </div>
          </div>

          {/* Right Panel - Light Theme Interaction */}
          <div 
            className="sim-panel-right flex flex-col min-h-0 relative"
            style={{ width: `${100 - leftPanelWidth}%` }}
          >
            {/* Tabs */}
            <div className="relative z-10 border-b border-gray-200/50">
              <div className="flex">
                <button
                  onClick={() => setActiveTab('conversation')}
                  className={`sim-tab px-6 py-3 text-sm font-medium border-b-2 ${
                    activeTab === 'conversation'
                      ? 'sim-tab-active text-blue-600 border-transparent'
                      : 'border-transparent text-gray-500'
                  }`}
                  style={{ fontFamily: "'Sora', sans-serif" }}
                >
                  <MessageCircle className="w-4 h-4 mr-2 inline" />
                  Conversation
                </button>
                <button
                  onClick={() => setActiveTab('case-study')}
                  className={`sim-tab px-6 py-3 text-sm font-medium border-b-2 ${
                    activeTab === 'case-study'
                      ? 'sim-tab-active text-blue-600 border-transparent'
                      : 'border-transparent text-gray-500'
                  }`}
                  style={{ fontFamily: "'Sora', sans-serif" }}
                >
                  <BookOpen className="w-4 h-4 mr-2 inline" />
                  Case Study
                </button>
                <div className="flex-1"></div>
                {simulationHasBegun && (
                  <div className="px-6 py-3">
                    <button
                      type="button"
                      onClick={() => setShowTimeoutModal(true)}
                      className="sim-turns-badge px-3 py-1 rounded-full text-xs font-semibold cursor-pointer transition-all"
                      style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}
                    >
                      Turns: {turnCount}/{simulationData.current_scene.timeout_turns || 15}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-hidden flex flex-col">
              {activeTab === 'conversation' ? (
                <>
                  {/* Messages Area - restructured for better overlay coverage */}
                  <div 
                    className="relative overflow-hidden flex-1 min-h-0"
                  >
                    {/* Gradient overlay when streaming - covers entire area */}
                    {(isStreaming || isSceneTransitioning) && (
                      <div className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/20 to-transparent z-40 pointer-events-none backdrop-blur-[2px] transition-opacity duration-300"></div>
                    )}
                    {/* Scrollable messages content */}
                    <div className="h-full overflow-y-auto p-6 space-y-4" style={{ fontFamily: "'DM Sans', sans-serif" }}>
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
                  }] : [])].map((message) => {
                      // Only highlight the currently streaming message by its specific ID
                      const isStreamingMessage = isStreaming && message.id === streamingMessageId
                      const isLoadingBubble = (message as any).gradingInProgress || (message as any).sceneLoading
                      const shouldHighlight = isStreamingMessage || isLoadingBubble
                      
                      return (
                  <div
                    key={message.id}
                        className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'} transition-all duration-300 ${
                          isStreaming && message.type !== 'ai_persona' ? 'grey-opacity-50' : ''
                        } ${shouldHighlight ? 'z-50 relative' : ''}`}
                      >
                        <div className={`${(message.type === 'orchestrator' && (message as any).showLoadingBar) ? 'max-w-none' : 'max-w-md'} px-4 py-3 rounded-lg transition-all duration-300 ${
                          shouldHighlight 
                            ? 'ring-2 ring-blue-400 shadow-lg scale-105' 
                            : ''
                        } ${
                      message.type === 'user'
                        ? 'sim-message-user text-white'
                        : message.type === 'system'
                        ? 'bg-gray-100 text-gray-800 border border-gray-200'
                        : message.type === 'ai_persona'
                        ? `sim-message-persona ${getPersonaBubbleClasses((message as any).persona_name || message.sender)} text-gray-800 border`
                        : message.type === 'orchestrator'
                        ? 'sim-message-ai text-gray-800'
                        : 'sim-message-ai text-gray-800'
                    }`} style={{ 
                      width: ((message.type === 'orchestrator' && (message as any).showLoadingBar) || (message as any).gradingInProgress || (message as any).sceneLoading) ? '36rem' : undefined,
                      fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif"
                    }}>
                      <div className="flex items-center gap-2 mb-1.5">
                        {message.type !== 'system' && message.type !== 'orchestrator' && (
                          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 text-[11px] flex items-center justify-center text-white font-semibold shadow-sm overflow-hidden">
                            {(() => {
                              const personaImage = message.type === 'ai_persona' && message.persona_name 
                                ? getPersonaImage(message.persona_name) 
                                : null;
                              if (personaImage) {
                                return <img src={personaImage} alt={message.sender} className="object-cover w-full h-full" />;
                              }
                              const label = (message.persona_name || message.sender || '');
                              return label.charAt(0).toUpperCase();
                            })()}
                          </div>
                        )}
                        <span className="text-xs font-semibold opacity-90" style={{ fontFamily: "'Sora', sans-serif" }}>
                          {message.type === 'orchestrator' ? 'System' : message.sender}
                        </span>
                        {message.type === 'ai_persona' && message.persona_name && (
                          <Badge variant="secondary" className="text-xs bg-white/90 backdrop-blur-sm text-gray-800 border border-gray-300/50 shadow-sm font-medium">
                            {(message as any).persona_role || getPersonaRole((message as any).persona_name || message.sender) || 'Persona'}
                          </Badge>
                        )}
                        {/* No badge for orchestrator/System messages */}
                      </div>
                      <div className="text-sm whitespace-pre-wrap leading-relaxed">
                        {(message.type === 'orchestrator' && (message as any).showLoadingBar) || (message as any).gradingInProgress || (message as any).sceneLoading ? (
                          <div className="flex flex-col gap-2">
                            <div className="text-sm text-gray-600 font-medium">{(message as any).sceneLoading ? 'Loading next scene...' : (message as any).gradingInProgress ? 'Submitting for grading...' : 'Processing your message...'}</div>
                            <div className="w-full h-1.5 bg-gray-200/60 rounded-full overflow-hidden backdrop-blur-sm">
                              <div className="h-full bg-gradient-to-r from-blue-400 via-blue-500 to-blue-600 animate-gradient rounded-full" style={{ width: '100%', backgroundSize: '200% 100%' }}></div>
                            </div>
                          </div>
                        ) : (
                          message.text.split('\n').map((line, index) => {
                            const boldFormatted = line.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
                            return (
                              <div key={index} dangerouslySetInnerHTML={{ __html: boldFormatted }} />
                            )
                          })
                        )}
                      </div>
                        {message.showViewGrading && (
                              <div className="flex flex-col items-center mt-3">
                            <Button
                              variant="default"
                              onClick={async () => {
                                if (gradingData) {
                                  setShowGrading(true)
                                } else {
                                  setGradingInProgress(true)
                                      await fetchGradingData(false, true)
                                  setGradingInProgress(false)
                                }
                              }}
                              disabled={gradingInProgress}
                            >
                              {gradingInProgress ? 'Loading...' : 'View Grading & Feedback'}
                            </Button>
                          </div>
                        )}
                        {/* gradingInProgress now uses the same loading UI above */}
                      </div>
                </div>
                      )
                    })}

                    {isTyping && (
                      <TypingIndicator personaName={typingPersona === "ChatOrchestrator" ? "System" : typingPersona} isInterfaceGreyed={isStreaming} />
                    )}

                <div ref={messagesEndRef} />
                    </div>
                  </div>

                  {/* Draggable Border for Input Area */}
                  <div
                    className={`sim-drag-border h-1 cursor-row-resize flex-shrink-0 ${
                      isInputDragging ? 'active' : ''
                    }`}
                    onMouseDown={handleInputMouseDown}
                  >
                    <div className="w-full h-full flex items-center justify-center">
                    </div>
                  </div>

                  {/* Input Area */}
                  <div 
                    className="sim-input-area-container p-4 flex-shrink-0"
                    style={{ height: `${inputAreaHeight}px` }}
                  >
                {simulationComplete ? (
                  /* Review Mode - Show message instead of input */
                  <div className="flex items-center justify-center py-4 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
                    <div className="text-center">
                      <Eye className="w-8 h-8 text-gray-400 mx-auto mb-2" />
                      <p className="text-sm font-medium text-gray-700">Simulation Completed</p>
                      <p className="text-xs text-gray-500 mt-1">All interactions are disabled in review mode</p>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1">
                    <div className="flex gap-2 items-center">
                          <div className="flex-1 relative">
                      <Input
                        value={input}
                              onChange={(e) => {
                                setInput(e.target.value);
                                // Show dropdown only when there's an incomplete mention at the end
                                setShowMentionDropdown(/@[^\s]*$/.test(e.target.value));
                              }}
                        onKeyPress={handleKeyPress}
                              placeholder={simulationHasBegun ? "Type your message or @mention a persona..." : "Type 'begin' to start the simulation or 'help' for commands..."}
                        disabled={inputBlocked || isLoading || isTyping || simulationComplete || gradingInProgress}
                              className="sim-input-enhanced w-full"
                            />
                            {showMentionDropdown && simulationHasBegun && (
                              <div className="sim-mention-dropdown absolute bottom-full left-0 right-0 z-20 mb-2 max-h-56 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-gray-100">
                                <div className="sim-mention-header">
                                  <div className="text-xs font-semibold text-gray-700 mb-1">All Personas</div>
                                  <div className="text-xs text-gray-500">Mention everyone in this scene</div>
                                </div>
                                <div className="p-2">
                                  {simulationData.current_scene.personas.map((persona) => (
                                    <div
                                      key={persona.id}
                                      className="sim-mention-item flex items-center gap-2 p-2 rounded cursor-pointer"
                                      onClick={() => {
                                        const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_');
                                        setInput(input.replace(/@[^@]*$/, `@${mentionId} `));
                                        setShowMentionDropdown(false);
                                      }}
                                    >
                                      <div className="w-7 h-7 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm overflow-hidden">
                                        {persona.image_url ? (
                                          <img src={persona.image_url} alt={persona.name} className="object-cover w-full h-full" />
                                        ) : (
                                          <User className="w-3.5 h-3.5 text-white" />
                                        )}
                                      </div>
                                      <div className="min-w-0 flex-1">
                                        <div className="text-sm font-semibold truncate text-gray-900">{persona.name}</div>
                                        <div className="text-xs text-gray-500 truncate">{persona.role}</div>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                      <Button
                        onClick={sendMessage}
                        disabled={inputBlocked || isLoading || isTyping || !input.trim() || simulationComplete || gradingInProgress}
                            className="sim-send-button px-4 py-2 text-white"
                      >
                        {isLoading ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : (
                          <Send className="w-4 h-4" />
                        )}
                      </Button>
                      
                      {/* Input Mode Toggle - moved to same line */}
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          variant={inputMode === 'text' ? 'default' : 'outline'}
                          onClick={() => setInputMode('text')}
                          disabled={simulationComplete || gradingInProgress}
                          className={`sim-mode-toggle ${inputMode === 'text' ? 'active' : ''}`}
                        >
                          <Type className="w-4 h-4 mr-1" />
                          Text
                        </Button>
                        <Button
                          size="sm"
                          variant={inputMode === 'voice' ? 'default' : 'outline'}
                          onClick={() => setInputMode('voice')}
                          disabled={simulationComplete || gradingInProgress}
                          className={`sim-mode-toggle ${inputMode === 'voice' ? 'active' : ''}`}
                        >
                          <Mic className="w-4 h-4 mr-1" />
                          Talk
                        </Button>
                      </div>
                    </div>
                  
                        {/* Quick Action Buttons */}
                    <div className="flex gap-2 flex-wrap">
                      {!simulationHasBegun && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setInput("begin")}
                              disabled={inputBlocked || isLoading || isTyping || simulationComplete || gradingInProgress}
                        >
                          Begin
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setInput("help")}
                            disabled={inputBlocked || isLoading || isTyping || simulationComplete || gradingInProgress}
                      >
                        Help
                      </Button>
                          {/* Only show persona mention buttons after simulation has begun */}
                          {simulationHasBegun && (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  setInput("@all ");
                                  setShowMentionDropdown(false);
                                }}
                                disabled={inputBlocked || isLoading || isTyping || simulationComplete || gradingInProgress}
                              >
                                <Users className="w-4 h-4 mr-1" />
                                @all
                              </Button>
                              {simulationData.current_scene.personas.map((persona, index) => (
                                <Button
                                  key={persona.id || index}
                                  size="sm"
                                  variant="outline"
                                  onClick={() => {
                                    const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_');
                                    setInput(`@${mentionId} `);
                                    setShowMentionDropdown(false);
                                  }}
                                  disabled={inputBlocked || isLoading || isTyping || simulationComplete || gradingInProgress}
                                >
                                  <User className="w-4 h-4 mr-1" />
                                  @{persona.name?.split(' ')[0] || 'Persona'}
                                </Button>
                              ))}
                            </>
                          )}
                        </div>

                  </div>
                )}
                  </div>
                </>
              ) : (
                <div className="flex-1 overflow-y-auto p-6">
                  <div className="text-center text-gray-500">
                    <BookOpen className="w-12 h-12 mx-auto mb-4" />
                    <p>Case Study content will be displayed here</p>
                  </div>
                </div>
              )}
            </div>
        </div>
      </div>

        {/* Modals */}
        <PersonaDetailsModal
          persona={selectedPersona}
          isOpen={showPersonaModal}
          onClose={() => setShowPersonaModal(false)}
          onMessage={(personaName) => {
            const mentionId = personaName.toLowerCase().replace(/\s+/g, '_');
            setInput(`@${mentionId} `);
          }}
        />

        <TimeoutTurnsModal
          isOpen={showTimeoutModal}
          onClose={() => setShowTimeoutModal(false)}
          currentTurns={turnCount}
          maxTurns={simulationData.current_scene.timeout_turns || 15}
        />
      
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
                  
                  // Keep input blocked if simulation was already completed (review mode)
                  // Only unblock if this was a fresh completion during this session
                  const wasAlreadyCompleted = simulationData?.simulation_status === 'completed' || 
                                             simulationData?.simulation_status === 'graded'
                  if (!wasAlreadyCompleted) {
                    setInputBlocked(false)
                    setCanSubmitForGrading(false)
                    setHasSubmittedForGrading(false)
                  }
                  
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
    </div>
  )
}
