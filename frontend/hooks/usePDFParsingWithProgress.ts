"use client"

import { useState, useCallback } from 'react'
import { buildApiUrl } from '@/lib/api'

interface ParsePDFWithProgressOptions {
  file: File
  contextFiles?: File[]
  saveToDb?: boolean
}

interface ParsePDFResult {
  success: boolean
  data?: any
  session_id?: string
  message?: string
  error?: string
}

export function usePDFParsingWithProgress() {
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<any>(null)

  const parsePDFWithProgress = useCallback(async ({
    file,
    contextFiles = [],
    saveToDb = false
  }: ParsePDFWithProgressOptions): Promise<ParsePDFResult> => {
    setIsLoading(true)
    setError(null)
    setResult(null)

    try {
      // Generate a unique session ID for this parsing request
      const sessionId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2) + Date.now().toString(36)
      setSessionId(sessionId)
      
      const formData = new FormData()
      formData.append('file', file)
      
      // Add context files if provided
      contextFiles.forEach((contextFile) => {
        formData.append('context_files', contextFile)
      })

      // Add save_to_db parameter
      formData.append('save_to_db', saveToDb.toString())
      
      // Add session_id parameter
      formData.append('session_id', sessionId)

      // Development-only logging (disabled in production to prevent information leakage)
      const isDev = process.env.NODE_ENV === 'development'
      
      if (isDev) {
        console.log('🚀 Starting PDF parsing with progress tracking...')
        console.log('📄 File size:', file.size, 'bytes')
        console.log('📚 Context files count:', contextFiles.length)
      }

      const url = buildApiUrl('/parse-pdf-with-progress')

      const response = await fetch(url, {
        method: 'POST',
        body: formData,
        credentials: 'include',
      })

      if (isDev) {
        console.log('📡 Response status:', response.status, response.statusText)
      }

      if (!response.ok) {
        const errorText = await response.text()
        // Only log detailed error in development
        if (isDev) {
          console.error('❌ PDF parsing request failed:', response.status, response.statusText)
        }
        throw new Error(`Failed to process PDF (HTTP ${response.status})`)
      }

      const resultData: ParsePDFResult = await response.json()
      
      if (isDev) {
        console.log('✅ PDF parsing request accepted:', resultData)
      }
      
      // If we get a session_id back, the parsing has started and we should start polling
      if (resultData.session_id) {
        setSessionId(resultData.session_id)
        if (isDev) {
          console.log('🔄 Starting progress polling for session:', resultData.session_id)
        }
        // The progress tracking component will handle the polling
        return {
          success: true,
          session_id: resultData.session_id,
          message: resultData.message || 'PDF parsing started'
        }
      }
      
      if (isDev) {
        console.log('✅ PDF parsing completed successfully')
      }

      if (resultData.success) {
        setSessionId(resultData.session_id || null)
        setResult(resultData.data)
        return resultData
      } else {
        throw new Error(resultData.error || 'PDF parsing failed')
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred'
      console.error('PDF parsing error:', errorMessage)
      setError(errorMessage)
      return {
        success: false,
        error: errorMessage
      }
    } finally {
      setIsLoading(false)
    }
  }, [])

  const reset = useCallback(() => {
    setIsLoading(false)
    setSessionId(null)
    setError(null)
    setResult(null)
  }, [])

  return {
    parsePDFWithProgress,
    isLoading,
    sessionId,
    error,
    result,
    reset
  }
}

