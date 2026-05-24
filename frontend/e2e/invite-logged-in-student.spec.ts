/**
 * E2E tests for issue #373 — Logged-in students must be able to use a cohort
 * invite link without logging out first.
 *
 * The fix:
 *  1. Exempts `/invite` from `RoleBasedRedirect` so authenticated users stay
 *     on the page long enough for the auto-accept effect to fire.
 *  2. Shows the "Already Enrolled" success panel (instead of an error) when
 *     the backend returns `already_enrolled: true`.
 *  3. Adds a "Log in as Student" button for authenticated non-student users
 *     so they can switch accounts without manually navigating away.
 */

import { test, expect, Page } from '@playwright/test'

const TOKEN = 'test-invite-token-123'

const INVITE_DATA = {
  token: TOKEN,
  cohort: { id: 1, title: 'Fall 2025 Marketing', description: 'Intro cohort' },
  professor: { name: 'Prof. Smith', email: 'smith@example.edu' },
  invite_type: 'MULTI_USE',
  expires_at: new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString(),
  uses_left: null,
}

function mockStudentUser(page: Page) {
  return page.route('**/api/auth/me', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 42,
        user_id: 'u_42',
        email: 'student@example.edu',
        full_name: 'Test Student',
        username: 'test_student',
        bio: null,
        avatar_url: null,
        role: 'student',
        is_active: true,
        is_verified: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
    }),
  )
}

function mockProfessorUser(page: Page) {
  return page.route('**/api/auth/me', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 99,
        user_id: 'u_99',
        email: 'prof@example.edu',
        full_name: 'Prof. User',
        username: 'prof_user',
        bio: null,
        avatar_url: null,
        role: 'professor',
        is_active: true,
        is_verified: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
    }),
  )
}

function mockValidateInvite(page: Page) {
  return page.route(`**/invites/${TOKEN}`, (route, request) => {
    if (request.method() !== 'GET') return route.fallback()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(INVITE_DATA),
    })
  })
}

function mockAcceptInvite(page: Page, body: Record<string, any>) {
  return page.route(`**/invites/${TOKEN}/accept`, route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    }),
  )
}

test.describe('Invite link flow for logged-in users (issue #373)', () => {
  test('logged-in student is NOT redirected away from /invite and auto-accepts', async ({
    page,
  }) => {
    await mockStudentUser(page)
    await mockValidateInvite(page)
    await mockAcceptInvite(page, {
      success: true,
      cohort_id: 1,
      already_enrolled: false,
    })

    await page.goto(`/invite/${TOKEN}`)

    // We must remain on /invite — RoleBasedRedirect should not bounce the
    // authenticated student to /student/dashboard before auto-accept runs.
    await expect(page).toHaveURL(new RegExp(`/invite/${TOKEN}`))

    // Cohort details should render.
    await expect(page.getByText('Fall 2025 Marketing')).toBeVisible({ timeout: 10000 })

    // The auto-accept effect fires, then redirects to the dashboard shortly.
    await expect(page.getByText(/Successfully Joined/i)).toBeVisible({ timeout: 15000 })
  })

  test('already-enrolled student sees the success "Already Enrolled" panel, not an error', async ({
    page,
  }) => {
    await mockStudentUser(page)
    await mockValidateInvite(page)
    await mockAcceptInvite(page, {
      success: true,
      cohort_id: 1,
      already_enrolled: true,
    })

    await page.goto(`/invite/${TOKEN}`)

    await expect(page.getByRole('heading', { name: /Already Enrolled/i })).toBeVisible({
      timeout: 15000,
    })
    await expect(page.getByRole('button', { name: /Go to Dashboard/i })).toBeVisible()

    // Regression: the old error panel must NOT render.
    await expect(page.getByText(/Cannot Join/i)).toHaveCount(0)
  })

  test('logged-in professor sees Switch Account button that logs out', async ({ page }) => {
    await mockProfessorUser(page)
    await mockValidateInvite(page)

    let logoutCalled = false
    await page.route('**/api/auth/logout', route => {
      logoutCalled = true
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    })

    await page.goto(`/invite/${TOKEN}`)

    // Non-student panel rendered.
    await expect(page.getByText(/Professors Cannot Join/i)).toBeVisible({ timeout: 10000 })

    const switchBtn = page.getByTestId('invite-switch-account')
    await expect(switchBtn).toBeVisible()
    await switchBtn.click()

    // Logout endpoint should have been hit.
    await expect.poll(() => logoutCalled, { timeout: 5000 }).toBe(true)
  })
})
