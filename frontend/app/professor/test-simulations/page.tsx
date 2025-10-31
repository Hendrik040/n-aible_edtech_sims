"use client"

import React, { useState, useRef, useEffect } from "react"
import { flushSync } from "react-dom"
import { useRouter } from "next/navigation"
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
  Play,
  RefreshCw,
  ArrowRight,
  BookOpen,
  User,
  X,
  MessageCircle,
  Mic,
  Type,
  ChevronDown,
  ArrowLeft
} from "lucide-react"
import { buildApiUrl, apiClient } from "@/lib/api"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { getImageUrl } from "@/lib/image-utils"

// Types aligned with backend database schema
interface Scenario {
  id: number
  unique_id: string
  title: string
  description: string
  challenge: string
  industry?: string
  learning_objectives: string[]
  student_role?: string
  created_at: string
  is_public: boolean
  status: "draft" | "active" | "archived"
  is_draft: boolean
  scenes?: Scene[]
  personas?: Persona[]
  total_scenes?: number  // Total number of scenes in the simulation
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
  personas_involved?: string[] // Add this to track which personas are actually involved
  timeout_turns?: number // Add this line
}

interface SimulationData {
  user_progress_id: number
  scenario: Scenario
  current_scene: Scene
  simulation_status: string
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
}

interface Message {
  id: number
  sender: string
  text: string
  timestamp: Date
  type: 'user' | 'ai_persona' | 'system' | 'orchestrator'
  persona_id?: number
  persona_name?: string  // Add persona name for display
  scene_completed?: boolean  // Add scene completion flag
  next_scene_id?: number  // Add next scene ID for progression
  showSubmitForGrading?: boolean // Add this for the new system message
  showViewGrading?: boolean // Add this for completion messages
  gradingInProgress?: boolean // Add this for loading bar
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
}

interface TimeoutTurnsModal {
  isOpen: boolean
  currentTurns: number
  maxTurns: number
}

// Scenario Selection Component
const ScenarioSelector = ({ 
  onScenarioSelect 
}: { 
  onScenarioSelect: (scenarioId: number) => void 
}) => {
  const { user, isLoading: authLoading } = useAuth()
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedScenario, setSelectedScenario] = useState<number | null>(null)
  const hasInitializedRef = useRef(false)
  const hasPreselectedRef = useRef(false)
  
  // Debug logging for selectedScenario changes
  useEffect(() => {
    console.log("[DEBUG] ScenarioSelector: selectedScenario changed to", selectedScenario)
  }, [selectedScenario])

  useEffect(() => {
    // Only fetch scenarios when user is authenticated and we haven't initialized yet
    if (!authLoading && user && !hasInitializedRef.current) {
      console.log("[DEBUG] ScenarioSelector: Fetching scenarios for first time")
      // Mark initialized immediately to prevent rapid double-invoke on re-render
      hasInitializedRef.current = true
      fetchScenarios()
    } else if (!authLoading && !user) {
      // User is not authenticated, stop loading
      setLoading(false)
    }
  }, [user, authLoading])

    const fetchScenarios = async () => {
      try {
        console.log("[DEBUG] ScenarioSelector: fetchScenarios called")
        // For test-simulations page, show all scenarios (both draft and active) for the professor
        const response = await apiClient.apiRequest("/api/scenarios/", {}, true) // silentAuthError = true
        if (response.ok) {
          const data = await response.json()
        // Filter scenarios that have both personas and scenes
        const validScenarios = data.filter((s: any) => 
          s.personas && s.personas.length > 0 && 
          s.scenes && s.scenes.length > 0
        )
        setScenarios(validScenarios)
        
        // If we already preselected from localStorage in a previous call, don't override it
        if (hasPreselectedRef.current) {
          console.log("[DEBUG] ScenarioSelector: Already preselected from localStorage, skipping auto/preselect")
          return
        }

        // Try to preselect scenario from dashboard play action
        let preselectId: number | null = null
        let hasPreselected = false
        
        try {
          const stored = localStorage.getItem("chatboxScenario")
          console.log("[DEBUG] ScenarioSelector: localStorage chatboxScenario =", stored)
          if (stored) {
            const parsed = JSON.parse(stored)
            if (parsed && typeof parsed.scenario_id === 'number') {
              preselectId = parsed.scenario_id
              console.log("[DEBUG] ScenarioSelector: Found preselectId =", preselectId)
            }
          }
        } catch (_) {}
        
        // If we have a preselected id and it exists and is not draft, use it
        if (preselectId) {
          const match = validScenarios.find((s: any) => s.id === preselectId)
          const isDraft = match ? (match.is_draft || match.status === 'draft') : false
          console.log("[DEBUG] ScenarioSelector: Found match for preselectId", preselectId, "isDraft:", isDraft)
          if (match && !isDraft) {
            console.log("[DEBUG] ScenarioSelector: Setting selectedScenario to", preselectId)
            setSelectedScenario(preselectId)
            hasPreselected = true
            hasPreselectedRef.current = true
            // Clear after consumption to prevent stale selections later
            localStorage.removeItem("chatboxScenario")
          }
        }
        
        // Auto-select the most recent scenario ONLY if we didn't preselect from localStorage
        if (!hasPreselected && validScenarios.length > 0) {
          const mostRecent = validScenarios.reduce((latest: any, current: any) => 
            new Date(current.created_at) > new Date(latest.created_at) ? current : latest
          )
          console.log("[DEBUG] ScenarioSelector: Auto-selecting most recent scenario", mostRecent.id)
          setSelectedScenario(mostRecent.id)
        }
        
      } else if (response.status === 401) {
        // User is not authenticated, show empty state
        setScenarios([])
      }
    } catch (error) {
      // Only log the error, don't show it to the user
      console.log("Failed to fetch scenarios:", error)
      // Set empty scenarios array to show "No Scenarios Available" message
      setScenarios([])
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <Card className="max-w-2xl mx-auto">
        <CardContent className="p-6 text-center">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-4" />
          <p>Loading available scenarios...</p>
        </CardContent>
      </Card>
    )
  }

  if (scenarios.length === 0) {
    return (
      <Card className="max-w-2xl mx-auto">
        <CardContent className="p-6 text-center">
          <BookOpen className="w-12 h-12 mx-auto mb-4 text-gray-400" />
          <h3 className="text-lg font-semibold mb-2">No Scenarios Available</h3>
          <p className="text-gray-600 mb-4">
            You need to create a simulation first using the Simulation Builder.
          </p>
          <Button onClick={() => window.open("/professor/simulation-builder", "_blank")}>
            Create Simulation
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Play className="w-5 h-5" />
            Select a Scenario to Simulate
          </CardTitle>
          <p className="text-sm text-gray-600">
            Choose from your available scenarios with AI personas and scenes
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {scenarios.map((scenario) => (
            <div
              key={scenario.id}
              className={`border rounded-lg p-4 transition-all ${
                scenario.is_draft || scenario.status === 'draft'
                  ? 'border-gray-300 bg-gray-50 cursor-not-allowed opacity-60'
                  : selectedScenario === scenario.id 
                    ? 'border-blue-500 bg-blue-50 cursor-pointer hover:shadow-md' 
                    : 'border-gray-200 cursor-pointer hover:shadow-md'
              }`}
              onClick={() => {
                if (!scenario.is_draft && scenario.status !== 'draft') {
                  setSelectedScenario(scenario.id)
                }
              }}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <h3 className="font-semibold">{scenario.title}</h3>
                    {scenario.is_draft ? (
                      <Badge variant="secondary" className="text-xs bg-yellow-100 text-yellow-800">Draft</Badge>
                    ) : scenario.is_public ? (
                      <Badge variant="secondary" className="text-xs bg-green-100 text-green-800">Active</Badge>
                    ) : (
                      <Badge variant="secondary" className="text-xs bg-gray-100 text-gray-800">Private</Badge>
                    )}
                  </div>
                  
                  <p className="text-sm text-gray-600 mb-3 line-clamp-2">
                    {scenario.description}
                  </p>
                  
                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    <span className="flex items-center gap-1">
                      <User className="w-3 h-3" />
                      {scenario.student_role || "Student"}
                    </span>
                    <span className="flex items-center gap-1">
                      <Users className="w-3 h-3" />
                      Multiple Personas
                    </span>
                    <span className="flex items-center gap-1">
                      <Target className="w-3 h-3" />
                      Multi-Scene
                    </span>
                  </div>
                </div>
                
                <div className="ml-4 flex flex-col items-end gap-2">
                  <Badge variant="outline" className="text-xs">
                    ID: {scenario.unique_id || scenario.id}
                  </Badge>
                  <div className="flex gap-2">
                    {scenario.is_draft && (
                      <Button
                        size="sm"
                        variant="default"
                        onClick={async (e) => {
                          e.stopPropagation();
                          if (!window.confirm(`Activate scenario '${scenario.title}'? This will make it available to students.`)) return;
                          try {
                            const res = await apiClient.apiRequest(`/api/publishing/scenarios/${scenario.id}/status`, {
                              method: 'PUT',
                              body: JSON.stringify({ status: 'active' })
                            });
                            if (!res.ok) throw new Error('Failed to activate');
                            // Update the scenario in the list
                            setScenarios(scenarios => scenarios.map(s => 
                              s.id === scenario.id 
                                ? { ...s, is_draft: false, is_public: true, status: 'active' }
                                : s
                            ));
                          } catch (err) {
                            alert('Failed to activate scenario.');
                          }
                        }}
                      >
                        Activate
                      </Button>
                    )}
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={async (e) => {
                        e.stopPropagation();
                        if (!window.confirm(`Delete scenario '${scenario.title}'? This cannot be undone.`)) return;
                        try {
                          const res = await apiClient.apiRequest(`/api/publishing/scenarios/unique/${scenario.unique_id}`, { method: 'DELETE' });
                          if (!res.ok) throw new Error('Failed to delete');
                          setScenarios(scenarios => scenarios.filter(s => s.unique_id !== scenario.unique_id));
                          if (selectedScenario === scenario.id) setSelectedScenario(null);
                        } catch (err) {
                          alert('Failed to delete scenario.');
                        }
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ))}
          
          <div className="pt-4 border-t">
            {(() => {
              const selectedScenarioData = scenarios.find(s => s.id === selectedScenario);
              const isDraft = selectedScenarioData ? (selectedScenarioData.is_draft || selectedScenarioData.status === 'draft') : false;
              
              return (
                <Button 
                  onClick={() => selectedScenario && onScenarioSelect(selectedScenario)}
                  disabled={!selectedScenario || isDraft}
                  className="w-full"
                  size="lg"
                >
                  <Play className="w-4 h-4 mr-2" />
                  {isDraft ? 'Draft - Cannot Play' : 'Start Simulation'}
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              );
            })()}
          </div>
        </CardContent>
      </Card>
    </div>
  )
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
  // Debug logging removed to prevent infinite loops

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
        
        {/* Scene Image */}
        {scene.image_url && (
          <div className="mb-3">
            <img 
              src={getImageUrl(scene.image_url)} 
              alt={scene.title}
              className="w-full h-32 object-cover rounded-lg border"
              onError={(e) => {
                const target = e.target as HTMLImageElement;
                console.log("[DEBUG] Image failed to load:", scene.image_url);
                console.log("[DEBUG] Proxied URL:", getImageUrl(scene.image_url));
                target.style.display = 'none';
              }}
              onLoad={() => {
                console.log("[DEBUG] Image loaded successfully:", scene.image_url);
                console.log("[DEBUG] Proxied URL:", getImageUrl(scene.image_url));
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
        
        {/* Always display timeout_turns and current turn count */}
        <div className="bg-yellow-50 border border-yellow-200 rounded p-3 mb-3">
          <p className="text-sm font-medium text-yellow-800">Timeout Turns:</p>
          <p className="text-sm text-yellow-700">
            {typeof scene.timeout_turns === 'number' ? `${Math.min(turnCount, scene.timeout_turns)} / ${scene.timeout_turns}` : 'Not set'}
          </p>
        </div>
        
        {/* Only show personas involved in this specific scene */}
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
            <div className="w-20 h-20 bg-gradient-to-br from-gray-300 to-gray-400 rounded-full flex items-center justify-center flex-shrink-0 shadow-lg">
              <User className="w-10 h-10 text-white" />
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

export default function LinearSimulationChat() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  // All hooks must be called before any conditional returns
  // Core simulation state
  const [simulationData, setSimulationData] = useState<SimulationData | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [typingPersona, setTypingPersona] = useState("")
  const [streamingMessageId, setStreamingMessageId] = useState<number | string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [leftPanelWidth, setLeftPanelWidth] = useState(33.33) // Percentage
  const [isDragging, setIsDragging] = useState(false)
  const [inputAreaHeight, setInputAreaHeight] = useState(120) // Height in pixels
  const [isInputDragging, setIsInputDragging] = useState(false)

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

  // UI state
  const [selectedScenarioId, setSelectedScenarioId] = useState<number | null>(null)
  const [completedScenes, setCompletedScenes] = useState<number[]>([])
  // 1. Add state for current turn count
  const [turnCount, setTurnCount] = useState(0);
  // Add a state to block input when scene is completed and next scene is loading
  const [inputBlocked, setInputBlocked] = useState(false);
  // Add a state for all scenes
  const [allScenes, setAllScenes] = useState<Scene[]>([]);
  // Grading/Feedback state (must be at top)
  const [gradingData, setGradingData] = useState<any>(null);
  const [showGrading, setShowGrading] = useState(false);
  // Block input after grading is shown
  useEffect(() => {
    if (gradingData && showGrading) {
      setInputBlocked(true);
    }
  }, [gradingData, showGrading]);
  // Add state for submit button
  const [canSubmitForGrading, setCanSubmitForGrading] = useState(false);
  const [hasSubmittedForGrading, setHasSubmittedForGrading] = useState(false);
  // Add state to track if grading has been shown
  const [gradingHasBeenShown, setGradingHasBeenShown] = useState(false);
  const [simulationComplete, setSimulationComplete] = useState(false);
  // Add gradingInProgress state
  const [gradingInProgress, setGradingInProgress] = useState(false);
  // Add state for scene transition loading
  const [isSceneTransitioning, setIsSceneTransitioning] = useState(false);
  // Add state to track if simulation has begun (derived from backend status)
  const simulationHasBegun = simulationData?.simulation_status === "in_progress";
  // Add state to track if scene introduction has been shown for current scene
  const [sceneIntroShown, setSceneIntroShown] = useState<Set<number>>(new Set());
  
  // New state for enhanced features
  const [activeTab, setActiveTab] = useState<'conversation' | 'case-study'>('conversation');
  const [selectedPersona, setSelectedPersona] = useState<PersonaDetails | null>(null);
  const [showPersonaModal, setShowPersonaModal] = useState(false);
  const [showTimeoutModal, setShowTimeoutModal] = useState(false);
  const [showMentionDropdown, setShowMentionDropdown] = useState(false);
  const [inputMode, setInputMode] = useState<'text' | 'voice'>('text');
  const [isInterfaceGreyed, setIsInterfaceGreyed] = useState(false);
  const [currentTypingPersona, setCurrentTypingPersona] = useState<string>('');
  
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
  ] as const;
  const hashPersona = (name: string) => {
    let h = 0;
    for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
    return h;
  };
  const getPersonaBubbleClasses = (personaName?: string) => {
    const key = (personaName || '').trim();
    if (!key) return 'bg-green-50 border-green-200';
    const idx = hashPersona(key) % personaPalette.length;
    return personaPalette[idx];
  };

  // Lookup a persona's role by name from current scene
  const getPersonaRole = (personaName?: string) => {
    const name = (personaName || '').trim();
    if (!name || !simulationData?.current_scene?.personas) return undefined;
    const p = simulationData.current_scene.personas.find(p => p.name === name);
    return p?.role;
  };

  // Helper to add a scene to allScenes if not already present
  const addSceneIfMissing = (scene: Scene) => {
    setAllScenes(prev => {
      if (!scene || !scene.id) return prev;
      const exists = prev.some(s => s.id === scene.id);
      if (!exists) {
        return [...prev, scene];
      }
      return prev;
    });
  };

  // Helper to check if scene introduction should be shown
  const shouldShowSceneIntro = (scene: Scene) => {
    if (!scene || !scene.id) return false;
    return !sceneIntroShown.has(scene.id);
  };

  // Helper to mark scene introduction as shown
  const markSceneIntroShown = (scene: Scene) => {
    if (!scene || !scene.id) return;
    setSceneIntroShown(prev => new Set(prev).add(scene.id));
  };
  
  // Helper to generate scene introduction text
  const generateSceneIntroduction = (scene: Scene) => {
    // Use only the personas field which should already be filtered by the backend
    // The backend sends only the personas involved in this specific scene
    const availablePersonas = scene.personas || [];
    
    return `**Scene ${scene.scene_order} — ${scene.title}**

*${scene.description}*

**Objective:** ${scene.user_goal || 'Complete the interaction'}

**Active Participants:**
${availablePersonas.map(persona => `• @${persona.name.toLowerCase().replace(/\s+/g, '_')}: ${persona.name} (${persona.role})`).join('\n')}

*You have ${scene.timeout_turns || 15} turns to achieve the objective.*`;
  };
  const messagesEndRef = useRef<HTMLDivElement>(null)
  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Stable unique ID generator to avoid duplicate React keys
  const messageSequenceRef = useRef(0)
  const nextMessageId = () => {
    messageSequenceRef.current += 1
    return `${Date.now()}-${messageSequenceRef.current}`
  }
  // Ensure overlay/bubble clears as soon as a new scene becomes active
  useEffect(() => {
    if (simulationData?.current_scene?.id) {
      setIsSceneTransitioning(false)
      setMessages(prev => prev.filter((m: any) => !m?.sceneLoading))
    }
  }, [simulationData?.current_scene?.id])

  // Authentication logic - must be after all hooks
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

  // Start simulation with selected scenario
  const startSimulation = async (scenarioId: number) => {
    setSelectedScenarioId(scenarioId)
    setIsLoading(true)
    setSimulationComplete(false)
    setCanSubmitForGrading(false) // Reset submit button state
    setHasSubmittedForGrading(false)
    setSceneIntroShown(new Set()) // Reset scene introduction tracking
    
    try {
      const response = await apiClient.apiRequest("/api/simulation/start", {
        method: "POST",
        body: JSON.stringify({
          scenario_id: scenarioId
        })
      }, true) // Add silentAuthError = true to handle auth errors gracefully

      if (!response.ok) {
        if (response.status === 401) {
          // User is not authenticated, redirect to login
          console.log("Authentication failed, redirecting to login")
          router.push("/")
          return
        }
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data: SimulationData = await response.json()
      setSimulationData(data)
      
      // No need to fetch additional scene data - simulation endpoint provides everything needed
      // The publishing endpoint returns all personas per scene, which conflicts with scene-specific filtering
      // Initialize allScenes with just the current scene
      setAllScenes([data.current_scene]);
      console.log("[DEBUG] allScenes initialized with current_scene:", [data.current_scene]);
      
      // Load conversation history from database if available
      if (data.conversation_history && data.conversation_history.length > 0) {
        console.log("[DEBUG] Loading conversation history from database:", data.conversation_history.length, "messages");
        console.log("[DEBUG] Conversation history content:", data.conversation_history);
        const existingMessages = data.conversation_history.map((msg: any) => ({
          id: msg.id || nextMessageId(),
          sender: msg.sender,
          text: msg.text,
          timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
          type: msg.type || 'system'
        }));
        setMessages(existingMessages);
      } else {
        // Fallback: Add welcome message locally if no conversation history
        console.log("[DEBUG] No conversation history found, adding welcome message locally");
        setMessages([{
          id: nextMessageId() as any,
          sender: "System",
          text: `🎯 **${data.scenario.title}**\n\n${data.scenario.description}\n\n**Your Role:** ${data.scenario.student_role}\n\n**Current Scene:** ${data.current_scene.title}\n\n**Instructions:**\n• Type **"begin"** to start the simulation\n• Type **"help"** for available commands\n• Use natural conversation to interact with personas`,
          timestamp: new Date(),
          type: 'system'
        }]);
      }

    } catch (error) {
      console.error("Failed to start simulation:", error)
      alert(`Failed to start simulation: ${error}`)
    } finally {
      setIsLoading(false)
    }
  }



  // Send message to orchestrator
  const sendMessage = async () => {
    console.log("[DEBUG] sendMessage called. Input:", input);
    if (inputBlocked) return;
    if (!simulationData || !input.trim() || isLoading) return;

    const trimmedInput = input.trim();
    const mentionMatch = trimmedInput.match(/@(\w+)/);
    
    // Block persona mentions before simulation begins (unless it's the begin command)
    if (!simulationHasBegun && trimmedInput !== 'begin' && trimmedInput !== 'help') {
      if (mentionMatch) {
        alert('Please type "begin" to start the simulation before mentioning personas.');
        return;
      }
    }

    // Restrict @mentions to only personas in the current scene (only after simulation begins)
    if (simulationHasBegun && mentionMatch) {
      const mentionId = mentionMatch[1].toLowerCase();
      // Use only the personas from the current scene for validation
      const validPersonaMentions = simulationData.current_scene.personas.map(
        p => p.name.toLowerCase().replace(/\s+/g, '_')
      );
      console.log("[DEBUG] @mention validation:");
      console.log("  - Mentioned ID:", mentionId);
      console.log("  - Valid persona mentions:", validPersonaMentions);
      console.log("  - Current scene personas:", simulationData.current_scene.personas.map(p => p.name));
      if (!validPersonaMentions.includes(mentionId)) {
        console.log("[DEBUG] Invalid mention detected - blocking message");
        alert('You can only @mention personas involved in this scene.');
        return;
      }
      console.log("[DEBUG] Valid mention - allowing message");
    }

    const userMessage: Message = {
      id: nextMessageId() as any,
      sender: "You",
      text: input.trim(),
      timestamp: new Date(),
      type: 'user'
    };

    setMessages(prev => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    setIsTyping(true);
    
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
    setTypingPersona(typingPersonaName);
    setCurrentTypingPersona(typingPersonaName);
    
    // Grey out interface will be controlled by isStreaming state;

    // Only increment turn count for non-command messages
    if (trimmedInput !== 'begin' && trimmedInput !== 'help') {
      setTurnCount(prev => prev + 1);
      setHasSubmittedForGrading(false);
      // Hide submit button when user sends a new message
      setCanSubmitForGrading(false);
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
      });

      if (!response.ok) {
        throw new Error(`Chat failed: ${response.status}`);
      }

      // Handle streaming response
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let streamedText = "";
      let chatData: any = {};
      
      // Create a placeholder AI message that will be updated in real-time
      const aiMessageId: any = nextMessageId();
      const isBeginCommand = userMessage.text.trim().toLowerCase() === 'begin';
      const placeholderMessage: any = {
        id: aiMessageId,
        sender: typingPersonaName === "ChatOrchestrator" ? "System" : typingPersonaName,
        text: "",
        timestamp: new Date(),
        type: typingPersonaName !== "ChatOrchestrator" ? 'ai_persona' : 'orchestrator',
        persona_name: typingPersonaName,
        persona_id: undefined,
        // show a loading bar instead of streaming orchestrator text only for 'begin'
        showLoadingBar: typingPersonaName === "ChatOrchestrator" && isBeginCommand
      };
      
      setIsTyping(false); // Hide typing indicator when streaming starts
      setIsStreaming(false); // Don't start streaming state yet - wait for first content
      setStreamingMessageId(aiMessageId); // Track the streaming message ID
      // Add placeholder to messages state for streaming display
      setMessages(prev => [...prev, placeholderMessage]);
      
      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.substring(6);
              try {
                const parsed = JSON.parse(data);
                
                if (parsed.error) {
                  throw new Error(parsed.error);
                }
                
                if (parsed.content && !parsed.done) {
                  // Start streaming state when first content arrives
                  if (!isStreaming) {
                    setIsStreaming(true);
                  }
                  // Stream text for personas and non-begin orchestrator messages
                  if (typingPersonaName !== "ChatOrchestrator" || !isBeginCommand) {
                    // Append streamed content
                    streamedText += parsed.content;
                    setMessages(prev => prev.map(msg => 
                      msg.id === aiMessageId 
                        ? { ...msg, text: streamedText, sender: (typingPersonaName === "ChatOrchestrator") ? "System" : (parsed.persona_name || msg.sender) }
                        : msg
                    ));
                  }
                }
                
                if (parsed.done) {
                  // Final metadata received - streaming finished
                  chatData = parsed;
                  setIsStreaming(false); // Clear streaming state when streaming finishes
                  setStreamingMessageId(null); // Clear streaming message ID
                  
                  // Show loading screen immediately when scene is completed
                  if (parsed.scene_completed) {
                    setIsSceneTransitioning(true);
                  }
                  
                  if (typingPersonaName === "ChatOrchestrator" && isBeginCommand) {
                    // For 'begin', remove the loading placeholder when finished
                    setMessages(prev => prev.filter(msg => msg.id !== aiMessageId));
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
                    ));
                  }
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }
        }
      }
      
      
      // Now process the final chatData metadata
        
        // If this is the first "begin" response, add scene introduction as separate message
        if (trimmedInput === 'begin') {
          // Update simulation status to "in_progress" after begin command
          setSimulationData(prev => prev ? {
            ...prev,
            simulation_status: "in_progress"
          } : null);
          
          // Only show scene introduction if it hasn't been shown for this scene
          const currentScene = simulationData.current_scene;
          if (shouldShowSceneIntro(currentScene)) {
            console.log('[DEBUG] Showing scene introduction for:', currentScene.title);
            const sceneIntro = generateSceneIntroduction(currentScene);
            const sceneMessage: Message = {
              id: nextMessageId() as any,
              sender: "System",
              text: sceneIntro,
              timestamp: new Date(),
              type: 'system'
            }
            setMessages(prev => [...prev, sceneMessage])
            markSceneIntroShown(currentScene);
          } else {
            console.log('[DEBUG] Scene introduction already shown for:', currentScene.title);
          }
        }
        
        // Allow submit for grading after ANY AI response is received
        console.log("[DEBUG] Setting canSubmitForGrading to true after AI response");
        setCanSubmitForGrading(true);

        // Handle scene progression if indicated
        if (typeof chatData.turn_count === 'number') {
          setTurnCount(chatData.turn_count);
        }
        // Robust last scene detection
        const isLastScene =
          allScenes.length > 0 &&
          simulationData.current_scene &&
          simulationData.current_scene.id === allScenes[allScenes.length - 1].id;
        if (chatData.scene_completed) {
          // Safety timeout to ensure loading screen doesn't get stuck
          setTimeout(() => {
            setIsSceneTransitioning(false)
          }, 500) 
          
          setCompletedScenes(prev => {
            // Always add the current scene if not already present
            if (!prev.includes(simulationData.current_scene.id)) {
              return [...prev, simulationData.current_scene.id];
            }
            return prev;
          });
          addSceneIfMissing(simulationData.current_scene);

          if (chatData.next_scene_id) {
            setInputBlocked(true);
            const sceneLoadingId: any = nextMessageId();
            flushSync(() => {
              setMessages(prev => [...prev, { id: sceneLoadingId, sender: 'System', text: '', timestamp: new Date(), type: 'system' as const, sceneLoading: true } as any]);
              setIsSceneTransitioning(true);
            })
            // Force a paint before starting fetch (double rAF)
            requestAnimationFrame(() => requestAnimationFrame(() => {
              // Fetch next scene data and update simulationData
              fetch(buildApiUrl(`/api/simulation/scenes/${chatData.next_scene_id}`), {
                credentials: 'include'
              })
              .then(response => {
                if (response.ok) {
                  return response.json();
                }
                throw new Error('Failed to fetch next scene');
              })
              .then(nextSceneData => {
                // Use the fresh scene data from backend
                setSimulationData(prev => prev ? {
                  ...prev,
                  current_scene: nextSceneData,
                  simulation_status: "in_progress" // Preserve simulation status across scenes
                } : null);
                setTurnCount(0);
                setInputBlocked(false);
                setCanSubmitForGrading(true); // Enable submit button after scene transition
                addSceneIfMissing(nextSceneData);
                // Add scene transition message (don't filter existing messages)
                console.log("[DEBUG] Scene transition - adding new scene intro for scene:", nextSceneData.title);
                const sceneIntroMessage = {
                  id: nextMessageId() as any,
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
                  setMessages(prev => prev.filter(m => m.id !== sceneLoadingId));
                  setIsSceneTransitioning(false);
                }, 800);
              })
              .catch(error => {
                console.error("Failed to fetch next scene:", error);
                setInputBlocked(false);
                setIsSceneTransitioning(false);
                setMessages(prev => prev.filter(m => m.id !== sceneLoadingId));
                // Fallback completion message
                const completionMessage: Message = {
                  id: nextMessageId() as any,
                  sender: "System",
                  text: "🎉 Scene completed! Moving to the next scene...",
                  timestamp: new Date(),
                  type: 'system'
                };
                setMessages(prev => [...prev, completionMessage]);
              });
            }));
            return;
          } else if (isLastScene && !chatData.next_scene_id) {
            // Only trigger completion if this is the last scene
            setInputBlocked(false);
            setMessages(prev => [
              ...prev,
              {
                id: nextMessageId() as any,
                sender: "System",
                text: "🎉 Simulation complete! You have finished all scenes. View your grading and feedback.",
                timestamp: new Date(),
                type: 'system'
              }
            ]);
            setGradingInProgress(true);
            setSimulationComplete(true); // Set simulation complete when grading starts
            fetchGradingData().then(() => setGradingInProgress(false));
            return;
          }
          // If not last scene and no next_scene_id, fallback
          if (!chatData.next_scene_id) {
            setInputBlocked(false);
            setMessages(prev => [
              ...prev,
              {
                id: nextMessageId() as any,
                sender: "System",
                text: "🎉 Scene completed! Moving to the next scene...",
                timestamp: new Date(),
                type: 'system'
              }
            ]);
          }
          return;
        }

    } catch (error) {
      console.error("Failed to send message:", error)
      setIsTyping(false)
      setMessages(prev => [...prev, {
        id: nextMessageId() as any,
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

  // Handle Enter key
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  // If no simulation is active, show scenario selection
  if (!simulationData) {
    return (
      <div className="min-h-screen bg-gray-50 flex">
        <RoleBasedSidebar currentPath="/professor/test-simulations" />
        <div className="flex-1 ml-20 p-4">
          <div className="max-w-6xl mx-auto py-8">
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold mb-2">Linear Simulation Experience</h1>
              <p className="text-gray-600">
                Select a scenario to begin your interactive simulation with AI personas
              </p>
            </div>
            
            <ScenarioSelector onScenarioSelect={startSimulation} />
          </div>
        </div>
      </div>
    )
  }

  // Main simulation interface
  // Calculate totalScenes correctly - use the total_scenes from backend
  const totalScenes = simulationData?.scenario?.total_scenes || 
                     (allScenes.length > 0 ? allScenes.length : 4); // Default to 4 scenes

  // --- FEEDBACK/GRADING INTERFACE LOGIC (finalized) ---
  // Function to fetch grading data after simulation
  const fetchGradingData = async () => {
    if (!simulationData) return;
    const res = await apiClient.apiRequest(`/api/simulation/grade?user_progress_id=${simulationData.user_progress_id}`);
    if (res.ok) {
      const data = await res.json();
      setGradingData(data);
      setShowGrading(true);
    }
  };

  // In sendMessage, after the last scene is completed, trigger grading
  // (Insert this logic in your sendMessage or scene progression handler)
  // if (chatData.scene_completed && !chatData.next_scene_id) {
  //   fetchGradingData();
  // }

  // Enhanced Grading Modal
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
          
          {/* Enhanced feedback sections if available */}
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
          {gradingData.scenes && gradingData.scenes.map((scene: any, idx: number) => (
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
              
              {/* Enhanced scene feedback if available */}
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
          <button className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-8 rounded-lg transition-colors duration-200" onClick={() => {
            console.log("[DEBUG] Closing grading modal");
            setShowGrading(false);
            setGradingHasBeenShown(true);
            setInputBlocked(false);
            setCanSubmitForGrading(false);
            setHasSubmittedForGrading(false);
            
            // Update the completion message to show the "View Grading" button
            setMessages(prev => {
              console.log("[DEBUG] Current messages before update:", prev);
              console.log("[DEBUG] Looking for completion message with text containing '🎉 Simulation complete!'");
              const updatedMessages = prev.map(msg => {
                console.log("[DEBUG] Checking message:", msg.text.substring(0, 50), "showViewGrading:", msg.showViewGrading, "type:", msg.type);
                if (msg.text.includes("🎉 Simulation complete!") && msg.type === 'system') {
                  console.log("[DEBUG] FOUND COMPLETION MESSAGE! Updating showViewGrading to true");
                  const updatedMsg = { ...msg, showViewGrading: true };
                  console.log("[DEBUG] Updated message:", updatedMsg);
                  return updatedMsg;
                }
                return msg;
              });
              console.log("[DEBUG] Final updated messages:", updatedMessages);
              return updatedMessages;
            });
          }}>Close Assessment</button>
        </div>
      </div>
    </div>
  )}

  // Handler for submit button
  const handleSubmitForGrading = async () => {
    console.log("[DEBUG] handleSubmitForGrading called");
    console.log("[DEBUG] Current state before submit:");
    console.log("  - canSubmitForGrading:", canSubmitForGrading);
    console.log("  - hasSubmittedForGrading:", hasSubmittedForGrading);
    console.log("  - inputBlocked:", inputBlocked);
    console.log("  - simulationComplete:", simulationComplete);
    setHasSubmittedForGrading(true);
    setInputBlocked(true);
    // Show loading screen for manual submit for grading
    setIsSceneTransitioning(true);
    
    // Safety timeout to ensure loading screen doesn't get stuck
    setTimeout(() => {
      setIsSceneTransitioning(false);
    }, 500);
    
    // Don't add submit message to chat history - it's a UI action, not a conversation message
    
    // Instead of calling /progress directly, send a special message through the normal chat flow
    // This ensures the turn counting logic is respected
    const specialMessage = "SUBMIT_FOR_GRADING";
    
    try {
      const response = await apiClient.apiRequest("/api/simulation/linear-chat", {
        method: "POST",
        body: JSON.stringify({
          user_progress_id: simulationData.user_progress_id,
          scene_id: simulationData.current_scene.id,
          message: specialMessage,
          user_id: 1,
          scenario_id: simulationData.scenario.id
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log("[DEBUG] Submit for grading response:", data);
      console.log("[DEBUG] scene_completed:", data.scene_completed);
      console.log("[DEBUG] next_scene_id:", data.next_scene_id);
      console.log("[DEBUG] next_scene:", data.next_scene);
      console.log("[DEBUG] Has next_scene data:", !!data.next_scene);
      
      if (data.scene_completed) {
        if (data.next_scene_id) {
          console.log("[DEBUG] Moving to next scene via submit for grading");
          console.log("[DEBUG] Current scene ID:", simulationData.current_scene.id);
          console.log("[DEBUG] Next scene ID:", data.next_scene_id);
          console.log("[DEBUG] Current scene title:", simulationData.current_scene.title);
          
          // Update completed scenes
          setCompletedScenes(prev => {
            const currentSceneId = simulationData.current_scene.id;
            if (!prev.includes(currentSceneId)) {
              return [...prev, currentSceneId];
            }
            return prev;
          });
          
          // Move to next scene using the data provided by backend
          if (data.next_scene) {
            console.log("[DEBUG] Using next_scene data from backend response:", data.next_scene);
            console.log("[DEBUG] Next scene title:", data.next_scene.title);
            console.log("[DEBUG] Next scene personas:", data.next_scene.personas);
            
            setSimulationData(prev => prev ? {
              ...prev,
              current_scene: data.next_scene,
              simulation_status: "in_progress"
            } : null);
            
            setTurnCount(0);
            setCanSubmitForGrading(true);
            setHasSubmittedForGrading(false);
            
            // Add scene to allScenes and generate introduction message
            addSceneIfMissing(data.next_scene);
            
            // Always show scene introduction for new scenes (don't filter existing messages)
            setMessages(prev => [
              ...prev,
              {
                id: nextMessageId() as any,
                sender: "System",
                text: generateSceneIntroduction(data.next_scene),
                timestamp: new Date(),
                type: 'system'
              }
            ]);
            markSceneIntroShown(data.next_scene);
          } else {
            console.log("[DEBUG] No next_scene data in response, falling back to API fetch");
            
            // Fallback: Fetch the scene data from backend to get properly filtered personas
            try {
              const sceneResponse = await apiClient.apiRequest(`/api/simulation/scenes/${data.next_scene_id}`, {
                method: "GET"
              });
              
              if (sceneResponse.ok) {
                const sceneData = await sceneResponse.json();
                console.log("[DEBUG] Fetched new scene data:", sceneData);
                console.log("[DEBUG] New scene title:", sceneData.title);
                console.log("[DEBUG] New scene personas:", sceneData.personas);
                
                setSimulationData(prev => prev ? {
                  ...prev,
                  current_scene: sceneData,
                  simulation_status: "in_progress" // Preserve simulation status across scenes
                } : null);
              } else {
                // Fallback to cached data if backend fetch fails
                const filteredNextScene = allScenes.find(s => s.id === data.next_scene_id) || data.next_scene;
                setSimulationData(prev => prev ? {
                  ...prev,
                  current_scene: filteredNextScene,
                  simulation_status: "in_progress"
                } : null);
              }
            } catch (error) {
              console.error("Failed to fetch scene data:", error);
              // Fallback to cached data
              const filteredNextScene = allScenes.find(s => s.id === data.next_scene_id) || data.next_scene;
              setSimulationData(prev => prev ? {
                ...prev,
                current_scene: filteredNextScene,
                simulation_status: "in_progress"
              } : null);
            }
            setTurnCount(0);
            setCanSubmitForGrading(true); // Enable submit button immediately for new scene
            setHasSubmittedForGrading(false);
            
            // Add scene to allScenes and generate introduction message
            // Use the fresh scene data from the backend response
            const newScene = simulationData.current_scene;
            addSceneIfMissing(newScene);
            
            // Always show scene introduction for new scenes (don't filter existing messages)
            setMessages(prev => [
              ...prev,
              {
                id: nextMessageId() as any,
                sender: "System",
                text: generateSceneIntroduction(newScene),
                timestamp: new Date(),
                type: 'system'
              }
            ]);
            markSceneIntroShown(newScene);
          }
          // Confirm backend state before unblocking input
          apiClient.apiRequest(`/api/simulation/progress/${simulationData.user_progress_id}`)
            .then(res => res.json())
            .then(progress => {
              if (progress.current_scene_id === data.next_scene_id) {
                console.log("[DEBUG] Backend state synced, enabling submit button");
                setInputBlocked(false);
                // Enable submit button after scene transition is complete
                setCanSubmitForGrading(true);
              } else {
                // Retry after a short delay if not yet synced
                setTimeout(() => {
                  setInputBlocked(false);
                  setCanSubmitForGrading(true);
                }, 300);
              }
            })
            .catch(() => {
              setTimeout(() => {
                setInputBlocked(false);
                setCanSubmitForGrading(true);
              }, 300);
            });
        } else {
          console.log("[DEBUG] Simulation complete via chat flow");
          setSimulationComplete(true);
          // Update completed scenes
          setCompletedScenes(prev => {
            const currentSceneId = simulationData.current_scene.id;
            if (!prev.includes(currentSceneId)) {
              return [...prev, currentSceneId];
            }
            return prev;
          });
          
          // Add completion message to chat
          setMessages(prev => [
            ...prev,
            {
              id: nextMessageId() as any,
              sender: "System",
              text: "🎉 Simulation complete! You have finished all scenes. View your grading and feedback.",
              timestamp: new Date(),
              type: 'system',
              showViewGrading: false
            }
          ]);
          
          // Show grading modal
          setGradingInProgress(true);
          setSimulationComplete(true); // Set simulation complete when grading starts
          fetchGradingData().then(() => setGradingInProgress(false));
        }
      } else {
        console.log("[DEBUG] Scene not completed, continuing normally");
        setInputBlocked(false);
        setCanSubmitForGrading(false);
        setHasSubmittedForGrading(false);
      }
    } catch (error) {
      console.error("[ERROR] Submit for grading failed:", error);
      setInputBlocked(false);
      setCanSubmitForGrading(false);
      setHasSubmittedForGrading(false);
      alert('Failed to submit for grading.');
    }
  };

  // Helper to determine if we should show the submit button system message
  const isLastScene = simulationData && simulationData.current_scene.scene_order >= totalScenes;
  const timeoutTurns = simulationData?.current_scene?.timeout_turns ?? 15;
  const hasTurnsRemaining = turnCount < timeoutTurns;
  const shouldShowSubmitSystemMessage = canSubmitForGrading && !hasSubmittedForGrading && !inputBlocked && !simulationComplete && hasTurnsRemaining;
  
  // Debug logging removed to prevent infinite loops

  return (
    <div className="h-screen bg-white flex">
      <RoleBasedSidebar currentPath="/professor/test-simulations" />
      
      <div className="flex-1 ml-20 flex flex-col">
        {/* Top Navigation Bar */}
        <div className="bg-white px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.back()}
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
            {!simulationHasBegun ? (
              <div className="text-center text-gray-400 py-12">
                <p className="text-sm">Start the simulation to see scene content.</p>
              </div>
            ) : (
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
                    <div className="absolute bottom-3 left-4 bg-black/80 backdrop-blur-sm text-white px-3 py-1.5 rounded text-sm font-medium" style={{ fontFamily: "'Sora', sans-serif" }}>
                      {simulationData.current_scene.title}
                    </div>
                  </div>
                )}

                {/* Content area - Flex to fill remaining space */}
                <div className="flex-1 min-h-0 flex flex-col space-y-4 overflow-hidden">
                  {/* Scene Description - Full text display */}
                  <div className="flex-shrink-0 animate-fade-in-up stagger-1" style={{ fontFamily: "'Sora', sans-serif" }}>
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
                    <h3 className="text-sm font-semibold mb-2 text-gradient-sim flex-shrink-0" style={{ fontFamily: "'Sora', sans-serif" }}>Available Personas ({simulationData.current_scene.personas.length})</h3>
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
                                background: persona.background
                              });
                              setShowPersonaModal(true);
                            }}
                          >
                            <div className="flex items-center gap-1.5 min-w-0 w-full">
                              <div className="w-5 h-5 bg-gray-600 rounded-full flex items-center justify-center flex-shrink-0">
                                <User className="w-2.5 h-2.5" />
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
                    className="relative overflow-hidden flex-1"
                    style={{ height: `calc(100% - ${inputAreaHeight}px)` }}
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
                        type: 'system',
                        showSubmitForGrading: false,
                        showViewGrading: false,
                        gradingInProgress: true
                      }] : [])].map((message, idx) => {
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
                              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 text-[11px] flex items-center justify-center text-white font-semibold shadow-sm">
                                {(() => {
                                  const label = ((message as any).persona_name || message.sender || '');
                                  return label.charAt(0).toUpperCase();
                                })()}
                              </div>
                            )}
                            <span className="text-xs font-semibold opacity-90" style={{ fontFamily: "'Sora', sans-serif" }}>
                              {message.type === 'orchestrator' ? 'System' : message.sender}
                            </span>
                            {'persona_name' in message && message.type === 'ai_persona' && (
                              <Badge variant="secondary" className="text-xs bg-white/90 backdrop-blur-sm text-gray-800 border border-gray-300/50 shadow-sm font-medium">
                                {('persona_role' in message && (message as any).persona_role) || getPersonaRole((message as any).persona_name || message.sender) || 'Persona'}
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
                            {message.showViewGrading && (
                              <div className="flex flex-col items-center mt-3">
                                <Button
                                  variant="default"
                                  onClick={() => {
                                    if (gradingData) {
                                      setShowGrading(true);
                                    } else {
                                      setGradingInProgress(true);
                                      fetchGradingData().then(() => setGradingInProgress(false));
                                    }
                                  }}
                                >
                                  View Grading & Feedback
                                </Button>
                              </div>
                            )}
                            {/* gradingInProgress now uses the same loading UI above */}
                          </div>
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
                                    <div className="w-7 h-7 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm">
                                      <User className="w-3.5 h-3.5 text-white" />
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
          <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-lg p-8 max-w-4xl w-full overflow-y-auto max-h-[90vh]">
              <h2 className="text-2xl font-bold mb-4 text-center">Simulation Grading & Feedback</h2>
              <div className="mb-6">
                <div className="text-lg font-semibold">Overall Score: <span className="text-blue-600">{gradingData.overall_score}</span></div>
                <div className="text-gray-700 mt-2">{gradingData.overall_feedback}</div>
              </div>
              {gradingData.scenes && gradingData.scenes.map((scene: any, idx: number) => (
                <div key={scene.id} className="mb-6 border-b pb-4">
                  <div className="font-semibold text-blue-700">{scene.title}</div>
                  <div className="text-sm text-gray-500 mb-2">{scene.objective}</div>
                  <div className="mb-2">
                    <span className="font-medium">Your Responses:</span>
                    <div
                      style={{
                        maxHeight: '120px',
                        overflowY: 'auto',
                        background: '#f9fafb',
                        border: '1px solid #e5e7eb',
                        borderRadius: '0.375rem',
                        padding: '0.5rem',
                        marginTop: '0.5rem',
                        fontSize: '0.95rem',
                        whiteSpace: 'pre-wrap',
                        width: '100%',
                        fontFamily: 'inherit',
                        resize: 'none',
                        color: '#222'
                      }}
                      tabIndex={-1}
                      aria-readonly="true"
                    >
                      {scene.user_responses && scene.user_responses.length > 0
                        ? scene.user_responses.map((msg: any) => `• ${msg.content}`).join('\n\n')
                        : <span className="text-gray-400">No responses.</span>}
                    </div>
                  </div>
                  <div className="text-sm text-green-700 mb-1">Score: {scene.score}</div>
                  <div className="text-gray-700">{scene.feedback}</div>
                  {scene.teaching_notes && (
                    <div className="mt-2 text-xs text-gray-500 italic">Teaching Notes: {scene.teaching_notes}</div>
                  )}
                </div>
              ))}
              <div className="flex justify-center mt-6">
                <button 
                  className="btn btn-primary" 
                  onClick={() => {
                    console.log("[DEBUG] Closing grading modal");
                    setShowGrading(false);
                    setGradingHasBeenShown(true);
                    setInputBlocked(false);
                    setCanSubmitForGrading(false);
                    setHasSubmittedForGrading(false);
                    
                    // Update the completion message to show the "View Grading" button
                    setMessages(prev => {
                      console.log("[DEBUG] Current messages before update:", prev);
                      console.log("[DEBUG] Looking for completion message with text containing '🎉 Simulation complete!'");
                      const updatedMessages = prev.map(msg => {
                        console.log("[DEBUG] Checking message:", msg.text.substring(0, 50), "showViewGrading:", msg.showViewGrading, "type:", msg.type);
                        if (msg.text.includes("🎉 Simulation complete!") && msg.type === 'system') {
                          console.log("[DEBUG] FOUND COMPLETION MESSAGE! Updating showViewGrading to true");
                          const updatedMsg = { ...msg, showViewGrading: true };
                          console.log("[DEBUG] Updated message:", updatedMsg);
                          return updatedMsg;
                        }
                        return msg;
                      });
                      console.log("[DEBUG] Final updated messages:", updatedMessages);
                      return updatedMessages;
                    });
                  }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
} 