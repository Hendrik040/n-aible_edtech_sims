/**
 * E2E tests for issue #371 — the floating feedback widget must not overlap
 * the chat composer on the student simulation runtime page.
 *
 * The fix hides `DraggableFeedback` entirely on `/student/run-simulation/*`
 * so students cannot accidentally mis-click "Submit for Grading" when
 * reaching for the send button.
 */

import { test, expect, Page } from '@playwright/test'

/** Mock the start-simulation endpoint so the sim page renders the composer. */
async function mockStartSimulation(page: Page, turnCount = 3, timeoutTurns = 15) {
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
          timeout_turns: timeoutTurns,
          personas: [],
        },
        simulation: { id: 1, title: 'Test Sim', total_scenes: 1 },
        simulation_status: 'in_progress',
        is_resuming: true,
        turn_count: turnCount,
        conversation_history: [
          {
            id: 1,
            sender: 'System',
            text: 'Welcome.',
            timestamp: new Date().toISOString(),
            type: 'system',
          },
        ],
        all_scenes: [{ id: 1, scene_order: 1, title: 'Test Scene', personas: [] }],
      }),
    }),
  )
}

test.describe('Feedback widget visibility (issue #371)', () => {
  test('feedback widget is hidden on the student simulation runtime page', async ({ page }) => {
    await mockStartSimulation(page)

    await page.goto('/student/run-simulation/test-instance-123')

    // Chat composer loaded — use Submit button as a loaded-signal.
    await expect(page.getByRole('button', { name: /submit for grading/i })).toBeVisible({
      timeout: 10000,
    })

    // The Feedback pill/card must not be rendered on this route.
    await expect(page.getByText('Feedback', { exact: true })).toHaveCount(0)
    await expect(page.getByText('Give Us Feedback')).toHaveCount(0)
  })

  test('feedback widget still renders on non-simulation pages', async ({ page }) => {
    // Visit a route outside /student/run-simulation/. If auth redirects us
    // away, the assertion below is skipped — we only care that the widget
    // is not suppressed by the pathname guard when the pathname doesn't
    // match the simulation prefix.
    await page.goto('/dashboard')

    // If the page actually rendered as /dashboard (user is authenticated in
    // the test environment), the feedback pill should be present. Otherwise
    // we skip — the important assertion is the suppression on the sim page.
    if (page.url().includes('/dashboard')) {
      await expect(page.getByText('Feedback', { exact: true })).toBeVisible({ timeout: 5000 })
    } else {
      test.skip(true, 'Not authenticated in test env; skipping positive check.')
    }
  })
})
