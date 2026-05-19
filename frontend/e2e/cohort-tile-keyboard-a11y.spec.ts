/**
 * E2E tests for cohort tile keyboard accessibility (issue #306).
 *
 * Verifies that cohort tiles on the My Cohorts page are semantic <button>
 * elements with aria-pressed, enabling keyboard navigation and screen-reader
 * support.
 */

import { test, expect, Page } from '@playwright/test'

const MY_COHORTS_URL = '/student/my-cohorts'

const MOCK_COHORTS = [
  {
    id: 1,
    unique_id: 'cohort-aaa',
    title: 'Intro to Business',
    description: 'First cohort',
    professor: { name: 'Dr. Smith' },
    is_active: true,
    student_count: 25,
    enrollment_date: '2026-01-15T00:00:00Z',
  },
  {
    id: 2,
    unique_id: 'cohort-bbb',
    title: 'Advanced Strategy',
    description: 'Second cohort',
    professor: { name: 'Prof. Jones' },
    is_active: true,
    student_count: 12,
    enrollment_date: '2026-02-01T00:00:00Z',
  },
]

/** Mock auth and cohort API endpoints so the page renders without a real backend. */
async function setupMocks(page: Page) {
  await page.route('**/api/auth/me', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: 'student@example.com',
        full_name: 'Test Student',
        username: 'teststudent',
        role: 'student',
        is_active: true,
      }),
    }),
  )

  await page.route('**/api/student/cohorts**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(MOCK_COHORTS),
    }),
  )

  // Catch cohort detail / assignment routes so they don't error
  await page.route('**/api/student/cohorts/*/assignments**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    }),
  )
}

test.describe('Cohort tile keyboard accessibility', () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page)
    await page.goto(MY_COHORTS_URL)
  })

  test('cohort tiles are rendered as <button> elements', async ({ page }) => {
    const tiles = page.locator('button:has-text("Intro to Business"), button:has-text("Advanced Strategy")')
    await expect(tiles).toHaveCount(2)
  })

  test('cohort tiles have type="button"', async ({ page }) => {
    const tile = page.locator('button:has-text("Intro to Business")')
    await expect(tile).toHaveAttribute('type', 'button')
  })

  test('unselected cohort tile has aria-pressed="false"', async ({ page }) => {
    const tile = page.locator('button:has-text("Advanced Strategy")')
    await expect(tile).toHaveAttribute('aria-pressed', 'false')
  })

  test('clicking a cohort tile sets aria-pressed="true"', async ({ page }) => {
    const tile = page.locator('button:has-text("Advanced Strategy")')
    await expect(tile).toHaveAttribute('aria-pressed', 'false')
    await tile.click()
    await expect(tile).toHaveAttribute('aria-pressed', 'true')
  })

  test('cohort tile is focusable via Tab key', async ({ page }) => {
    // Tab through the page until we reach a cohort tile
    let foundViaTab = false
    for (let i = 0; i < 20; i++) {
      await page.keyboard.press('Tab')
      const focused = page.locator(':focus')
      const text = await focused.textContent().catch(() => '')
      if (text?.includes('Intro to Business')) {
        await expect(focused).toHaveAttribute('type', 'button')
        foundViaTab = true
        break
      }
    }
    expect(foundViaTab).toBeTruthy()
  })

  test('pressing Enter on focused cohort tile selects it', async ({ page }) => {
    const tile = page.locator('button:has-text("Advanced Strategy")')
    await tile.focus()
    await page.keyboard.press('Enter')
    await expect(tile).toHaveAttribute('aria-pressed', 'true')
  })

  test('pressing Space on focused cohort tile selects it', async ({ page }) => {
    const tile = page.locator('button:has-text("Advanced Strategy")')
    await tile.focus()
    await page.keyboard.press('Space')
    await expect(tile).toHaveAttribute('aria-pressed', 'true')
  })
})
