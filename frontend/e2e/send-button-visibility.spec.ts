/**
 * E2E tests for send button visibility in the simulation chat (issue #380).
 *
 * Verifies that the send button displays a "Send" text label alongside
 * the icon so users can easily identify the primary action.
 */

import { test, expect } from '@playwright/test'

test.describe('Send button visibility', () => {
  const SIM_URL = '/student/run-simulation/test-instance-1'

  // Simulation data matching the SimulationData interface from page.tsx
  function makeSimulationData() {
    return {
      user_progress_id: 1,
      instance_id: 1,
      simulation_status: 'in_progress',
      simulation: {
        id: 1,
        title: 'Test Simulation',
        description: 'A test simulation',
        challenge: 'Test challenge',
        learning_objectives: [],
        student_role: 'Analyst',
        total_scenes: 1,
        case_study_url: null,
      },
      current_scene: {
        id: 1,
        scene_order: 1,
        title: 'Scene 1',
        description: 'First scene',
        timeout_turns: 15,
        personas: [
          {
            id: 1,
            name: 'Alice',
            role: 'Manager',
            background: 'Test background',
            correlation: null,
            primary_goals: [],
            personality_traits: {},
          },
        ],
      },
      conversation_history: [],
      all_scenes: [],
      turn_count: 0,
      completed_scene_ids: [],
    }
  }

  /** Mock auth and simulation API routes before each test */
  async function setupRoutes(page: import('@playwright/test').Page) {
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 1,
          email: 'student@test.com',
          full_name: 'Test Student',
          role: 'student',
        }),
      })
    })

    await page.route('**/student-simulation-instances/*/start-simulation', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSimulationData()),
      })
    })
  }

  test('send button displays "Send" text label', async ({ page }) => {
    await setupRoutes(page)
    await page.goto(SIM_URL)

    // The send button should contain the text "Send"
    const sendButton = page.locator('button', { hasText: 'Send' })
    await expect(sendButton).toBeVisible()

    // Verify the button has the expected styling classes
    await expect(sendButton).toHaveClass(/bg-gray-900/)
    await expect(sendButton).toHaveClass(/rounded-lg/)
  })

  test('send button shows icon alongside text', async ({ page }) => {
    await setupRoutes(page)
    await page.goto(SIM_URL)

    // The send button should contain both an SVG icon and "Send" text
    const sendButton = page.locator('button', { hasText: 'Send' })
    await expect(sendButton).toBeVisible()

    const icon = sendButton.locator('svg')
    await expect(icon).toBeVisible()

    const label = sendButton.locator('span', { hasText: 'Send' })
    await expect(label).toBeVisible()
  })

  test('send button is disabled when input is empty', async ({ page }) => {
    await setupRoutes(page)
    await page.goto(SIM_URL)

    const sendButton = page.locator('button', { hasText: 'Send' })
    await expect(sendButton).toBeDisabled()
  })
})
