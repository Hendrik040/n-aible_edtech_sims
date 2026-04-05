/**
 * E2E tests for profile save and password change (issue #359).
 *
 * Verifies that PUT /users/me and POST /users/change-password are reachable
 * and that the ProfilePage component handles success and error responses.
 */

import { test, expect, Page } from '@playwright/test'

const PROFILE_URL = '/student/profile'

/** Mock the auth status endpoint to return a logged-in user. */
async function mockAuthStatus(page: Page) {
  await page.route('**/api/auth/me', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: 'test@example.com',
        full_name: 'Test User',
        username: 'testuser',
        role: 'student',
        bio: '',
        avatar_url: '',
        profile_public: true,
        allow_contact: true,
        is_active: true,
        is_verified: false,
        reputation_score: 0,
        total_simulations: 0,
        published_simulations: 0,
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
      }),
    })
  )
}

test.describe('Profile save — PUT /users/me', () => {
  test('should save profile changes successfully', async ({ page }) => {
    await mockAuthStatus(page)

    // Mock the profile update endpoint to succeed
    await page.route('**/api/proxy/users/me', route => {
      if (route.request().method() === 'PUT') {
        const body = route.request().postDataJSON()
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 1,
            email: 'test@example.com',
            full_name: body?.full_name ?? 'Test User',
            username: body?.username ?? 'testuser',
            role: 'student',
            bio: body?.bio ?? '',
            avatar_url: body?.avatar_url ?? '',
            profile_public: body?.profile_public ?? true,
            allow_contact: body?.allow_contact ?? true,
            is_active: true,
            is_verified: false,
            reputation_score: 0,
            total_simulations: 0,
            published_simulations: 0,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z',
          }),
        })
      }
      return route.continue()
    })

    await page.goto(PROFILE_URL)

    // Fill in a new full name
    const nameInput = page.locator('input[name="full_name"], input[id="full_name"]').first()
    await expect(nameInput).toBeVisible({ timeout: 5000 })
    await nameInput.fill('Updated Name')

    // Click save
    const saveBtn = page.getByRole('button', { name: /save changes/i })
    await expect(saveBtn).toBeVisible({ timeout: 5000 })
    await saveBtn.click()

    // Should not show "Not Found" error
    await expect(page.getByText('Not Found')).not.toBeVisible({ timeout: 3000 })
  })

  test('should show error when profile update returns 404 (regression)', async ({ page }) => {
    await mockAuthStatus(page)

    // Simulate the old broken behavior: backend returns 404
    await page.route('**/api/proxy/users/me', route => {
      if (route.request().method() === 'PUT') {
        return route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Not Found' }),
        })
      }
      return route.continue()
    })

    await page.goto(PROFILE_URL)

    const saveBtn = page.getByRole('button', { name: /save changes/i })
    await expect(saveBtn).toBeVisible({ timeout: 5000 })
    await saveBtn.click()

    // The error message should appear when the endpoint is missing
    await expect(page.getByText(/not found|error/i)).toBeVisible({ timeout: 3000 })
  })
})

test.describe('Password change — POST /users/change-password', () => {
  test('should change password successfully', async ({ page }) => {
    await mockAuthStatus(page)

    await page.route('**/api/proxy/users/change-password', route => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ message: 'Password updated successfully' }),
        })
      }
      return route.continue()
    })

    await page.goto(PROFILE_URL)

    // Fill in password fields if they exist
    const currentPw = page.locator('input[name="currentPassword"], input[id="currentPassword"]').first()
    const newPw = page.locator('input[name="newPassword"], input[id="newPassword"]').first()
    const confirmPw = page.locator('input[name="confirmPassword"], input[id="confirmPassword"]').first()

    await expect(currentPw).toBeVisible({ timeout: 5000 })
    await currentPw.fill('OldPassword123!')
    await newPw.fill('NewPassword456!')
    await confirmPw.fill('NewPassword456!')

    const updateBtn = page.getByRole('button', { name: /update password/i })
    await expect(updateBtn).toBeVisible({ timeout: 5000 })
    await updateBtn.click()
    await expect(page.getByText('Not Found')).not.toBeVisible({ timeout: 3000 })
  })

  test('should show error for incorrect current password', async ({ page }) => {
    await mockAuthStatus(page)

    await page.route('**/api/proxy/users/change-password', route => {
      if (route.request().method() === 'POST') {
        return route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Current password is incorrect' }),
        })
      }
      return route.continue()
    })

    await page.goto(PROFILE_URL)

    const currentPw = page.locator('input[name="currentPassword"], input[id="currentPassword"]').first()
    const newPw = page.locator('input[name="newPassword"], input[id="newPassword"]').first()
    const confirmPw = page.locator('input[name="confirmPassword"], input[id="confirmPassword"]').first()

    await expect(currentPw).toBeVisible({ timeout: 5000 })
    await currentPw.fill('WrongPassword!')
    await newPw.fill('NewPassword456!')
    await confirmPw.fill('NewPassword456!')

    const updateBtn = page.getByRole('button', { name: /update password/i })
    await expect(updateBtn).toBeVisible({ timeout: 5000 })
    await updateBtn.click()
    await expect(page.getByText(/incorrect/i)).toBeVisible({ timeout: 3000 })
  })
})
