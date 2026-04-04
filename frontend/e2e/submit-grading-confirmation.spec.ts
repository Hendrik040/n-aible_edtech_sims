/**
 * E2E tests for the "Submit for Grading" confirmation dialog (issue #355).
 *
 * Verifies that clicking "Submit for Grading" shows a confirmation dialog
 * instead of immediately submitting, preventing accidental submissions.
 */

import { test, expect } from '@playwright/test'

test.describe('Submit for Grading confirmation dialog', () => {
  const SIM_URL = '/student/run-simulation/test-instance-123'

  /** Mock the start-simulation endpoint with a response that enables the submit button. */
  async function mockStartSimulation(page: import('@playwright/test').Page, turnCount = 3, timeoutTurns = 15) {
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
            personas: []
          },
          simulation: { id: 1, title: 'Test Sim', total_scenes: 1 },
          simulation_status: 'in_progress',
          is_resuming: true,
          turn_count: turnCount,
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

  test('clicking Submit for Grading shows confirmation dialog instead of submitting', async ({ page }) => {
    await mockStartSimulation(page, 3, 15)

    // Ensure the grading endpoint is NOT called prematurely
    let gradingCalled = false
    await page.route('**/api/simulation/linear-chat', route => {
      gradingCalled = true
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ scene_completed: false })
      })
    })

    await page.goto(SIM_URL)

    const submitButton = page.getByRole('button', { name: /submit for grading/i })
    await expect(submitButton).toBeVisible({ timeout: 10000 })

    // Click the submit button — should show dialog, NOT submit
    await submitButton.click()

    // Confirmation dialog should appear
    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toBeVisible({ timeout: 5000 })

    // Dialog should mention remaining turns
    await expect(dialog.getByText(/12 turns remaining/i)).toBeVisible()

    // Dialog should have cancel and confirm buttons
    await expect(dialog.getByRole('button', { name: /cancel/i })).toBeVisible()
    await expect(dialog.getByRole('button', { name: /yes, submit for grading/i })).toBeVisible()

    // Grading endpoint should NOT have been called yet
    expect(gradingCalled).toBe(false)
  })

  test('cancelling the confirmation dialog does not submit', async ({ page }) => {
    await mockStartSimulation(page, 5, 15)

    let gradingCalled = false
    await page.route('**/api/simulation/linear-chat', route => {
      gradingCalled = true
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ scene_completed: false })
      })
    })

    await page.goto(SIM_URL)

    const submitButton = page.getByRole('button', { name: /submit for grading/i })
    await expect(submitButton).toBeVisible({ timeout: 10000 })

    // Open dialog
    await submitButton.click()
    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toBeVisible({ timeout: 5000 })

    // Click cancel
    await dialog.getByRole('button', { name: /cancel/i }).click()

    // Dialog should close
    await expect(dialog).not.toBeVisible({ timeout: 3000 })

    // Grading should NOT have been called
    expect(gradingCalled).toBe(false)

    // Submit button should still be visible and clickable
    await expect(submitButton).toBeVisible()
    await expect(submitButton).toBeEnabled()
  })

  test('confirming the dialog triggers actual grading submission', async ({ page }) => {
    await mockStartSimulation(page, 10, 15)

    let gradingCalled = false
    await page.route('**/api/simulation/linear-chat', route => {
      gradingCalled = true
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ scene_completed: false })
      })
    })

    await page.goto(SIM_URL)

    const submitButton = page.getByRole('button', { name: /submit for grading/i })
    await expect(submitButton).toBeVisible({ timeout: 10000 })

    // Open dialog
    await submitButton.click()
    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toBeVisible({ timeout: 5000 })

    // Confirm submission
    await dialog.getByRole('button', { name: /yes, submit for grading/i }).click()

    // Grading endpoint should now be called
    await page.waitForTimeout(1000)
    expect(gradingCalled).toBe(true)
  })

  test('dialog shows correct remaining turns count', async ({ page }) => {
    // Student has used 14 of 15 turns — only 1 remaining
    await mockStartSimulation(page, 14, 15)

    await page.route('**/api/simulation/linear-chat', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ scene_completed: false })
      })
    )

    await page.goto(SIM_URL)

    const submitButton = page.getByRole('button', { name: /submit for grading/i })
    await expect(submitButton).toBeVisible({ timeout: 10000 })

    await submitButton.click()

    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toBeVisible({ timeout: 5000 })

    // Should show "1 turn remaining" (singular)
    await expect(dialog.getByText(/1 turn remaining/i)).toBeVisible()
  })

  test('dialog shows generic message when no turns remain', async ({ page }) => {
    // Student has used all 15 turns
    await mockStartSimulation(page, 15, 15)

    await page.route('**/api/simulation/linear-chat', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ scene_completed: false })
      })
    )

    await page.goto(SIM_URL)

    const submitButton = page.getByRole('button', { name: /submit for grading/i })
    await expect(submitButton).toBeVisible({ timeout: 10000 })

    await submitButton.click()

    const dialog = page.getByRole('alertdialog')
    await expect(dialog).toBeVisible({ timeout: 5000 })

    // Should show the generic "cannot be undone" message without turn count
    await expect(dialog.getByText(/this will end your simulation/i)).toBeVisible()
  })
})
