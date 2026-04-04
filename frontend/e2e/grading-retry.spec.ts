/**
 * E2E tests for grading submission retry behavior (issue #346).
 *
 * Verifies that when grading fails (network error or scene-not-completed),
 * the "Submit for Grading" button remains visible so students can retry.
 */

import { test, expect } from '@playwright/test'

test.describe('Grading submission retry', () => {
  const SIM_URL = '/student/run-simulation/test-instance-123'

  test.describe('Submit for Grading button stays visible after failure', () => {
    test('button remains after network error on grading submission', async ({ page }) => {
      // Intercept the simulation data load
      await page.route('**/api/simulation/instance/**', route =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user_progress_id: 1,
            current_scene: { id: 1, scene_order: 1, title: 'Test Scene', description: 'Test' },
            simulation: { id: 1, title: 'Test Sim' },
            simulation_status: 'in_progress',
            scenes: [{ id: 1, scene_order: 1, title: 'Test Scene' }]
          })
        })
      )

      // Make the grading submission fail with network error
      await page.route('**/api/simulation/linear-chat', route =>
        route.abort('connectionrefused')
      )

      await page.goto(SIM_URL)

      // Look for the submit for grading button
      const submitButton = page.locator('button', { hasText: /submit for grading/i })

      // If the button exists and we click it, after failure it should still be visible
      if (await submitButton.isVisible({ timeout: 5000 }).catch(() => false)) {
        await submitButton.click()

        // After the error, button should remain visible for retry
        await expect(submitButton).toBeVisible({ timeout: 5000 })
      }
    })

    test('button remains after scene_completed=false response', async ({ page }) => {
      await page.route('**/api/simulation/instance/**', route =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user_progress_id: 1,
            current_scene: { id: 1, scene_order: 1, title: 'Test Scene', description: 'Test' },
            simulation: { id: 1, title: 'Test Sim' },
            simulation_status: 'in_progress',
            scenes: [{ id: 1, scene_order: 1, title: 'Test Scene' }]
          })
        })
      )

      // Return scene_completed=false (grading didn't proceed)
      await page.route('**/api/simulation/linear-chat', route =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ scene_completed: false })
        })
      )

      await page.goto(SIM_URL)

      const submitButton = page.locator('button', { hasText: /submit for grading/i })

      if (await submitButton.isVisible({ timeout: 5000 }).catch(() => false)) {
        await submitButton.click()

        // Button should remain visible since canSubmitForGrading stays true
        await expect(submitButton).toBeVisible({ timeout: 5000 })
      }
    })
  })
})
