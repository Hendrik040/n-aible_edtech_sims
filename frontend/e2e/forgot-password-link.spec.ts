/**
 * E2E tests for the forgot-password + reset-password flow (issues #343, #363).
 *
 * Verifies:
 *  - Login page has a visible "Forgot password?" link that navigates to /forgot-password
 *  - Forgot-password page renders the new email-only request form
 *  - Submitting the form shows a generic success message (backend response mocked)
 *  - Reset-password page renders the new-password form when a token is present in the URL
 *  - Reset-password page shows an error state when the token is missing
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

  test('regression: login page must not lack forgot-password navigation', async ({ page }) => {
    await page.goto(LOGIN_URL)

    const links = page.locator('a[href="/forgot-password"]')
    await expect(links).toHaveCount(1)
  })
})

test.describe('Forgot-password page (email token flow)', () => {
  test('should render an email-only request form (no confirm_email/new_password fields)', async ({ page }) => {
    await page.goto('/forgot-password')

    await expect(page.locator('input#email')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('input#confirmEmail')).toHaveCount(0)
    await expect(page.locator('input#newPassword')).toHaveCount(0)
    await expect(page.getByRole('button', { name: /send reset link/i })).toBeVisible()
  })

  test('submitting the form shows a generic success message', async ({ page }) => {
    // Mock the frontend proxy so the test does not need a live backend.
    await page.route('**/api/auth/request-reset', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'If an account exists with this email, a reset link has been sent.',
        }),
      })
    })

    await page.goto('/forgot-password')
    await page.locator('input#email').fill('someone@example.com')
    await page.getByRole('button', { name: /send reset link/i }).click()

    const banner = page.getByTestId('forgot-password-success')
    await expect(banner).toBeVisible({ timeout: 5000 })
    await expect(banner).toContainText(/reset link/i)
  })
})

test.describe('Reset-password page', () => {
  test('shows an error state when the token query parameter is missing', async ({ page }) => {
    await page.goto('/reset-password')

    await expect(page.getByTestId('reset-password-missing-token')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('input#password')).toHaveCount(0)
  })

  test('renders the new-password form when a token is present', async ({ page }) => {
    await page.goto('/reset-password?token=sample-token-value')

    await expect(page.locator('input#password')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('input#confirmPassword')).toBeVisible()
    await expect(page.getByRole('button', { name: /reset password/i })).toBeVisible()
  })

  test('client-side validation: mismatched passwords show an error', async ({ page }) => {
    await page.goto('/reset-password?token=sample-token-value')

    await page.locator('input#password').fill('newpassword123')
    await page.locator('input#confirmPassword').fill('different456')
    await page.getByRole('button', { name: /reset password/i }).click()

    const errorBanner = page.getByTestId('reset-password-error')
    await expect(errorBanner).toBeVisible({ timeout: 3000 })
    await expect(errorBanner).toContainText(/do not match/i)
  })

  test('successful reset shows a success banner (backend mocked)', async ({ page }) => {
    await page.route('**/api/auth/reset-password', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'Your password has been reset. You can now log in.',
        }),
      })
    })

    await page.goto('/reset-password?token=sample-token-value')
    await page.locator('input#password').fill('newpassword123')
    await page.locator('input#confirmPassword').fill('newpassword123')
    await page.getByRole('button', { name: /reset password/i }).click()

    await expect(page.getByTestId('reset-password-success')).toBeVisible({ timeout: 5000 })
  })
})
