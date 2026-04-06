"use client"

/**
 * Test harness for CodeEditor component — used by Playwright E2E tests only.
 * Not linked from any navigation; only accessible at /test/code-editor.
 */

import { useState } from 'react'
import CodeEditor from '@/components/CodeEditor'

export default function CodeEditorTestPage() {
  const [sceneId, setSceneId] = useState(1)

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '4px 8px', background: '#222', display: 'flex', gap: 8, alignItems: 'center' }}>
        <span style={{ color: '#aaa', fontSize: 12 }}>Scene: {sceneId}</span>
        <button
          data-testid="switch-scene"
          onClick={() => setSceneId((prev) => prev + 1)}
          style={{ padding: '2px 8px', fontSize: 12, cursor: 'pointer' }}
        >
          Next Scene
        </button>
      </div>
      <div style={{ flex: 1 }}>
        <CodeEditor
          userProgressId={1}
          sceneId={sceneId}
          starterCode={'print("hello world")'}
          onSubmitToChat={() => {}}
          sandboxAvailable={true}
          personas={[{ id: 1, name: 'Test Persona' }]}
        />
      </div>
    </div>
  )
}
