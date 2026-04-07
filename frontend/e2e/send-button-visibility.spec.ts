/**
 * E2E tests for send button visibility in the simulation chat (issue #380).
 *
 * Verifies that the send button displays a "Send" text label alongside
 * the icon so users can easily identify the primary action.
 */

import { test, expect } from '@playwright/test'

test.describe('Send button visibility', () => {
  const SIM_URL = '/student/run-simulation/test-instance-1'

  // Minimal simulation data to render the chat interface
  function makeSimulationData() {
    return {
      simulation: {
        id: 1,
        title: 'Test Simulation',
        description: 'A test simulation',
        case_study_url: null,
        scenes: [
          {
            id: 1,
            scene_order: 1,
            title: 'Scene 1',
            description: 'First scene',
            personas: [{ id: 1, name: 'Alice', role: 'Manager' }],
          },
        ],
      },
      current_scene: {
        id: 1,
        scene_order: 1,
        title: 'Scene 1',
        description: 'First scene',
      },
      user_progress: {
        id: 1,
        current_scene_id: 1,
        current_scene_order: 1,
        completion_percentage: 0,
      },
      conversation_history: [],
    }
  }

  test('send button displays "Send" text label', async ({ page }) => {
    // Mock the simulation API to return test data
    await page.route('**/api/student/simulation/**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSimulationData()),
      })
    })

    await page.goto(SIM_URL)

    // The send button should contain the text "Send"
    const sendButton = page.locator('button', { hasText: 'Send' })
    await expect(sendButton).toBeVisible()

    // Verify the button has the expected styling classes
    await expect(sendButton).toHaveClass(/bg-gray-900/)
    await expect(sendButton).toHaveClass(/rounded-lg/)
  })

  test('send button shows icon alongside text', async ({ page }) => {
    await page.route('**/api/student/simulation/**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSimulationData()),
      })
    })

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
    await page.route('**/api/student/simulation/**', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSimulationData()),
      })
    })

    await page.goto(SIM_URL)

    const sendButton = page.locator('button', { hasText: 'Send' })
    await expect(sendButton).toBeDisabled()
  })
})
