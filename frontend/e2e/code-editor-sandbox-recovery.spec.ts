/**
 * Tests for code editor sandbox recovery logic (issue #348).
 *
 * Section 1: Unit tests for the transient-error detection regex and API
 * response classification that the CodeEditor component relies on.
 *
 * Section 2: Component-level E2E tests using a test harness page at
 * /test/code-editor that mounts CodeEditor with mock props. These tests
 * intercept API routes to simulate sandbox states and verify the actual
 * recovery UI (waking banner, destroyed banner, error display).
 */

import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Section 1 — Unit tests (no browser navigation needed)
// ---------------------------------------------------------------------------

// Mirror of the frontend regex in CodeEditor.tsx – kept in sync manually.
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

  if (state === 'destroyed' || state === 'error_unrecoverable' || (state === 'error' && errStr === 'sandbox_error_unrecoverable')) return 'destroyed'
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

  test('sandbox_state=error + sandbox_error_unrecoverable → destroyed', () => {
    expect(
      classifyResponse({ success: false, error: 'sandbox_error_unrecoverable', sandbox_state: 'error' }),
    ).toBe('destroyed')
  })

  test('sandbox_state=error + other error → show_error (not destroyed)', () => {
    expect(
      classifyResponse({ success: false, error: 'some_other_error', sandbox_state: 'error' }),
    ).toBe('show_error')
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

// ---------------------------------------------------------------------------
// Section 2 — Component E2E tests (render CodeEditor via test harness)
// ---------------------------------------------------------------------------

test.describe('CodeEditor component — sandbox recovery UI', () => {
  test('transient error (stopped) triggers waking banner', async ({ page }) => {
    // Intercept execute-code to return a "stopped" sandbox state
    await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
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

    // Intercept sandbox-state polling to return 'archived' (keeps polling)
    await page.route('**/api/proxy/api/simulation/sandbox-state*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sandbox_state: 'archived',
          sandbox_id: 'test-sandbox-1',
        }),
      })
    })

    await page.goto('/test/code-editor')
    await page.waitForLoadState('networkidle')

    // Click the Run button
    await page.click('button:has-text("Run")')

    // The waking banner should appear
    await expect(page.locator('text=sandbox is waking up')).toBeVisible({ timeout: 5000 })
  })

  test('destroyed sandbox shows reload banner', async ({ page }) => {
    // Intercept execute-code to return a "destroyed" sandbox state
    await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          output: '',
          error: 'sandbox_destroyed',
          sandbox_state: 'destroyed',
        }),
      })
    })

    await page.goto('/test/code-editor')
    await page.waitForLoadState('networkidle')

    // Click the Run button
    await page.click('button:has-text("Run")')

    // The destroyed/expired banner with Reload button should appear
    await expect(page.locator('text=sandbox session has expired')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('button:has-text("Reload")')).toBeVisible()
  })

  test('sandbox_state=error with sandbox_error_unrecoverable shows reload banner', async ({ page }) => {
    await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          output: '',
          error: 'sandbox_error_unrecoverable',
          sandbox_state: 'error',
        }),
      })
    })

    await page.goto('/test/code-editor')
    await page.waitForLoadState('networkidle')

    await page.click('button:has-text("Run")')

    // Should show destroyed/expired banner, not a generic error
    await expect(page.locator('text=sandbox session has expired')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('button:has-text("Reload")')).toBeVisible()
  })

  test('non-transient error displays error message', async ({ page }) => {
    await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          output: '',
          error: 'SyntaxError: invalid syntax',
          sandbox_state: null,
        }),
      })
    })

    await page.goto('/test/code-editor')
    await page.waitForLoadState('networkidle')

    // Click the Run button
    await page.click('button:has-text("Run")')

    // Should display the error, NOT the waking banner
    await expect(page.locator('text=SyntaxError: invalid syntax')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('text=sandbox is waking up')).not.toBeVisible()
  })

  test('WebSocket fallback error (no sandbox_state) triggers waking banner', async ({ page }) => {
    // Return a raw WebSocket error without sandbox_state — the frontend regex should catch it
    await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          output: '',
          error: 'server rejected WebSocket connection: HTTP 400',
          sandbox_state: null,
        }),
      })
    })

    await page.route('**/api/proxy/api/simulation/sandbox-state*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sandbox_state: 'archived',
          sandbox_id: 'test-sandbox-1',
        }),
      })
    })

    await page.goto('/test/code-editor')
    await page.waitForLoadState('networkidle')

    // Click the Run button
    await page.click('button:has-text("Run")')

    // The waking banner should appear (fallback regex matched)
    await expect(page.locator('text=sandbox is waking up')).toBeVisible({ timeout: 5000 })
  })

  test('polling resolves when sandbox becomes started and re-executes code', async ({ page }) => {
    let executeCount = 0

    await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
      executeCount++
      if (executeCount === 1) {
        // First call: sandbox is stopped
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
      } else {
        // Second call (after sandbox wakes): success
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            output: 'hello world\n',
            error: null,
            sandbox_state: 'started',
          }),
        })
      }
    })

    let pollCount = 0
    await page.route('**/api/proxy/api/simulation/sandbox-state*', async (route) => {
      pollCount++
      // First poll: still waking; second poll: started
      const state = pollCount >= 2 ? 'started' : 'archived'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sandbox_state: state,
          sandbox_id: 'test-sandbox-1',
        }),
      })
    })

    await page.goto('/test/code-editor')
    await page.waitForLoadState('networkidle')

    // Click Run — triggers stopped → polling → started → re-execute
    await page.click('button:has-text("Run")')

    // Waking banner should appear
    await expect(page.locator('text=sandbox is waking up')).toBeVisible({ timeout: 5000 })

    // After polling resolves, the output should appear (re-execution succeeded)
    await expect(page.locator('text=hello world')).toBeVisible({ timeout: 15000 })

    // Verify polling actually happened
    expect(pollCount).toBeGreaterThan(0)
    // Verify code was executed twice (initial + retry after wake)
    expect(executeCount).toBe(2)
  })
})
