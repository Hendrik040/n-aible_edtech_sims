"use client"

import { useState, useEffect, useRef } from "react"
import { X, Save, RotateCcw, History, Clock, User, Brain, GraduationCap, MessageCircle, Target, BookOpen, Trophy, ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { apiClient } from "@/lib/api"
import { getImageUrl } from "@/lib/image-utils"

interface ProfessorGradingModalProps {
  isOpen: boolean
  onClose: () => void
  instanceId: number
  onGraded: () => void
}

interface ConversationMessage {
  id: number
  type: string
  sender: string
  content: string
  timestamp?: string
  scene_id?: number
  persona_name?: string
  persona_role?: string
}

interface Persona {
  id: number
  name: string
  role: string
  background: string
  image_url?: string
}

export default function ProfessorGradingModal({
  isOpen,
  onClose,
  instanceId,
  onGraded
}: ProfessorGradingModalProps) {
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [submissionData, setSubmissionData] = useState<any>(null)
  const [gradeHistory, setGradeHistory] = useState<any[]>([])
  const [showHistory, setShowHistory] = useState(false)
  // Resizable left panel state
  const [leftPanelWidth, setLeftPanelWidth] = useState<number>(33.33)
  const [isResizing, setIsResizing] = useState<boolean>(false)
  
  // Form state
  const [grade, setGrade] = useState("")
  const [feedback, setFeedback] = useState("")
  const [error, setError] = useState<string | null>(null)
  
  // Chat scroll ref
  const chatEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Drag-to-resize handlers
  useEffect(() => {
    if (!isResizing) return
    const handleMouseMove = (e: MouseEvent) => {
      const container = containerRef.current
      if (!container) return
      const rect = container.getBoundingClientRect()
      const minPct = 15 // min 15%
      const maxPct = 50 // max 50%
      const x = e.clientX - rect.left
      const pct = (x / rect.width) * 100
      const clamped = Math.max(minPct, Math.min(maxPct, pct))
      setLeftPanelWidth(clamped)
    }
    const handleMouseUp = () => setIsResizing(false)
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing])

  useEffect(() => {
    if (isOpen && instanceId) {
      fetchSubmissionData()
    }
  }, [isOpen, instanceId])

  useEffect(() => {
    // Auto-scroll chat to bottom when new data loads
    if (submissionData?.conversation_history && chatEndRef.current) {
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
      }, 100)
    }
  }, [submissionData])

  const fetchSubmissionData = async () => {
    try {
      setLoading(true)
      setError(null)
      const [submission, history] = await Promise.all([
        apiClient.getSubmissionDetails(instanceId),
        apiClient.getGradeHistory(instanceId)
      ])
      setSubmissionData(submission)
      setGradeHistory(history)
      
      // Pre-fill form with current professor grade or AI grade
      if (submission.professor_grade !== null) {
        setGrade(submission.professor_grade.toString())
        setFeedback(submission.professor_feedback || "")
      } else if (submission.ai_grade !== null) {
        setGrade(submission.ai_grade.toString())
        setFeedback("")
      }
    } catch (err: any) {
      setError(err.message || "Failed to load submission data")
      console.error("Error loading submission:", err)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!grade || parseFloat(grade) < 0 || parseFloat(grade) > 100) {
      setError("Please enter a valid grade between 0 and 100")
      return
    }

    try {
      setSubmitting(true)
      setError(null)
      await apiClient.submitProfessorReview(instanceId, {
        grade: parseFloat(grade),
        feedback: feedback
      })
      await fetchSubmissionData()
      onGraded()
    } catch (err: any) {
      setError(err.message || "Failed to submit grade")
      console.error("Error submitting grade:", err)
    } finally {
      setSubmitting(false)
    }
  }

  const handleRevertToAI = async () => {
    if (!confirm("Are you sure you want to revert to the AI grade? This will remove your manual grade.")) {
      return
    }

    try {
      setSubmitting(true)
      setError(null)
      await apiClient.revertToAIGrade(instanceId)
      await fetchSubmissionData()
      onGraded()
    } catch (err: any) {
      setError(err.message || "Failed to revert to AI grade")
      console.error("Error reverting:", err)
    } finally {
      setSubmitting(false)
    }
  }

  // Lookup persona image from all scenes
  const getPersonaImage = (personaName?: string, sceneId?: number) => {
    if (!personaName || !submissionData?.all_scenes) return undefined
    
    for (const scene of submissionData.all_scenes) {
      const persona = scene.personas?.find((p: Persona) => p.name === personaName)
      if (persona?.image_url) {
        return getImageUrl(persona.image_url)
      }
    }
    
    // Fallback to current scene
    if (submissionData?.current_scene?.personas) {
      const persona = submissionData.current_scene.personas.find((p: Persona) => p.name === personaName)
      if (persona?.image_url) {
        return getImageUrl(persona.image_url)
      }
    }
    
    return undefined
  }

  // Lookup persona role
  const getPersonaRole = (personaName?: string) => {
    if (!personaName || !submissionData?.all_scenes) return undefined
    
    for (const scene of submissionData.all_scenes) {
      const persona = scene.personas?.find((p: Persona) => p.name === personaName)
      if (persona) return persona.role
    }
    
    if (submissionData?.current_scene?.personas) {
      const persona = submissionData.current_scene.personas.find((p: Persona) => p.name === personaName)
      if (persona) return persona.role
    }
    
    return undefined
  }

  // Get persona bubble classes (same as student simulation)
  const getPersonaBubbleClasses = (personaName?: string) => {
    const personaPalette = [
      'bg-green-50 border-green-200',
      'bg-blue-50 border-blue-200',
      'bg-purple-50 border-purple-200',
      'bg-pink-50 border-pink-200',
      'bg-yellow-50 border-yellow-200',
      'bg-indigo-50 border-indigo-200',
      'bg-teal-50 border-teal-200',
      'bg-orange-50 border-orange-200'
    ]
    
    if (!personaName) return personaPalette[0]
    
    // Simple hash function
    let hash = 0
    for (let i = 0; i < personaName.length; i++) {
      hash = personaName.charCodeAt(i) + ((hash << 5) - hash)
    }
    return personaPalette[Math.abs(hash) % personaPalette.length]
  }

  if (!isOpen) return null

  const conversationHistory = submissionData?.conversation_history || []
  const currentScene = submissionData?.current_scene
  const scenario = submissionData?.scenario

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 overflow-hidden">
      <div className="bg-white w-[98vw] h-[95vh] mx-2 my-2 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="bg-white px-6 py-4 border-b border-gray-200/50 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={onClose}
                className="text-gray-600 hover:text-gray-900"
              >
                <X className="w-5 h-5" />
              </button>
              <h1 className="text-lg font-semibold text-gray-900 truncate">
                {scenario?.title || submissionData?.simulation_title || 'Review Submission'}
              </h1>
              {scenario && (
                <span className="text-sm text-gray-600">
                  {submissionData?.student_name} • Scene {currentScene?.scene_order || 0}/{scenario.total_scenes || 0}
                </span>
              )}
            </div>
            <div className="flex items-center gap-4">
              {scenario && currentScene && (
                <div className="w-32 bg-gray-200 rounded-full h-2">
                  <div 
                    className="bg-green-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${((currentScene.scene_order || 0) / (scenario.total_scenes || 1)) * 100}%` }}
                  ></div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main Content - Three Panel Layout */}
        <div className="flex flex-1 min-h-0 relative" ref={containerRef}>
          {/* Left Panel - Dark Theme Context (same as student simulation) */}
          {currentScene && (
            <div 
              className={`sim-panel-gradient text-white flex flex-col min-h-0 transition-all duration-150 ease-in-out relative`}
              style={{ width: `${leftPanelWidth}%` }}
            >
              {/* Drag Handle */}
              <div
                onMouseDown={() => setIsResizing(true)}
                className={`absolute right-0 top-0 bottom-0 w-1 bg-white/20 hover:bg-white/40 z-30 transition-colors duration-150 group cursor-col-resize`}
              ></div>
              
              <div className="flex flex-col h-full p-6">
                {/* Scene Image */}
                {currentScene.image_url && (
                  <div className="mb-4 relative -mx-6 -mt-6 flex-shrink-0 animate-fade-in-up">
                    <img 
                      src={getImageUrl(currentScene.image_url)} 
                      alt={currentScene.title}
                      className="w-full h-56 object-cover"
                    />
                    <div className="scene-image-overlay absolute inset-0 pointer-events-none"></div>
                    <div className="absolute bottom-3 left-4 bg-black/80 backdrop-blur-sm text-white px-3 py-1.5 rounded text-sm font-medium" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                      {currentScene.title}
                    </div>
                  </div>
                )}

                {/* Content area */}
                <div className="flex-1 min-h-0 flex flex-col space-y-4 overflow-hidden">
                  {/* Scene Description */}
                  <div className="flex-shrink-0 animate-fade-in-up stagger-1" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                    <h3 className="text-base font-semibold mb-2 text-gradient-sim">Scene Description</h3>
                    <p className="text-gray-300 text-xs leading-relaxed">
                      {currentScene.description}
                    </p>
                  </div>

                  {/* Objective */}
                  <div className="flex-shrink-0 animate-fade-in-up stagger-2">
                    <div className="objective-card rounded-lg p-3 sim-glow-hover">
                      <div className="flex items-center gap-2 mb-1 relative z-10">
                        <Target className="w-4 h-4" />
                        <span className="font-semibold text-sm" style={{ fontFamily: "'Sora', sans-serif" }}>OBJECTIVE</span>
                      </div>
                      <p className="text-xs leading-relaxed relative z-10">
                        {currentScene.user_goal || 'Complete the interaction'}
                      </p>
                    </div>
                  </div>

                  {/* Available Personas */}
                  <div className="flex-1 min-h-0 flex flex-col animate-fade-in-up stagger-3">
                    <h3 className="text-sm font-semibold mb-2 text-gradient-sim flex-shrink-0" style={{ fontFamily: "'Sora', sans-serif" }}>
                      Available Personas ({currentScene.personas?.length || 0})
                    </h3>
                    <div className="bg-gray-800/80 backdrop-blur-sm rounded-lg p-2 flex-1 min-h-0 overflow-y-auto space-y-1.5 scrollbar-thin border border-gray-700/30">
                      {currentScene.personas && currentScene.personas.length > 0 ? (
                        currentScene.personas.map((persona: Persona, idx: number) => (
                          <div
                            key={persona.id}
                            className="persona-card-hover bg-gray-700/90 rounded-lg p-1.5 flex-shrink-0 animate-slide-in-right"
                            style={{ animationDelay: `${0.25 + idx * 0.05}s` }}
                          >
                            <div className="flex items-center gap-1.5 min-w-0 w-full">
                              <div className="w-5 h-5 bg-gray-600 rounded-full flex-shrink-0 overflow-hidden relative">
                                {persona.image_url && persona.image_url.trim() ? (
                                  <img 
                                    src={getImageUrl(persona.image_url)} 
                                    alt={persona.name} 
                                    className="object-cover w-full h-full"
                                  />
                                ) : (
                                  <div className="w-full h-full flex items-center justify-center">
                                    <User className="w-2.5 h-2.5 text-gray-400" />
                                  </div>
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
              </div>
            </div>
          )}

          {/* Collapsed toggle removed in favor of drag-to-resize */}

          {/* Middle Panel - Conversation History */}
          <div 
            className="sim-panel-right flex flex-col min-h-0 relative border-r border-gray-200/50 transition-all duration-150" 
            style={{ 
              width: currentScene 
                ? `${(100 - leftPanelWidth) / 2}%`
                : '50%'
            }}
          >
            {/* Conversation Header */}
            <div className="relative z-10 border-b border-gray-200/50 bg-white/80 backdrop-blur-sm">
              <div className="px-6 py-3">
                <div className="flex items-center gap-2">
                  <MessageCircle className="w-4 h-4 text-blue-600" />
                  <span className="text-sm font-semibold text-gray-900" style={{ fontFamily: "'Sora', sans-serif" }}>
                    Conversation
                  </span>
                </div>
              </div>
            </div>

            {/* Messages Area - same style as student simulation */}
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
                  <p className="text-black">Loading submission...</p>
                </div>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 m-4">
                {error}
              </div>
            ) : submissionData ? (
              <div className="relative overflow-hidden flex-1 min-h-0">
                <div className="h-full overflow-y-auto p-6 space-y-4" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                  {conversationHistory.map((msg: ConversationMessage) => {
                    const isUser = msg.type === 'user'
                    const isSystem = msg.type === 'system' || msg.type === 'orchestrator'
                    
                    return (
                      <div
                        key={msg.id}
                        className={`flex ${isUser ? 'justify-end' : 'justify-start'} transition-all duration-300`}
                      >
                        <div className={`max-w-md px-4 py-3 rounded-lg transition-all duration-300 ${
                          isUser
                            ? 'sim-message-user text-white'
                            : isSystem
                            ? 'bg-gray-100 text-gray-800 border border-gray-200'
                            : `sim-message-persona ${getPersonaBubbleClasses(msg.persona_name || msg.sender)} text-gray-800 border`
                        }`} style={{ 
                          fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif"
                        }}>
                          <div className="flex items-center gap-2 mb-1.5">
                            {!isUser && !isSystem && (
                              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 text-[11px] flex items-center justify-center text-white font-semibold shadow-sm overflow-hidden">
                                {(() => {
                                  const personaImage = msg.persona_name ? getPersonaImage(msg.persona_name, msg.scene_id) : null
                                  if (personaImage) {
                                    return (
                                      <img 
                                        src={personaImage} 
                                        alt={msg.persona_name || msg.sender} 
                                        className="object-cover w-full h-full rounded-full"
                                        onError={(e) => {
                                          e.currentTarget.style.display = 'none'
                                          const parent = e.currentTarget.parentElement
                                          if (parent) {
                                            const label = (msg.persona_name || msg.sender || '').charAt(0).toUpperCase()
                                            parent.textContent = label
                                          }
                                        }}
                                      />
                                    )
                                  }
                                  const label = (msg.persona_name || msg.sender || '')
                                  return label.charAt(0).toUpperCase()
                                })()}
                              </div>
                            )}
                            <span className="text-xs font-semibold opacity-90" style={{ fontFamily: "'Sora', sans-serif" }}>
                              {isSystem ? 'System' : msg.sender}
                            </span>
                            {!isUser && !isSystem && msg.persona_name && (
                              <Badge variant="secondary" className="text-xs bg-white/90 backdrop-blur-sm text-gray-800 border border-gray-300/50 shadow-sm font-medium">
                                {msg.persona_role || getPersonaRole(msg.persona_name) || msg.persona_name}
                              </Badge>
                            )}
                          </div>
                          <div className="text-sm whitespace-pre-wrap leading-relaxed">
                            {msg.content.split('\n').map((line, index) => {
                              const boldFormatted = line.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
                              return (
                                <div key={index} dangerouslySetInnerHTML={{ __html: boldFormatted }} />
                              )
                            })}
                          </div>
                          {msg.timestamp && (
                            <p className="text-xs mt-2 opacity-70">
                              {new Date(msg.timestamp).toLocaleTimeString()}
                            </p>
                          )}
                        </div>
                      </div>
                    )
                  })}
                  <div ref={chatEndRef} />
                </div>
              </div>
            ) : null}
          </div>

          {/* Right Panel - Grading Interface */}
          <div 
            className="flex flex-col min-h-0 bg-white transition-all duration-150" 
            style={{ 
              width: currentScene 
                ? `${(100 - leftPanelWidth) / 2}%`
                : '50%'
            }}
          >
            {/* Grading Header */}
            <div className="border-b border-gray-200/50 bg-white/80 backdrop-blur-sm flex-shrink-0">
              <div className="px-6 py-3">
                <div className="flex items-center gap-2">
                  <Trophy className="w-4 h-4 text-emerald-600" />
                  <span className="text-sm font-semibold text-gray-900" style={{ fontFamily: "'Sora', sans-serif" }}>
                    Grading
                  </span>
                </div>
              </div>
            </div>

            {/* Grading Panel */}
            {loading ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto mb-4"></div>
                  <p className="text-black">Loading submission...</p>
                </div>
              </div>
            ) : error ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 m-4">
                {error}
              </div>
            ) : submissionData ? (
              <div className="h-full overflow-y-auto p-6 space-y-6">
                {/* Student Info Cards */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-gradient-to-br from-blue-50 to-blue-100/50 rounded-xl p-4 border border-blue-200/60">
                    <div className="flex items-center gap-2 mb-2">
                      <User className="h-4 w-4 text-blue-600" />
                      <span className="text-xs font-semibold text-blue-900 uppercase tracking-wide" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                        Student
                      </span>
                    </div>
                    <p className="text-sm font-bold text-blue-900" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                      {submissionData.student_name}
                    </p>
                  </div>
                  <div className="bg-gradient-to-br from-green-50 to-green-100/50 rounded-xl p-4 border border-green-200/60">
                    <div className="flex items-center gap-2 mb-2">
                      <Clock className="h-4 w-4 text-green-600" />
                      <span className="text-xs font-semibold text-green-900 uppercase tracking-wide" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                        Progress
                      </span>
                    </div>
                    <p className="text-sm font-bold text-green-900" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                      {submissionData.completion_percentage.toFixed(0)}%
                    </p>
                  </div>
                </div>

                {/* AI Grade Reference */}
                {submissionData.ai_grade !== null && (
                  <div className="bg-gradient-to-br from-amber-50/80 to-amber-100/40 rounded-xl p-5 border border-amber-200/60">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-10 h-10 bg-gradient-to-br from-amber-100 to-amber-50 rounded-xl flex items-center justify-center">
                        <Brain className="h-5 w-5 text-amber-600" />
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-slate-900" style={{ fontFamily: "'Crimson Text', serif" }}>
                          AI-Generated Grade
                        </h3>
                        <p className="text-xs text-slate-600" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                          Reference only
                        </p>
                      </div>
                    </div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-bold text-amber-700" style={{ fontFamily: "'Crimson Text', serif" }}>
                        {submissionData.ai_grade.toFixed(1)}
                      </span>
                      <span className="text-lg text-amber-600">/ 100</span>
                    </div>
                  </div>
                )}

                {/* Grading Form */}
                <div className="bg-gradient-to-br from-white to-slate-50/30 rounded-xl p-5 border border-slate-200/60 shadow-sm">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 bg-gradient-to-br from-emerald-100 to-teal-50 rounded-xl flex items-center justify-center">
                      <GraduationCap className="h-5 w-5 text-emerald-600" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-900" style={{ fontFamily: "'Crimson Text', serif" }}>
                      Your Assessment
                    </h3>
                  </div>
                  
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-semibold text-slate-700 mb-2" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                        Grade (0-100)
                      </label>
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.1"
                        value={grade}
                        onChange={(e) => setGrade(e.target.value)}
                        className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 transition-all text-lg font-semibold"
                        placeholder="0.0"
                        style={{ fontFamily: "'DM Sans', sans-serif" }}
                      />
                    </div>
                    
                    <div>
                      <label className="block text-sm font-semibold text-slate-700 mb-2" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                        Feedback
                      </label>
                      <textarea
                        value={feedback}
                        onChange={(e) => setFeedback(e.target.value)}
                        rows={8}
                        className="w-full px-4 py-3 border-2 border-slate-200 rounded-xl focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 transition-all resize-none"
                        placeholder="Enter your detailed feedback for the student..."
                        style={{ fontFamily: "'DM Sans', sans-serif" }}
                      />
                    </div>
                    
                    {error && (
                      <div className="bg-red-50 border-2 border-red-200 rounded-xl p-3 text-red-700 text-sm">
                        {error}
                      </div>
                    )}
                    
                    <div className="flex gap-2 pt-2">
                      {submissionData.professor_grade !== null && (
                        <Button
                          variant="outline"
                          onClick={handleRevertToAI}
                          disabled={submitting}
                          className="flex-1 text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                        >
                          <RotateCcw className="h-4 w-4 mr-2" />
                          Revert
                        </Button>
                      )}
                      <Button
                        onClick={handleSubmit}
                        disabled={submitting || !grade}
                        className="flex-1 bg-gradient-to-r from-emerald-500 to-teal-600 text-white hover:from-emerald-600 hover:to-teal-700 shadow-lg"
                      >
                        <Save className="h-4 w-4 mr-2" />
                        {submitting ? "Saving..." : "Save Grade"}
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Grade History */}
                <div className="bg-slate-50/50 rounded-xl border border-slate-200/60 p-4">
                  <button
                    onClick={() => setShowHistory(!showHistory)}
                    className="flex items-center gap-2 text-sm font-semibold text-slate-700 w-full"
                    style={{ fontFamily: "'DM Sans', sans-serif" }}
                  >
                    <History className="h-4 w-4" />
                    {showHistory ? "Hide" : "Show"} Grade History
                  </button>
                  
                  {showHistory && gradeHistory.length > 0 && (
                    <div className="mt-4 space-y-3">
                      {gradeHistory.map((record) => (
                        <div key={record.id} className="bg-white rounded-lg p-3 border border-slate-200">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              {record.grade_type === "ai" ? (
                                <Brain className="h-4 w-4 text-amber-600" />
                              ) : (
                                <GraduationCap className="h-4 w-4 text-emerald-600" />
                              )}
                              <span className="text-xs font-semibold text-slate-900 capitalize">
                                {record.grade_type}
                              </span>
                            </div>
                            <span className="text-lg font-bold text-slate-900">
                              {record.grade_value?.toFixed(1)}%
                            </span>
                          </div>
                          {record.created_at && (
                            <p className="text-xs text-slate-500">
                              {new Date(record.created_at).toLocaleString()}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
