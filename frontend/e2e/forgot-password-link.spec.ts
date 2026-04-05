/**
 * E2E tests for forgot-password link on login page (issue #363).
 *
 * Verifies that the login page contains a visible "Forgot password?" link
 * that navigates to /forgot-password.
 */

import { test, expect } from '@playwright/test'

const LOGIN_URL = '/login'

test.describe('Forgot password link on login page', () => {
  test('should display a "Forgot password?" link on the login page', async ({ page }) => {
    await page.goto(LOGIN_URL)

    const forgotLink = page.getByRole('link', { name: /forgot password/i })
    await expect(forgotLink).toBeVisible({ timeout: 5000 })
  })

  test('should navigate to /forgot-password when clicking the link', async ({ page }) => {
    await page.goto(LOGIN_URL)

    const forgotLink = page.getByRole('link', { name: /forgot password/i })
    await expect(forgotLink).toBeVisible({ timeout: 5000 })
    await forgotLink.click()

    await expect(page).toHaveURL(/\/forgot-password/)
  })

  test('should have the forgot-password page render a reset form', async ({ page }) => {
    await page.goto('/forgot-password')

    // The forgot-password page should have email and password fields
    await expect(page.locator('input#email')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('input#confirmEmail')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('input#newPassword')).toBeVisible({ timeout: 5000 })
    await expect(page.getByRole('button', { name: /update password/i })).toBeVisible()
  })

  test('regression: login page must not lack forgot-password navigation', async ({ page }) => {
    await page.goto(LOGIN_URL)

    // There must be at least one link pointing to /forgot-password
    const links = page.locator('a[href="/forgot-password"]')
    await expect(links).toHaveCount(1)
  })
})
