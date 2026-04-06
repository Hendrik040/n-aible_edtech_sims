/**
 * E2E tests for Settings button backward compatibility (issue #264).
 *
 * Verifies that the Settings button in ProfessorGradingModal renders
 * correctly when the API response uses either the current `simulation`
 * key or the legacy `scenario` key.
 */

import { test, expect } from '@playwright/test'

test.describe('Settings button backward compatibility', () => {
  const GRADING_URL = '/professor/grading/test-instance-123'

  function makeSubmissionData(simKey: 'simulation' | 'scenario') {
    const simObj = { id: 42, title: 'Test Simulation', scenes: [] }
    return {
      student_name: 'Test Student',
      current_scene: { id: 1, scene_order: 1, title: 'Scene 1' },
      all_scenes: [],
      conversation_log: [],
      grades: { overall_grade: 85, feedback: 'Good work' },
      [simKey]: simObj,
    }
  }

  async function mockGradingEndpoint(
    page: import('@playwright/test').Page,
    simKey: 'simulation' | 'scenario',
  ) {
    await page.route('**/professor/grading/**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(makeSubmissionData(simKey)),
      }),
    )
    // Also mock auth so the page doesn't redirect
    await page.route('**/auth/me', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, email: 'prof@test.com', role: 'professor' }),
      }),
    )
  }

  test('renders Settings button when response uses "simulation" key', async ({ page }) => {
    await mockGradingEndpoint(page, 'simulation')
    await page.goto(GRADING_URL)

    const settingsLink = page.locator('a[href*="/professor/edit-grading?id=42"]')
    // The link should exist in the DOM (it may or may not be visible depending
    // on whether the grading section renders, but its href should reference id=42)
    await expect(settingsLink).toHaveCount(1)
  })

  test('renders Settings button when response uses legacy "scenario" key', async ({ page }) => {
    await mockGradingEndpoint(page, 'scenario')
    await page.goto(GRADING_URL)

    const settingsLink = page.locator('a[href*="/professor/edit-grading?id=42"]')
    await expect(settingsLink).toHaveCount(1)
  })
})
