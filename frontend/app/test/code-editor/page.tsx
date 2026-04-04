"use client"

/**
 * Test harness for CodeEditor component — used by Playwright E2E tests only.
 * Not linked from any navigation; only accessible at /test/code-editor.
 */

import CodeEditor from '@/components/CodeEditor'

export default function CodeEditorTestPage() {
  return (
    <div style={{ height: '100vh' }}>
      <CodeEditor
        userProgressId={1}
        sceneId={1}
        starterCode={'print("hello world")'}
        onSubmitToChat={() => {}}
        sandboxAvailable={true}
        personas={[{ id: 1, name: 'Test Persona' }]}
      />
    </div>
  )
}
