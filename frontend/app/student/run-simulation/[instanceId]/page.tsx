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
  AlertTriangle,
  HelpCircle,
  RefreshCw,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  User,
  Eye,
  Trophy,
  X,
  MessageCircle,
  Mic,
  Type,
  ChevronDown,
  ChevronUp,
  PlayCircle
} from "lucide-react"
import { ChatMessages } from '@/components/ChatMessages'
import { ChatInput } from '@/components/ChatInput'
import { buildApiUrl, apiClient } from "@/lib/api"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { getImageUrl } from "@/lib/image-utils"
import dynamic from 'next/dynamic'
import ResourcesPanel from '@/components/ResourcesPanel'

const CodeEditor = dynamic(() => import('@/components/CodeEditor'), { ssr: false })

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
  case_study_url?: string
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
  scene_type?: 'conversation' | 'code_challenge'
  starter_code?: string
  data_files?: Array<{ filename: string; description?: string; preview?: { headers: string[]; rows: string[][]; totalRows?: number; totalCols?: number } }>
  reference_files?: Array<{ filename: string; description?: string; url: string }>
}

interface SimulationData {
  user_progress_id: number
  simulation: Scenario  // Changed from 'scenario' to 'simulation' to match backend
  current_scene: Scene
  // Backend returns all_scenes with personas using Persona interface (same structure as current_scene.personas)
  all_scenes?: Array<{
    id: number
    title: string
    scene_order: number
    personas: Persona[]  // Backend returns Persona[] with image_url field
  }>
  simulation_status: string
  instance_id: number
  conversation_history?: Array<{
    id: number
    sender: string
    text: string
    timestamp: string
    type: string
    persona_id?: number
    persona_name?: string
    persona_role?: string
    scene_id?: number
  }>
  is_resuming?: boolean
  turn_count?: number
  completed_scene_ids?: number[]
  sandbox_id?: string
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
          <div className="bg-gradient-to-br from-emerald-600 to-emerald-700 rounded-lg p-3 mb-3 border border-emerald-500/30 shadow-lg">
            <div className="flex items-center gap-2 mb-1.5">
              <Target className="w-3.5 h-3.5 text-white" />
              <p className="text-xs font-semibold text-white uppercase tracking-wide" style={{ fontFamily: "'Sora', sans-serif" }}>OBJECTIVE</p>
            </div>
            <p className="text-xs text-white/95 leading-snug" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{scene.user_goal}</p>
          </div>
        )}
        
        <div className="bg-gradient-to-br from-amber-50 via-yellow-50 to-amber-50 border border-amber-200/60 rounded-xl p-5 shadow-sm mb-3">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center">
              <Clock className="w-5 h-5 text-amber-700" />
            </div>
            <span className="font-semibold text-amber-900">Timeout Turns</span>
          </div>
          <p className="text-sm text-amber-800 mb-3">
            {typeof scene.timeout_turns === 'number' ? (
              <>
                You have used <span className="font-semibold">{turnCount}</span> out of <span className="font-semibold">{scene.timeout_turns}</span> available turns in this scene.
              </>
            ) : (
              'Not set'
            )}
          </p>
          {typeof scene.timeout_turns === 'number' && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-xs text-amber-700 mb-1">
                <span>Turns Remaining: {Math.max(0, scene.timeout_turns - turnCount)}</span>
                <span>{Math.round((turnCount / scene.timeout_turns) * 100)}% Used</span>
              </div>
              <div className="w-full h-2 bg-amber-200/50 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-gradient-to-r from-amber-400 to-amber-500 rounded-full transition-all duration-300"
                  style={{ width: `${Math.min((turnCount / scene.timeout_turns) * 100, 100)}%` }}
                ></div>
              </div>
            </div>
          )}
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
const TypingIndicator = ({ personaName, isInterfaceGreyed }: { personaName: string, isInterfaceGreyed: boolean }) => {
  // Special handling for "All Personas" to show "All personas responding..."
  const displayText = personaName === "All Personas" ? "All personas responding..." : `${personaName} is responding...`
  
  return (
    <div className={`flex justify-start mb-4 transition-all duration-300 ${isInterfaceGreyed ? 'opacity-100' : 'opacity-75'}`}>
      <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex space-x-1">
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"></div>
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
          </div>
          <span className="text-sm font-medium text-blue-700">{displayText}</span>
        </div>
      </div>
    </div>
  )
}

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
              {persona.image_url && persona.image_url.trim() ? (
                <img 
                  src={getImageUrl(persona.image_url)} 
                  alt={persona.name} 
                  className="object-cover w-full h-full"
                  onError={(e) => {
                    console.error(`[PERSONA_MODAL] Failed to load image for ${persona.name}:`, persona.image_url);
                    e.currentTarget.style.display = 'none';
                  }}
                />
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

// Grading Text Parser - handles unformatted grading text
const parseGradingText = (text: string) => {
  if (!text) return null
  
  const result: any = {
    overallScore: null,
    maxScore: null,
    scoreBreakdown: [],
    overallAssessment: {
      summary: null,
      keyStrengths: null,
      improvements: null
    },
    feedback: {
      recommendations: null,
      businessAcumen: null,
      reference: null
    }
  }
  
  // Extract overall score - multiple patterns
  const overallScoreMatch = text.match(/\*\*OVERALL SCORE:\*\*\s*(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)\s*points?/i)
  if (overallScoreMatch) {
    result.overallScore = parseFloat(overallScoreMatch[1])
    result.maxScore = parseFloat(overallScoreMatch[2])
  }
  
  // Extract score breakdown
  const breakdownMatch = text.match(/\*\*SCORE BREAKDOWN:\*\*([\s\S]*?)(?=\*\*OVERALL ASSESSMENT:\*\*|\*\*FEEDBACK:\*\*|$)/i)
  if (breakdownMatch) {
    const breakdownText = breakdownMatch[1]
    
    // Pattern 1: Numbered format with full details
    const numberedPattern = /(\d+)\.\s*\*\*([^*]+)\*\*\s*-\s*Score:\s*(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)\s*points?\s*-\s*Performance\s*level:\s*([^-\n]+(?:\n(?!\d+\.))?)\s*-\s*(?:Brief\s*)?reasoning:\s*([^-\n]+(?:\n(?!\d+\.))?)/gi
    let match
    while ((match = numberedPattern.exec(breakdownText)) !== null) {
      result.scoreBreakdown.push({
        criterion: match[2].trim(),
        score: parseFloat(match[3]),
        maxScore: parseFloat(match[4]),
        performanceLevel: match[5].trim(),
        reasoning: match[6].trim()
      })
    }
    
    // Pattern 2: Bullet format
    if (result.scoreBreakdown.length === 0) {
      const bulletPattern = /[-•]\s*\*\*([^*]+)\*\*\s*-\s*Score:\s*(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)\s*points?\s*-\s*Performance\s*level:\s*([^-\n]+)\s*-\s*(?:Brief\s*)?reasoning:\s*([^-\n]+(?:\n(?![-•]))?)/gi
      while ((match = bulletPattern.exec(breakdownText)) !== null) {
        result.scoreBreakdown.push({
          criterion: match[1].trim(),
          score: parseFloat(match[2]),
          maxScore: parseFloat(match[3]),
          performanceLevel: match[4].trim(),
          reasoning: match[5].trim()
        })
      }
    }
  }
  
  // Extract overall assessment
  const assessmentMatch = text.match(/\*\*OVERALL ASSESSMENT:\*\*([\s\S]*?)(?=\*\*FEEDBACK:\*\*|$)/i)
  if (assessmentMatch) {
    const assessmentText = assessmentMatch[1]
    
    const summaryMatch = assessmentText.match(/-?\s*\*\*Summary\s*of\s*performance[^:]*:\*\*\s*([\s\S]*?)(?=\*\*Key\s*strengths|\*\*Main\s*areas|$)/i)
    if (summaryMatch) {
      result.overallAssessment.summary = summaryMatch[1].trim()
    }

    const strengthsMatch = assessmentText.match(/-?\s*\*\*Key\s*strengths[^:]*:\*\*\s*([\s\S]*?)(?=\*\*Main\s*areas|\*\*FEEDBACK|$)/i)
    if (strengthsMatch) {
      result.overallAssessment.keyStrengths = strengthsMatch[1].trim()
    }

    const improvementsMatch = assessmentText.match(/-?\s*\*\*Main\s*areas\s*for\s*improvement[^:]*:\*\*\s*([\s\S]*?)(?=\*\*FEEDBACK|\*\*Specific|$)/i)
    if (improvementsMatch) {
      result.overallAssessment.improvements = improvementsMatch[1].trim()
    }
    
    // Alternative format without bold markers
    if (!result.overallAssessment.summary) {
      const altSummary = assessmentText.match(/-?\s*The\s+response\s+is[^.\n]+\./i)
      if (altSummary) {
        result.overallAssessment.summary = altSummary[0].trim()
      }
    }
  }
  
  // Extract feedback section
  const feedbackMatch = text.match(/\*\*FEEDBACK:\*\*([\s\S]*?)$/i)
  if (feedbackMatch) {
    const feedbackText = feedbackMatch[1]
    
    // Recommendations - handle both list and paragraph formats
    const recommendationsMatch = feedbackText.match(/-?\s*\*\*Specific\s*actionable\s*recommendations:\*\*\s*([\s\S]*?)(?=\*\*Business\s*(?:acumen|context)|\*\*Reference\s*to|$)/i)
    if (recommendationsMatch) {
      const recText = recommendationsMatch[1].trim()
      // Check if it's a numbered list format (1. ... 2. ... 3. ...)
      if (/\d+\.\s/.test(recText)) {
        result.feedback.recommendations = recText.split(/\d+\.\s+/).filter(Boolean).map((r: string) => r.trim())
      } else if (recText.includes('\n-') || recText.includes('\n•')) {
        result.feedback.recommendations = recText.split(/\n[-•]\s*/).filter(Boolean).map((r: string) => r.trim())
      } else {
        result.feedback.recommendations = recText.split(/\.\s+/).filter(Boolean).map((r: string) => r.trim())
      }
    }
    
    const acumenMatch = feedbackText.match(/-?\s*\*\*Business\s*(?:acumen\s*development\s*insights|context\s*insights):\*\*\s*([^-\n]+(?:\n(?!-?\s*\*\*))?)/i)
    if (acumenMatch) {
      result.feedback.businessAcumen = acumenMatch[1].trim()
    }
    
    const referenceMatch = feedbackText.match(/-?\s*\*\*Reference\s*to\s*grading\s*materials\s*used:\*\*\s*([^-\n]+(?:\n|$))/i)
    if (referenceMatch) {
      result.feedback.reference = referenceMatch[1].trim()
    }
  }
  
  return result
}

// Filter out "begin" from user responses
const filterBeginFromResponses = (responses: any[]) => {
  if (!responses || !Array.isArray(responses)) return []
  return responses.filter((r: any) => {
    const content = typeof r === 'string' ? r : r.content || r.text || ''
    return content.toLowerCase().trim() !== 'begin'
  })
}

// Parse scene-level grading feedback text
const parseSceneFeedback = (text: string) => {
  if (!text || typeof text !== 'string') return null
  
  const result: any = {
    scoreBreakdown: [],
    overallAssessment: {
      summary: null,
      keyStrengths: null,
      improvements: null,
      assessmentFields: [] // Store individual assessment fields separately
    },
    feedback: {
      recommendations: null,
      businessInsights: null,
      reference: null
    }
  }
  
  // Extract score breakdown
  const breakdownMatch = text.match(/\*\*SCORE BREAKDOWN:\*\*([\s\S]*?)(?=\*\*OVERALL ASSESSMENT:\*\*|$)/i)
  if (breakdownMatch) {
    const breakdownText = breakdownMatch[1]
    
    // Pattern: Numbered format - "1. **Criterion** - Score: X/Y points - Performance level: X - Brief reasoning: X"
    const numberedPattern = /(\d+)\.\s*\*\*([^*]+)\*\*\s*-\s*Score:\s*(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)\s*points?\s*-\s*Performance\s*level:\s*([^-\n]+)\s*-\s*(?:Brief\s*)?reasoning:\s*([^-\n]+(?:\n(?!\d+\.))?)/gi
    let match
    while ((match = numberedPattern.exec(breakdownText)) !== null) {
      result.scoreBreakdown.push({
        criterion: match[2].trim(),
        score: parseFloat(match[3]),
        maxScore: parseFloat(match[4]),
        performanceLevel: match[5].trim(),
        reasoning: match[6].trim()
      })
    }
  }
  
  // Extract overall assessment
  const assessmentMatch = text.match(/\*\*OVERALL ASSESSMENT:\*\*([\s\S]*?)(?=\*\*FEEDBACK:\*\*|$)/i)
  if (assessmentMatch) {
    const assessmentText = assessmentMatch[1]
    
    // Extract summary - look for "Summary of Performance:" or general description
    const summaryMatch = assessmentText.match(/\*\*Summary\s+of\s+Performance:\*\*\s*([^\n]+(?:\n(?!\*\*))?)/i)
    if (summaryMatch) {
      result.overallAssessment.summary = summaryMatch[1].trim().replace(/\*\*/g, '')
    }
    
    // Extract all individual assessment fields (like **Business Thinking Quality:**, **Recognition:**, etc.)
    // Handle format like: **Business Thinking Quality:** ... **Recognition:** ...
    const fieldMatches = assessmentText.matchAll(/\*\*([^:]+):\*\*\s*([^\n]+(?:\n(?!\*\*[^:]))?)/gi)
    for (const match of fieldMatches) {
      const fieldName = match[1].trim()
      const fieldValue = match[2].trim().replace(/\*\*/g, '')
      const fieldNameLower = fieldName.toLowerCase()
      
      // Skip if it's a section header we handle separately
      if (fieldNameLower.includes('summary of performance')) {
        continue
      }
      // Skip strengths (will be handled by strengthsMatch below)
      if (fieldNameLower.includes('strength')) {
        continue
      }
      // Skip improvements (will be handled by improvementsMatch below)
      if (fieldNameLower.includes('improvement') || fieldNameLower.includes('area for') || fieldNameLower.includes('areas for')) {
        continue
      }
      
      // Store as individual assessment field
      if (fieldValue) {
        result.overallAssessment.assessmentFields.push({
          field: fieldName,
          value: fieldValue
        })
      }
    }
    
    // If no explicit summary and no fields, extract general assessment text as fallback
    if (!result.overallAssessment.summary && result.overallAssessment.assessmentFields.length === 0) {
      const lines = assessmentText.split('\n').map(line => line.trim()).filter(line => line && !line.match(/^\*\*[A-Z]/))
      const generalLines: string[] = []
      let foundStrengths2 = false
      let foundImprovements2 = false
      
      for (const line of lines) {
        if (line.match(/^\*\*(?:Key\s*)?strengths?/i) || line.match(/^-\s*(?:Key\s*)?strengths?:/i)) {
          foundStrengths2 = true
          continue
        }
        if (line.match(/^\*\*Main\s*areas\s*for\s*improvement/i) || line.match(/^-\s*Main\s*areas\s*for\s*improvement:/i)) {
          foundImprovements2 = true
          continue
        }
        if (!foundStrengths2 && !foundImprovements2 && line.length > 10) {
          const cleaned = line.replace(/^-\s*/, '').replace(/\*\*/g, '').trim()
          if (cleaned && !cleaned.match(/^[A-Z][^:]*:\s*$/)) { // Skip header-only lines
            generalLines.push(cleaned)
          }
        }
      }
      
      if (generalLines.length > 0) {
        result.overallAssessment.summary = generalLines.join(' ')
      }
    }
    
    // Extract key strengths - handle both **Key Strengths:** and - Key strengths: formats
    // Also handle **Key Strengths Demonstrated:**
    const strengthsMatch = assessmentText.match(/\*\*(?:Key\s*)?strengths?\s*(?:demonstrated|shown)?:\*\*\s*([^\n]+(?:\n(?!\*\*Main|\*\*FEEDBACK|\*\*[A-Z]))?)/i) ||
                           assessmentText.match(/-?\s*(?:Key\s*)?strengths?\s*(?:demonstrated|shown)?:\s*([^-\n]+(?:\n(?!-?\s*(?:Main|\*\*FEEDBACK)))?)/i)
    if (strengthsMatch) {
      const strengthsText = strengthsMatch[1].trim().replace(/\*\*/g, '').replace(/^\s*[-•]\s*/gm, '')
      // Check if it says "None identified" or similar
      if (strengthsText.toLowerCase().includes('none') || 
          strengthsText.toLowerCase().includes('no') ||
          strengthsText.toLowerCase().includes('lack') ||
          strengthsText.toLowerCase().includes('not applicable')) {
        result.overallAssessment.keyStrengths = null
      } else {
        result.overallAssessment.keyStrengths = strengthsText
      }
    }
    
    // Extract main areas for improvement - handle both **Main Areas for Improvement:** and - Main areas: formats
    const improvementsMatch = assessmentText.match(/\*\*Main\s+areas\s+for\s+improvement:\*\*\s*([^\n]+(?:\n(?!\*\*FEEDBACK|\*\*[A-Z]))?)/i) ||
                               assessmentText.match(/-?\s*Main\s+areas\s+for\s+improvement:\s*([^-\n]+(?:\n(?!\*\*FEEDBACK))?)/i)
    if (improvementsMatch) {
      result.overallAssessment.improvements = improvementsMatch[1].trim().replace(/\*\*/g, '').replace(/^\s*[-•]\s*/gm, '')
    }
  }
  
  // Extract feedback section
  const feedbackMatch = text.match(/\*\*FEEDBACK:\*\*([\s\S]*?)$/i)
  if (feedbackMatch) {
      const feedbackText = feedbackMatch[1]
      
      // Extract specific actionable recommendations - handle both **Actionable Recommendations:** and - Specific actionable: formats
      const recommendationsMatch = feedbackText.match(/\*\*Actionable\s+Recommendations:\*\*\s*([^\n]+(?:\n(?!\*\*Business|\*\*Reference))?)/i) ||
                                   feedbackText.match(/-?\s*Specific\s*actionable\s*recommendations?:\s*([^-\n]+(?:\n(?!-?\s*(?:Business|Reference)))?)/i)
      if (recommendationsMatch) {
        result.feedback.recommendations = recommendationsMatch[1].trim().replace(/\*\*/g, '').replace(/^\s*[-•]\s*/gm, '')
      }
      
      // Extract business context insights - handle both **Business Context Insights:** and - Business context: formats
      const insightsMatch = feedbackText.match(/\*\*Business\s+Context\s+Insights:\*\*\s*([^\n]+(?:\n(?!\*\*Reference))?)/i) ||
                            feedbackText.match(/-?\s*Business\s*context\s*insights?:\s*([^-\n]+(?:\n(?!-?\s*Reference))?)/i)
      if (insightsMatch) {
        result.feedback.businessInsights = insightsMatch[1].trim().replace(/\*\*/g, '').replace(/^\s*[-•]\s*/gm, '')
      }
      
      // Extract reference to grading materials - handle both **Reference:** and - Reference: formats
      const referenceMatch = feedbackText.match(/\*\*Reference:\*\*\s*([^\n]+)/i) ||
                             feedbackText.match(/-?\s*Reference\s*(?:to\s+grading\s+materials\s+used)?:\s*([^-\n]+(?:\n|$))/i)
      if (referenceMatch) {
        result.feedback.reference = referenceMatch[1].trim().replace(/\*\*/g, '').replace(/^\s*[-•]\s*/gm, '')
      }
    }
  
  return result
}

// Helper function to clean markdown formatting from text
const cleanMarkdown = (text: string | null | undefined): string => {
  if (!text) return ''
  return text
    .replace(/\*\*/g, '') // Remove bold markdown
    .replace(/#{1,6}\s*/g, '') // Remove headers
    .replace(/^\s*[-•]\s*/gm, '') // Remove list markers at start of lines
    .replace(/\n{3,}/g, '\n\n') // Normalize multiple newlines
    .trim()
}

// Render markdown text as HTML (bold, lists, line breaks)
const renderMarkdownHtml = (text: string): string => {
  if (!text) return ''
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/^\s*(\d+)\.\s+/gm, '<br/>$1. ')
    .replace(/\n/g, '<br/>')
}

// Professional Grading Tab Component
const GradingTabView = ({ gradingData }: { gradingData: any }) => {
  // Get rubric_total_points from grading data, default to 100
  const rubricTotalPoints = gradingData.rubric_total_points || 100
  
  // Parse raw feedback text if needed
  const rawFeedback = gradingData.overall_feedback
  const parsedData = rawFeedback && typeof rawFeedback === 'string' && /\*\*(overall score|overall assessment|score breakdown|feedback):\*\*/i.test(rawFeedback)
    ? parseGradingText(rawFeedback)
    : null
  
  // Calculate overall score - use backend score if available, otherwise parsed score
  // Scale parsed score if it's out of a different max (e.g., 100 vs 75)
  let overallScore = gradingData.overall_score || parsedData?.overallScore || 0
  const parsedMaxScore = parsedData?.maxScore
  
  // If we have a parsed score that's out of a different max, scale it to rubricTotalPoints
  if (parsedMaxScore && parsedMaxScore !== rubricTotalPoints && overallScore > 0) {
    overallScore = (overallScore / parsedMaxScore) * rubricTotalPoints
  }
  
  // Always use rubricTotalPoints as the max score
  const maxScore = rubricTotalPoints
  const scorePercentage = (overallScore / maxScore) * 100
  
  // Get score color
  const getScoreColor = (score: number, max: number) => {
    const pct = (score / max) * 100
    if (pct >= 80) return 'text-emerald-600 bg-emerald-50 border-emerald-200'
    if (pct >= 60) return 'text-blue-600 bg-blue-50 border-blue-200'
    if (pct >= 40) return 'text-amber-600 bg-amber-50 border-amber-200'
    return 'text-red-600 bg-red-50 border-red-200'
  }
  
  const getScoreBorderColor = (score: number, max: number) => {
    const pct = (score / max) * 100
    if (pct >= 80) return 'border-l-emerald-500'
    if (pct >= 60) return 'border-l-blue-500'
    if (pct >= 40) return 'border-l-amber-500'
    return 'border-l-red-500'
  }
  
  return (
    <div className="flex-1 overflow-y-auto bg-gradient-to-br from-slate-50 via-white to-slate-50">
      <div className="max-w-6xl mx-auto py-6 px-6">
        {/* Header Section */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-2">
            <h2 className="text-3xl font-bold text-slate-900" style={{ fontFamily: "'Sora', sans-serif" }}>
              Simulation Grading & Feedback
            </h2>
          </div>
          <p className="text-slate-600 text-sm">Comprehensive assessment of performance</p>
        </div>
        
        {/* Overall Score Card */}
        <div className={`mb-6 rounded-2xl p-8 border-2 text-blue-600 bg-blue-50 border-blue-200 shadow-lg`}>
          <div className="space-y-4">
            <div>
              <div className="text-sm font-semibold uppercase tracking-wider text-slate-700 mb-2" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                Overall Performance
              </div>
              <div className="text-5xl font-bold mb-1" style={{ fontFamily: "'Sora', sans-serif" }}>
                {Math.round(overallScore)}<span className="text-2xl text-slate-500">/{Math.round(maxScore)}</span>
              </div>
            </div>
            <div className="flex-1">
              {gradingData.overall_feedback && !parsedData && (
                <div className="text-slate-700 leading-relaxed text-sm" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdownHtml(typeof gradingData.overall_feedback === 'string' ? gradingData.overall_feedback : '') }}
                />
              )}
              {parsedData?.overallAssessment?.summary && (
                <div className="text-slate-700 leading-relaxed text-sm" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdownHtml(parsedData.overallAssessment.summary) }}
                />
              )}
            </div>
          </div>
        </div>
        
        {/* Score Breakdown */}
        {(parsedData?.scoreBreakdown?.length > 0 || gradingData.score_breakdown) && (
          <div className="mb-6">
            <h2 className="text-xl font-bold text-slate-900 mb-4" style={{ fontFamily: "'Sora', sans-serif" }}>
              Score Breakdown
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {(parsedData?.scoreBreakdown || gradingData.score_breakdown || []).map((item: any, idx: number) => {
                const criterion = item.criterion || item.name || 'Assessment Criterion'
                let score = item.score || 0
                const itemMax = item.maxScore || item.max_score
                
                // Scale score if it's out of a different max than the total
                // For individual criteria, we need to calculate their proportional share
                // If the parsed max doesn't match rubricTotalPoints, scale the score proportionally
                if (itemMax && itemMax !== rubricTotalPoints && score > 0) {
                  // Calculate what percentage of the total this criterion represents
                  // Then scale that percentage to rubricTotalPoints
                  const itemPercentage = score / itemMax
                  // Assume criteria are evenly distributed or proportional to their max scores
                  // For now, scale directly based on ratio
                  score = (score / itemMax) * (rubricTotalPoints / (parsedData?.scoreBreakdown?.length || gradingData.score_breakdown?.length || 6))
                }
                
                // For display, use proportional max (assuming equal distribution)
                const max = itemMax && itemMax !== rubricTotalPoints 
                  ? (rubricTotalPoints / (parsedData?.scoreBreakdown?.length || gradingData.score_breakdown?.length || 6))
                  : (itemMax || rubricTotalPoints)
                const performanceLevel = item.performanceLevel || item.performance_level || 'Not Assessed'
                const reasoning = item.reasoning || item.feedback || ''
                
                return (
                  <div key={idx} className={`bg-white rounded-xl p-5 border-l-4 ${getScoreBorderColor(score, max)} border shadow-sm hover:shadow-md transition-shadow`}>
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="font-semibold text-slate-900 text-sm" style={{ fontFamily: "'Sora', sans-serif" }}>
                        {criterion}
                      </h3>
                      <div className={`text-lg font-bold ml-2 ${getScoreColor(score, max).split(' ')[0]}`} style={{ fontFamily: "'Sora', sans-serif" }}>
                        {Math.round(score)}/{typeof max === 'number' ? Math.round(max) : max}
                      </div>
                    </div>
                    <div className="text-xs text-slate-500 mb-2 uppercase tracking-wide" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                      {performanceLevel}
                    </div>
                    {reasoning && (
                      <p className="text-sm text-slate-700 leading-relaxed mt-2" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                        {cleanMarkdown(reasoning)}
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
        
        {/* Strengths and Improvements */}
        {(parsedData?.overallAssessment?.keyStrengths || 
          gradingData.key_strengths?.length > 0 ||
          parsedData?.overallAssessment?.improvements ||
          gradingData.development_areas?.length > 0) && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            {/* Key Strengths */}
            {(parsedData?.overallAssessment?.keyStrengths || gradingData.key_strengths?.length > 0) && (
              <div className="bg-gradient-to-br from-emerald-50 to-emerald-100/50 rounded-xl p-6 border border-emerald-200 shadow-sm">
                <h3 className="text-lg font-bold text-emerald-900 mb-3 flex items-center gap-2" style={{ fontFamily: "'Sora', sans-serif" }}>
                  <CheckCircle className="w-5 h-5" />
                  Key Strengths
                </h3>
                {parsedData?.overallAssessment?.keyStrengths ? (
                  <p className="text-sm text-emerald-800 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                    {parsedData.overallAssessment.keyStrengths}
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {gradingData.key_strengths.map((strength: string, idx: number) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-emerald-800">
                        <span className="text-emerald-600 mt-1">•</span>
                        <span style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{strength}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            
            {/* Areas for Improvement */}
            {(parsedData?.overallAssessment?.improvements || gradingData.development_areas?.length > 0) && (
              <div className="bg-gradient-to-br from-amber-50 to-amber-100/50 rounded-xl p-6 border border-amber-200 shadow-sm">
                <h3 className="text-lg font-bold text-amber-900 mb-3 flex items-center gap-2" style={{ fontFamily: "'Sora', sans-serif" }}>
                  <AlertCircle className="w-5 h-5" />
                  Areas for Development
                </h3>
                {parsedData?.overallAssessment?.improvements ? (
                  <p className="text-sm text-amber-800 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                    {parsedData.overallAssessment.improvements}
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {gradingData.development_areas.map((area: string, idx: number) => (
                      <li key={idx} className="flex items-start gap-2 text-sm text-amber-800">
                        <span className="text-amber-600 mt-1">•</span>
                        <span style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{area}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* Actionable Recommendations - Only show this */}
        {(parsedData?.feedback?.recommendations || gradingData.recommendations?.length > 0) && (
          <div className="mb-6 bg-white rounded-xl p-6 border border-slate-200 shadow-sm">
            <h2 className="text-xl font-bold text-slate-900 mb-4" style={{ fontFamily: "'Sora', sans-serif" }}>
              Actionable Recommendations
            </h2>
            
            {parsedData?.feedback?.recommendations && (
              <div>
                {Array.isArray(parsedData.feedback.recommendations) ? (
                  <ul className="space-y-3">
                    {parsedData.feedback.recommendations.map((rec: string, idx: number) => (
                      <li key={idx} className="flex items-start gap-3 text-sm text-slate-700">
                        <span className="text-blue-600 mt-0.5 font-bold">•</span>
                        <span className="flex-1 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{cleanMarkdown(rec)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-700 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                    {cleanMarkdown(parsedData.feedback.recommendations)}
                  </p>
                )}
              </div>
            )}
            
            {gradingData.recommendations?.length > 0 && !parsedData?.feedback?.recommendations && (
              <ul className="space-y-3">
                {gradingData.recommendations.map((rec: string, idx: number) => (
                  <li key={idx} className="flex items-start gap-3 text-sm text-slate-700">
                    <span className="text-blue-600 mt-0.5 font-bold">•</span>
                    <span className="flex-1 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{rec}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        
        {/* Scene-by-Scene Analysis */}
        {gradingData.scenes && gradingData.scenes.length > 0 && (
          <div className="mb-6">
            <h2 className="text-xl font-bold text-slate-900 mb-4" style={{ fontFamily: "'Sora', sans-serif" }}>
              Scene-by-Scene Analysis
            </h2>
            <div className="space-y-4">
              {gradingData.scenes.map((scene: any, idx: number) => {
                const filteredResponses = filterBeginFromResponses(scene.user_responses || [])
                const sceneScore = scene.score || 0
                
                // Parse scene feedback if it's unformatted text
                const sceneFeedbackText = scene.feedback || ''
                const parsedSceneFeedback = sceneFeedbackText.includes('**SCORE BREAKDOWN:**')
                  ? parseSceneFeedback(sceneFeedbackText)
                  : null
                
                // Scale scene score if needed - scenes might come out of 100 but should be out of rubricTotalPoints
                let scaledSceneScore = sceneScore
                // If scene score is out of 100 but rubricTotalPoints is different, scale it
                if (sceneScore > 0 && rubricTotalPoints !== 100) {
                  // Check if scene score appears to be out of 100 (common case)
                  if (sceneScore <= 100) {
                    scaledSceneScore = (sceneScore / 100) * rubricTotalPoints
                  }
                }
                
                // Use rubric_total_points for scene score display
                const sceneMaxScore = rubricTotalPoints
                
                // Use scaled score for display
                const displayScore = scaledSceneScore
                
                return (
                  <div key={scene.id || idx} className="bg-white rounded-xl p-6 border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
                    {/* Header */}
                    <div className="flex items-start justify-between mb-4 pb-4 border-b border-slate-200">
                      <div className="flex-1">
                        <h3 className="text-lg font-bold text-slate-900 mb-1" style={{ fontFamily: "'Sora', sans-serif" }}>
                          {scene.title || `Scene ${idx + 1}`}
                        </h3>
                        {scene.objective && (
                          <p className="text-sm text-slate-600" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                            {scene.objective}
                          </p>
                        )}
                      </div>
                      <div className={`text-2xl font-bold ml-4 ${getScoreColor(displayScore, sceneMaxScore).split(' ')[0]}`} style={{ fontFamily: "'Sora', sans-serif" }}>
                        {Math.round(displayScore)}/{Math.round(sceneMaxScore)}
                      </div>
                    </div>
                    
                    {/* Your Responses Section */}
                    {filteredResponses.length > 0 && (
                      <div className="mb-5 bg-slate-50 rounded-lg p-4 border border-slate-200">
                        <div className="text-xs font-semibold text-slate-700 mb-2 uppercase tracking-wide" style={{ fontFamily: "'Sora', sans-serif" }}>
                          Your Responses
                        </div>
                        <div className="space-y-2 max-h-32 overflow-y-auto">
                          {filteredResponses.map((msg: any, msgIdx: number) => {
                            const content = typeof msg === 'string' ? msg : msg.content || msg.text || ''
                            const cleanContent = cleanMarkdown(content)
                            if (!cleanContent) return null
                            return (
                              <div key={msgIdx} className="text-xs text-slate-700 flex gap-2 bg-white rounded px-2 py-1.5 border border-slate-200">
                                <span className="text-slate-400 font-medium flex-shrink-0">{msgIdx + 1}.</span>
                                <span className="flex-1" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{cleanContent}</span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}
                    
                    {/* Overall Assessment */}
                    {(parsedSceneFeedback?.overallAssessment?.keyStrengths ||
                      parsedSceneFeedback?.overallAssessment?.improvements ||
                      scene.strengths?.length > 0 ||
                      scene.improvements?.length > 0) && (
                      <div className="mb-5">
                        <h4 className="text-sm font-bold text-slate-900 mb-3 uppercase tracking-wide" style={{ fontFamily: "'Sora', sans-serif" }}>
                          Overall Assessment
                        </h4>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {/* Key Strengths */}
                          {(parsedSceneFeedback?.overallAssessment?.keyStrengths !== null || scene.strengths?.length > 0) && (
                            <div className="bg-emerald-50 rounded-lg p-3 border border-emerald-200">
                              <h5 className="text-xs font-semibold text-emerald-900 mb-2 uppercase tracking-wide flex items-center gap-1.5" style={{ fontFamily: "'Sora', sans-serif" }}>
                                <CheckCircle className="w-3.5 h-3.5" />
                                Key Strengths
                              </h5>
                              {parsedSceneFeedback?.overallAssessment?.keyStrengths ? (
                                <p className="text-xs text-emerald-800 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                                  {cleanMarkdown(parsedSceneFeedback.overallAssessment.keyStrengths)}
                                </p>
                              ) : scene.strengths?.length > 0 ? (
                                <ul className="space-y-1">
                                  {scene.strengths.map((strength: string, strengthIdx: number) => (
                                    <li key={strengthIdx} className="text-xs text-emerald-800 flex items-start gap-1.5">
                                      <span className="text-emerald-600 mt-0.5">•</span>
                                      <span style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{strength}</span>
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="text-xs text-emerald-700 italic" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                                  None identified
                                </p>
                              )}
                            </div>
                          )}
                          
                          {/* Areas for Improvement */}
                          {(parsedSceneFeedback?.overallAssessment?.improvements || scene.improvements?.length > 0) && (
                            <div className="bg-amber-50 rounded-lg p-3 border border-amber-200">
                              <h5 className="text-xs font-semibold text-amber-900 mb-2 uppercase tracking-wide flex items-center gap-1.5" style={{ fontFamily: "'Sora', sans-serif" }}>
                                <AlertCircle className="w-3.5 h-3.5" />
                                Areas for Improvement
                              </h5>
                              {parsedSceneFeedback?.overallAssessment?.improvements ? (
                                <p className="text-xs text-amber-800 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                                  {cleanMarkdown(parsedSceneFeedback.overallAssessment.improvements)}
                                </p>
                              ) : (
                                <ul className="space-y-1">
                                  {scene.improvements.map((improvement: string, impIdx: number) => (
                                    <li key={impIdx} className="text-xs text-amber-800 flex items-start gap-1.5">
                                      <span className="text-amber-600 mt-0.5">•</span>
                                      <span style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>{improvement}</span>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                    
                    {/* Actionable Recommendations - Only show this */}
                    {parsedSceneFeedback?.feedback?.recommendations && (
                      <div className="border-t border-slate-200 pt-4">
                        <h4 className="text-sm font-bold text-slate-900 mb-3 uppercase tracking-wide" style={{ fontFamily: "'Sora', sans-serif" }}>
                          Actionable Recommendations
                        </h4>
                        <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
                          <p className="text-xs text-slate-700 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                            {cleanMarkdown(parsedSceneFeedback.feedback.recommendations)}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
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

// Warning Modal for @all exceeding timeout turns
const AllPersonasTurnLimitModal = ({ 
  isOpen, 
  onClose, 
  currentTurns, 
  maxTurns,
  personaCount
}: { 
  isOpen: boolean
  onClose: () => void
  currentTurns: number
  maxTurns: number
  personaCount: number
}) => {
  if (!isOpen) return null

  const requiredTurns = personaCount
  const totalTurnsIfUsed = currentTurns + requiredTurns
  const turnsExceeded = totalTurnsIfUsed - maxTurns

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in p-4">
      <div 
        className="bg-gradient-to-b from-white via-white to-gray-50 rounded-2xl shadow-2xl max-w-md w-full max-h-[90vh] border border-gray-200/50 animate-modal-enter flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-6 pb-4 border-b border-gray-200 flex-shrink-0">
          <h3 className="text-xl font-semibold flex items-center gap-2 text-red-900" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>
            <AlertCircle className="w-5 h-5" />
            Cannot Use @all
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
            <div className="bg-gradient-to-br from-red-50 via-red-50 to-red-50 border border-red-200/60 rounded-xl p-5 shadow-sm">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
                  <AlertCircle className="w-5 h-5 text-red-700" />
                </div>
                <span className="font-semibold text-red-900">Turn Limit Exceeded</span>
              </div>
              <p className="text-sm text-red-800 mb-3">
                Using @all would require <span className="font-semibold">{requiredTurns} turn{requiredTurns !== 1 ? 's' : ''}</span> (one per persona response).
              </p>
              <p className="text-sm text-red-800 mb-3">
                This would exceed your available turns by <span className="font-semibold">{turnsExceeded} turn{turnsExceeded !== 1 ? 's' : ''}</span>.
              </p>
              <div className="mt-3">
                <div className="flex items-center justify-between text-xs text-red-700 mb-1">
                  <span>Current Turns: {currentTurns}/{maxTurns}</span>
                  <span>Would Use: {totalTurnsIfUsed}/{maxTurns}</span>
                </div>
                <div className="w-full h-2 bg-red-200/50 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-red-400 to-red-500 rounded-full transition-all duration-300"
                    style={{ width: `${Math.min((totalTurnsIfUsed / maxTurns) * 100, 100)}%` }}
                  ></div>
                </div>
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-gray-50 to-white rounded-xl p-4 border border-gray-200/50 shadow-sm">
              <h4 className="font-semibold text-gray-900 mb-2 text-sm uppercase tracking-wide" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>Why this limitation?</h4>
              <p className="text-sm text-gray-700 leading-relaxed">
                Each persona's response to an @all message counts as a separate turn. This ensures 
                that using @all requires strategic consideration of your available turns.
              </p>
            </div>
            
            <div className="bg-gradient-to-br from-gray-50 to-white rounded-xl p-4 border border-gray-200/50 shadow-sm">
              <h4 className="font-semibold text-gray-900 mb-2 text-sm uppercase tracking-wide" style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}>What can you do?</h4>
              <ul className="text-sm text-gray-700 space-y-2">
                <li className="flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">•</span>
                  <span>Use @mentions to contact specific personas individually</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">•</span>
                  <span>Wait until you have more turns available</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-gray-400 mt-0.5">•</span>
                  <span>Focus on the most important questions for your remaining turns</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
        
        <div className="p-6 pt-4 border-t border-gray-200 flex-shrink-0">
          <Button 
            onClick={onClose} 
            className="w-full bg-gradient-to-r from-red-600 to-red-700 hover:from-red-700 hover:to-red-800 text-white shadow-lg hover:shadow-xl transition-all duration-200"
            style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}
          >
            Understood
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
  const [allScenes, setAllScenes] = useState<Scene[]>([])
  // Store raw backend data - personas have same structure as Persona interface (with image_url)
  const [allScenesWithPersonas, setAllScenesWithPersonas] = useState<Array<{id: number, personas: Persona[]}>>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isTyping, setIsTyping] = useState(false)
  const [typingPersona, setTypingPersona] = useState("")
  const [streamingMessageId, setStreamingMessageId] = useState<number | string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [completedScenes, setCompletedScenes] = useState<number[]>([])
  const [turnCount, setTurnCount] = useState(0)
  const [inputBlocked, setInputBlocked] = useState(false)
  // Immersive UI state
  const [selectedPersonas, setSelectedPersonas] = useState<string[]>([])
  const [currentTurnStartIndex, setCurrentTurnStartIndex] = useState(0)
  const [showAllMessages, setShowAllMessages] = useState(false)
  const [showObjectiveModal, setShowObjectiveModal] = useState(false)
  const [showStartModal, setShowStartModal] = useState(true)
  const [lastSpeakingPersona, setLastSpeakingPersona] = useState<string | null>(null)
  const [sceneIntroShown, setSceneIntroShown] = useState<Set<number>>(new Set())
  const [gradingData, setGradingData] = useState<any>(null)
  const [canSubmitForGrading, setCanSubmitForGrading] = useState(false)
  const [hasSubmittedForGrading, setHasSubmittedForGrading] = useState(false)
  const [gradingHasBeenShown, setGradingHasBeenShown] = useState(false)
  const [simulationComplete, setSimulationComplete] = useState(false)
  const [gradingInProgress, setGradingInProgress] = useState(false)
  const [loadingSimulation, setLoadingSimulation] = useState(true)
  const [isSceneTransitioning, setIsSceneTransitioning] = useState(false)
  const [showRerunConfirmation, setShowRerunConfirmation] = useState(false)
  const [isResettingSimulation, setIsResettingSimulation] = useState(false)
  // Stable unique ID generator to avoid duplicate React keys
  const messageSequenceRef = useRef(0)
  const nextMessageId = () => {
    messageSequenceRef.current += 1
    return `${Date.now()}-${messageSequenceRef.current}`
  }
  
  // New state for enhanced features
  const [activeTab, setActiveTab] = useState<'conversation' | 'case-study' | 'grading' | 'code-editor' | 'resources'>('conversation')
  const [selectedPersona, setSelectedPersona] = useState<PersonaDetails | null>(null)
  const [showPersonaModal, setShowPersonaModal] = useState(false)
  const [showTimeoutModal, setShowTimeoutModal] = useState(false)
  const [showAllPersonasWarningModal, setShowAllPersonasWarningModal] = useState(false)
  const [showMentionDropdown, setShowMentionDropdown] = useState(false)
  const [mentionSelectedIndex, setMentionSelectedIndex] = useState(0)
  const [inputMode, setInputMode] = useState<'text' | 'voice'>('text')
  const [isInterfaceGreyed, setIsInterfaceGreyed] = useState(false)
  // Persona bubble color utilities - expanded palette for better uniqueness
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
  ] as const
  
  // Improved hash function for consistent color assignment
  const hashPersona = (name: string) => {
    // Normalize name: lowercase, trim, and remove extra spaces for consistency
    const normalized = name.toLowerCase().trim().replace(/\s+/g, ' ')
    let h = 0
    for (let i = 0; i < normalized.length; i++) {
      h = ((h << 5) - h) + normalized.charCodeAt(i)
      h = h & h // Convert to 32-bit integer
    }
    return Math.abs(h)
  }
  
  // Get unique color for each persona based on their name
  const getPersonaBubbleClasses = (personaName?: string) => {
    const key = (personaName || '').trim()
    if (!key || key === 'All Personas' || key === 'ChatOrchestrator' || key === 'System') {
      return 'bg-gray-50 border-gray-200' // Default for system messages
    }
    // Use hash to consistently assign color to each persona
    const idx = hashPersona(key) % personaPalette.length
    return personaPalette[idx]
  }

  // Lookup a persona's role by name - search across all scenes
  const getPersonaRole = (personaName?: string, messageSceneId?: number) => {
    const name = (personaName || '').trim()
    if (!name) return undefined
    
    // First try to find in all_scenes_with_personas if available
    if (allScenesWithPersonas.length > 0) {
      for (const scene of allScenesWithPersonas) {
        const p = scene.personas.find(p => p.name === name)
        if (p) return p.role
      }
    }
    
    // Fallback to current scene
    if (simulationData?.current_scene?.personas) {
      const p = simulationData.current_scene.personas.find(p => p.name === name)
      if (p) return p.role
    }
    
    return undefined
  }

  // Lookup a persona's image by name - search across all scenes
  // Use same approach as scene images: access image_url directly from backend data
  const getPersonaImage = (personaName?: string, messageSceneId?: number) => {
    const name = (personaName || '').trim()
    if (!name) return undefined
    
    // First try to find in all_scenes_with_personas (raw backend data)
    if (allScenesWithPersonas.length > 0) {
      for (const scene of allScenesWithPersonas) {
        const p = scene.personas?.find((p: any) => p.name === name)
        if (p && p.image_url) {
          // Use image_url directly from backend (same as scene images)
          return getImageUrl(p.image_url)
        }
      }
    }
    
    // Fallback to current scene (raw backend data)
    if (simulationData?.current_scene?.personas) {
      const p = simulationData.current_scene.personas.find((p: any) => p.name === name)
      if (p && p.image_url) {
        // Use image_url directly from backend (same as scene images)
        return getImageUrl(p.image_url)
      }
    }
    
    return undefined
  }
  const [currentTypingPersona, setCurrentTypingPersona] = useState<string>('')

  // Persona card selection: click = toggle @mention in input
  const togglePersonaSelection = (persona: Persona) => {
    const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_')
    setSelectedPersonas(prev => {
      if (prev.includes(mentionId)) {
        setInput(cur => cur.replace(new RegExp(`@${mentionId}\\s*`, 'g'), '').trim())
        return prev.filter(id => id !== mentionId)
      } else {
        setInput(cur => {
          const base = cur.trimEnd()
          return base ? `${base} @${mentionId} ` : `@${mentionId} `
        })
        return [...prev, mentionId]
      }
    })
  }

  const clearPersonaSelection = () => setSelectedPersonas([])

  const simulationHasBegun = simulationData?.simulation_status === "in_progress"
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  // Block input when grading tab is active (simulation complete)
  useEffect(() => {
    if (simulationComplete && activeTab === 'grading') {
      setInputBlocked(true)
    }
  }, [simulationComplete, activeTab])

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
    
    // Also add scene personas to allScenesWithPersonas if not already present
    // Use scene data directly from backend (no normalization needed)
    if (scene && scene.id && scene.personas) {
      setAllScenesWithPersonas(prev => {
        const exists = prev.some(s => s.id === scene.id)
        if (!exists) {
          return [...prev, {
            id: scene.id,
            personas: scene.personas || []
          }]
        }
        return prev
      })
    }
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
      
      // Load turn_count immediately (for both new and resuming simulations)
      if (data.turn_count !== undefined && data.turn_count !== null) {
        setTurnCount(data.turn_count)
      } else {
        setTurnCount(0)  // Default to 0 for new simulations
      }
      
      // Store all scenes with personas for persona lookup
      // Use data exactly as backend sends it - no normalization needed
      // Backend returns personas with image_url field directly (same as scene images)
      if (data.all_scenes && data.all_scenes.length > 0) {
        setAllScenesWithPersonas(data.all_scenes)
      } else {
        // Fallback: create from current scene if all_scenes not provided
        setAllScenesWithPersonas([{
          id: data.current_scene.id,
          personas: data.current_scene.personas || []
        }])
      }
      
      // Check if simulation is already completed/graded (review mode)
      const isCompleted = data.simulation_status === 'completed' || 
                          data.simulation_status === 'graded' ||
                          data.simulation_status === 'submitted'
      
      if (isCompleted) {
        try {
          setInputBlocked(true)
          setSimulationComplete(true)
          setHasSubmittedForGrading(true)
          setShowStartModal(false)
          
          // Load conversation history for review
          if (data.conversation_history && data.conversation_history.length > 0) {
            const existingMessages = data.conversation_history.map((msg: any) => ({
              id: msg.id || nextMessageId(),
              sender: msg.sender_name || msg.sender || 'System',
              text: msg.message_content || msg.text || '',
              timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
              type: msg.message_type || msg.type || 'system',
              persona_name: msg.persona_name || (msg.message_type === 'ai_persona' || msg.type === 'ai_persona' ? (msg.sender_name || msg.sender) : undefined),
              persona_role: msg.persona_role,
              persona_id: msg.persona_id,
              // Add "View Grading" button to completion messages
              showViewGrading: (msg.message_content || msg.text || '')?.includes("🎉 Simulation complete!") && (msg.message_type || msg.type) === 'system'
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
            // Auto-show for graded and completed simulations (so students can review)
            const shouldAutoShow = true
            await fetchGradingData(false, shouldAutoShow, data).catch(err => {
              // Silently handle error
            })
            // Reset button states since simulation is already graded
            // Tab switching is handled inside fetchGradingData when autoShow=true
            setHasSubmittedForGrading(false)
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
          sender: msg.sender_name || msg.sender || 'System',
          text: msg.message_content || msg.text || '',
          timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
          type: msg.message_type || msg.type || 'system',
          persona_name: msg.persona_name || ((msg.message_type === 'ai_persona' || msg.type === 'ai_persona') ? (msg.sender_name || msg.sender) : undefined),
          persona_role: msg.persona_role,
          persona_id: msg.persona_id
        }))
        
        setMessages(existingMessages)
        
        // Restore turn count - load immediately on resume
        if (data.turn_count !== undefined && data.turn_count !== null) {
          setTurnCount(data.turn_count)
        } else {
          // Fallback: if turn_count not in response, default to 0
          setTurnCount(0)
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
          setShowStartModal(false)
        }
      } else {
        // Starting fresh - add welcome message and reset state
        setSceneIntroShown(new Set())
        setTurnCount(0)
        setCompletedScenes([])
        
        setMessages([{
          id: nextMessageId(),
          sender: "System",
          text: `🎯 **${data.simulation.title}**\n\n${data.simulation.description}\n\n**Your Role:** ${data.simulation.student_role}\n\n**Current Scene:** ${data.current_scene.title}\n\n**Instructions:**\n• Type **"begin"** to start the simulation\n• Type **"help"** for available commands\n• Use natural conversation to interact with personas`,
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

  const sendMessage = async (messageOverride?: string) => {
    const messageToSend = messageOverride ?? input
    if (inputBlocked || simulationComplete) return
    if (!simulationData || !messageToSend.trim() || isLoading) return

    const trimmedInput = messageToSend.trim()
    
    // Check for @all anywhere in the message (not just at start) - case-insensitive
    const allMatch = trimmedInput.match(/(^|\s)@all(\s|$)/i)
    // Also treat multiple @mentions as an "all-style" multi-persona message
    const mentionCount = (trimmedInput.match(/@[\w().\-&]+/g) || []).filter(m => m.toLowerCase() !== '@all').length
    const isAllMention = allMatch !== null || mentionCount > 1
    
    // Block persona mentions before simulation begins (unless it's the begin command)
    if (!simulationHasBegun && trimmedInput !== 'begin' && trimmedInput !== 'help') {
      if (isAllMention || trimmedInput.includes('@')) {
        alert('Please type "begin" to start the simulation before mentioning personas.')
        return
      }
    }

    // Handle @all or multi-mention - check turn count BEFORE sending
    if (isAllMention && simulationHasBegun) {
      // For @all use all personas count, for multi-mention use actual mention count
      const requiredTurns = allMatch ? simulationData.current_scene.personas.length : mentionCount
      const timeoutTurns = simulationData.current_scene.timeout_turns || 15
      const totalTurnsIfUsed = turnCount + requiredTurns
      
      // Check if using @all would exceed timeout turns
      if (totalTurnsIfUsed > timeoutTurns) {
        setShowAllPersonasWarningModal(true)
        return
      }
      // @all is valid, continue with sending (skip persona validation below)
    } else if (simulationHasBegun) {
      // Check for other @mentions only if not @all
      // Updated regex to capture special chars in persona names (dots, parentheses, hyphens, ampersands, etc.)
      const mentionMatch = trimmedInput.match(/@([\w().\-&]+)/)
      if (mentionMatch) {
        const mentionId = mentionMatch[1].toLowerCase().trim()
        
        // Explicitly skip validation for @all (safety check)
        if (mentionId === 'all') {
          // Re-run the @all logic
          const personaCount = simulationData.current_scene.personas.length
          const timeoutTurns = simulationData.current_scene.timeout_turns || 15
          const requiredTurns = personaCount
          const totalTurnsIfUsed = turnCount + requiredTurns
          
          if (totalTurnsIfUsed > timeoutTurns) {
            setShowAllPersonasWarningModal(true)
            return
          }
          // @all is valid, continue
        } else {
          // Restrict @mentions to only personas in the current scene
          // Generate both original and sanitized versions for backwards compatibility
          const validPersonaMentions: string[] = []
          simulationData.current_scene.personas.forEach(p => {
            const original = p.name.toLowerCase().replace(/\s+/g, '_')
            const sanitized = original.replace(/[^a-z0-9_]/g, '')
            validPersonaMentions.push(original)
            validPersonaMentions.push(sanitized)
          })
          // Also sanitize the mentionId for comparison
          const sanitizedMentionId = mentionId.replace(/[^a-z0-9_]/g, '')
          if (!validPersonaMentions.includes(mentionId) && !validPersonaMentions.includes(sanitizedMentionId)) {
            alert('You can only @mention personas involved in this scene.')
            return
          }
        }
      }
    }

    const userMessage: Message = {
      id: nextMessageId() as any,
      sender: "You",
      text: trimmedInput,
      timestamp: new Date(),
      type: 'user'
    }

    // Capture turn start index and clear persona selection before appending
    setCurrentTurnStartIndex(messages.length)
    setShowAllMessages(false)
    clearPersonaSelection()
    setMessages(prev => [...prev, userMessage])
    setInput("")
    setIsLoading(true)
    setIsTyping(true)
    
    // Extract mentioned persona name, otherwise default to ChatOrchestrator
    let typingPersonaName = "ChatOrchestrator"
    if (isAllMention) {
      typingPersonaName = "All Personas"
    } else {
      // Updated regex to capture special chars in persona names (dots, parentheses, hyphens, ampersands, etc.)
      const mentionMatch = trimmedInput.match(/@([\w().\-&]+)/)
      if (mentionMatch) {
        const mentionId = mentionMatch[1].toLowerCase()
        const sanitizedMentionId = mentionId.replace(/[^a-z0-9_]/g, '')
        const mentionedPersona = simulationData.current_scene.personas.find(
          p => {
            const original = p.name.toLowerCase().replace(/\s+/g, '_')
            const sanitized = original.replace(/[^a-z0-9_]/g, '')
            return original === mentionId || sanitized === mentionId || sanitized === sanitizedMentionId
          }
        )
        if (mentionedPersona) {
          typingPersonaName = mentionedPersona.name
        }
      }
    }
    setTypingPersona(typingPersonaName)
    setCurrentTypingPersona(typingPersonaName)
    if (typingPersonaName !== "ChatOrchestrator" && typingPersonaName !== "All Personas") {
      setLastSpeakingPersona(typingPersonaName)
    }

    // Grey out interface will be controlled by isStreaming state

    // The backend increments turn_count right when the message is saved, so we rely on
    // the authoritative value from the backend response
    if (trimmedInput !== 'begin' && trimmedInput !== 'help') {
      // Don't increment here - backend will handle it and return updated count
      setHasSubmittedForGrading(false)
      setCanSubmitForGrading(false)
    }

    try {
      // Use dedicated streaming endpoint through proxy
      const response = await fetch('/api/proxy/api/simulation/linear-chat-stream', {
        method: "POST",
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          simulation_id: simulationData.simulation.id,
          user_id: 1,
          scene_id: simulationData.current_scene.id,
          message: userMessage.text,
          user_progress_id: simulationData.user_progress_id
        })
      })

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error')
        console.error("[DEBUG] Chat request failed:", response.status, errorText)
        throw new Error(`Chat failed: ${response.status}`)
      }

      // Handle streaming response
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let streamedText = ""
      let chatData: any = {}
      
      // For @all messages, we'll create messages dynamically as each persona responds
      // For regular messages, create a single placeholder
      const isAllMessage = isAllMention
      const isBeginCommand = userMessage.text.trim().toLowerCase() === 'begin'
      
      // Map to track streaming text and message IDs for each persona (for @all messages)
      const personaStreamTexts: { [key: string]: string } = {}
      const personaMessageIds: { [key: string]: any } = {}
      
      // Create a placeholder AI message for non-@all messages
      let aiMessageId: any = null
      if (!isAllMessage) {
        aiMessageId = nextMessageId()
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
        setMessages(prev => [...prev, placeholderMessage])
      }
      
      setIsTyping(false) // Hide typing indicator when streaming starts
      setIsStreaming(false) // Don't start streaming state yet - wait for first content
      setStreamingMessageId(aiMessageId) // Track the streaming message ID (null for @all)
      
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
                  
                  if (isAllMessage && parsed.persona_name) {
                    // @all message: Handle each persona separately
                    const personaKey = parsed.persona_name
                    
                    // Initialize streaming text for this persona if not exists
                    if (!personaStreamTexts[personaKey]) {
                      personaStreamTexts[personaKey] = ""
                      setLastSpeakingPersona(personaKey)
                      // Create a new message for this persona
                      const personaMessageId = nextMessageId()
                      personaMessageIds[personaKey] = personaMessageId
                      
                      const personaPlaceholder: any = {
                        id: personaMessageId,
                        sender: personaKey,
                        text: "",
                        timestamp: new Date(),
                        type: 'ai_persona',
                        persona_name: personaKey,
                        persona_id: parsed.persona_id,
                      }
                      setMessages(prev => [...prev, personaPlaceholder])
                      setStreamingMessageId(personaMessageId)
                    }
                    
                    // Append streamed content to this persona's message
                    personaStreamTexts[personaKey] += parsed.content
                    const currentText = personaStreamTexts[personaKey]
                    const currentMessageId = personaMessageIds[personaKey]
                    
                    setMessages(prev => prev.map(msg => 
                      msg.id === currentMessageId 
                        ? { ...msg, text: currentText, sender: parsed.persona_name || msg.sender, persona_name: parsed.persona_name, persona_id: parsed.persona_id }
                        : msg
                    ))
                  } else if (!isAllMessage) {
                    // Regular message: Stream text for personas and non-begin orchestrator messages
                    if (typingPersonaName !== "ChatOrchestrator" || !isBeginCommand) {
                      // Append streamed content
                      streamedText += parsed.content
                      setMessages(prev => prev.map(msg => 
                        msg.id === aiMessageId 
                          ? { ...msg, text: streamedText, sender: (typingPersonaName === "ChatOrchestrator") ? "System" : (parsed.persona_name || msg.sender) }
                          : msg
                      ))
                    }
                  }
                }
                
                if (parsed.done) {
                  if (isAllMessage && parsed.persona_name) {
                    // @all message: Finalize this specific persona's message
                    const personaKey = parsed.persona_name
                    const personaMessageId = personaMessageIds[personaKey]
                    const finalText = parsed.full_content || personaStreamTexts[personaKey] || ""
                    
                    if (personaMessageId) {
                      setMessages(prev => prev.map(msg => 
                        msg.id === personaMessageId 
                          ? { 
                              ...msg, 
                              text: finalText,
                              sender: parsed.persona_name || msg.sender,
                              persona_name: parsed.persona_name,
                              persona_id: parsed.persona_id,
                              scene_completed: parsed.scene_completed,
                              next_scene_id: parsed.next_scene_id
                            }
                          : msg
                      ))
                    }
                    
                    // Update chatData with the last persona's data
                    chatData = parsed
                    
                    // Show loading screen if scene is completed
                    if (parsed.scene_completed) {
                      setIsSceneTransitioning(true)
                    }
                    
                    // After all personas have finished streaming, clear streaming state
                    // We'll do this after the loop completes
                  } else if (!isAllMessage) {
                    // Regular message: Final metadata received - streaming finished
                    chatData = parsed
                    setIsStreaming(false) // Clear streaming state when streaming finishes
                    setStreamingMessageId(null) // Clear streaming message ID
                    
                    // Show loading screen if scene is completed
                    if (parsed.scene_completed) {
                      setIsSceneTransitioning(true)
                    }
                    
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
                }
              } catch (e) {
                console.error("[DEBUG] Error parsing streaming response:", e, "Data:", data)
                // Don't silently handle - log it for debugging
              }
            }
          }
        }
      }
      
      // Final cleanup for @all messages
      if (isAllMessage) {
        setIsStreaming(false)
        setStreamingMessageId(null)
      }
      
      // Now process the final chatData metadata

      // If chatData is empty, it means we didn't receive the final done message
      // This could indicate an error or incomplete response
      if (Object.keys(chatData).length === 0) {
        console.warn("[DEBUG] chatData is empty - streaming may have failed or completed without metadata")
      }
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
        
        // If this is the first "begin" response, update simulation status and dismiss start modal
        if (trimmedInput === 'begin') {
          setSimulationData(prev => prev ? {
            ...prev,
            simulation_status: "in_progress"
          } : null)
          setShowStartModal(false)
        }
        
        setCanSubmitForGrading(true)

        // Use backend's authoritative turn_count when it arrives
        // This corrects any discrepancies from optimistic updates and handles edge cases
        if (typeof chatData.turn_count === 'number') {
          // Only update if backend value differs from current (to avoid unnecessary re-renders)
          setTurnCount(prev => {
            if (prev !== chatData.turn_count) {
              return chatData.turn_count
            }
            return prev
          })
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
                const sceneIntroMessage = {
                  id: nextMessageId(),
                  sender: "System",
                  text: generateSceneIntroduction(nextSceneData),
                  timestamp: new Date(),
                  type: 'system' as const
                };
                
                setMessages(prev => [...prev, sceneIntroMessage]);
                
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
          } else if (chatData.simulation_complete || (isLastScene && !chatData.next_scene_id)) {
            // Simulation complete - mark the last scene as completed
            setCompletedScenes(prev => {
              const currentSceneId = simulationData.current_scene.id
              if (!prev.includes(currentSceneId)) {
                return [...prev, currentSceneId]
              }
              return prev
            })
            
            // Block input immediately
            setInputBlocked(true)
            setSimulationComplete(true)
            
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
            fetchGradingData(false, true).then(() => {
              setGradingInProgress(false)
              // Tab switching is handled inside fetchGradingData when autoShow=true
              // Reset button states after grading completes
              setHasSubmittedForGrading(false)
              // Keep input blocked since simulation is complete
              setInputBlocked(true)
            }) // autoShow=true for fresh completions
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
      // REMOVED: Optimistic rollback - no longer needed since we removed optimistic updates
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

  // Handle keyboard navigation for mention dropdown and Enter to send
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showMentionDropdown && simulationData?.current_scene?.personas) {
      const personas = simulationData.current_scene.personas;
      
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (prev + 1) % personas.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (prev - 1 + personas.length) % personas.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const selectedPersona = personas[mentionSelectedIndex];
        if (selectedPersona) {
          const mentionId = selectedPersona.name.toLowerCase().replace(/\s+/g, '_');
          setInput(input.replace(/@[^@]*$/, `@${mentionId} `));
          setShowMentionDropdown(false);
          setMentionSelectedIndex(0);
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        setShowMentionDropdown(false);
        setMentionSelectedIndex(0);
      }
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    // Now handled by handleKeyDown
  }

  const handleResetSimulation = async () => {
    if (!instanceId) return

    setIsResettingSimulation(true)
    try {
      const response = await apiClient.apiRequest(
        `/student-simulation-instances/${instanceId}/reset-simulation`,
        {
          method: "POST"
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to reset simulation')
      }

      // Close confirmation dialog
      setShowRerunConfirmation(false)

      // Reload the page to start fresh
      window.location.reload()
    } catch (error) {
      console.error('Error resetting simulation:', error)
      alert(error instanceof Error ? error.message : 'Failed to reset simulation. Please try again.')
    } finally {
      setIsResettingSimulation(false)
    }
  }

  const fetchGradingData = async (forceRegenerate = false, autoShow = false, dataOverride?: SimulationData) => {
    // Use override data if provided, otherwise use state
    const data = dataOverride || simulationData
    if (!data) return
    
    try {
      // First, check if instance already has grading data (for completed simulations)
      if (!forceRegenerate) {
        try {
          const instanceRes = await apiClient.apiRequest(`/student-simulation-instances/${instanceId}`)
          if (instanceRes.ok) {
            const instanceData = await instanceRes.json()
            
            // If instance has AI grading data, use it as a quick preview while we fetch full data
            if (instanceData.ai_grade !== null && instanceData.ai_grade !== undefined && instanceData.ai_feedback) {
              // Set cached data immediately so user sees something
              setGradingData({
                overall_score: instanceData.ai_grade,
                overall_feedback: instanceData.ai_feedback,
                scenes: [],
                rubric_total_points: 100
              })
              if (autoShow) {
                setActiveTab('grading')
              }
              setHasSubmittedForGrading(false)
              // Don't return — fall through to fetch full grading with scene breakdown
            }
          }
        } catch (err) {
          // Error checking instance, will proceed to call grading API
        }
      }
      
      // No cached grading or force regenerate - call AI grading
      const res = await apiClient.apiRequest(`/api/simulation/grade?user_progress_id=${data.user_progress_id}`)
      if (!res.ok) {
        throw new Error('Failed to fetch grading')
      }
      
      const gradingResult = await res.json()
      setGradingData(gradingResult)
      if (autoShow) {
        setActiveTab('grading')
      }
      // Reset button states after grading completes
      setHasSubmittedForGrading(false)
      
      // Save the grade to the StudentSimulationInstance
      try {
        await apiClient.apiRequest(`/student-simulation-instances/${instanceId}`, {
          method: 'PUT',
          body: JSON.stringify({
            status: 'graded',
            completion_percentage: 100,
            ai_grade: gradingResult.overall_score,
            ai_feedback: gradingResult.overall_feedback
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
    // Clear the turn messages so old conversation doesn't stick
    setCurrentTurnStartIndex(messages.length)
    setShowAllMessages(false)
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
          scenario_id: simulationData!.simulation.id
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
            fetchGradingData(false, true).then(() => {
              setGradingInProgress(false)
              // Tab switching is handled inside fetchGradingData when autoShow=true
              // Reset button states after grading completes
              setHasSubmittedForGrading(false)
              setInputBlocked(true) // Keep input blocked since simulation is complete
            }) // autoShow=true for fresh completions
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

  const totalScenes = simulationData.simulation?.total_scenes || 0
  // Calculate actual scene position (1-based) from all_scenes array instead of using scene_order
  const currentScenePosition = simulationData.all_scenes && simulationData.all_scenes.length > 0
    ? [...simulationData.all_scenes]
        .sort((a, b) => a.scene_order - b.scene_order)
        .findIndex(s => s.id === simulationData.current_scene.id) + 1
    : simulationData.current_scene.scene_order // Fallback: scene_order is already 1-based
  const isLastScene = currentScenePosition >= totalScenes
  const timeoutTurns = simulationData?.current_scene?.timeout_turns ?? 15
  const hasTurnsRemaining = turnCount < timeoutTurns
  const shouldShowSubmitSystemMessage = simulationHasBegun && canSubmitForGrading && !hasSubmittedForGrading && !inputBlocked && !simulationComplete

  // ── Inline modal components (close over component state) ──────────────────
  const ObjectiveModal = () => {
    const scene = simulationData!.current_scene
    return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={() => setShowObjectiveModal(false)}>
        <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Target className="w-5 h-5 text-emerald-600" />
              <h3 className="font-semibold text-gray-900">Scene Objective</h3>
            </div>
            <button onClick={() => setShowObjectiveModal(false)} className="text-gray-400 hover:text-gray-600 transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>
          <p className="text-xs text-gray-400 mb-3">{scene.title}</p>
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mb-4">
            <p className="text-sm text-emerald-900 leading-relaxed">{scene.user_goal || 'Complete the interaction'}</p>
          </div>
          {scene.personas_involved && scene.personas_involved.length > 0 && (
            <div className="mb-4">
              <p className="text-xs text-gray-500 mb-2 font-medium">Personas Involved</p>
              <div className="flex flex-wrap gap-1">
                {scene.personas_involved.map((name, i) => (
                  <span key={i} className="bg-gray-100 text-gray-600 text-xs px-2 py-1 rounded-full">{name}</span>
                ))}
              </div>
            </div>
          )}
          <button onClick={() => setShowObjectiveModal(false)} className="w-full bg-gray-900 text-white py-2.5 rounded-xl text-sm font-medium hover:bg-gray-700 transition-colors">
            Got it
          </button>
        </div>
      </div>
    )
  }

  const StartSimulationModal = () => {
    const scene = simulationData!.current_scene
    return (
      <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full overflow-hidden flex max-h-[90vh] relative">
          {/* Exit button */}
          <button
            onClick={() => router.push("/student/simulations")}
            className="absolute top-3 right-3 z-10 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-full p-1.5 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
          {/* Left: scene image */}
          <div className="w-72 flex-shrink-0 relative">
            {scene.image_url ? (
              <img src={getImageUrl(scene.image_url)} alt={scene.title} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full bg-gradient-to-br from-gray-800 to-gray-900 flex items-center justify-center min-h-64">
                <BookOpen className="w-20 h-20 text-gray-600" />
              </div>
            )}
            <div className="absolute inset-0 bg-gradient-to-r from-transparent to-black/20" />
          </div>
          {/* Right: content */}
          <div className="flex-1 p-8 flex flex-col overflow-y-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-1" style={{ fontFamily: "'Sora', sans-serif" }}>
              {simulationData!.simulation.title}
            </h2>
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wider mb-3">Description</p>
            <p className="text-gray-600 text-sm leading-relaxed mb-4">
              {simulationData!.simulation.description}
            </p>
            {/* Metadata: scenes, personas, estimated time */}
            <div className="flex items-center gap-4 mb-5 text-xs text-gray-500">
              <span className="flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5" />
                {totalScenes} {totalScenes === 1 ? 'scene' : 'scenes'}
              </span>
              <span className="flex items-center gap-1.5">
                <Users className="w-3.5 h-3.5" />
                {scene.personas?.length || 0} {(scene.personas?.length || 0) === 1 ? 'persona' : 'personas'}
              </span>
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                ~{totalScenes * 6} min
              </span>
            </div>
            <div className="mt-auto">
              <button
                onClick={() => { setShowStartModal(false); sendMessage("begin") }}
                disabled={isLoading || isTyping}
                className="w-full bg-gray-900 text-white py-4 rounded-xl font-semibold text-sm hover:bg-gray-700 transition-all flex items-center justify-center gap-2 shadow-lg disabled:opacity-60"
              >
                {isLoading ? (
                  <><RefreshCw className="w-5 h-5 animate-spin" />Starting...</>
                ) : (
                  <><PlayCircle className="w-5 h-5" />Start Now</>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Scene list for progress bar
  const progressScenes = simulationData.all_scenes
    ? [...simulationData.all_scenes].sort((a, b) => a.scene_order - b.scene_order)
    : allScenes.slice().sort((a, b) => a.scene_order - b.scene_order)

  return (
    <div className="h-screen flex overflow-hidden">
      <RoleBasedSidebar currentPath={`/student/run-simulation/${instanceId}`} />

      {/* Offset for fixed sidebar */}
      <div className="flex-1 ml-20 flex overflow-hidden min-w-0">

      {/* ── LEFT PANEL ─────────────────────────────────────────────────────────── */}
      <div className="w-80 flex-shrink-0 bg-[#0f1117] text-white flex flex-col overflow-y-auto">
        {/* Exit Simulation (visible when header tabs are not yet shown) */}
        {!simulationHasBegun && !simulationComplete && (
          <div className="px-4 pt-4 pb-2 flex-shrink-0">
            <button
              onClick={() => router.push("/student/simulations")}
              className="flex items-center gap-1.5 text-white/40 hover:text-white/80 transition-colors text-sm"
            >
              <ArrowLeft className="w-4 h-4" />
              Exit Simulation
            </button>
          </div>
        )}
        {/* Scene progress bar */}
        <div className="px-4 pt-4 pb-4 flex-shrink-0">
          <p className="text-[10px] text-white/30 uppercase tracking-widest mb-3 flex-shrink-0" style={{ fontFamily: "'Sora', sans-serif" }}>
            Scenes
          </p>
          <div className="flex items-center gap-1 mb-2">
            {(progressScenes.length > 0 ? progressScenes : Array.from({ length: totalScenes || 1 })).map((scene, i) => {
              const sceneId = (scene as any)?.id
              const isDone = sceneId ? completedScenes.includes(sceneId) : false
              const isCurrent = sceneId
                ? sceneId === simulationData.current_scene.id && !isDone
                : i === currentScenePosition - 1
              return (
                <div
                  key={sceneId || i}
                  className={`h-1 flex-1 rounded-full transition-all duration-500 ${
                    isDone ? 'bg-emerald-400' : isCurrent ? 'bg-white' : 'bg-white/20'
                  }`}
                />
              )
            })}
          </div>
          <p className="text-xs text-white/40 mb-3" style={{ fontFamily: "'DM Sans', sans-serif" }}>
            Scene {currentScenePosition} of {totalScenes} — {simulationData.current_scene.title}
          </p>
          {/* Simulation info card (scene description) */}
          <div className="border border-white/10 rounded-xl p-4" style={{ background: 'rgba(255,255,255,0.05)' }}>
            <h1 className="text-sm font-semibold text-white/90 leading-tight" style={{ fontFamily: "'Sora', sans-serif" }}>
              {simulationData.current_scene.title}
            </h1>
            {simulationData.current_scene.description && (
              <p className="text-xs text-white/40 mt-1.5 leading-relaxed">
                {simulationData.current_scene.description}
              </p>
            )}
          </div>
        </div>

        {/* Divider */}
        <div className="h-px mx-4 mb-4 flex-shrink-0" style={{ background: 'rgba(255,255,255,0.08)' }} />

        {/* Available Personas */}
        <div className="px-4 flex-1 min-h-0 flex flex-col pb-4">
          <p className="text-[10px] text-white/30 uppercase tracking-widest mb-3 flex-shrink-0" style={{ fontFamily: "'Sora', sans-serif" }}>
            Available Personas
          </p>
          <div className="space-y-2 overflow-y-auto flex-1">
            {simulationData.current_scene.personas && simulationData.current_scene.personas.length > 0 ? (
              simulationData.current_scene.personas.map((persona) => {
                const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_')
                const isSelected = selectedPersonas.includes(mentionId)
                const personaImg = getPersonaImage(persona.name)
                const canSelect = simulationHasBegun && !isLoading && !isTyping && !simulationComplete
                return (
                  <div
                    key={persona.id}
                    role="button"
                    tabIndex={canSelect ? 0 : -1}
                    aria-pressed={isSelected}
                    onClick={() => canSelect && togglePersonaSelection(persona)}
                    onKeyDown={(e) => {
                      if (!canSelect) return
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        togglePersonaSelection(persona)
                      }
                    }}
                    className={`rounded-xl p-3 border transition-all duration-200 ${
                      !canSelect
                        ? 'opacity-50 cursor-not-allowed border-white/10'
                        : isSelected
                        ? 'persona-card-selected cursor-pointer border-blue-400/50'
                        : 'cursor-pointer border-white/10 hover:border-white/25'
                    }`}
                    style={{
                      background: isSelected
                        ? 'rgba(59,130,246,0.15)'
                        : 'rgba(255,255,255,0.04)'
                    }}
                  >
                    <div className="flex items-start gap-2.5">
                      <div className="w-12 h-12 rounded-full flex-shrink-0 overflow-hidden bg-gray-700 flex items-center justify-center">
                        {personaImg ? (
                          <img src={personaImg} alt={persona.name} className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none' }} />
                        ) : (
                          <User className="w-6 h-6 text-gray-400" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-white text-sm font-medium truncate">{persona.name}</p>
                        <p className="text-white/50 text-xs truncate">{persona.role}</p>
                        <p className="text-white/35 text-xs mt-0.5 line-clamp-2 leading-relaxed">{persona.background}</p>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedPersona({ id: persona.id, name: persona.name, role: persona.role, bio: persona.background, personality: persona.correlation, background: persona.background, image_url: persona.image_url })
                          setShowPersonaModal(true)
                        }}
                        className="text-white/25 hover:text-white/60 transition-colors flex-shrink-0 mt-0.5"
                      >
                        <HelpCircle className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )
              })
            ) : (
              <p className="text-white/25 text-xs text-center py-6">No personas in this scene</p>
            )}
          </div>
        </div>
      </div>

      {/* ── RIGHT PANEL ─────────────────────────────────────────────────────────── */}
      <div
        className="flex-1 relative flex flex-col overflow-hidden"
        style={{
          backgroundImage: simulationData.current_scene.image_url
            ? `url(${getImageUrl(simulationData.current_scene.image_url)})`
            : undefined,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundColor: '#1a1a2e'
        }}
      >
        {/* Overlay */}
        <div className="absolute inset-0 bg-black/55" />

        {/* Content */}
        <div className="relative z-10 flex flex-col h-full">

          {/* ── SOLID HEADER BAR — tabs + Exit Simulation ── */}
          {(simulationHasBegun || simulationComplete) && (
            <div className="flex-shrink-0 flex items-center justify-between gap-1 px-4 py-3 border-b border-white/10" style={{ background: '#0f1117' }}>
              <div className="flex items-center gap-1">
              {(['conversation', 'case-study', 'grading'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                    activeTab === tab
                      ? 'bg-white/15 text-white'
                      : 'text-white/50 hover:text-white/80 hover:bg-white/8'
                  }`}
                  style={{ fontFamily: "'Sora', sans-serif" }}
                >
                  {tab === 'conversation' ? 'Conversation' : tab === 'case-study' ? 'Case Study' : 'Grading'}
                </button>
              ))}
              </div>
              <button
                onClick={() => router.push("/student/simulations")}
                className="flex items-center gap-1.5 text-white/50 hover:text-white/90 transition-colors text-sm ml-auto"
              >
                <ArrowLeft className="w-4 h-4" />
                Exit Simulation
              </button>
            </div>
          )}

          {/* ── OBJECTIVE BAR — solid blue, centered ── */}
          {simulationHasBegun && simulationData.current_scene.user_goal && activeTab === 'conversation' && (
            <div
              className="flex-shrink-0 px-6 py-3 flex items-center justify-center gap-2.5 cursor-pointer hover:brightness-110 transition-all"
              style={{ background: '#1e3a5f' }}
              onClick={() => setShowObjectiveModal(true)}
            >
              <Target className="w-4 h-4 text-blue-300 flex-shrink-0" />
              <p className="text-blue-100 text-sm font-medium text-center leading-snug">
                {simulationData.current_scene.user_goal}
              </p>
            </div>
          )}

          {/* ── CONVERSATION TAB ── */}
          {activeTab === 'conversation' && (
            <div className="flex flex-col flex-1 min-h-0 px-6 pb-6">

              {/* Center — dynamic persona avatars for current turn */}
              <div className="flex-1 flex flex-col items-center justify-center min-h-0 py-2">
                {(() => {
                  // Collect unique personas who responded in this turn
                  const turnMsgs = messages.slice(currentTurnStartIndex)
                  const respondingPersonas = Array.from(
                    new Map(
                      turnMsgs
                        .filter(m => m.type === 'ai_persona' && (m.persona_name || m.sender))
                        .map(m => {
                          const name = m.persona_name || m.sender
                          return [name, name]
                        })
                    ).values()
                  )
                  // Also include currently typing persona if not already listed
                  if (isTyping && typingPersona && typingPersona !== 'ChatOrchestrator' && !respondingPersonas.includes(typingPersona)) {
                    respondingPersonas.push(typingPersona)
                  }

                  if (respondingPersonas.length > 0) {
                    // Dynamic sizing: fewer personas = larger avatars
                    const count = respondingPersonas.length
                    const avatarSize = count <= 2 ? 'w-36 h-36' : count <= 4 ? 'w-28 h-28' : 'w-20 h-20'
                    const iconSize = count <= 2 ? 'w-16 h-16' : count <= 4 ? 'w-12 h-12' : 'w-8 h-8'
                    const textSize = count <= 2 ? 'text-sm' : 'text-xs'
                    const borderWidth = count <= 2 ? 'border-4' : 'border-2'

                    return (
                      <div className="flex flex-col items-center gap-3">
                        <div className={`flex items-center justify-center flex-wrap gap-4 ${count > 3 ? 'max-w-md' : ''}`}>
                          {respondingPersonas.map((name) => {
                            const img = getPersonaImage(name)
                            const isSpeaking = name === lastSpeakingPersona || (isTyping && name === typingPersona)
                            return (
                              <div key={name} className="flex flex-col items-center gap-2">
                                <div className={`${avatarSize} rounded-full overflow-hidden bg-gray-700 ${borderWidth} shadow-2xl flex items-center justify-center transition-all duration-300 ${isSpeaking ? 'border-blue-400 scale-105' : 'border-white/20'}`}>
                                  {img
                                    ? <img src={img} alt={name} className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none' }} />
                                    : <User className={`${iconSize} text-gray-400`} />}
                                </div>
                                <p className={`text-white/80 ${textSize} font-medium text-center`} style={{ fontFamily: "'DM Sans', sans-serif" }}>
                                  {name}
                                </p>
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
                <button
                  onClick={() => setActiveTab('grading')}
                  className={`sim-tab px-6 py-3 text-sm font-medium border-b-2 ${
                    activeTab === 'grading'
                      ? 'sim-tab-active text-blue-600 border-transparent'
                      : 'border-transparent text-gray-500'
                  }`}
                  style={{ fontFamily: "'Sora', sans-serif" }}
                >
                  <Trophy className="w-4 h-4 mr-2 inline" />
                  Grading
                </button>
                {simulationData?.current_scene?.scene_type === 'code_challenge' && (
                  <>
                    <button
                      onClick={() => setActiveTab('code-editor')}
                      className={`sim-tab px-6 py-3 text-sm font-medium border-b-2 ${
                        activeTab === 'code-editor'
                          ? 'sim-tab-active text-blue-600 border-transparent'
                          : 'border-transparent text-gray-500'
                      }`}
                      style={{ fontFamily: "'Sora', sans-serif" }}
                    >
                      <PlayCircle className="w-4 h-4 mr-2 inline" />
                      Code Editor
                    </button>
                    <button
                      onClick={() => setActiveTab('resources')}
                      className={`sim-tab px-6 py-3 text-sm font-medium border-b-2 ${
                        activeTab === 'resources'
                          ? 'sim-tab-active text-blue-600 border-transparent'
                          : 'border-transparent text-gray-500'
                      }`}
                      style={{ fontFamily: "'Sora', sans-serif" }}
                    >
                      <BookOpen className="w-4 h-4 mr-2 inline" />
                      Resources
                      {(simulationData.current_scene.data_files?.length || 0) + (simulationData.current_scene.reference_files?.length || 0) > 0 && (
                        <span className="ml-1.5 bg-blue-100 text-blue-700 text-xs px-1.5 py-0.5 rounded-full">
                          {(simulationData.current_scene.data_files?.length || 0) + (simulationData.current_scene.reference_files?.length || 0)}
                        </span>
                      )}
                    </button>
                  </>
                )}
                <div className="flex-1"></div>
                {simulationHasBegun && (
                  <div className="px-6 py-3">
                    <button
                      type="button"
                      onClick={() => setShowTimeoutModal(true)}
                      className="bg-gradient-to-br from-amber-50 via-yellow-50 to-amber-50 border border-amber-200/60 rounded-xl px-4 py-2 text-xs font-semibold text-amber-900 cursor-pointer transition-all shadow-sm hover:shadow-md"
                      style={{ fontFamily: "'Helvetica Neue', 'Helvetica', 'Arial', sans-serif" }}
                    >
                      <div className="flex items-center gap-2">
                        <Clock className="w-3.5 h-3.5 text-amber-700" />
                        <span>Turns: {turnCount}/{simulationData.current_scene.timeout_turns || 15}</span>
                      </div>
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
                        {/* Hide avatar for system, orchestrator, and grading progress messages */}
                        {message.type !== 'system' && 
                         message.type !== 'orchestrator' && 
                         !(message as any).gradingInProgress && 
                         !(message as any).sceneLoading && (
                          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 text-[11px] flex items-center justify-center text-white font-semibold shadow-sm overflow-hidden">
                            {(() => {
                              // Use persona_name from message if available, otherwise try to extract from sender
                              const personaName = message.persona_name || (message.type === 'ai_persona' ? message.sender : null);
                              const personaImage = personaName ? getPersonaImage(personaName, (message as any).scene_id) : null;
                              
                              if (personaImage) {
                                return (
                                  <img 
                                    src={personaImage} 
                                    alt={personaName || message.sender} 
                                    className="object-cover w-full h-full rounded-full"
                                    onError={(e) => {
                                      // Hide image on error, show initial instead
                                      e.currentTarget.style.display = 'none';
                                      const parent = e.currentTarget.parentElement;
                                      if (parent) {
                                        const label = (personaName || message.sender || '').charAt(0).toUpperCase();
                                        parent.textContent = label;
                                      }
                                    }}
                                  />
                                );
                              }
                              const label = (personaName || message.sender || '');
                              return label.charAt(0).toUpperCase();
                            })()}
                          </div>
                        )}
                        <span className="text-xs font-semibold opacity-90" style={{ fontFamily: "'Sora', sans-serif" }}>
                          {message.type === 'orchestrator' ? 'System' : message.sender}
                        </span>
                        {message.type === 'ai_persona' && message.persona_name && (
                          <Badge variant="secondary" className="text-xs bg-white/90 backdrop-blur-sm text-gray-800 border border-gray-300/50 shadow-sm font-medium">
                            {(message as any).persona_role || getPersonaRole(message.persona_name, (message as any).scene_id) || message.persona_name}
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
                          (message.text || '').split('\n').map((line, index) => {
                            const escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                            const boldFormatted = escaped.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
                            return (
                              <div key={index} dangerouslySetInnerHTML={{ __html: boldFormatted }} />
                            )
                          })}
                        </div>
                        {isTyping && (
                          <div className="flex gap-1.5">
                            <div className="w-2 h-2 bg-white/50 rounded-full animate-bounce" />
                            <div className="w-2 h-2 bg-white/50 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                            <div className="w-2 h-2 bg-white/50 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                          </div>
                        )}
                      </div>
                    )
                  } else if (simulationHasBegun) {
                    return (
                      <div className="text-center">
                        <div className="w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-3" style={{ background: 'rgba(255,255,255,0.05)', border: '2px solid rgba(255,255,255,0.1)' }}>
                          <Users className="w-10 h-10 text-white/20" />
                        </div>
                        <p className="text-sm text-white/30">@mention a persona to respond</p>
                      </div>
                    )
                  }
                  return null
                })()}
              </div>

              {/* Confined response box — current turn messages only (expandable) */}
              {simulationHasBegun && (() => {
                const turnMsgs = messages.slice(currentTurnStartIndex)
                const displayMsgs = showAllMessages ? messages : turnMsgs
                const hasContent = turnMsgs.length > 0 || gradingInProgress
                const hasPreviousMessages = currentTurnStartIndex > 0
                if (!hasContent && !showAllMessages) return null
                return (
                  <div className={`group mb-3 flex-shrink-0 rounded-2xl overflow-y-auto space-y-3 ${showAllMessages ? 'max-h-[28rem] pt-0 px-4 pb-4' : 'max-h-52 p-4'}`} style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(12px)', scrollbarWidth: 'thin', transition: 'max-height 0.3s ease' }}>
                    {/* See all / Hide all toggle — visible on hover (collapsed) or always (expanded) */}
                    {hasPreviousMessages && (
                      <button
                        onClick={() => setShowAllMessages(prev => !prev)}
                        className={`w-full flex items-center justify-center gap-1.5 hover:text-white/55 transition-all text-xs ${showAllMessages ? 'sticky top-0 z-10 text-white/40 opacity-100 py-2' : 'text-white/35 opacity-0 group-hover:opacity-100 py-0.5'}`}
                        style={{ fontFamily: "'Sora', sans-serif", ...(showAllMessages ? { background: 'linear-gradient(to bottom, rgba(0,0,0,0.6) 60%, transparent)', backdropFilter: 'blur(12px)' } : {}) }}
                      >
                        {showAllMessages ? (
                          <>
                            <ChevronDown className="w-3 h-3" />
                            Hide previous
                          </>
                        ) : (
                          <>
                            <ChevronUp className="w-3 h-3" />
                            See all
                          </>
                        )}
                      </button>
                    )}
                    {/* Separator when showing all */}
                    {showAllMessages && hasPreviousMessages && (
                      <div className="border-t border-white/10" />
                    )}
                    {gradingInProgress && (
                      <div className="flex items-center gap-3 text-white/60">
                        <RefreshCw className="w-4 h-4 animate-spin flex-shrink-0" />
                        <span className="text-sm">Grading in progress…</span>
                      </div>
                    )}
                    {displayMsgs.map((msg) => {
                      const isStreamingMsg = isStreaming && msg.id === streamingMessageId
                      const isUserMsg = msg.type === 'user'
                      const personaName = msg.persona_name || (msg.type === 'ai_persona' ? msg.sender : null)
                      const personaImg = personaName ? getPersonaImage(personaName) : null
                      return (
                        <div key={msg.id} className={`flex gap-2 ${isUserMsg ? 'justify-end' : ''}`}>
                          {msg.type === 'ai_persona' && (
                            <div className="w-7 h-7 rounded-full bg-gray-600 flex-shrink-0 overflow-hidden flex items-center justify-center">
                              {personaImg
                                ? <img src={personaImg} alt={personaName || ''} className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = 'none' }} />
                                : <User className="w-3.5 h-3.5 text-gray-400" />}
                            </div>
                          )}
                          <div className={`min-w-0 ${isUserMsg ? 'max-w-[80%] bg-white/15 rounded-xl px-3 py-2' : 'flex-1'}`}>
                            {isUserMsg && (
                              <p className="text-blue-300/70 text-xs mb-0.5 font-medium" style={{ fontFamily: "'Sora', sans-serif" }}>You</p>
                            )}
                            {msg.type === 'ai_persona' && (
                              <p className="text-white/55 text-xs mb-0.5 font-medium" style={{ fontFamily: "'Sora', sans-serif" }}>
                                {personaName}
                              </p>
                            )}
                            {isStreamingMsg ? (
                              <div className="h-1.5 rounded-full w-full animate-pulse" style={{ background: 'linear-gradient(90deg, #60a5fa, #3b82f6, #60a5fa)', backgroundSize: '200% 100%' }} />
                            ) : (
                              <div className="text-white/85 text-sm leading-relaxed">
                                {(msg.text || '').split('\n').map((line, i) => {
                                  const escaped = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                                  const formatted = escaped.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                                  return <div key={i} dangerouslySetInnerHTML={{ __html: formatted }} />
                                })}
                              </div>
                            )}
                            {msg.showViewGrading && (
                              <button
                                onClick={async () => {
                                  if (gradingData) { setActiveTab('grading') } else { setGradingInProgress(true); await fetchGradingData(false, true); setGradingInProgress(false) }
                                }}
                                disabled={gradingInProgress}
                                className="mt-2 text-xs text-blue-300 hover:text-blue-200 underline transition-colors"
                              >
                                {gradingInProgress ? 'Loading…' : 'View Grading & Feedback'}
                              </button>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )
              })()}

              {/* Simulation complete strip */}
              {simulationComplete && (
                <div className="mb-3 rounded-2xl p-4 flex-shrink-0" style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(12px)' }}>
                  <div className="flex items-center gap-2 mb-3">
                    <Trophy className="w-4 h-4 text-yellow-400" />
                    <span className="text-white text-sm font-semibold">Simulation Complete</span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={async () => { if (gradingData) { setActiveTab('grading') } else { setGradingInProgress(true); await fetchGradingData(false, true); setGradingInProgress(false) } }}
                      disabled={gradingInProgress}
                      className="flex-1 text-white text-xs font-medium py-2 rounded-xl border transition-colors flex items-center justify-center gap-1.5"
                      style={{ background: 'rgba(255,255,255,0.08)', borderColor: 'rgba(255,255,255,0.15)' }}
                    >
                      <Trophy className="w-3.5 h-3.5" />
                      {gradingInProgress ? 'Loading…' : 'View Grade'}
                    </button>
                    <button
                      onClick={() => setShowRerunConfirmation(true)}
                      className="flex-1 text-amber-300 text-xs font-medium py-2 rounded-xl border transition-colors flex items-center justify-center gap-1.5"
                      style={{ background: 'rgba(245,158,11,0.12)', borderColor: 'rgba(245,158,11,0.25)' }}
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      Re-run
                    </button>
                  </div>
                </div>
              )}

              {/* Input bar */}
              <div className="flex-shrink-0">
                {simulationComplete ? (
                  <div className="rounded-2xl p-4 flex items-center gap-3 border" style={{ background: 'rgba(255,255,255,0.08)', backdropFilter: 'blur(12px)', borderColor: 'rgba(255,255,255,0.12)' }}>
                    <Eye className="w-5 h-5 text-white/30 flex-shrink-0" />
                    <p className="text-white/35 text-sm">Review mode — interactions disabled</p>
                  </div>
                ) : !simulationHasBegun ? (
                  <button
                    onClick={() => sendMessage("begin")}
                    disabled={isLoading || isTyping}
                    className="w-full bg-white text-gray-900 font-semibold py-4 rounded-2xl hover:bg-white/90 transition-all flex items-center justify-center gap-2 text-sm shadow-lg disabled:opacity-60"
                  >
                    {isLoading ? <RefreshCw className="w-5 h-5 animate-spin" /> : <><PlayCircle className="w-5 h-5" />Begin Simulation</>}
                  </button>
                ) : (
                  <div className="rounded-2xl shadow-lg overflow-hidden" style={{ background: 'rgba(255,255,255,0.95)', backdropFilter: 'blur(12px)' }}>
                    {/* Textarea section — expands upward */}
                    <div className="relative px-4 pt-3 pb-2">
                      {/* @mention dropdown */}
                      {showMentionDropdown && (
                        <div className="sim-mention-dropdown absolute bottom-full left-0 right-0 z-20 mb-2 max-h-56 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-gray-100">
                          <div className="sim-mention-header">
                            <div className="text-xs font-semibold text-gray-700 mb-1">Personas</div>
                            <div className="text-xs text-gray-500">Select to @mention</div>
                          </div>
                          <div className="p-2">
                            {simulationData.current_scene.personas.map((persona, index) => (
                              <div
                                key={persona.id}
                                className={`sim-mention-item flex items-center gap-2 p-2 rounded cursor-pointer ${index === mentionSelectedIndex ? 'sim-mention-item-selected' : ''}`}
                                onClick={() => {
                                  const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_')
                                  setInput(input.replace(/@[^@]*$/, `@${mentionId} `))
                                  setShowMentionDropdown(false)
                                  setMentionSelectedIndex(0)
                                }}
                                onMouseEnter={() => setMentionSelectedIndex(index)}
                              >
                                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center flex-shrink-0 overflow-hidden">
                                  {persona.image_url && persona.image_url.trim()
                                    ? <img src={getImageUrl(persona.image_url)} alt={persona.name} className="object-cover w-full h-full" onError={(e) => { e.currentTarget.style.display = 'none' }} />
                                    : <User className="w-3.5 h-3.5 text-white" />}
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
                      <textarea
                        value={input}
                        onChange={(e) => {
                          setInput(e.target.value)
                          // Auto-resize
                          e.target.style.height = 'auto'
                          e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
                          const shouldShow = /@[^\s]*$/.test(e.target.value)
                          setShowMentionDropdown(shouldShow)
                          if (shouldShow) setMentionSelectedIndex(0)
                        }}
                        onKeyDown={handleKeyDown}
                        placeholder="Ask anything…"
                        disabled={inputBlocked || isLoading || isTyping || gradingInProgress}
                        rows={1}
                        className="w-full border-0 bg-transparent text-gray-900 placeholder-gray-400 focus:ring-0 focus:outline-none text-sm p-0 resize-none overflow-y-auto"
                        style={{ minHeight: '24px', maxHeight: '160px' }}
                      />
                    </div>
                    {/* Dividing line */}
                    <div className="border-t border-gray-200 mx-3" />
                    {/* Bottom row — Submit left, turns + send right */}
                    <div className="flex items-center justify-between px-3 py-2">
                      <div className="flex items-center">
                        {(canSubmitForGrading || hasSubmittedForGrading) && (
                          <button
                            onClick={handleSubmitForGrading}
                            disabled={inputBlocked || hasSubmittedForGrading || isLoading || isTyping}
                            className="flex items-center gap-1.5 h-8 px-3 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                          >
                            {hasSubmittedForGrading
                              ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" />Submitting…</>
                              : <><CheckCircle className="w-3.5 h-3.5" />Submit for Grading</>}
                          </button>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {/* Turns */}
                        <button
                          onClick={() => setShowTimeoutModal(true)}
                          className="flex items-center gap-1 h-8 px-2.5 rounded-lg bg-gray-100 border border-gray-200 text-xs font-mono text-gray-600 hover:bg-gray-200 transition-colors"
                        >
                          <Clock className="w-3 h-3 text-gray-400" />
                          {turnCount}/{simulationData.current_scene.timeout_turns || 15}
                        </button>
                        {/* Send */}
                        <button
                          onClick={() => sendMessage()}
                          disabled={inputBlocked || isLoading || isTyping || !input.trim() || gradingInProgress}
                          className="flex items-center justify-center h-8 w-8 rounded-lg bg-gray-900 text-white hover:bg-gray-700 disabled:opacity-30 transition-colors"
                        >
                          {isLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── CASE STUDY TAB ── */}
          {activeTab === 'case-study' && (
            <div className="flex-1 p-4 flex flex-col min-h-0">
              <div className="relative z-10 bg-white rounded-2xl overflow-hidden shadow-2xl flex flex-col flex-1">
                {simulationData?.simulation?.case_study_url ? (
                  <>
                    <div className="p-4 border-b flex items-center justify-between flex-shrink-0">
                      <h3 className="font-semibold text-gray-900 text-sm">Case Study Document</h3>
                      <Button variant="outline" size="sm" onClick={() => window.open(simulationData.simulation?.case_study_url, '_blank')}>
                        <ArrowRight className="w-4 h-4 mr-2" />Open in New Tab
                      </Button>
                    </div>
                    <iframe src={simulationData.simulation.case_study_url} className="flex-1 border-0 w-full" title="Case Study PDF" />
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-center p-6">
                    <div>
                      <BookOpen className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                      <p className="text-gray-500 font-medium">Case Study</p>
                      <p className="text-gray-400 text-sm mt-1">No case study PDF available for this simulation</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── GRADING TAB ── */}
          {activeTab === 'grading' && (
            <div className="flex-1 p-4 flex flex-col min-h-0">
              <div className="relative z-10 bg-white rounded-2xl shadow-2xl flex-1 overflow-y-auto">
                {gradingData ? (
                  <GradingTabView gradingData={gradingData} />
                ) : (
                  <div className="flex items-center justify-center h-full text-center p-6">
                    <div>
                      <Trophy className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                      <p className="text-gray-500 font-medium" style={{ fontFamily: "'Sora', sans-serif" }}>
                        Complete simulation for grading
                      </p>
                      <p className="text-gray-400 text-sm mt-2" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                        Finish all scenes to receive comprehensive feedback and assessment
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── CODE EDITOR TAB ── */}
          {activeTab === 'code-editor' && simulationData?.current_scene?.scene_type === 'code_challenge' && (
            <div className="flex-1 min-h-0">
              <CodeEditor
                userProgressId={simulationData.user_progress_id}
                sceneId={simulationData.current_scene.id}
                starterCode={simulationData.current_scene.starter_code || ''}
                sandboxAvailable={!!simulationData?.sandbox_id}
                personas={simulationData.current_scene.personas?.map(p => ({ id: p.id, name: p.name })) || []}
                onSubmitToChat={(_code, formatted) => {
                  sendMessage(formatted)
                  setActiveTab('conversation')
                }}
              />
            </div>
          )}

          {/* ── RESOURCES TAB ── */}
          {activeTab === 'resources' && simulationData?.current_scene?.scene_type === 'code_challenge' && (
            <div className="flex-1 min-h-0">
              <ResourcesPanel
                dataFiles={simulationData.current_scene.data_files || []}
                referenceFiles={simulationData.current_scene.reference_files || []}
                sceneObjective={simulationData.current_scene.user_goal}
                dataPath="/home/daytona/data/"
              />
            </div>
          )}

        </div>{/* end relative z-10 */}
      </div>{/* end right panel */}

      {/* ── MODALS ────────────────────────────────────────────────────────────── */}
      {showStartModal && !simulationHasBegun && !simulationComplete && <StartSimulationModal />}
      {showObjectiveModal && <ObjectiveModal />}

      <PersonaDetailsModal
        persona={selectedPersona}
        isOpen={showPersonaModal}
        onClose={() => setShowPersonaModal(false)}
        onMessage={(personaName) => {
          const mentionId = personaName.toLowerCase().replace(/\s+/g, '_')
          const base = input.trimEnd()
          setInput(base ? `${base} @${mentionId} ` : `@${mentionId} `)
        }}
      />

      <TimeoutTurnsModal
        isOpen={showTimeoutModal}
        onClose={() => setShowTimeoutModal(false)}
        currentTurns={turnCount}
        maxTurns={simulationData.current_scene.timeout_turns || 15}
      />

      <AllPersonasTurnLimitModal
        isOpen={showAllPersonasWarningModal}
        onClose={() => setShowAllPersonasWarningModal(false)}
        currentTurns={turnCount}
        maxTurns={simulationData.current_scene.timeout_turns || 15}
        personaCount={simulationData.current_scene.personas.length}
      />

      {showRerunConfirmation && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full border border-gray-200 animate-modal-enter" onClick={(e) => e.stopPropagation()}>
            <div className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center">
                  <AlertTriangle className="w-6 h-6 text-amber-600" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Re-run Simulation?</h3>
                  <p className="text-sm text-gray-500">This action cannot be undone</p>
                </div>
              </div>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6">
                <p className="text-sm text-amber-800"><strong>Warning:</strong> Re-running this simulation will permanently delete:</p>
                <ul className="text-sm text-amber-700 mt-2 ml-4 list-disc space-y-1">
                  <li>Your current grade and feedback</li>
                  <li>All conversation history</li>
                  <li>Your progress in all scenes</li>
                </ul>
                <p className="text-sm text-amber-800 mt-3">You will start the simulation completely fresh from Scene 1.</p>
              </div>
              <div className="flex gap-3">
                <Button onClick={() => setShowRerunConfirmation(false)} variant="outline" className="flex-1" disabled={isResettingSimulation}>Cancel</Button>
                <Button onClick={handleResetSimulation} className="flex-1 bg-amber-500 hover:bg-amber-600 text-white" disabled={isResettingSimulation}>
                  {isResettingSimulation ? <><RefreshCw className="w-4 h-4 mr-2 animate-spin" />Resetting…</> : <><RefreshCw className="w-4 h-4 mr-2" />Yes, Re-run Simulation</>}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      </div>{/* end ml-20 wrapper */}
    </div>
  )
}
