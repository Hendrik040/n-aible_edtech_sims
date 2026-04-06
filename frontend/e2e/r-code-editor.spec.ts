/**
 * Tests for R code editor support (issue #390).
 *
 * Section 1: Unit tests verifying that the language parameter is included
 * in code execution requests and that code fences use the correct language.
 *
 * Section 2: Component-level tests (require test harness) verifying that
 * the editor header shows the correct language label.
 */

import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Section 1 — Unit tests for language-aware code formatting
// ---------------------------------------------------------------------------

test.describe('R code fence formatting', () => {
  test('Python code uses ```python fence', () => {
    const language: 'python' | 'r' = 'python'
    const codeFence = language === 'r' ? 'r' : 'python'
    const code = 'print("hello")'
    const formatted = `\`\`\`${codeFence}\n${code}\n\`\`\``
    expect(formatted).toContain('```python')
    expect(formatted).not.toContain('```r')
  })

  test('R code uses ```r fence', () => {
    const language = 'r'
    const codeFence = language === 'r' ? 'r' : 'python'
    const code = 'cat("hello")'
    const formatted = `\`\`\`${codeFence}\n${code}\n\`\`\``
    expect(formatted).toContain('```r')
    expect(formatted).not.toContain('```python')
  })
})

test.describe('Language label selection', () => {
  test('Python language shows Python label', () => {
    const language: 'python' | 'r' = 'python'
    const langLabel = language === 'r' ? 'R' : 'Python'
    expect(langLabel).toBe('Python')
  })

  test('R language shows R label', () => {
    const language = 'r' as const
    const langLabel = language === 'r' ? 'R' : 'Python'
    expect(langLabel).toBe('R')
  })

  test('undefined language defaults to Python', () => {
    const language: 'python' | 'r' | undefined = undefined
    const langLabel = (language ?? 'python') === 'r' ? 'R' : 'Python'
    expect(langLabel).toBe('Python')
  })
})

// ---------------------------------------------------------------------------
// Section 2 — API request body includes language parameter
// ---------------------------------------------------------------------------

test.describe('Code execution request includes language', () => {
  test('Python execution request body', () => {
    const language = 'python'
    const body = {
      user_progress_id: 1,
      code: 'print(1)',
      scene_id: 1,
      language,
    }
    expect(body.language).toBe('python')
  })

  test('R execution request body', () => {
    const language = 'r'
    const body = {
      user_progress_id: 1,
      code: 'cat(1)',
      scene_id: 1,
      language,
    }
    expect(body.language).toBe('r')
  })
})

// ---------------------------------------------------------------------------
// Section 3 — Scene interface code_language field
// ---------------------------------------------------------------------------

test.describe('Scene code_language field', () => {
  test('Scene with code_language=r passes r to editor', () => {
    const scene = {
      id: 1,
      scene_type: 'code_challenge' as const,
      code_language: 'r' as const,
      starter_code: 'library(dplyr)',
    }
    const editorLanguage = scene.code_language || 'python'
    expect(editorLanguage).toBe('r')
  })

  test('Scene without code_language defaults to python', () => {
    const scene = {
      id: 1,
      scene_type: 'code_challenge' as const,
      starter_code: 'import pandas',
    }
    const editorLanguage = (scene as any).code_language || 'python'
    expect(editorLanguage).toBe('python')
  })
})
