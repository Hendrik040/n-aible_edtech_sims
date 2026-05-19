/**
 * E2E tests for grading submission retry behavior (issue #346).
 *
 * Verifies that when grading fails (network error or scene-not-completed),
 * the "Submit for Grading" button remains visible so students can retry.
 */

import { test, expect } from '@playwright/test'

test.describe('Grading submission retry', () => {
  const SIM_URL = '/student/run-simulation/test-instance-123'

  /** Mock the start-simulation endpoint with a valid response that renders the UI. */
  async function mockStartSimulation(page: import('@playwright/test').Page) {
    await page.route('**/student-simulation-instances/**/start-simulation', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_progress_id: 1,
          instance_id: 123,
          current_scene: {
            id: 1,
            scene_order: 1,
            title: 'Test Scene',
            description: 'Test',
            personas: []
          },
          simulation: { id: 1, title: 'Test Sim', total_scenes: 1 },
          simulation_status: 'in_progress',
          is_resuming: true,
          turn_count: 1,
          conversation_history: [
            {
              id: 1,
              sender: 'System',
              text: 'Welcome to the simulation.',
              timestamp: new Date().toISOString(),
              type: 'system'
            }
          ],
          all_scenes: [
            { id: 1, scene_order: 1, title: 'Test Scene', personas: [] }
          ]
        })
      })
    )
  }

  test.describe('Submit for Grading button stays visible after failure', () => {
    test('button remains after network error on grading submission', async ({ page }) => {
      await mockStartSimulation(page)

      // Track how many times the grading endpoint is called
      let gradingCallCount = 0
      await page.route('**/api/simulation/linear-chat', route => {
        gradingCallCount++
        return route.abort('connectionrefused')
      })

      await page.goto(SIM_URL)

      const submitButton = page.getByRole('button', { name: /submit for grading/i })
      await expect(submitButton).toBeVisible({ timeout: 10000 })

      // First attempt — should fail with network error
      await submitButton.click()

      // Button must remain visible for retry after the error
      await expect(submitButton).toBeVisible({ timeout: 5000 })
      expect(gradingCallCount).toBeGreaterThanOrEqual(1)

      // Second attempt — proves retry is possible
      await submitButton.click()
      await expect(submitButton).toBeVisible({ timeout: 5000 })
      expect(gradingCallCount).toBeGreaterThanOrEqual(2)
    })

    test('button remains after scene_completed=false response', async ({ page }) => {
      await mockStartSimulation(page)

      let gradingCallCount = 0
      await page.route('**/api/simulation/linear-chat', route => {
        gradingCallCount++
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ scene_completed: false })
        })
      })

      await page.goto(SIM_URL)

      const submitButton = page.getByRole('button', { name: /submit for grading/i })
      await expect(submitButton).toBeVisible({ timeout: 10000 })

      await submitButton.click()

      // Button should remain visible since scene was not completed
      await expect(submitButton).toBeVisible({ timeout: 5000 })
      expect(gradingCallCount).toBeGreaterThanOrEqual(1)

      // Retry is possible
      await submitButton.click()
      await expect(submitButton).toBeVisible({ timeout: 5000 })
      expect(gradingCallCount).toBeGreaterThanOrEqual(2)
    })
  })
})
