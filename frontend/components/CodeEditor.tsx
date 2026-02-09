"use client"

import React, { useState, useCallback } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import { Play, Send, Loader2 } from 'lucide-react'

interface CodeEditorProps {
  userProgressId: number
  sceneId: number
  starterCode?: string
  onSubmitToChat: (code: string, output: string) => void
  sandboxAvailable?: boolean
}

export default function CodeEditor({
  userProgressId,
  sceneId,
  starterCode = '',
  onSubmitToChat,
  sandboxAvailable = true,
}: CodeEditorProps) {
  const [code, setCode] = useState(starterCode)
  const [output, setOutput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)

  const runCode = useCallback(async () => {
    setIsRunning(true)
    setError(null)
    setOutput('')

    try {
      const response = await fetch('/api/proxy/simulation/execute-code', {
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
    const formatted = `Here are my results:\n\`\`\`python\n${code}\n\`\`\`\n\nOutput:\n\`\`\`\n${combined}\n\`\`\`\n\nLet me know if this looks right.`
    onSubmitToChat(code, formatted)
  }, [code, output, error, onSubmitToChat])

  const isDisabled = !sandboxAvailable

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
          <button
            onClick={submitToChat}
            disabled={!output && !error}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-md transition-colors"
          >
            <Send className="w-4 h-4" />
            Submit &amp; Discuss
          </button>
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
