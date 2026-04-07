"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { X, Save, RotateCcw, History, Clock, User, Brain, GraduationCap, MessageCircle, Target, BookOpen, ChevronLeft, ChevronRight, Sparkles, Settings } from "lucide-react"
import Link from "next/link"
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
  const RIGHT_PANEL_PCT = 33.34
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [regrading, setRegrading] = useState(false)
  const [submissionData, setSubmissionData] = useState<any>(null)
  const [gradeHistory, setGradeHistory] = useState<any[]>([])
  const [showHistory, setShowHistory] = useState(false)
  // Resizable left panel state
  const [leftPanelWidth, setLeftPanelWidth] = useState<number>(33.33)
  const [isResizing, setIsResizing] = useState<boolean>(false)
  // Scene navigation within left panel
  const [sceneIndex, setSceneIndex] = useState<number>(0)
  
  // Form state
  const [grade, setGrade] = useState("")
  const [feedback, setFeedback] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set())
  
  // Chat scroll ref
  const chatEndRef = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Drag handler refs (same approach as test-simulations)
  const dragStartX = useRef<number>(0)
  const dragStartWidth = useRef<number>(0)

  // Drag-to-resize handlers (replicated from test-simulations for smooth performance)
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const container = containerRef.current
    if (!container) return
    
    dragStartX.current = e.clientX
    dragStartWidth.current = leftPanelWidth
    setIsResizing(true)
  }

  // Add event listeners for mouse move and up
  useEffect(() => {
    if (!isResizing) return

    const handleMouseMove = (e: MouseEvent) => {
      const container = containerRef.current
      if (!container) return
      
      const rect = container.getBoundingClientRect()
      const containerWidth = rect.width
      const deltaX = e.clientX - dragStartX.current
      const deltaPercent = (deltaX / containerWidth) * 100
      const newLeftWidth = dragStartWidth.current + deltaPercent
      
      // Constrain between 0% and 50%
      const constrainedWidth = Math.min(Math.max(newLeftWidth, 0), 50)
      setLeftPanelWidth(constrainedWidth)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing])

  const fetchSubmissionData = useCallback(async () => {
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

      // Initialize scene index to first scene
      setSceneIndex(0)
    } catch (err: any) {
      setError(err.message || "Failed to load submission data")
      console.error("Error loading submission:", err)
    } finally {
      setLoading(false)
    }
  }, [instanceId])

  useEffect(() => {
    if (isOpen && instanceId) {
      fetchSubmissionData()
    }
  }, [isOpen, instanceId, fetchSubmissionData])

  useEffect(() => {
    // Auto-scroll chat to bottom when new data loads
    if (submissionData?.conversation_history && chatEndRef.current) {
      setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
      }, 100)
    }
  }, [submissionData])

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

  const handleRegradeWithAI = async () => {
    if (!submissionData?.user_progress_id) {
      setError("Unable to re-grade: missing user progress ID")
      return
    }

    try {
      setRegrading(true)
      setError(null)
      const result = await apiClient.regradeSimulation(submissionData.user_progress_id)
      if (result.success) {
        // Refresh the submission data to show new AI grade
        await fetchSubmissionData()
        onGraded()
      }
    } catch (err: any) {
      setError(err.message || "Failed to re-grade with AI")
      console.error("Error re-grading:", err)
    } finally {
      setRegrading(false)
    }
  }

  // Lookup persona image from all scenes
  const getPersonaImage = (personaName?: string, sceneId?: number) => {
    const name = (personaName || '').trim()
    if (!name) return undefined
    
    // First try to find in all_scenes if available
    if (submissionData?.all_scenes && submissionData.all_scenes.length > 0) {
      for (const scene of submissionData.all_scenes) {
        const persona = scene.personas?.find((p: Persona) => p.name === name)
        if (persona?.image_url) {
          const imageUrl = persona.image_url
          if (imageUrl && typeof imageUrl === 'string' && imageUrl.trim().length > 0) {
            return getImageUrl(imageUrl)
          }
        }
      }
    }
    
    // Fallback to current scene
    if (submissionData?.current_scene?.personas) {
      const persona = submissionData.current_scene.personas.find((p: Persona) => p.name === name)
      if (persona?.image_url) {
        const imageUrl = persona.image_url
        if (imageUrl && typeof imageUrl === 'string' && imageUrl.trim().length > 0) {
          return getImageUrl(imageUrl)
        }
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

  // Get persona bubble classes (same as student/professor simulation)
  const getPersonaBubbleClasses = (personaName?: string) => {
    // Expanded palette for better uniqueness - matches other pages
    const personaPalette = [
      'bg-rose-50 border-rose-200',
      'bg-amber-50 border-amber-200',
      'bg-emerald-50 border-emerald-200',
      'bg-sky-50 border-sky-200',
      'bg-violet-50 border-violet-200',
      'bg-fuchsia-50 border-fuchsia-200',
      'bg-lime-50 border-lime-200',
      'bg-cyan-50 border-cyan-200',
      'bg-teal-50 border-teal-200',
      'bg-indigo-50 border-indigo-200',
      'bg-pink-50 border-pink-200',
      'bg-orange-50 border-orange-200',
      'bg-yellow-50 border-yellow-200',
      'bg-purple-50 border-purple-200',
      'bg-blue-50 border-blue-200',
      'bg-green-50 border-green-200'
    ]
    
    const key = (personaName || '').trim()
    if (!key || key === 'All Personas' || key === 'ChatOrchestrator' || key === 'System') {
      return 'bg-gray-50 border-gray-200' // Default for system messages
    }
    
    // Improved hash function with normalization for consistency
    const normalized = key.toLowerCase().trim().replace(/\s+/g, ' ')
    let hash = 0
    for (let i = 0; i < normalized.length; i++) {
      hash = ((hash << 5) - hash) + normalized.charCodeAt(i)
      hash = hash & hash // Convert to 32-bit integer
    }
    return personaPalette[Math.abs(hash) % personaPalette.length]
  }

  if (!isOpen) return null

  // Map conversation history to match expected format
  const conversationHistory: ConversationMessage[] = (submissionData?.conversation_history || []).map((msg: any) => ({
    id: msg.id,
    type: msg.message_type || msg.type || 'system',
    sender: msg.sender_name || msg.sender || 'System',
    content: msg.message_content || msg.content || msg.text || '',
    timestamp: msg.timestamp,
    scene_id: msg.scene_id,
    persona_name: msg.persona_name,
    persona_role: msg.persona_role
  }))
  const currentScene = submissionData?.current_scene
  const simulation = submissionData?.simulation || submissionData?.scenario  // Support both for backward compatibility
  const allScenes = submissionData?.all_scenes || []
  const simulationScenes = (simulation?.scenes as any[]) || []
  const selectedFromAll = allScenes.length > 0 ? allScenes[sceneIndex] : null
  // Try to resolve the full scene from simulation.scenes using id or scene_order
  const resolvedSimulationScene = (() => {
    if (!selectedFromAll && !currentScene) return undefined
    const targetId = (selectedFromAll as any)?.id ?? (currentScene as any)?.id
    const targetOrder = (selectedFromAll as any)?.scene_order ?? (currentScene as any)?.scene_order
    let match = simulationScenes.find((s: any) => s?.id === targetId)
    if (!match && typeof targetOrder === 'number') {
      match = simulationScenes.find((s: any) => s?.scene_order === targetOrder)
    }
    return match
  })()
  const displaySceneRaw = resolvedSimulationScene || selectedFromAll || currentScene || {}
  // Use selected scene or current scene for display
  const displaySceneForPanel = selectedFromAll || currentScene || (allScenes.length > 0 ? allScenes[0] : null)
  // Normalize scene shape and keys - use displaySceneForPanel for the left panel
  const displayScene = displaySceneForPanel || displaySceneRaw || {}
  const displayTitle = (displayScene as any)?.title || (displayScene as any)?.name || (currentScene as any)?.title
  const displayDescription = (displayScene as any)?.description || (displayScene as any)?.scene_description || (currentScene as any)?.description
  const displayObjective = (displayScene as any)?.user_goal || (displayScene as any)?.objective || (displayScene as any)?.goal || (currentScene as any)?.user_goal || (currentScene as any)?.objective
  const rawImage = (displayScene as any)?.image_url || (displayScene as any)?.image || (displayScene as any)?.scene_image || (currentScene as any)?.image_url || (currentScene as any)?.image
  const displayImageUrl = typeof rawImage === 'string' ? rawImage : (rawImage && typeof rawImage === 'object' ? rawImage.url : undefined)

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 overflow-hidden">
      <div className="bg-white w-[98vw] h-[95vh] mx-2 my-2 rounded-2xl shadow-2xl flex flex-col overflow-hidden relative">
        {/* Atmospheric background layer */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage:
              'radial-gradient(1500px 600px at 20% -10%, rgba(16,185,129,0.35) 0%, rgba(16,185,129,0) 60%), radial-gradient(1200px 500px at 110% 110%, rgba(20,184,166,0.30) 0%, rgba(20,184,166,0) 60%), radial-gradient(800px 400px at -10% 110%, rgba(245,158,11,0.20) 0%, rgba(245,158,11,0) 60%)'
          }}
        />
        {/* Header */}
        <div className="bg-white/90 px-6 py-4 border-b border-gray-200/70 flex-shrink-0 backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={onClose}
                className="text-gray-600 hover:text-gray-900"
              >
                <X className="w-5 h-5" />
              </button>
              <h1 className="text-lg font-semibold text-gray-900 truncate">
                {simulation?.title || submissionData?.simulation_title || 'Review Submission'}
              </h1>
              {/* Removed student/scene indicator per request */}
            </div>
            {/* Removed progress bar per request */}
          </div>
        </div>

        {/* Main Content - Three Panel Layout */}
        <div className="flex flex-1 min-h-0 relative" ref={containerRef}>
          {/* Left Panel - Dark Theme Context (same as student simulation) */}
          {displaySceneForPanel && (
            <div 
              key={`left-panel-${sceneIndex}`}
              className={`sim-panel-gradient text-white flex flex-col min-h-0 ${isResizing ? 'transition-none' : 'transition-all duration-150 ease-in-out'} relative`}
              style={{ 
                width: `${leftPanelWidth}%`,
                willChange: isResizing ? 'width' : 'auto'
              }}
            >
              <div className={`${leftPanelWidth <= 0.5 ? 'opacity-0 pointer-events-none select-none' : 'opacity-100'} transition-opacity duration-150 h-full`}>
              <div className="flex flex-col h-full p-6" key={`left-scene-${sceneIndex}`}>
                {/* Scene navigation controls */}
                <div className="absolute top-3 right-3 flex items-center gap-2 z-20">
                  <button
                    aria-label="Previous scene"
                    onClick={() => setSceneIndex((prev) => (prev - 1 + allScenes.length) % Math.max(1, allScenes.length))}
                    className={`rounded-md border border-slate-700/60 bg-slate-800/80 text-white p-1.5 shadow-sm hover:bg-slate-700/80 transition`}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    aria-label="Next scene"
                    onClick={() => setSceneIndex((prev) => (prev + 1) % Math.max(1, allScenes.length))}
                    className={`rounded-md border border-slate-700/60 bg-slate-800/80 text-white p-1.5 shadow-sm hover:bg-slate-700/80 transition`}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
                {/* Scene Image */}
                {displayImageUrl && (
                  <div className="mb-4 relative -mx-6 -mt-6 flex-shrink-0 animate-fade-in-up" key={`scene-image-${sceneIndex}`}>
                    <img 
                      src={getImageUrl(displayImageUrl)} 
                      alt={displayTitle}
                      className="w-full h-56 object-cover"
                    />
                    <div className="scene-image-overlay absolute inset-0 pointer-events-none"></div>
                    <div className="absolute bottom-3 left-4 bg-black/80 backdrop-blur-sm text-white px-3 py-1.5 rounded text-sm font-medium" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                      {displayTitle || 'Scene'}
                    </div>
                  </div>
                )}

                {/* Content area */}
                <div className="flex-1 min-h-0 flex flex-col space-y-4 overflow-hidden">
                  {/* Scene Description */}
                  <div className="flex-shrink-0 animate-fade-in-up stagger-1" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                    <h3 className="text-base font-semibold mb-2 text-gradient-sim">Scene Description</h3>
                    <p className="text-gray-300 text-xs leading-relaxed">
                      {displayDescription || '—'}
                    </p>
                  </div>

                  {/* Objective */}
                  <div className="flex-shrink-0 animate-fade-in-up stagger-2">
                    <div className="bg-gradient-to-br from-emerald-600 to-emerald-700 rounded-lg p-3 border border-emerald-500/30 shadow-lg">
                      <div className="flex items-center gap-2 mb-1.5">
                        <Target className="w-3.5 h-3.5 text-white" />
                        <span className="font-semibold text-xs text-white uppercase tracking-wide" style={{ fontFamily: "'Sora', sans-serif" }}>OBJECTIVE</span>
                      </div>
                      <p className="text-xs text-white/95 leading-snug" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                        {displayObjective || 'Complete the interaction'}
                      </p>
                    </div>
                  </div>

                  {/* Available Personas */}
                  <div className="flex-1 min-h-0 flex flex-col animate-fade-in-up stagger-3">
                    <h3 className="text-sm font-semibold mb-2 text-gradient-sim flex-shrink-0" style={{ fontFamily: "'Sora', sans-serif" }}>
                        Available Personas ({displayScene?.personas?.length || 0})
                    </h3>
                    <div className="bg-gray-800/80 backdrop-blur-sm rounded-lg p-2 flex-1 min-h-0 overflow-y-auto space-y-1.5 scrollbar-thin border border-gray-700/30">
                        {displayScene?.personas && displayScene.personas.length > 0 ? (
                          displayScene.personas.map((persona: Persona, idx: number) => (
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
            </div>
          )}

          {/* Global Drag Handle at boundary (works even when left panel is 0%) */}
          {displaySceneForPanel && (
            <div
              onMouseDown={handleMouseDown}
              onDragStart={(e) => e.preventDefault()}
              className="absolute top-0 bottom-0 z-50 cursor-col-resize group"
              style={{
                left: `${leftPanelWidth}%`,
                transform: 'translateX(-50%)',
                width: '12px',
                background: 'rgba(156,163,175,0.25)'
              }}
            >
              {/* Center high-contrast indicator line */}
              <div
                className="absolute top-0 bottom-0 left-1/2 -translate-x-1/2 w-[2px] bg-gray-300 shadow-[0_0_0_1px_rgba(0,0,0,0.15),0_0_6px_rgba(0,0,0,0.15)] group-hover:bg-gray-400"
              />
              {/* Grip dots for affordance */}
              <div className="absolute top-1/2 -translate-y-1/2 left-1/2 -translate-x-1/2 flex flex-col gap-1 opacity-70 group-hover:opacity-100 transition-opacity">
                <span className="block w-1 h-1 rounded-full bg-gray-400"></span>
                <span className="block w-1 h-1 rounded-full bg-gray-400"></span>
                <span className="block w-1 h-1 rounded-full bg-gray-400"></span>
              </div>
              {/* Hover highlight to increase visibility */}
              <div className="absolute inset-0 rounded-sm group-hover:bg-gray-300/20 transition-colors duration-150" />

              {leftPanelWidth <= 0.5 && (
                <div className="absolute top-1/2 -translate-y-1/2 translate-x-3 bg-slate-900/95 border border-gray-700 rounded-md px-1.5 py-1 shadow-lg z-50">
                  <ChevronRight className="w-3 h-3 text-gray-100" />
                </div>
              )}
            </div>
          )}

          {/* Middle Panel - Conversation History */}
          <div 
            className={`sim-panel-right flex flex-col min-h-0 relative border-r border-gray-200/60 ${isResizing ? 'transition-none' : 'transition-all duration-150'} bg-white`} 
            style={{ 
              width: currentScene 
                ? `${Math.max(0, 100 - leftPanelWidth - RIGHT_PANEL_PCT)}%`
                : `${100 - RIGHT_PANEL_PCT}%`,
              willChange: isResizing ? 'width' : 'auto'
            }}
          >
            {/* Conversation Header */}
            <div className="relative z-10 border-b border-gray-200/70 bg-white/85 backdrop-blur-sm shadow-[0_1px_0_0_rgba(0,0,0,0.02)]">
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
                                  const imageKey = `${msg.persona_name || msg.sender}-${msg.scene_id || 'default'}`
                                  const hasFailed = failedImages.has(imageKey)
                                  
                                  if (personaImage && !hasFailed) {
                                    return (
                                      <img 
                                        src={personaImage} 
                                        alt={msg.persona_name || msg.sender} 
                                        className="object-cover w-full h-full rounded-full"
                                        onError={() => {
                                          setFailedImages(prev => new Set(prev).add(imageKey))
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
                            {(msg.content || '').split('\n').map((line, lineIdx) => {
                              const parts = line.split(/\*\*(.*?)\*\*/g)
                              return (
                                <div key={lineIdx}>
                                  {parts.map((part, partIdx) =>
                                    partIdx % 2 === 1 ? (
                                      <strong key={partIdx} className="font-semibold">
                                        {part}
                                      </strong>
                                    ) : (
                                      part
                                    )
                                  )}
                                </div>
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
            className={`flex flex-col min-h-0 bg-white ${isResizing ? 'transition-none' : 'transition-all duration-150'} shadow-[inset_1px_0_0_0_rgba(0,0,0,0.02)]`} 
            style={{ 
              width: currentScene 
                ? `${RIGHT_PANEL_PCT}%`
                : `${RIGHT_PANEL_PCT}%`,
              willChange: isResizing ? 'width' : 'auto'
            }}
          >
            {/* Grading Header */}
            <div className="border-b border-gray-200/70 bg-white/85 backdrop-blur-sm flex-shrink-0 shadow-[0_1px_0_0_rgba(0,0,0,0.02)]">
              <div className="px-6 py-3">
                <div className="flex items-center gap-2">
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

                {/* Removed AI Grade Reference per request */}

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

                {/* Re-grade with AI */}
                <div className="bg-gradient-to-br from-violet-50 to-purple-50/50 rounded-xl border border-violet-200/60 p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Sparkles className="h-4 w-4 text-violet-600" />
                    <span className="text-sm font-semibold text-violet-900" style={{ fontFamily: "'DM Sans', sans-serif" }}>
                      AI Grading
                    </span>
                  </div>
                  <p className="text-xs text-violet-700 mb-3">
                    Re-run the AI grading to get an updated assessment based on the latest grading logic.
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      onClick={handleRegradeWithAI}
                      disabled={regrading || submitting}
                      className="flex-1 border-violet-300 text-violet-700 hover:bg-violet-100 hover:text-violet-800"
                    >
                      <Brain className="h-4 w-4 mr-2" />
                      {regrading ? "Re-grading..." : "Re-grade with AI"}
                    </Button>
                    {simulation?.id && (
                      <Link href={`/professor/edit-grading?id=${simulation.id}&returnTo=${instanceId}`}>
                        <Button
                          variant="outline"
                          className="border-violet-300 text-violet-700 hover:bg-violet-100 hover:text-violet-800"
                          title="Edit grading criteria"
                        >
                          <Settings className="h-4 w-4" />
                        </Button>
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
