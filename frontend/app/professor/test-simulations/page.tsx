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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Send,
  Users,
  Target,
  Clock,
  CheckCircle,
  AlertCircle,
  HelpCircle,
  Play,
  PlayCircle,
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
import { Trophy } from "lucide-react"
import dynamic from 'next/dynamic'
import ResourcesPanel from '@/components/ResourcesPanel'
import MarkdownRenderer from '@/components/MarkdownRenderer'

const CodeEditor = dynamic(() => import('@/components/CodeEditor'), { ssr: false })

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
  case_study_url?: string
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
  data_files?: any[]
  reference_files?: any[]
}

interface SimulationData {
  user_progress_id: number
  simulation: Scenario  // Changed from 'scenario' to 'simulation' to match backend
  current_scene: Scene
  all_scenes?: Array<{  // Add all_scenes for persona lookup across scenes
    id: number
    title: string
    scene_order: number
    personas: PersonaDetails[]
  }>
  simulation_status: string
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
  sandbox_id?: string
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
  image_url?: string
}

interface TimeoutTurnsModal {
  isOpen: boolean
  currentTurns: number
  maxTurns: number
}

/** Parses raw grading feedback text into structured score breakdown, assessment, and recommendations. */
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
    
    // Pattern 2: Bullet format with score on same line, Performance Level and Reasoning on separate lines
    if (result.scoreBreakdown.length === 0) {
      // Split by bullet points first
      const bulletSections = breakdownText.split(/^[-•]\s*\*\*/m).filter(Boolean)
      
      for (const section of bulletSections) {
        // Extract criterion name and score from first line
        const headerMatch = section.match(/^([^*]+):\*\*\s*(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)\s*points?/i)
        if (headerMatch) {
          const criterion = headerMatch[1].trim()
          const score = parseFloat(headerMatch[2])
          const maxScore = parseFloat(headerMatch[3])
          
          // Extract Performance Level
          const perfLevelMatch = section.match(/\*\*Performance\s+Level:\*\*\s*([^\n]+)/i)
          const performanceLevel = perfLevelMatch ? perfLevelMatch[1].trim() : ''
          
          // Extract Reasoning
          const reasoningMatch = section.match(/\*\*Reasoning:\*\*\s*([^\n]+(?:\n(?![-•]\s*\*\*))?)/i)
          const reasoning = reasoningMatch ? reasoningMatch[1].trim() : ''
          
          result.scoreBreakdown.push({
            criterion: criterion,
            score: score,
            maxScore: maxScore,
            performanceLevel: performanceLevel,
            reasoning: reasoning
          })
        }
      }
    }
    
    // Pattern 3: Bullet format with inline details (original pattern as fallback)
    if (result.scoreBreakdown.length === 0) {
      const bulletPattern = /[-•]\s*\*\*([^*]+)\*\*\s*-\s*Score:\s*(\d+(?:\.\d+)?)\/(\d+(?:\.\d+)?)\s*points?\s*-\s*Performance\s*level:\s*([^-\n]+)\s*-\s*(?:Brief\s*)?reasoning:\s*([^-\n]+(?:\n(?![-•]))?)/gi
      let match
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
    
    // Try multiple formats for summary
    const summaryMatch = assessmentText.match(/\*\*Summary\s+of\s+performance\s+across\s+the\s+simulation:\*\*\s*([^\n]+(?:\n(?!\*\*))?)/i) ||
                         assessmentText.match(/-?\s*\*\*Summary\s*of\s*performance:\*\*\s*([^-\n]+(?:\n(?!-?\s*\*\*))?)/i)
    if (summaryMatch) {
      result.overallAssessment.summary = summaryMatch[1].trim()
    }
    
    const strengthsMatch = assessmentText.match(/-?\s*\*\*Key\s*strengths(?:\s*demonstrated)?:\*\*\s*([^-\n]+(?:\n(?!-?\s*\*\*))?)/i)
    if (strengthsMatch) {
      result.overallAssessment.keyStrengths = strengthsMatch[1].trim()
    }
    
    const improvementsMatch = assessmentText.match(/-?\s*\*\*Main\s*areas\s*for\s*improvement:\*\*\s*([^-\n]+(?:\n(?!-?\s*\*\*))?)/i)
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
    const recommendationsMatch = feedbackText.match(/-?\s*\*\*Specific\s*actionable\s*recommendations:\*\*\s*([^-\n]+(?:\n(?!-?\s*\*\*))?)/i)
    if (recommendationsMatch) {
      const recText = recommendationsMatch[1].trim()
      // Check if it's a list format
      if (recText.includes('\n-') || recText.includes('\n•')) {
        result.feedback.recommendations = recText.split(/\n[-•]\s*/).filter(Boolean).map((r: string) => r.trim())
      } else {
        result.feedback.recommendations = recText.split(/\.\s+/).filter(Boolean)
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

/** Filters out the initial "begin" command from user response arrays. */
const filterBeginFromResponses = (responses: any[]) => {
  if (!responses || !Array.isArray(responses)) return []
  return responses.filter((r: any) => {
    const content = typeof r === 'string' ? r : r.content || r.text || ''
    return content.toLowerCase().trim() !== 'begin'
  })
}

/** Parses scene-level grading feedback into structured assessment with strengths, improvements, and recommendations. */
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

/** Renders the professional grading tab with score breakdown, assessment, and per-scene feedback using MarkdownRenderer. */
const GradingTabView = ({ gradingData }: { gradingData: any }) => {
  // Get rubric_total_points from grading data, default to 100
  const rubricTotalPoints = gradingData.rubric_total_points || 100
  
  // Parse raw feedback text if needed
  const rawFeedback = gradingData.overall_feedback
  const parsedData = rawFeedback && typeof rawFeedback === 'string' && rawFeedback.includes('**OVERALL SCORE:**') 
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
    <div className="flex-1 overflow-y-auto bg-white">
      <div className="max-w-5xl mx-auto py-8 px-6">
        {/* Header Section */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-slate-900 mb-1" style={{ fontFamily: "'Sora', sans-serif" }}>
            Grading & Feedback
          </h2>
          <p className="text-slate-500 text-sm">Performance assessment and recommendations</p>
        </div>
        
        {/* Overall Score Card - Simplified */}
        <div className="mb-8 rounded-xl p-6 text-blue-600 bg-blue-50 border border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-medium uppercase tracking-wider text-slate-600 mb-1" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                Overall Score
              </div>
              <div className="text-4xl font-bold" style={{ fontFamily: "'Sora', sans-serif" }}>
                {Math.round(overallScore)}<span className="text-xl text-slate-500 font-normal">/{Math.round(maxScore)}</span>
              </div>
            </div>
            {parsedData?.overallAssessment?.summary ? (
              <div className="flex-1 max-w-lg ml-8">
                <MarkdownRenderer content={parsedData.overallAssessment.summary} className="text-sm text-slate-700" />
              </div>
            ) : gradingData.overall_feedback ? (
              <div className="flex-1 max-w-lg ml-8">
                <MarkdownRenderer content={typeof gradingData.overall_feedback === 'string' ? gradingData.overall_feedback : ''} className="text-sm text-slate-700" />
              </div>
            ) : null}
          </div>
        </div>
        
        {/* Score Breakdown - Cleaner */}
        {(parsedData?.scoreBreakdown?.length > 0 || gradingData.score_breakdown) && (
          <div className="mb-8">
            <h3 className="text-lg font-semibold text-slate-900 mb-4" style={{ fontFamily: "'Sora', sans-serif" }}>
              Assessment Criteria
            </h3>
            <div className="space-y-3">
              {(parsedData?.scoreBreakdown || gradingData.score_breakdown || []).map((item: any, idx: number) => {
                const criterion = item.criterion || item.name || 'Assessment Criterion'
                let score = item.score || 0
                const itemMax = item.maxScore || item.max_score
                
                if (itemMax && itemMax !== rubricTotalPoints && score > 0) {
                  score = (score / itemMax) * (rubricTotalPoints / (parsedData?.scoreBreakdown?.length || gradingData.score_breakdown?.length || 6))
                }
                
                const max = itemMax && itemMax !== rubricTotalPoints 
                  ? (rubricTotalPoints / (parsedData?.scoreBreakdown?.length || gradingData.score_breakdown?.length || 6))
                  : (itemMax || rubricTotalPoints)
                const performanceLevel = item.performanceLevel || item.performance_level || 'Not Assessed'
                const reasoning = item.reasoning || item.feedback || ''
                
                return (
                  <div key={idx} className="bg-slate-50 rounded-lg p-4 border border-slate-200">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-medium text-slate-900 text-sm flex-1" style={{ fontFamily: "'Sora', sans-serif" }}>
                        {criterion}
                      </h4>
                      <div className="flex items-center gap-3 ml-4">
                        <span className="text-xs text-slate-500 uppercase tracking-wide" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                          {performanceLevel}
                        </span>
                        <span className={`text-base font-semibold ${getScoreColor(score, max).split(' ')[0]}`} style={{ fontFamily: "'Sora', sans-serif" }}>
                          {Math.round(score)}/{typeof max === 'number' ? Math.round(max) : max}
                        </span>
                      </div>
                    </div>
                    {reasoning && (
                      <MarkdownRenderer content={reasoning} className="text-sm text-slate-600 mt-2" />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
        
        {/* Strengths and Improvements - Simplified */}
        {(parsedData?.overallAssessment?.keyStrengths || 
          gradingData.key_strengths?.length > 0 ||
          parsedData?.overallAssessment?.improvements ||
          gradingData.development_areas?.length > 0) && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {/* Key Strengths */}
            {(parsedData?.overallAssessment?.keyStrengths || gradingData.key_strengths?.length > 0) && (
              <div className="bg-slate-50 rounded-lg p-5 border border-slate-200">
                <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2" style={{ fontFamily: "'Sora', sans-serif" }}>
                  <CheckCircle className="w-4 h-4 text-emerald-600" />
                  Strengths
                </h3>
                {parsedData?.overallAssessment?.keyStrengths ? (
                  <MarkdownRenderer content={parsedData.overallAssessment.keyStrengths} className="text-sm text-slate-700" />
                ) : (
                  <ul className="space-y-2">
                    {gradingData.key_strengths.map((strength: string, idx: number) => (
                      <li key={idx} className="text-sm text-slate-700 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                        {strength}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* Areas for Improvement */}
            {(parsedData?.overallAssessment?.improvements || gradingData.development_areas?.length > 0) && (
              <div className="bg-slate-50 rounded-lg p-5 border border-slate-200">
                <h3 className="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2" style={{ fontFamily: "'Sora', sans-serif" }}>
                  <AlertCircle className="w-4 h-4 text-amber-600" />
                  Areas for Improvement
                </h3>
                {parsedData?.overallAssessment?.improvements ? (
                  <MarkdownRenderer content={parsedData.overallAssessment.improvements} className="text-sm text-slate-700" />
                ) : (
                  <ul className="space-y-2">
                    {gradingData.development_areas.map((area: string, idx: number) => (
                      <li key={idx} className="text-sm text-slate-700 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                        {area}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* Actionable Recommendations - Cleaner */}
        {(parsedData?.feedback?.recommendations || gradingData.recommendations?.length > 0) && (
          <div className="mb-8 bg-blue-50/50 rounded-lg p-5 border border-blue-100">
            <h3 className="text-sm font-semibold text-slate-900 mb-3" style={{ fontFamily: "'Sora', sans-serif" }}>
              Recommendations
            </h3>
            
            {parsedData?.feedback?.recommendations && (
              <div>
                {Array.isArray(parsedData.feedback.recommendations) ? (
                  <ul className="space-y-2.5">
                    {parsedData.feedback.recommendations.map((rec: string, idx: number) => (
                      <li key={idx} className="text-sm text-slate-700 leading-relaxed">
                        <MarkdownRenderer content={rec} className="text-sm text-slate-700" />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <MarkdownRenderer content={parsedData.feedback.recommendations} className="text-sm text-slate-700" />
                )}
              </div>
            )}
            
            {gradingData.recommendations?.length > 0 && !parsedData?.feedback?.recommendations && (
              <ul className="space-y-2.5">
                {gradingData.recommendations.map((rec: string, idx: number) => (
                  <li key={idx} className="text-sm text-slate-700 leading-relaxed" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                    {rec}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        
        {/* Scene-by-Scene Analysis - Cleaner */}
        {gradingData.scenes && gradingData.scenes.length > 0 && (
          <div className="mb-8">
            <h3 className="text-lg font-semibold text-slate-900 mb-5" style={{ fontFamily: "'Sora', sans-serif" }}>
              Scene Analysis
            </h3>
            <div className="space-y-5">
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
                  <div key={scene.id || idx} className="bg-slate-50 rounded-lg p-5 border border-slate-200">
                    {/* Header */}
                    <div className="flex items-start justify-between mb-4 pb-3 border-b border-slate-200">
                      <div className="flex-1">
                        <h4 className="text-base font-semibold text-slate-900 mb-1" style={{ fontFamily: "'Sora', sans-serif" }}>
                          {scene.title || `Scene ${idx + 1}`}
                        </h4>
                      </div>
                      <div className={`text-lg font-semibold ml-4 ${getScoreColor(displayScore, sceneMaxScore).split(' ')[0]}`} style={{ fontFamily: "'Sora', sans-serif" }}>
                        {Math.round(displayScore)}/{Math.round(sceneMaxScore)}
                      </div>
                    </div>
                    
                    {/* Assessment and Recommendations - Simplified */}
                    {(parsedSceneFeedback?.overallAssessment?.improvements || 
                      parsedSceneFeedback?.feedback?.recommendations ||
                      scene.improvements?.length > 0) && (
                      <div className="space-y-3">
                        {parsedSceneFeedback?.overallAssessment?.improvements && (
                          <div>
                            <p className="text-xs font-medium text-slate-600 mb-1.5 uppercase tracking-wide" style={{ fontFamily: "'Sora', sans-serif" }}>
                              Areas for Improvement
                            </p>
                            <MarkdownRenderer content={parsedSceneFeedback.overallAssessment.improvements} className="text-sm text-slate-700" />
                          </div>
                        )}

                        {parsedSceneFeedback?.feedback?.recommendations && (
                          <div>
                            <p className="text-xs font-medium text-slate-600 mb-1.5 uppercase tracking-wide" style={{ fontFamily: "'Sora', sans-serif" }}>
                              Recommendations
                            </p>
                            <MarkdownRenderer content={parsedSceneFeedback.feedback.recommendations} className="text-sm text-slate-700" />
                          </div>
                        )}
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
  const [startingScenario, setStartingScenario] = useState<number | null>(null)
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
        const response = await apiClient.apiRequest("/api/publishing/simulations/?include_drafts=true", {}, true) // silentAuthError = true
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
          const stored = localStorage.getItem("chatboxSimulation")
          console.log("[DEBUG] SimulationSelector: localStorage chatboxSimulation =", stored)
          if (stored) {
            const parsed = JSON.parse(stored)
            if (parsed && typeof parsed.simulation_id === 'number') {
              preselectId = parsed.simulation_id
              console.log("[DEBUG] SimulationSelector: Found preselectId =", preselectId)
            } else if (parsed && typeof parsed.scenario_id === 'number') {
              // Backward compatibility: support old scenario_id key
              preselectId = parsed.scenario_id
              console.log("[DEBUG] SimulationSelector: Found preselectId (legacy scenario_id) =", preselectId)
            }
          }
        } catch (_) {}
        
        // If we have a preselected id and it exists and is not draft, use it
        if (preselectId) {
          const match = validScenarios.find((s: any) => s.id === preselectId)
          const isDraft = match ? (match.is_draft || match.status === 'draft') : false
          console.log("[DEBUG] SimulationSelector: Found match for preselectId", preselectId, "isDraft:", isDraft)
          if (match && !isDraft) {
            console.log("[DEBUG] SimulationSelector: Setting selectedSimulation to", preselectId)
            setSelectedScenario(preselectId)
            hasPreselected = true
            hasPreselectedRef.current = true
            // Clear after consumption to prevent stale selections later
            localStorage.removeItem("chatboxSimulation")
            localStorage.removeItem("chatboxScenario") // Also clear old key for backward compatibility
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
    <div className="max-w-4xl mx-auto space-y-5">
      <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
        <CardHeader>
          <CardTitle className="text-xl">
            Select a Scenario to Simulate
          </CardTitle>
          <p className="text-gray-600 text-base">
            Choose from your available scenarios with AI personas and scenes
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {scenarios.map((scenario, index) => {
            const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
            return (
            <div
              key={scenario.id}
              className={`card-elevated border rounded-xl p-5 transition-all duration-300 ${staggerClass} animate-fade-scale ${
                scenario.is_draft || scenario.status === 'draft'
                  ? 'border-gray-300/60 bg-gray-50/90 backdrop-blur-sm cursor-not-allowed opacity-60'
                  : selectedScenario === scenario.id 
                    ? 'border-blue-500/60 bg-gradient-to-br from-blue-50/60 to-blue-100/30 shadow-lg cursor-pointer' 
                    : 'border-gray-200/60 bg-white/90 backdrop-blur-sm cursor-pointer hover:shadow-md'
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
                        className="btn-gradient-purple text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                        onClick={async (e) => {
                          e.stopPropagation();
                          if (!window.confirm(`Activate scenario '${scenario.title}'? This will make it available to students.`)) return;
                          try {
                            const res = await apiClient.apiRequest(`/api/publishing/simulations/${scenario.id}/status`, {
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
                          const res = await apiClient.apiRequest(`/api/publishing/simulations/${scenario.id}`, { method: 'DELETE' });
                          if (!res || !res.ok) throw new Error('Failed to delete');
                          setScenarios(prev => {
                            if (!prev || !Array.isArray(prev)) {
                              console.error("[ERROR] scenarios state is invalid during delete");
                              return [];
                            }
                            return prev.filter(s => s && s.id !== scenario.id);
                          });
                          if (selectedScenario === scenario.id) setSelectedScenario(null);
                        } catch (err) {
                          console.error("Delete scenario error:", err);
                          alert('Failed to delete scenario. Please try again.');
                        }
                      }}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            </div>
            )
          })}
          
          <div className="pt-4 border-t border-gray-200/60">
            {(() => {
              const selectedScenarioData = scenarios.find(s => s.id === selectedScenario);
              const isDraft = selectedScenarioData ? (selectedScenarioData.is_draft || selectedScenarioData.status === 'draft') : false;
              const isLoading = startingScenario === selectedScenario;
              
              return (
                <Button 
                  onClick={() => {
                    if (selectedScenario) {
                      setStartingScenario(selectedScenario)
                      onScenarioSelect(selectedScenario)
                    }
                  }}
                  disabled={!selectedScenario || isDraft || isLoading}
                  className="w-full btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                  size="lg"
                >
                  {isLoading ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 sim-loading-spinner" />
                      Starting...
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 mr-2" />
                      {isDraft ? 'Draft - Cannot Play' : 'Start Simulation'}
                      <ArrowRight className="w-4 h-4 ml-2" />
                    </>
                  )}
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
              {persona.image_url ? (
                <img src={getImageUrl(persona.image_url)} alt={persona.name} className="object-cover w-full h-full" />
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

export default function LinearSimulationChat() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  // All hooks must be called before any conditional returns
  // Core simulation state
  const [simulationData, setSimulationData] = useState<SimulationData | null>(null)
  const [allScenesWithPersonas, setAllScenesWithPersonas] = useState<Array<{id: number, personas: PersonaDetails[]}>>([])
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
  // New state for enhanced features (must be before useEffect that uses it)
  const [activeTab, setActiveTab] = useState<'conversation' | 'case-study' | 'grading'>('conversation');
  const [codeTab, setCodeTab] = useState<'editor' | 'resources'>('editor');
  const [editorCode, setEditorCode] = useState<string>('');
  // Reset editor buffer whenever the active scene changes so stale code doesn't persist
  useEffect(() => {
    setEditorCode(simulationData?.current_scene?.starter_code ?? '')
  }, [simulationData?.current_scene?.id])
  // Block input when viewing grading tab
  useEffect(() => {
    if (activeTab === 'grading' && gradingData) {
      setInputBlocked(true);
    }
  }, [activeTab, gradingData]);
  // Add state for submit button
  const [canSubmitForGrading, setCanSubmitForGrading] = useState(false);
  const [hasSubmittedForGrading, setHasSubmittedForGrading] = useState(false);
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false);
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
  const [selectedPersona, setSelectedPersona] = useState<PersonaDetails | null>(null);
  const [showPersonaModal, setShowPersonaModal] = useState(false);
  const [showTimeoutModal, setShowTimeoutModal] = useState(false);
  const [showAllPersonasWarningModal, setShowAllPersonasWarningModal] = useState(false);
  const [showMentionDropdown, setShowMentionDropdown] = useState(false);
  const [mentionSelectedIndex, setMentionSelectedIndex] = useState(0);
  const [inputMode, setInputMode] = useState<'text' | 'voice'>('text');
  const [isInterfaceGreyed, setIsInterfaceGreyed] = useState(false);
  const [currentTypingPersona, setCurrentTypingPersona] = useState<string>('');
  
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
  ] as const;
  
  // Improved hash function for consistent color assignment
  const hashPersona = (name: string) => {
    // Normalize name: lowercase, trim, and remove extra spaces for consistency
    const normalized = name.toLowerCase().trim().replace(/\s+/g, ' ');
    let h = 0;
    for (let i = 0; i < normalized.length; i++) {
      h = ((h << 5) - h) + normalized.charCodeAt(i);
      h = h & h; // Convert to 32-bit integer
    }
    return Math.abs(h);
  };
  
  // Get unique color for each persona based on their name
  const getPersonaBubbleClasses = (personaName?: string) => {
    const key = (personaName || '').trim();
    if (!key || key === 'All Personas' || key === 'ChatOrchestrator' || key === 'System') {
      return 'bg-gray-50 border-gray-200'; // Default for system messages
    }
    // Use hash to consistently assign color to each persona
    const idx = hashPersona(key) % personaPalette.length;
    return personaPalette[idx];
  };

  // Lookup a persona's role by name - search across all scenes
  const getPersonaRole = (personaName?: string, messageSceneId?: number) => {
    const name = (personaName || '').trim();
    if (!name) return undefined;
    
    // First try to find in all_scenes_with_personas if available
    if (allScenesWithPersonas.length > 0) {
      for (const scene of allScenesWithPersonas) {
        const p = scene.personas.find(p => p.name === name);
        if (p) return p.role;
      }
    }
    
    // Fallback to current scene
    if (simulationData?.current_scene?.personas) {
      const p = simulationData.current_scene.personas.find(p => p.name === name);
      if (p) return p.role;
    }
    
    return undefined;
  };

  // Lookup a persona's image by name - search across all scenes
  const getPersonaImage = (personaName?: string, messageSceneId?: number) => {
    const name = (personaName || '').trim();
    if (!name) return undefined;
    
    // First try to find in all_scenes_with_personas if available
    if (allScenesWithPersonas.length > 0) {
      for (const scene of allScenesWithPersonas) {
        const p = scene.personas.find(p => p.name === name);
        if (p) {
          // Check image_url first, then fallback to profile_picture
          // Handle null, undefined, and empty strings properly
          const imageUrl = p.image_url || p.profile_picture || (p as any).imageUrl;
          if (imageUrl && typeof imageUrl === 'string' && imageUrl.trim().length > 0) {
            const processedUrl = getImageUrl(imageUrl);
            // Debug log in production to help diagnose issues
            if (process.env.NODE_ENV === 'production' && !processedUrl) {
              console.warn(`[PERSONA_IMAGE] Empty processed URL for ${name}:`, { imageUrl, processedUrl, persona: p });
            }
            return processedUrl;
          }
        }
      }
    }
    
    // Fallback to current scene
    if (simulationData?.current_scene?.personas) {
      const p = simulationData.current_scene.personas.find(p => p.name === name);
      if (p) {
        // Check image_url first, then fallback to profile_picture
        // Handle null, undefined, and empty strings properly
        const imageUrl = p.image_url || (p as any).profile_picture || (p as any).imageUrl;
        if (imageUrl && typeof imageUrl === 'string' && imageUrl.trim().length > 0) {
          const processedUrl = getImageUrl(imageUrl);
          // Debug log in production to help diagnose issues
          if (process.env.NODE_ENV === 'production' && !processedUrl) {
            console.warn(`[PERSONA_IMAGE] Empty processed URL for ${name} (fallback):`, { imageUrl, processedUrl, persona: p });
          }
          return processedUrl;
        }
      }
    }
    
    return undefined;
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
    
    // Also add scene personas to allScenesWithPersonas if not already present
    if (scene && scene.id && scene.personas) {
      setAllScenesWithPersonas(prev => {
        const exists = prev.some(s => s.id === scene.id);
        if (!exists) {
          // Map Persona to PersonaDetails format
          const mappedPersonas: PersonaDetails[] = scene.personas.map((p: Persona) => ({
            id: p.id,
            name: p.name,
            role: p.role,
            bio: p.background || '',
            personality: p.correlation || '',
            background: p.background || '',
            profile_picture: p.image_url,
            image_url: p.image_url
          }));
          return [...prev, {
            id: scene.id,
            personas: mappedPersonas
          }];
        }
        return prev;
      });
    }
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
  
  // Reset page state when component unmounts (user leaves page)
  useEffect(() => {
    return () => {
      // Cleanup: reset all state when leaving the page
      setMessages([])
      setSimulationData(null)
      setInput("")
      setIsLoading(false)
      setIsTyping(false)
      setGradingData(null)
      setShowGrading(false)
      setCanSubmitForGrading(false)
      setHasSubmittedForGrading(false)
      setSimulationComplete(false)
      setActiveTab('conversation')
    }
  }, [])
 
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
          simulation_id: scenarioId
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
      
      // Store all scenes with personas for persona lookup
      if (data.all_scenes && data.all_scenes.length > 0) {
        // Debug: Log persona image URLs in production
        if (process.env.NODE_ENV === 'production') {
          console.log('[SIMULATION_LOAD] All scenes with personas:', data.all_scenes.map((s: any) => ({
            scene: s.title,
            personas: s.personas.map((p: any) => ({ name: p.name, image_url: p.image_url }))
          })));
        }
        setAllScenesWithPersonas(data.all_scenes)
      } else {
        // Fallback: create from current scene if all_scenes not provided
        // Map Persona to PersonaDetails format
        const mappedPersonas: PersonaDetails[] = (data.current_scene.personas || []).map((p: Persona) => ({
          id: p.id,
          name: p.name,
          role: p.role,
          bio: p.background || '',
          personality: p.correlation || '',
          background: p.background || '',
          profile_picture: p.image_url,
          image_url: p.image_url
        }))
        setAllScenesWithPersonas([{
          id: data.current_scene.id,
          personas: mappedPersonas
        }])
      }
      
      // Load conversation history from database if available
      if (data.conversation_history && data.conversation_history.length > 0) {
        console.log("[DEBUG] Loading conversation history from database:", data.conversation_history.length, "messages");
        console.log("[DEBUG] Conversation history content:", data.conversation_history);
        const existingMessages = data.conversation_history.map((msg: any) => ({
          id: msg.id || nextMessageId(),
          sender: msg.sender || msg.sender_name || 'System',
          text: msg.text || msg.message_content || '',
          timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
          type: msg.type || msg.message_type || 'system',
          persona_name: msg.persona_name || (msg.type === 'ai_persona' || msg.message_type === 'ai_persona' ? (msg.sender || msg.sender_name) : undefined),
          persona_role: msg.persona_role,
          persona_id: msg.persona_id,
          scene_id: msg.scene_id
        }));
        setMessages(existingMessages);
      } else {
        // Fallback: Add welcome message locally if no conversation history
        console.log("[DEBUG] No conversation history found, adding welcome message locally");
        setMessages([{
          id: nextMessageId() as any,
          sender: "System",
          text: `🎯 **${data.simulation.title}**\n\n${data.simulation.description}\n\n**Your Role:** ${data.simulation.student_role}\n\n**Current Scene:** ${data.current_scene.title}\n\n**Instructions:**\n• Type **"begin"** to start the simulation\n• Type **"help"** for available commands\n• Use natural conversation to interact with personas`,
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
  const sendMessage = async (messageOverride?: string) => {
    const messageToSend = messageOverride ?? input;
    console.log("[DEBUG] sendMessage called. Input:", messageToSend);
    if (inputBlocked) return;
    if (!simulationData || !messageToSend.trim() || isLoading) return;

    const trimmedInput = messageToSend.trim();
    
    // Define command words once at the top of the function
    const commandWords = ['begin', 'help'];
    const isBeginCommand = trimmedInput === 'begin' && messageToSend.trim().split(/\s+/).length === 1;
    
    // Check for @all anywhere in the message (not just at start) - case-insensitive
    const allMatch1 = trimmedInput.match(/(^|\s)@all(\s|$)/i);
    const allMatch2 = trimmedInput.toLowerCase().includes('@all');
    const allMatch3 = /@all/i.test(trimmedInput);
    // Also treat multiple @mentions as an "all-style" multi-persona message
    const mentionCount = (trimmedInput.match(/@[\w().\-&]+/g) || []).filter((m: string) => m.toLowerCase() !== '@all').length;
    const isAllMention = allMatch1 !== null || allMatch2 || allMatch3 || mentionCount > 1;
    
    console.log("[DEBUG] @all detection:", {
      trimmedInput,
      allMatch1,
      allMatch2,
      allMatch3,
      isAllMention,
      simulationHasBegun
    });
    
    // Validate commands are one-word only
    const isSingleWordCommand = commandWords.includes(trimmedInput) && messageToSend.trim().split(/\s+/).length === 1;
    
    // Block persona mentions before simulation begins (unless it's a valid begin command)
    if (!simulationHasBegun && !isSingleWordCommand) {
      if (isAllMention || trimmedInput.includes('@')) {
        alert('Please type "begin" to start the simulation before mentioning personas.');
        return;
      }
    }
    
    // Handle @all or multi-mention - check turn count BEFORE sending
    // This MUST be checked before any persona validation
    if (isAllMention && simulationHasBegun) {
      console.log("[DEBUG] @all detected - checking turn count");
      // For @all use all personas count, for multi-mention use actual mention count
      const requiredTurns = (allMatch1 || allMatch2 || allMatch3) ? simulationData.current_scene.personas.length : mentionCount;
      const timeoutTurns = simulationData.current_scene.timeout_turns || 15;
      const totalTurnsIfUsed = turnCount + requiredTurns;
      
      console.log("[DEBUG] @all turn check:", {
        currentTurns: turnCount,
        requiredTurns,
        totalTurnsIfUsed,
        timeoutTurns,
        wouldExceed: totalTurnsIfUsed > timeoutTurns
      });
      
      // Check if using @all would exceed timeout turns
      if (totalTurnsIfUsed > timeoutTurns) {
        setShowAllPersonasWarningModal(true);
        return;
      }
      console.log("[DEBUG] @all validated - proceeding with message send");
      // @all is valid, continue with sending (skip persona validation below)
    } 
    
    // IMPORTANT: Check for @all in validation block as a safety net
    // This runs regardless of the first check to ensure @all is never blocked
    if (simulationHasBegun) {
      // Updated regex to capture special chars in persona names (dots, parentheses, hyphens, ampersands, etc.)
      const mentionMatch = trimmedInput.match(/@([\w().\-&]+)/);
      if (mentionMatch) {
        const mentionId = mentionMatch[1].toLowerCase().trim();
        
        // ABSOLUTE PRIORITY: Check for @all BEFORE any persona validation
        // This must be the first check in this block
        if (mentionId === 'all') {
          console.log("[DEBUG] @all detected in validation block (safety check) - handling @all logic");
          const personaCount = simulationData.current_scene.personas.length;
          const timeoutTurns = simulationData.current_scene.timeout_turns || 15;
          const requiredTurns = personaCount;
          const totalTurnsIfUsed = turnCount + requiredTurns;
          
          console.log("[DEBUG] @all turn check in validation block:", {
            currentTurns: turnCount,
            requiredTurns,
            totalTurnsIfUsed,
            timeoutTurns,
            wouldExceed: totalTurnsIfUsed > timeoutTurns
          });
          
          if (totalTurnsIfUsed > timeoutTurns) {
            setShowAllPersonasWarningModal(true);
            return;
          }
          // @all is valid, continue - skip all persona validation below
          console.log("[DEBUG] @all validated in validation block - proceeding with message");
          // Exit early - don't validate against persona names
        } else {
          // Only validate persona names if it's NOT @all
          console.log("[DEBUG] @mention validation (not @all):");
          console.log("  - Mentioned ID:", mentionId);
          
          // Restrict @mentions to only personas in the current scene
          // Generate both original and sanitized versions for backwards compatibility
          const validPersonaMentions: string[] = [];
          simulationData.current_scene.personas.forEach(p => {
            const original = p.name.toLowerCase().replace(/\s+/g, '_');
            const sanitized = p.name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
            validPersonaMentions.push(original);
            validPersonaMentions.push(sanitized);
          });
          console.log("  - Valid persona mentions:", validPersonaMentions);
          console.log("  - Current scene personas:", simulationData.current_scene.personas.map(p => p.name));
          
          // Also sanitize the mentionId for comparison
          const sanitizedMentionId = mentionId.replace(/[^a-z0-9_]/g, '');
          if (!validPersonaMentions.includes(mentionId) && !validPersonaMentions.includes(sanitizedMentionId)) {
            console.log("[DEBUG] Invalid mention detected - blocking message");
            alert('You can only @mention personas involved in this scene.');
            return;
          }
          console.log("[DEBUG] Valid mention - allowing message");
        }
      }
    }

    const userMessage: Message = {
      id: nextMessageId() as any,
      sender: "You",
      text: trimmedInput,
      timestamp: new Date(),
      type: 'user'
    };

    setMessages(prev => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    setIsTyping(true);
    
    // Extract mentioned persona name, otherwise default to ChatOrchestrator
    let typingPersonaName = "ChatOrchestrator"
    if (isAllMention) {
      typingPersonaName = "All Personas"
    } else {
      // Updated regex to capture special chars in persona names (dots, parentheses, hyphens, ampersands, etc.)
      const mentionMatch = trimmedInput.match(/@([\w().\-&]+)/);
      if (mentionMatch) {
        const mentionId = mentionMatch[1].toLowerCase()
        const sanitizedMentionId = mentionId.replace(/[^a-z0-9_]/g, '');
        const mentionedPersona = simulationData.current_scene.personas.find(
          p => {
            const original = p.name.toLowerCase().replace(/\s+/g, '_');
            const sanitized = original.replace(/[^a-z0-9_]/g, '');
            return original === mentionId || sanitized === mentionId || sanitized === sanitizedMentionId;
          }
        )
        if (mentionedPersona) {
          typingPersonaName = mentionedPersona.name
        }
      }
    }
    setTypingPersona(typingPersonaName);
    setCurrentTypingPersona(typingPersonaName);
    
    // Grey out interface will be controlled by isStreaming state;

    // Only increment turn count for non-command messages
    // Note: For @all, the backend will increment by the number of personas
    // For regular messages, increment by 1 (backend also increments, but frontend does it for immediate UI update)
    // Actually, let's let the backend handle all turn counting to avoid double-counting
    // We'll update the turn count from the backend response
    // Only reset grading flags for non-command messages
    const isCommand = commandWords.includes(trimmedInput) && input.trim().split(/\s+/).length === 1;
    
    if (!isCommand) {
      // Don't increment here - backend will handle it and return updated count
      setHasSubmittedForGrading(false);
      // Hide submit button when user sends a new message
      setCanSubmitForGrading(false);
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
      });

      if (!response.ok) {
        throw new Error(`Chat failed: ${response.status}`);
      }

      // Handle streaming response
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let streamedText = "";
      let chatData: any = {};
      
      // For @all messages, we'll create messages dynamically as each persona responds
      // For regular messages, create a single placeholder
      const isAllMessage = isAllMention;
      
      // Map to track streaming text and message IDs for each persona (for @all messages)
      const personaStreamTexts: { [key: string]: string } = {};
      const personaMessageIds: { [key: string]: any } = {};
      
      // Create a placeholder AI message for non-@all messages
      let aiMessageId: any = null;
      if (!isAllMessage) {
        aiMessageId = nextMessageId();
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
        setMessages(prev => [...prev, placeholderMessage]);
      }
      
      setIsTyping(false); // Hide typing indicator when streaming starts
      setIsStreaming(false); // Don't start streaming state yet - wait for first content
      setStreamingMessageId(aiMessageId); // Track the streaming message ID (null for @all)
      
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
                  
                  if (isAllMessage && parsed.persona_name) {
                    // @all message: Handle each persona separately
                    const personaKey = parsed.persona_name;
                    
                    // Initialize streaming text for this persona if not exists
                    if (!personaStreamTexts[personaKey]) {
                      personaStreamTexts[personaKey] = "";
                      // Create a new message for this persona
                      const personaMessageId = nextMessageId();
                      personaMessageIds[personaKey] = personaMessageId;
                      
                      const personaPlaceholder: any = {
                        id: personaMessageId,
                        sender: personaKey,
                        text: "",
                        timestamp: new Date(),
                        type: 'ai_persona',
                        persona_name: personaKey,
                        persona_id: parsed.persona_id,
                      };
                      setMessages(prev => [...prev, personaPlaceholder]);
                      setStreamingMessageId(personaMessageId);
                    }
                    
                    // Append streamed content to this persona's message
                    personaStreamTexts[personaKey] += parsed.content;
                    const currentText = personaStreamTexts[personaKey];
                    const currentMessageId = personaMessageIds[personaKey];
                    
                    // Use flushSync to force immediate render for streaming effect
                    flushSync(() => {
                      setMessages(prev => prev.map(msg => 
                        msg.id === currentMessageId 
                          ? { ...msg, text: currentText, sender: parsed.persona_name || msg.sender, persona_name: parsed.persona_name, persona_id: parsed.persona_id }
                          : msg
                      ));
                    });
                  } else if (!isAllMessage) {
                    // Regular message: Stream text for personas and non-begin orchestrator messages
                    if (typingPersonaName !== "ChatOrchestrator" || !isBeginCommand) {
                      // Append streamed content
                      streamedText += parsed.content;
                      // Use flushSync to force immediate render for streaming effect
                      flushSync(() => {
                        setMessages(prev => prev.map(msg => 
                          msg.id === aiMessageId 
                            ? { ...msg, text: streamedText, sender: (typingPersonaName === "ChatOrchestrator") ? "System" : (parsed.persona_name || msg.sender) }
                            : msg
                        ));
                      });
                    }
                  }
                }
                
                if (parsed.done) {
                  if (isAllMessage && parsed.persona_name) {
                    // @all message: Finalize this specific persona's message
                    const personaKey = parsed.persona_name;
                    const personaMessageId = personaMessageIds[personaKey];
                    const finalText = parsed.full_content || personaStreamTexts[personaKey] || "";
                    
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
                      ));
                    }
                    
                    // Update chatData with the last persona's data
                    chatData = parsed;
                    
                    // Show loading screen if scene is completed
                    if (parsed.scene_completed) {
                      setIsSceneTransitioning(true);
                    }
                    
                    // After all personas have finished streaming, clear streaming state
                    // We'll do this after the loop completes
                  } else if (!isAllMessage) {
                    // Regular message: Final metadata received - streaming finished
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
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }
        }
      }
      
      // Final cleanup for @all messages
      if (isAllMessage) {
        setIsStreaming(false);
        setStreamingMessageId(null);
      }
      
      // Now process the final chatData metadata
        
        // If this is the first "begin" response, add scene introduction as separate message
        if (isBeginCommand) {
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
          
          // Add null checks to prevent crashes
          if (simulationData?.current_scene?.id) {
            setCompletedScenes(prev => {
              // Always add the current scene if not already present
              if (!prev.includes(simulationData.current_scene.id)) {
                return [...prev, simulationData.current_scene.id];
              }
              return prev;
            });
            addSceneIfMissing(simulationData.current_scene);
          }

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
                // Validate nextSceneData before using it
                if (!nextSceneData || !nextSceneData.id) {
                  throw new Error('Invalid next scene data received');
                }
                
                // Use the fresh scene data from backend
                setSimulationData(prev => {
                  if (!prev) {
                    console.error("[ERROR] simulationData is null during scene transition");
                    return null;
                  }
                  return {
                    ...prev,
                    current_scene: nextSceneData,
                    simulation_status: "in_progress" // Preserve simulation status across scenes
                  };
                });
                setTurnCount(0);
                setEditorCode('');
                setInputBlocked(false);
                setCanSubmitForGrading(true); // Enable submit button after scene transition
                addSceneIfMissing(nextSceneData);
                // Add scene transition message (don't filter existing messages)
                console.log("[DEBUG] Scene transition - adding new scene intro for scene:", nextSceneData.title || 'Unknown');
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
                
                // Save the scene intro message to the database (only if simulationData exists)
                if (simulationData?.user_progress_id) {
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
                }
                
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
                setMessages(prev => {
                  if (!prev || !Array.isArray(prev)) return [];
                  return prev.filter(m => m && m.id !== sceneLoadingId);
                });
                // Fallback completion message
                const completionMessage: Message = {
                  id: nextMessageId() as any,
                  sender: "System",
                  text: "⚠️ Scene transition error. Please refresh the page or try again.",
                  timestamp: new Date(),
                  type: 'system'
                };
                setMessages(prev => {
                  if (!prev || !Array.isArray(prev)) return [completionMessage];
                  return [...prev, completionMessage];
                });
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
            fetchGradingData().then(() => {
              setGradingInProgress(false);
              // Reset button states after grading completes
              setHasSubmittedForGrading(false);
              setInputBlocked(true); // Keep input blocked since simulation is complete
            });
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

  // Handle Enter key (legacy - kept for compatibility)
  const handleKeyPress = (e: React.KeyboardEvent) => {
    // Now handled by handleKeyDown
  }

  // If no simulation is active, show scenario selection
  if (!simulationData) {
    return (
      <div className="min-h-screen bg-atmospheric relative pattern-dots flex">
        <RoleBasedSidebar currentPath="/professor/test-simulations" />
        <div className="flex-1 ml-20 p-8 animate-page-enter">
          <div className="max-w-6xl mx-auto py-8 stagger-1 animate-fade-scale">
            <div className="text-center mb-10">
              <h1 className="text-4xl font-bold mb-3 tracking-tight">Linear Simulation Experience</h1>
              <p className="text-gray-600 text-lg">
                Select a scenario to begin your interactive simulation with AI personas
              </p>
            </div>
            
            <div className="stagger-2 animate-fade-scale">
              <ScenarioSelector onScenarioSelect={startSimulation} />
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Main simulation interface
  // Calculate totalScenes correctly - use the total_scenes from backend
  const totalScenes = simulationData?.simulation?.total_scenes || 
                     (allScenes.length > 0 ? allScenes.length : 4); // Default to 4 scenes

  // --- FEEDBACK/GRADING INTERFACE LOGIC (finalized) ---
  // Function to fetch grading data after simulation
  const fetchGradingData = async () => {
    if (!simulationData) return;
    const res = await apiClient.apiRequest(`/api/simulation/grade?user_progress_id=${simulationData.user_progress_id}`);
    if (res.ok) {
      const data = await res.json();
      setGradingData(data);
      setActiveTab('grading');
    }
  };

  // In sendMessage, after the last scene is completed, trigger grading
  // (Insert this logic in your sendMessage or scene progression handler)
  // if (chatData.scene_completed && !chatData.next_scene_id) {
  //   fetchGradingData();
  // }

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
          simulation_id: simulationData.simulation.id
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
            setEditorCode('');
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
          fetchGradingData().then(() => {
            setGradingInProgress(false);
            // Reset button states after grading completes
            setHasSubmittedForGrading(false);
            setInputBlocked(true); // Keep input blocked since simulation is complete
          });
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
    <div className="h-screen bg-atmospheric relative pattern-dots flex">
      <RoleBasedSidebar currentPath="/professor/test-simulations" />
      
      <div className="flex-1 ml-20 flex flex-col animate-page-enter">
        {/* Top Navigation Bar */}
        <div className="bg-white/80 backdrop-blur-sm px-6 py-4 border-b border-gray-200/60 shadow-sm stagger-1 animate-fade-scale">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setSimulationData(null)}
                className="text-gray-600 hover:text-gray-900"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <h1 className="text-lg font-semibold text-gray-900 truncate">
                {simulationData.simulation.title}
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
                    <div className="bg-gradient-to-br from-emerald-600 to-emerald-700 rounded-lg p-3 border border-emerald-500/30 shadow-lg">
                      <div className="flex items-center gap-2 mb-1.5">
                        <Target className="w-3.5 h-3.5 text-white" />
                        <span className="font-semibold text-xs text-white uppercase tracking-wide" style={{ fontFamily: "'Sora', sans-serif" }}>OBJECTIVE</span>
                      </div>
                      <p className="text-xs text-white/95 leading-snug" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
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
                                background: persona.background,
                                image_url: persona.image_url
                              });
                              setShowPersonaModal(true);
                            }}
                          >
                            <div className="flex items-center gap-1.5 min-w-0 w-full">
                              <div className="w-5 h-5 bg-gray-600 rounded-full flex items-center justify-center flex-shrink-0 overflow-hidden">
                                {persona.image_url ? (
                                  <img src={getImageUrl(persona.image_url)} alt={persona.name} className="object-cover w-full h-full" />
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

                {/* Submit for Grading Button - Hide when simulation is complete and graded */}
                {(canSubmitForGrading || (inputBlocked && !simulationComplete)) && !simulationComplete ? (
                  <div className="mt-2 flex-shrink-0 animate-fade-in-up stagger-4">
                    <Button
                      onClick={() => setShowSubmitConfirm(true)}
                      disabled={inputBlocked || hasSubmittedForGrading}
                      className="btn-gradient-green w-full text-white text-sm font-semibold relative overflow-hidden shadow-md hover:shadow-lg transition-all"
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
                <div className={`flex flex-1 min-h-0 ${simulationData?.current_scene?.scene_type === 'code_challenge' ? '' : 'flex-col'}`}>
                {/* Chat half (or full width when not code_challenge) */}
                <div className={`flex flex-col min-h-0 ${simulationData?.current_scene?.scene_type === 'code_challenge' ? 'w-1/2 min-w-0 border-r border-gray-200' : 'flex-1'}`}>
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
                            {/* Hide avatar for system, orchestrator, user messages, and grading progress messages */}
                            {message.type !== 'system' && 
                             message.type !== 'orchestrator' && 
                             message.type !== 'user' &&
                             !(message as any).gradingInProgress && 
                             !(message as any).sceneLoading && (
                              <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 text-[11px] flex items-center justify-center text-white font-semibold shadow-sm overflow-hidden">
                                {(() => {
                                  // Use persona_name from message if available, otherwise try to extract from sender
                                  const personaName = (message as any).persona_name || (message.type === 'ai_persona' ? message.sender : null);
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
                            {'persona_name' in message && message.type === 'ai_persona' && (message as any).persona_name && (
                              <Badge variant="secondary" className="text-xs bg-white/90 backdrop-blur-sm text-gray-800 border border-gray-300/50 shadow-sm font-medium">
                                {('persona_role' in message && (message as any).persona_role) || getPersonaRole((message as any).persona_name || message.sender, (message as any).scene_id) || (message as any).persona_name}
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
                              })
                            )}
                            {message.showViewGrading && (
                              <div className="flex flex-col items-center mt-3">
                                <Button
                                  variant="default"
                                  onClick={() => {
                                    if (gradingData) {
                                      setActiveTab('grading');
                                    } else {
                                      setGradingInProgress(true);
                                      fetchGradingData().then(() => setGradingInProgress(false));
                                    }
                                  }}
                                  className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
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
                              const shouldShow = /@[^\s]*$/.test(e.target.value);
                              setShowMentionDropdown(shouldShow);
                              if (shouldShow) setMentionSelectedIndex(0); // Reset selection when dropdown opens
                            }}
                            onKeyDown={handleKeyDown}
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
                                {simulationData.current_scene.personas.map((persona, index) => (
                                  <div
                                    key={persona.id}
                                    className={`sim-mention-item flex items-center gap-2 p-2 rounded cursor-pointer ${index === mentionSelectedIndex ? 'sim-mention-item-selected' : ''}`}
                                    onClick={() => {
                                      const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_');
                                      setInput(input.replace(/@[^@]*$/, `@${mentionId} `));
                                      setShowMentionDropdown(false);
                                      setMentionSelectedIndex(0);
                                    }}
                                    onMouseEnter={() => setMentionSelectedIndex(index)}
                                  >
                                    <div className="w-7 h-7 bg-gradient-to-br from-blue-400 to-blue-600 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm overflow-hidden">
                                      {persona.image_url ? (
                                        <img src={getImageUrl(persona.image_url)} alt={persona.name} className="object-cover w-full h-full" />
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
                          onClick={() => sendMessage()}
                          disabled={inputBlocked || isLoading || isTyping || !input.trim() || simulationComplete || gradingInProgress}
                          className="sim-send-button px-4 py-2 text-white"
                        >
                          {isLoading ? (
                            <RefreshCw className="w-4 h-4 animate-spin" />
                          ) : (
                            <Send className="w-4 h-4" />
                          )}
                        </Button>
                      </div>
                      
                      {/* Quick Action Buttons */}
                      <div className="flex gap-2 flex-wrap">
                        {!simulationHasBegun && (
                          <Button
                            size="lg"
                            variant="default"
                            onClick={() => sendMessage("begin")}
                            disabled={inputBlocked || isLoading || isTyping || simulationComplete || gradingInProgress}
                            className="bg-green-600 hover:bg-green-700 text-white font-semibold px-6 animate-pulse"
                          >
                            <PlayCircle className="w-5 h-5 mr-2" />
                            Begin Simulation
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => sendMessage("help")}
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
                                const base = input.trimEnd();
                                setInput(base ? `${base} @all ` : `@all `);
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
                                  const base = input.trimEnd();
                                  setInput(base ? `${base} @${mentionId} ` : `@${mentionId} `);
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
                </div>
                {/* Code panel (right half, only for code_challenge) */}
                {simulationData?.current_scene?.scene_type === 'code_challenge' && (
                  <div className="w-1/2 min-w-0 flex flex-col bg-[#0f172a] min-h-0 overflow-hidden">
                    {/* Editor / Resources sub-tabs */}
                    <div className="flex bg-[#0f172a] border-b border-[#1e293b] flex-shrink-0">
                      <button
                        onClick={() => setCodeTab('editor')}
                        className={`px-4 py-2.5 text-sm font-medium flex items-center gap-1.5 border-b-2 transition-colors ${
                          codeTab === 'editor'
                            ? 'text-gray-100 border-blue-500'
                            : 'text-gray-500 border-transparent hover:text-gray-300'
                        }`}
                      >
                        <PlayCircle className="w-4 h-4" />
                        Editor
                      </button>
                      <button
                        onClick={() => setCodeTab('resources')}
                        className={`px-4 py-2.5 text-sm font-medium flex items-center gap-1.5 border-b-2 transition-colors ${
                          codeTab === 'resources'
                            ? 'text-gray-100 border-blue-500'
                            : 'text-gray-500 border-transparent hover:text-gray-300'
                        }`}
                      >
                        <BookOpen className="w-4 h-4" />
                        Resources
                        {simulationData?.current_scene?.data_files?.length ? (
                          <span className="bg-[#334155] text-gray-400 text-[10px] px-1.5 py-0.5 rounded-full font-semibold">{simulationData.current_scene.data_files.length}</span>
                        ) : null}
                      </button>
                    </div>
                    {/* Sub-tab content */}
                    <div className="flex-1 min-h-0 overflow-hidden">
                      {codeTab === 'editor' ? (
                        <CodeEditor
                          userProgressId={simulationData.user_progress_id}
                          sceneId={simulationData.current_scene.id}
                          starterCode={simulationData.current_scene.starter_code || ''}
                          sandboxAvailable={!!simulationData?.sandbox_id}
                          code={editorCode !== '' ? editorCode : (simulationData.current_scene.starter_code ?? '')}
                          onCodeChange={setEditorCode}
                          personas={simulationData.current_scene.personas.map(p => ({ id: p.id, name: p.name }))}
                          onSubmitToChat={(_code, formatted) => {
                            sendMessage(formatted)
                          }}
                        />
                      ) : (
                        <ResourcesPanel
                          dataFiles={simulationData.current_scene.data_files || []}
                          referenceFiles={simulationData.current_scene.reference_files || []}
                          sceneObjective={simulationData.current_scene.user_goal}
                          dataPath="/home/daytona/data/"
                        />
                      )}
                    </div>
                  </div>
                )}
                </div>
              ) : activeTab === 'grading' ? (
                gradingData ? (
                  <GradingTabView gradingData={gradingData} />
                ) : (
                  <div className="flex-1 overflow-y-auto p-6">
                    <div className="text-center text-gray-500 py-12">
                      <Trophy className="w-16 h-16 mx-auto mb-4 text-gray-400" />
                      <p className="text-lg font-medium text-gray-600" style={{ fontFamily: "'Sora', sans-serif" }}>
                        Complete simulation for grading
                      </p>
                      <p className="text-sm text-gray-500 mt-2" style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}>
                        Finish all scenes to receive comprehensive feedback and assessment
                      </p>
                    </div>
                  </div>
                )
              ) : (
                <div className="flex-1 overflow-y-auto p-6">
                  {simulationData?.simulation?.case_study_url ? (
                    <div className="w-full h-full flex flex-col">
                      <div className="mb-4 flex justify-between items-center">
                        <h3 className="text-lg font-semibold">Case Study Document</h3>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => window.open(simulationData.simulation.case_study_url, '_blank')}
                        >
                          <ArrowRight className="w-4 h-4 mr-2" />
                          Open in New Tab
                        </Button>
                      </div>
                      <div className="flex-1 border rounded-lg overflow-hidden bg-gray-50">
                        <iframe
                          src={simulationData.simulation.case_study_url}
                          className="w-full h-full min-h-[600px] border-0"
                          title="Case Study PDF"
                          onError={(e) => {
                            console.error("Failed to load PDF in iframe:", e);
                          }}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="text-center text-gray-500">
                      <BookOpen className="w-12 h-12 mx-auto mb-4" />
                      <p>Case Study content will be displayed here</p>
                      <p className="text-sm text-gray-400 mt-2">No case study PDF available for this simulation</p>
                    </div>
                  )}
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
            const base = input.trimEnd();
            setInput(base ? `${base} @${mentionId} ` : `@${mentionId} `);
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
      </div>

      <AlertDialog open={showSubmitConfirm} onOpenChange={setShowSubmitConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Submit for Grading?</AlertDialogTitle>
            <AlertDialogDescription>
              {(() => {
                const timeoutTurns = simulationData?.current_scene?.timeout_turns ?? 15
                const remaining = Math.max(0, timeoutTurns - turnCount)
                return remaining > 0
                  ? `You have ${remaining} turn${remaining === 1 ? '' : 's'} remaining. Submitting now will end your simulation and you will not be able to continue. This action cannot be undone.`
                  : 'This will end your simulation and submit it for grading. This action cannot be undone.'
              })()}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleSubmitForGrading}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              Yes, Submit for Grading
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}