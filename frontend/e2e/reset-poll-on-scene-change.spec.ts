/**
 * Tests that the CodeEditor resets its wake/poll state when the scene changes
 * (issue #316).
 *
 * Uses the test harness at /test/code-editor which mounts CodeEditor with
 * a "Next Scene" button to change sceneId.
 */

import { test, expect } from '@playwright/test'

test.describe('CodeEditor — reset poll state on scene change', () => {
  test('scene change clears waking banner and stops polling', async ({ page }) => {
    let pollCount = 0

    // Intercept execute-code to return a "stopped" sandbox → triggers polling
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

    // Intercept sandbox-state polling — always return 'archived' to keep polling
    await page.route('**/api/proxy/api/simulation/sandbox-state*', async (route) => {
      pollCount++
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

    // Click Run — triggers stopped → waking banner + polling
    await page.click('button:has-text("Run")')
    await expect(page.locator('text=sandbox is waking up')).toBeVisible({ timeout: 5000 })

    // Record poll count before scene switch
    const pollsBefore = pollCount

    // Switch scene — should clear waking state
    await page.click('[data-testid="switch-scene"]')

    // Waking banner should disappear
    await expect(page.locator('text=sandbox is waking up')).not.toBeVisible({ timeout: 3000 })

    // Wait to verify polling has stopped (no new polls after scene change)
    const pollsAtSwitch = pollCount
    await page.waitForTimeout(7000) // Wait longer than the 5s poll interval
    expect(pollCount).toBe(pollsAtSwitch)

    // Verify at least one poll happened before scene switch
    expect(pollsBefore).toBeGreaterThan(0)
  })

  test('scene change clears destroyed banner', async ({ page }) => {
    // Intercept execute-code to return destroyed sandbox
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

    // Click Run — triggers destroyed banner
    await page.click('button:has-text("Run")')
    await expect(page.locator('text=sandbox session has expired')).toBeVisible({ timeout: 5000 })

    // Switch scene — destroyed banner should clear
    await page.click('[data-testid="switch-scene"]')
    await expect(page.locator('text=sandbox session has expired')).not.toBeVisible({ timeout: 3000 })
  })

  test('scene change clears output and error from previous scene', async ({ page }) => {
    let callCount = 0

    await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
      callCount++
      if (callCount === 1) {
        // First run: success with output
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            output: 'scene-1-output',
            error: null,
            sandbox_state: 'started',
          }),
        })
      } else {
        // After scene change: different output
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            output: 'scene-2-output',
            error: null,
            sandbox_state: 'started',
          }),
        })
      }
    })

    await page.goto('/test/code-editor')
    await page.waitForLoadState('networkidle')

    // Run code on scene 1
    await page.click('button:has-text("Run")')
    await expect(page.locator('text=scene-1-output')).toBeVisible({ timeout: 5000 })

    // Switch scene — previous output should be cleared
    await page.click('[data-testid="switch-scene"]')
    await expect(page.locator('text=scene-1-output')).not.toBeVisible({ timeout: 3000 })
  })
})
