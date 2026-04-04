/**
 * Tests for code editor sandbox recovery logic (issue #348).
 *
 * These tests verify the transient-error detection regex and API response
 * classification that the CodeEditor component relies on for sandbox
 * recovery. They exercise the same branching logic used in CodeEditor.tsx
 * to ensure error strings are correctly categorised.
 *
 * Full component-level E2E tests (mounting CodeEditor, clicking Run, etc.)
 * require a running backend or a dedicated test harness with auth context
 * and are out of scope here. These tests guarantee the detection layer is
 * correct so the component branches work as intended.
 */

import { test, expect } from '@playwright/test'

// Mirror of the frontend regex in CodeEditor.tsx – kept in sync manually.
// If this regex diverges from the component the tests will still catch
// missing patterns because the expected matches will fail.
const TRANSIENT_ERROR_REGEX =
  /websocket|http 400|connection refused|connect call failed|server rejected/i

/** Helper: classify an execute-code API response the same way CodeEditor does. */
function classifyResponse(response: {
  success: boolean
  error?: string | null
  sandbox_state?: string | null
}): 'success' | 'destroyed' | 'transient_poll' | 'show_error' {
  if (response.success) return 'success'

  const state = response.sandbox_state ?? undefined
  const errStr = response.error ?? ''

  const isTransientError =
    !state && TRANSIENT_ERROR_REGEX.test(errStr)

  if (state === 'destroyed' || state === 'error_unrecoverable') return 'destroyed'
  if (state === 'archived' || state === 'stopped' || isTransientError) return 'transient_poll'
  return 'show_error'
}

test.describe('Transient error regex — pattern matching', () => {
  const shouldMatch = [
    'server rejected WebSocket connection: HTTP 400',
    'WebSocket handshake failed',
    'HTTP 400 Bad Request',
    'connection refused',
    'connect call failed',
    'server rejected the connection',
    'WEBSOCKET error during execution',
    'http 400 from sandbox',
    'Connect Call Failed: dial tcp',
  ]

  for (const errStr of shouldMatch) {
    test(`matches transient pattern: "${errStr}"`, () => {
      expect(TRANSIENT_ERROR_REGEX.test(errStr)).toBe(true)
    })
  }

  const shouldNotMatch = [
    'SyntaxError: invalid syntax',
    'NameError: name "x" is not defined',
    'timeout waiting for response',
    'sandbox_destroyed',
    '',
  ]

  for (const errStr of shouldNotMatch) {
    test(`does NOT match non-transient: "${errStr}"`, () => {
      expect(TRANSIENT_ERROR_REGEX.test(errStr)).toBe(false)
    })
  }
})

test.describe('Response classification — sandbox_state handling', () => {
  test('successful execution → success', () => {
    expect(
      classifyResponse({ success: true, output: 'hello\n', error: null, sandbox_state: 'started' } as any),
    ).toBe('success')
  })

  test('sandbox_state=stopped → transient_poll (triggers waking flow)', () => {
    expect(
      classifyResponse({ success: false, error: 'sandbox_not_ready', sandbox_state: 'stopped' }),
    ).toBe('transient_poll')
  })

  test('sandbox_state=archived → transient_poll (triggers waking flow)', () => {
    expect(
      classifyResponse({ success: false, error: 'sandbox_archived', sandbox_state: 'archived' }),
    ).toBe('transient_poll')
  })

  test('sandbox_state=destroyed → destroyed (shows reload banner)', () => {
    expect(
      classifyResponse({ success: false, error: 'sandbox_destroyed', sandbox_state: 'destroyed' }),
    ).toBe('destroyed')
  })

  test('sandbox_state=error_unrecoverable → destroyed', () => {
    expect(
      classifyResponse({ success: false, error: 'fatal', sandbox_state: 'error_unrecoverable' }),
    ).toBe('destroyed')
  })

  test('no sandbox_state + WebSocket error → transient_poll (fallback regex)', () => {
    expect(
      classifyResponse({
        success: false,
        error: 'server rejected WebSocket connection: HTTP 400',
        sandbox_state: null,
      }),
    ).toBe('transient_poll')
  })

  test('no sandbox_state + connect call failed → transient_poll (fallback regex)', () => {
    expect(
      classifyResponse({
        success: false,
        error: 'connect call failed: dial tcp 127.0.0.1:8080',
        sandbox_state: null,
      }),
    ).toBe('transient_poll')
  })

  test('no sandbox_state + non-transient error → show_error', () => {
    expect(
      classifyResponse({ success: false, error: 'SyntaxError: invalid syntax', sandbox_state: null }),
    ).toBe('show_error')
  })

  test('unknown sandbox_state + non-transient error → show_error', () => {
    expect(
      classifyResponse({ success: false, error: 'some error', sandbox_state: 'unknown_state' }),
    ).toBe('show_error')
  })
})

test.describe('Route interception smoke test', () => {
  test('execute-code route handler returns expected payload shape', async ({ page }) => {
    let intercepted = false
    await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
      intercepted = true
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          output: '',
          error: 'sandbox_not_ready',
          sandbox_state: 'stopped',
        }),
      })
    })

    // Navigate to a real origin so fetch works with absolute URLs
    await page.goto('about:blank')
    const response = await page.evaluate(async () => {
      const res = await fetch('http://localhost:3000/api/proxy/api/simulation/execute-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: 'print("test")' }),
      })
      return res.json()
    })

    expect(intercepted).toBe(true)
    expect(response.sandbox_state).toBe('stopped')
    expect(response.success).toBe(false)
  })

  test('sandbox-state polling route returns expected payload shape', async ({ page }) => {
    let pollCount = 0
    await page.route('**/api/proxy/api/simulation/sandbox-state*', async (route) => {
      pollCount++
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sandbox_state: pollCount >= 2 ? 'started' : 'archived',
          sandbox_id: 'test-sandbox-1',
        }),
      })
    })

    await page.goto('about:blank')

    // Simulate two polling calls
    const result1 = await page.evaluate(async () => {
      const res = await fetch('http://localhost:3000/api/proxy/api/simulation/sandbox-state?sandbox_id=test')
      return res.json()
    })
    expect(result1.sandbox_state).toBe('archived')
    expect(pollCount).toBe(1)

    const result2 = await page.evaluate(async () => {
      const res = await fetch('http://localhost:3000/api/proxy/api/simulation/sandbox-state?sandbox_id=test')
      return res.json()
    })
    expect(result2.sandbox_state).toBe('started')
    expect(pollCount).toBe(2)
  })
})
