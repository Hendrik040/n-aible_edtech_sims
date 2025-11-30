"use client"

import React, { useState, useEffect, useRef } from 'react'
import { Progress } from '@/components/ui/progress'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { CheckCircle, AlertCircle, Loader2, Upload, Cpu, Brain } from 'lucide-react'

interface ProgressData {
  type: 'progress_update' | 'completion' | 'error' | 'field_update'
  session_id: string
  overall_progress: number
  current_stage: string
  stage_progress: number
  message: string
  details?: any
  timestamp: number
  result?: any
  error?: string
  field_name?: string
  field_value?: any
}

interface PDFProgressTrackerProps {
  sessionId: string
  onComplete?: (result: any) => void
  onError?: (error: string) => void
  onFieldUpdate?: (fieldName: string, fieldValue: any) => void
  className?: string
}

export default function PDFProgressTracker({ 
  sessionId, 
  onComplete, 
  onError, 
  onFieldUpdate,
  className = "" 
}: PDFProgressTrackerProps) {
  const [progressData, setProgressData] = useState<ProgressData | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttempts = useRef(0)
  const maxReconnectAttempts = 5

  const connectWebSocket = () => {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const backendHost = process.env.NEXT_PUBLIC_API_URL?.replace(/^https?:\/\//, '') || 'localhost:8000'
      const wsUrl = `${protocol}//${backendHost}/ws/pdf-progress/${sessionId}`
      
      console.log('Connecting to WebSocket:', wsUrl)
      
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        console.log('WebSocket connected')
        setIsConnected(true)
        setConnectionError(null)
        reconnectAttempts.current = 0
        
        // Send ping to keep connection alive
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }))
          } else {
            clearInterval(pingInterval)
          }
        }, 30000) // Ping every 30 seconds
      }

      ws.onmessage = (event) => {
        try {
          const data: ProgressData = JSON.parse(event.data)
          console.log('Received progress update:', data)
          console.log('Progress data type:', data.type)
          console.log('Overall progress:', data.overall_progress)
          console.log('Current stage:', data.current_stage)
          console.log('Stage progress:', data.stage_progress)
          
          setProgressData(data)
          
          if (data.type === 'completion') {
            onComplete?.(data.result)
          } else if (data.type === 'error') {
            onError?.(data.error || 'Unknown error occurred')
          } else if (data.type === 'field_update' && data.field_name) {
            console.log('Field update received:', data.field_name, data.field_value)
            onFieldUpdate?.(data.field_name, data.field_value)
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }

      ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason)
        setIsConnected(false)
        
        // Attempt to reconnect if not a normal closure
        if (event.code !== 1000 && reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 10000)
          
          console.log(`Attempting to reconnect in ${delay}ms (attempt ${reconnectAttempts.current}/${maxReconnectAttempts})`)
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connectWebSocket()
          }, delay)
        } else if (reconnectAttempts.current >= maxReconnectAttempts) {
          setConnectionError('Failed to maintain connection to progress tracker')
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setConnectionError('Connection error occurred')
      }
    } catch (error) {
      console.error('Error creating WebSocket:', error)
      setConnectionError('Failed to create connection')
    }
  }

  useEffect(() => {
    if (sessionId) {
      connectWebSocket()
    }

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [sessionId])

  const getStageIcon = (stage: string) => {
    switch (stage) {
      case 'upload':
        return <Upload className="h-4 w-4" />
      case 'processing':
        return <Cpu className="h-4 w-4" />
      case 'ai_analysis':
        return <Brain className="h-4 w-4" />
      default:
        return <Loader2 className="h-4 w-4 animate-spin" />
    }
  }

  const getStageLabel = (stage: string) => {
    switch (stage) {
      case 'upload':
        return 'Uploading Files'
      case 'processing':
        return 'Processing Document'
      case 'ai_analysis':
        return 'AI Analysis'
      default:
        return 'Processing'
    }
  }

  const getStageColor = (stage: string) => {
    switch (stage) {
      case 'upload':
        return 'text-slate-600'
      case 'processing':
        return 'text-orange-600'
      case 'ai_analysis':
        return 'text-purple-600'
      default:
        return 'text-gray-600'
    }
  }

  const getStageBgColor = (stage: string) => {
    switch (stage) {
      case 'upload':
        return 'bg-gradient-to-br from-slate-100 to-slate-50'
      case 'processing':
        return 'bg-gradient-to-br from-orange-100 to-orange-50'
      case 'ai_analysis':
        return 'bg-gradient-to-br from-purple-100 to-purple-50'
      default:
        return 'bg-gradient-to-br from-gray-100 to-gray-50'
    }
  }

  if (connectionError) {
    return (
      <Alert className={`card-elevated bg-red-50/90 backdrop-blur-sm border border-red-200/60 rounded-xl shadow-md ${className} animate-fade-scale`}>
        <AlertCircle className="h-4 w-4 text-red-600" />
        <AlertDescription className="text-red-800 font-medium">
          {connectionError}
        </AlertDescription>
      </Alert>
    )
  }

  if (!progressData) {
    return (
      <Card className={`card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${className} animate-fade-scale`}>
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center shadow-sm">
              <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
            </div>
            <div>
              <span className="text-sm font-semibold text-gray-900 block">
                {isConnected ? 'Waiting for progress updates...' : 'Connecting...'}
              </span>
              <span className="text-xs text-gray-500 mt-0.5 block">Establishing connection</span>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={`card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${className} animate-fade-scale`}>
      <CardHeader className="pb-3 border-b border-gray-200/60">
        <CardTitle className="text-lg font-bold flex items-center gap-3 tracking-tight">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-sm ${
            progressData.type === 'completion' 
              ? 'bg-gradient-to-br from-green-100 to-green-50' 
              : progressData.type === 'error' 
              ? 'bg-gradient-to-br from-red-100 to-red-50'
              : 'bg-gradient-to-br from-blue-100 to-blue-50'
          }`}>
            {progressData.type === 'completion' ? (
              <CheckCircle className="h-5 w-5 text-green-600" />
            ) : progressData.type === 'error' ? (
              <AlertCircle className="h-5 w-5 text-red-600" />
            ) : (
              <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
            )}
          </div>
          <span className="text-gray-900">PDF Processing Progress</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        {/* Overall Progress */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-sm font-semibold text-gray-900">Overall Progress</span>
            <span className="text-sm font-bold text-gray-700">
              {progressData.overall_progress}%
            </span>
          </div>
          <Progress 
            value={progressData.overall_progress} 
            className="h-2.5"
          />
        </div>

        {/* Current Stage */}
        <div className="space-y-2 p-4 bg-gray-50/50 rounded-xl border border-gray-200/60">
          <div className="flex items-center gap-3 mb-2">
            <div className={`w-8 h-8 ${getStageBgColor(progressData.current_stage)} rounded-lg flex items-center justify-center shadow-sm`}>
              <span className={getStageColor(progressData.current_stage)}>
                {getStageIcon(progressData.current_stage)}
              </span>
            </div>
            <div className="flex-1">
              <span className={`text-sm font-semibold ${getStageColor(progressData.current_stage)} block`}>
                {getStageLabel(progressData.current_stage)}
              </span>
              <span className="text-xs text-gray-600 mt-0.5 block">
                {progressData.message}
              </span>
            </div>
            <span className={`text-xs font-bold ${getStageColor(progressData.current_stage)}`}>
              {progressData.stage_progress}%
            </span>
          </div>
          <Progress 
            value={progressData.stage_progress} 
            className="h-1.5"
          />
        </div>

        {/* Additional Details */}
        {progressData.details && Object.keys(progressData.details).length > 0 && (
          <div className="text-xs text-gray-600 bg-gray-50/50 rounded-lg p-3 border border-gray-200/60">
            {progressData.details.job_id && (
              <div className="font-medium">Job ID: <span className="font-mono">{progressData.details.job_id}</span></div>
            )}
            {progressData.details.attempt && (
              <div className="mt-1">Attempt: <span className="font-semibold">{progressData.details.attempt}</span></div>
            )}
          </div>
        )}

        {/* Connection Status */}
        <div className="flex items-center gap-2 text-xs text-gray-600 pt-2 border-t border-gray-200/60">
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
          <span className="font-medium">{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </CardContent>
    </Card>
  )
}
