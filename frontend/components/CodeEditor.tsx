"use client"

import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { StreamLanguage } from '@codemirror/language'
import { r } from '@codemirror/legacy-modes/mode/r'
import { oneDark } from '@codemirror/theme-one-dark'
import { Play, Send, Loader2, ChevronDown, Users, User, RefreshCw } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

type SandboxStatus = 'ready' | 'waking' | 'destroyed' | 'error'

interface SubmitTarget {
  type: 'all' | 'persona'
  name: string
  /** The @mention id used in the message, e.g. "all" or "eleni_makri" */
  mentionId: string
}

interface CodeEditorPersona {
  id: number
  name: string
}

interface CodeEditorProps {
  userProgressId: number
  sceneId: number
  starterCode?: string
  onSubmitToChat: (code: string, output: string) => void
  sandboxAvailable?: boolean
  /** Controlled code value — pass this + onCodeChange to persist code across tab switches */
  code?: string
  onCodeChange?: (code: string) => void
  /** Available personas for Submit & Discuss target selection */
  personas?: CodeEditorPersona[]
  /** Programming language for syntax highlighting and execution (default: 'python') */
  language?: 'python' | 'r'
}

export default function CodeEditor({
  userProgressId,
  sceneId,
  starterCode = '',
  onSubmitToChat,
  sandboxAvailable = true,
  code: controlledCode,
  onCodeChange,
  personas = [],
  language = 'python',
}: CodeEditorProps) {
  const langExtension = useMemo(
    () => (language === 'r' ? StreamLanguage.define(r) : python()),
    [language],
  )
  const langLabel = language === 'r' ? 'R' : 'Python'
  const codeFence = language === 'r' ? 'r' : 'python'

  const [internalCode, setInternalCode] = useState(starterCode)
  const code = controlledCode !== undefined ? controlledCode : internalCode
  const setCode = onCodeChange || setInternalCode
  const [output, setOutput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
  const [sandboxStatus, setSandboxStatus] = useState<SandboxStatus>('ready')
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Reset uncontrolled editor content when the scene or starter code changes
  useEffect(() => {
    if (controlledCode === undefined) {
      setInternalCode(starterCode ?? '')
    }
    setOutput('')
    setError(null)
  }, [sceneId, starterCode, controlledCode])
  const [showTargetDropdown, setShowTargetDropdown] = useState(false)
  const [submitTarget, setSubmitTarget] = useState<SubmitTarget>({
    type: 'all',
    name: '@all',
    mentionId: 'all',
  })
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowTargetDropdown(false)
      }
    }
    if (showTargetDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showTargetDropdown])

  // Build target list: @all + each persona
  const targets: SubmitTarget[] = [
    { type: 'all', name: '@all', mentionId: 'all' },
    ...personas.map((p) => ({
      type: 'persona' as const,
      name: p.name,
      mentionId: p.name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, ''),
    })),
  ]

  // Stop polling for sandbox state
  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
  }, [])

  // Poll /sandbox-state until the sandbox is started, then re-run code
  const startPollingAndRetry = useCallback((pendingCode: string) => {
    setSandboxStatus('waking')
    stopPolling()

    const TERMINAL_STATES = new Set(['sandbox_destroyed', 'sandbox_error_unrecoverable', 'destroyed', 'error'])

    pollIntervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(
          `/api/proxy/api/simulation/sandbox-state?user_progress_id=${userProgressId}`,
          { credentials: 'include' }
        )
        if (!res.ok) return
        const data = await res.json()

        // Terminal error — stop polling and surface the error
        if (TERMINAL_STATES.has(data.sandbox_state) || TERMINAL_STATES.has(data.error)) {
          stopPolling()
          setSandboxStatus('destroyed')
          return
        }

        if (data.sandbox_state === 'started') {
          stopPolling()
          setSandboxStatus('ready')
          // Sandbox is up — automatically re-execute the code
          setIsRunning(true)
          setError(null)
          try {
            const execRes = await fetch('/api/proxy/api/simulation/execute-code', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              credentials: 'include',
              body: JSON.stringify({ user_progress_id: userProgressId, code: pendingCode, scene_id: sceneId, language }),
            })
            const execResult = await execRes.json()
            if (execResult.success) {
              setOutput(execResult.output)
            } else {
              setError(execResult.error || 'Unknown error')
              if (execResult.output) setOutput(execResult.output)
            }
          } finally {
            setIsRunning(false)
          }
        }
      } catch {
        // Polling errors are non-fatal — keep trying
      }
    }, 5000)
  }, [userProgressId, sceneId, language, stopPolling])

  // Clean up polling on unmount
  useEffect(() => () => stopPolling(), [stopPolling])

  const runCode = useCallback(async () => {
    setIsRunning(true)
    setError(null)
    setOutput('')
    setSandboxStatus('ready')

    try {
      const response = await fetch('/api/proxy/api/simulation/execute-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          user_progress_id: userProgressId,
          code,
          scene_id: sceneId,
          language,
        }),
      })

      const result = await response.json()

      if (result.success) {
        setOutput(result.output)
      } else {
        const state: string | undefined = result.sandbox_state
        const errStr: string = result.error || ''

        // Detect transient sandbox connectivity errors (WebSocket rejection, etc.)
        // even if the backend didn't categorize them with a sandbox_state.
        const isTransientError =
          !state &&
          /websocket|http 400|connection refused|connect call failed|server rejected/i.test(errStr)

        if (state === 'destroyed' || state === 'error_unrecoverable') {
          setSandboxStatus('destroyed')
          setError(null)
        } else if (state === 'archived' || state === 'stopped' || isTransientError) {
          // Backend couldn't restart inline or sandbox is transiently unreachable — poll and retry
          startPollingAndRetry(code)
        } else {
          setError(errStr || 'Unknown error')
          if (result.output) setOutput(result.output)
        }
      }
    } catch {
      setError('Failed to connect to code execution service')
    } finally {
      setIsRunning(false)
    }
  }, [code, userProgressId, sceneId, language, startPollingAndRetry])

  const submitToChat = useCallback(() => {
    const mention = `@${submitTarget.mentionId}`
    let formatted: string
    if (output || error) {
      const combined = output || error || ''
      formatted = `${mention} Here are my results:\n\`\`\`${codeFence}\n${code}\n\`\`\`\n\nOutput:\n\`\`\`\n${combined}\n\`\`\`\n\nLet me know if this looks right.`
    } else {
      // Sandbox offline — share code for discussion without execution output
      formatted = `${mention} Here is my code (sandbox unavailable, could not run):\n\`\`\`${codeFence}\n${code}\n\`\`\``
    }
    onSubmitToChat(code, formatted)
  }, [code, output, error, onSubmitToChat, submitTarget, codeFence])

  const isDisabled = !sandboxAvailable
  // Allow submission when there's output/error OR when sandbox is offline and code has been written
  const canSubmit = !!(output || error || (isDisabled && code.trim()))

  return (
    <div className="flex flex-col h-full bg-gray-900">
      {/* Editor Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">{langLabel} Editor</span>
        <div className="flex gap-2">
          <button
            onClick={runCode}
            disabled={isRunning || isDisabled || !code.trim() || sandboxStatus === 'waking'}
            title={
              isDisabled
                ? 'Code execution is temporarily unavailable'
                : sandboxStatus === 'waking'
                ? 'Sandbox is starting up — your code will run automatically'
                : undefined
            }
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-md transition-colors"
          >
            {isRunning || sandboxStatus === 'waking' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {sandboxStatus === 'waking' ? 'Starting...' : isRunning ? 'Running...' : 'Run'}
          </button>

          {/* Submit & Discuss split button */}
          <div className="relative" ref={dropdownRef}>
            <div className="flex">
              <button
                onClick={submitToChat}
                disabled={!canSubmit}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-l-md transition-colors border-r border-blue-500/50"
              >
                <Send className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Submit to</span>
                <span className="font-medium">
                  {submitTarget.type === 'all' ? '@all' : `@${submitTarget.name.split(' ')[0]}`}
                </span>
              </button>
              <button
                onClick={() => setShowTargetDropdown((v) => !v)}
                disabled={!canSubmit}
                className="flex items-center px-1.5 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-r-md transition-colors"
              >
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Dropdown */}
            {showTargetDropdown && (
              <div className="absolute right-0 top-full mt-1 w-56 bg-gray-800 border border-gray-600 rounded-lg shadow-xl z-50 py-1 overflow-hidden">
                <div className="px-3 py-1.5 text-[10px] text-gray-500 uppercase tracking-wider font-semibold">
                  Send results to...
                </div>
                {targets.map((target) => (
                  <button
                    key={target.mentionId}
                    onClick={() => {
                      setSubmitTarget(target)
                      setShowTargetDropdown(false)
                    }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${
                      submitTarget.mentionId === target.mentionId
                        ? 'bg-blue-600/30 text-blue-300'
                        : 'text-gray-300 hover:bg-gray-700'
                    }`}
                  >
                    {target.type === 'all' ? (
                      <Users className="w-4 h-4 text-blue-400 flex-shrink-0" />
                    ) : (
                      <User className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    )}
                    <span className="truncate">
                      {target.type === 'all' ? '@all — All Personas' : target.name}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Offline Banner */}
      {isDisabled && (
        <div className="px-4 py-2 bg-amber-900/60 text-amber-200 text-xs border-b border-amber-800 flex-shrink-0">
          Code execution is temporarily unavailable. You can still write code and discuss with personas.
        </div>
      )}

      {/* Sandbox waking up banner */}
      {sandboxStatus === 'waking' && (
        <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
          <Alert className="py-2 bg-blue-950/60 border-blue-800 text-blue-200">
            <Loader2 className="h-4 w-4 animate-spin text-blue-400" />
            <AlertDescription className="text-xs text-blue-200">
              Your sandbox is waking up after being idle — your code will run automatically once it&apos;s ready (usually under 30s).
            </AlertDescription>
          </Alert>
        </div>
      )}

      {/* Sandbox destroyed / expired banner */}
      {sandboxStatus === 'destroyed' && (
        <div className="px-3 py-2 border-b border-gray-700 flex-shrink-0">
          <Alert variant="destructive" className="py-2 flex items-center justify-between gap-2">
            <AlertDescription className="text-xs">
              Your sandbox session has expired. Please reload the page to start a fresh session.
            </AlertDescription>
            <Button
              size="sm"
              variant="destructive"
              className="h-7 text-xs flex-shrink-0"
              onClick={() => window.location.reload()}
            >
              <RefreshCw className="w-3 h-3 mr-1" />
              Reload
            </Button>
          </Alert>
        </div>
      )}

      {/* Code Editor */}
      <div className="flex-1 overflow-auto min-h-0">
        <CodeMirror
          value={code}
          onChange={(value) => setCode(value)}
          extensions={[langExtension]}
          theme={oneDark}
          height="100%"
          basicSetup={{
            lineNumbers: true,
            foldGutter: true,
            autocompletion: true,
          }}
        />
      </div>

      {/* Output Panel */}
      <div className="h-1/3 border-t border-gray-700 bg-black overflow-auto flex-shrink-0">
        <div className="px-4 py-2 bg-gray-800 border-b border-gray-700">
          <span className="text-xs text-gray-400 font-medium uppercase tracking-wide">
            Output
          </span>
        </div>
        <div className="p-4 font-mono text-sm">
          {sandboxStatus === 'waking' && !isRunning && (
            <span className="text-blue-400 flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Waiting for sandbox to start...
            </span>
          )}
          {isRunning && sandboxStatus !== 'waking' && (
            <span className="text-yellow-400">Running code...</span>
          )}
          {output && (
            <pre className="text-green-400 whitespace-pre-wrap">{output}</pre>
          )}
          {error && (
            <pre className="text-red-400 whitespace-pre-wrap">{error}</pre>
          )}
          {!isRunning && !output && !error && sandboxStatus === 'ready' && (
            <span className="text-gray-500">Run your code to see output here</span>
          )}
        </div>
      </div>
    </div>
  )
}
