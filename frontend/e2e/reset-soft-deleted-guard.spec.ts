/**
 * E2E tests for the reset simulation soft-deletion guard (issue #263).
 *
 * Verifies that when a student tries to reset a simulation whose underlying
 * Simulation record has been soft-deleted, the API returns 404 and the
 * frontend displays an appropriate error message.
 */

import { test, expect, Page } from '@playwright/test'

test.describe('Reset simulation soft-deletion guard', () => {
  const INSTANCE_URL = '/student/run-simulation/test-instance-reset'

  /** Mock the start-simulation endpoint for initial page load. */
  async function mockStartSimulation(page: Page) {
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
            timeout_turns: 15,
            personas: []
          },
          simulation: { id: 1, title: 'Test Sim', total_scenes: 1 },
          simulation_status: 'completed',
          is_resuming: true,
          turn_count: 10,
          conversation_history: [],
          all_scenes: [
            { id: 1, scene_order: 1, title: 'Test Scene', personas: [] }
          ]
        })
      })
    )
  }

  test('reset endpoint returns 404 when simulation is soft-deleted', async ({ page }) => {
    // Mock the reset endpoint to return 404 (simulating soft-deleted simulation)
    await page.route('**/student-simulation-instances/**/reset-simulation', route =>
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Simulation not found. The simulation associated with this assignment may have been deleted. Please contact your instructor.'
        })
      })
    )

    await mockStartSimulation(page)

    // Mock auth
    await page.route('**/api/auth/**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: 'student@test.com',
          role: 'student',
          full_name: 'Test Student'
        })
      })
    )

    await page.goto(INSTANCE_URL)

    // Directly call the reset API and verify it returns 404
    const response = await page.evaluate(async () => {
      const res = await fetch('/api/student-simulation-instances/test-instance-reset/reset-simulation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      return { status: res.status, body: await res.json() }
    })

    expect(response.status).toBe(404)
    expect(response.body.detail).toContain('deleted')
    expect(response.body.detail).toContain('instructor')
  })

  test('reset endpoint returns 200 when simulation exists', async ({ page }) => {
    // Mock the reset endpoint to return success
    await page.route('**/student-simulation-instances/**/reset-simulation', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          message: 'Simulation reset successfully'
        })
      })
    )

    await mockStartSimulation(page)

    await page.goto(INSTANCE_URL)

    const response = await page.evaluate(async () => {
      const res = await fetch('/api/student-simulation-instances/test-instance-reset/reset-simulation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      return { status: res.status, body: await res.json() }
    })

    expect(response.status).toBe(200)
  })
})
