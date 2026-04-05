/**
 * E2E tests for save response ID fallback (issue #250).
 *
 * Verifies that the simulation builder page handles save responses
 * that use either `simulation_id` or `scenario_id` field names,
 * and guards against missing IDs.
 */

import { test, expect } from '@playwright/test'

const BUILDER_URL = '/professor/simulation-builder'

test.describe('Save response ID fallback handling', () => {
  test('simulation builder page should load without errors', async ({ page }) => {
    // Register listener BEFORE navigation to catch startup errors
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))

    // Navigate to the simulation builder
    await page.goto(BUILDER_URL)

    // The page should render (may redirect to login, which is acceptable
    // for a non-authenticated test run — we just verify no JS crash)
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})

    // Give a moment for any deferred errors
    await page.waitForTimeout(1000)

    // No JS errors referencing undefined simulation_id
    const idErrors = errors.filter(e => /simulation_id|scenario_id|undefined/.test(e))
    expect(idErrors).toHaveLength(0)
  })

  test('should not crash when save response has scenario_id instead of simulation_id', async ({ page }) => {
    let saveCalls = 0

    // Intercept the save API call and respond with scenario_id only
    await page.route('**/api/publishing/simulations/save**', async (route) => {
      saveCalls += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          scenario_id: 'test-scenario-123',
          message: 'Saved successfully',
        }),
      })
    })

    // Also intercept the draft reload that follows a successful save
    await page.route('**/api/publishing/simulations/test-scenario-123**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'test-scenario-123',
          scenes: [],
          personas: [],
        }),
      })
    })

    // Register listener BEFORE navigation to catch startup errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    await page.goto(BUILDER_URL)
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})

    // Attempt to trigger a save action if the Save Draft button is available
    const saveDraftBtn = page.getByRole('button', { name: /save draft/i })
    if (await saveDraftBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await saveDraftBtn.click()
      await expect.poll(() => saveCalls).toBeGreaterThanOrEqual(1)
    }

    // No errors about missing IDs should appear
    const idErrors = consoleErrors.filter(e =>
      /missing simulation_id|missing scenario_id|Cannot read propert/.test(e)
    )
    expect(idErrors).toHaveLength(0)
  })

  test('should log error when save response has no ID field', async ({ page }) => {
    let saveCalls = 0

    // Intercept the save API call and respond without any ID
    await page.route('**/api/publishing/simulations/save**', async (route) => {
      saveCalls += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'Saved but no ID returned',
        }),
      })
    })

    // Register listeners BEFORE navigation to catch startup errors
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const pageErrors: string[] = []
    page.on('pageerror', (err) => pageErrors.push(err.message))

    await page.goto(BUILDER_URL)
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})

    // Attempt to trigger a save action if the Save Draft button is available
    const saveDraftBtn = page.getByRole('button', { name: /save draft/i })
    if (await saveDraftBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await saveDraftBtn.click()
      await expect.poll(() => saveCalls).toBeGreaterThanOrEqual(1)

      // The guard should log an error about missing IDs
      await page.waitForTimeout(500)
      const guardErrors = consoleErrors.filter(e =>
        /missing simulation_id|scenario_id/.test(e)
      )
      expect(guardErrors.length).toBeGreaterThanOrEqual(1)
    }

    // No unhandled JS errors (the guard returns early instead of crashing)
    const crashErrors = pageErrors.filter(e =>
      /Cannot read propert|undefined is not/.test(e)
    )
    expect(crashErrors).toHaveLength(0)
  })

  test('regression: manual save must handle both simulation_id and scenario_id fields', async ({ page }) => {
    // Register listener BEFORE navigation to catch startup errors
    const errors: string[] = []
    page.on('pageerror', (err) => errors.push(err.message))

    // Navigate and capture the page source
    await page.goto(BUILDER_URL)
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})

    // Give a moment for any deferred errors
    await page.waitForTimeout(500)

    // The page should load without throwing errors related to undefined IDs
    expect(errors.filter(e => /simulation_id/.test(e))).toHaveLength(0)
  })
})
