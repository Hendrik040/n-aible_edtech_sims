"use client"

import React, { useState, useCallback, useRef, useEffect } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import { Play, Send, Loader2, ChevronDown, Users, User } from 'lucide-react'

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
}: CodeEditorProps) {
  const [internalCode, setInternalCode] = useState(starterCode)
  const code = controlledCode !== undefined ? controlledCode : internalCode
  const setCode = onCodeChange || setInternalCode
  const [output, setOutput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)
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
      mentionId: p.name.toLowerCase().replace(/\s+/g, '_'),
    })),
  ]

  const runCode = useCallback(async () => {
    setIsRunning(true)
    setError(null)
    setOutput('')

    try {
      const response = await fetch('/api/proxy/api/simulation/execute-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          user_progress_id: userProgressId,
          code,
          scene_id: sceneId,
        }),
      })

      const result = await response.json()

      if (result.success) {
        setOutput(result.output)
      } else {
        setError(result.error || 'Unknown error')
        if (result.output) setOutput(result.output)
      }
    } catch {
      setError('Failed to connect to code execution service')
    } finally {
      setIsRunning(false)
    }
  }, [code, userProgressId, sceneId])

  const submitToChat = useCallback(() => {
    const combined = output || error || ''
    const mention = `@${submitTarget.mentionId}`
    const formatted = `${mention} Here are my results:\n\`\`\`python\n${code}\n\`\`\`\n\nOutput:\n\`\`\`\n${combined}\n\`\`\`\n\nLet me know if this looks right.`
    onSubmitToChat(code, formatted)
  }, [code, output, error, onSubmitToChat, submitTarget])

  const isDisabled = !sandboxAvailable
  const canSubmit = !!(output || error)

  return (
    <div className="flex flex-col h-full bg-gray-900">
      {/* Editor Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700 flex-shrink-0">
        <span className="text-sm text-gray-300 font-medium">Python Editor</span>
        <div className="flex gap-2">
          <button
            onClick={runCode}
            disabled={isRunning || isDisabled || !code.trim()}
            title={isDisabled ? 'Code execution is temporarily unavailable' : undefined}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-green-600 hover:bg-green-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-md transition-colors"
          >
            {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {isRunning ? 'Running...' : 'Run'}
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

      {/* Code Editor */}
      <div className="flex-1 overflow-auto min-h-0">
        <CodeMirror
          value={code}
          onChange={(value) => setCode(value)}
          extensions={[python()]}
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
          {isRunning && (
            <span className="text-yellow-400">Running code...</span>
          )}
          {output && (
            <pre className="text-green-400 whitespace-pre-wrap">{output}</pre>
          )}
          {error && (
            <pre className="text-red-400 whitespace-pre-wrap">{error}</pre>
          )}
          {!isRunning && !output && !error && (
            <span className="text-gray-500">Run your code to see output here</span>
          )}
        </div>
      </div>
    </div>
  )
}
