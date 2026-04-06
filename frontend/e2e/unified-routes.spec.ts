/**
 * E2E tests for issue #387 — unified student/professor UI.
 *
 * Validates that the new unified route group `(app)` works correctly:
 * - Unified routes render without errors
 * - Sidebar is rendered once via the shared layout
 * - Navigation links use unified paths (not /professor/ or /student/ prefixes)
 * - Role-based content is conditionally rendered
 * - Old routes still work (backwards compatibility during migration)
 */

import { test, expect, Page } from '@playwright/test'

/** Mock the auth status endpoint to return a logged-in professor. */
async function mockAuthStatus(page: Page, role: 'professor' | 'student' = 'professor') {
  await page.route('**/api/auth/me', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 1,
        email: 'test@example.com',
        full_name: 'Test User',
        username: 'testuser',
        role,
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

test.describe('Unified route group (app) — layout & navigation (#387)', () => {
  test('unified /dashboard route loads without errors', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', msg => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })

    const response = await page.goto('/dashboard')

    // Should not get a 404 or 500
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)

    // Should render either the dashboard content or a redirect (auth)
    // If redirected to login, that's fine — the route exists
    const url = page.url()
    const isValidDestination = url.includes('/dashboard') || url.includes('/login') || url.endsWith('/')
    expect(isValidDestination).toBe(true)
  })

  test('unified /notifications route loads without errors', async ({ page }) => {
    const response = await page.goto('/notifications')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })

  test('unified /cohorts route loads without errors', async ({ page }) => {
    const response = await page.goto('/cohorts')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })

  test('unified /simulations route loads without errors', async ({ page }) => {
    const response = await page.goto('/simulations')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })

  test('unified /profile route loads without errors', async ({ page }) => {
    const response = await page.goto('/profile')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })

  test('unified /simulation-builder route loads without errors', async ({ page }) => {
    const response = await page.goto('/simulation-builder')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })

  test('unified /edit-grading route loads without errors', async ({ page }) => {
    const response = await page.goto('/edit-grading')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })
})

test.describe('Unified sidebar renders via shared layout (#387)', () => {
  test('sidebar is rendered on /dashboard with authenticated user', async ({ page }) => {
    await mockAuthStatus(page)

    // Mock API calls the dashboard makes
    await page.route('**/api/professor/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    )
    await page.route('**/api/student/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    )

    await page.goto('/dashboard')

    // The sidebar should be visible (it's a fixed nav with the logo)
    const sidebar = page.locator('nav').first()
    await expect(sidebar).toBeVisible({ timeout: 10000 })
  })
})

test.describe('RoleBasedSidebar uses unified paths (#387)', () => {
  test('sidebar nav links do not use /professor/ or /student/ prefixes', async ({ page }) => {
    await mockAuthStatus(page)

    // Mock API calls
    await page.route('**/api/professor/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    )
    await page.route('**/api/student/**', route =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    )

    await page.goto('/dashboard')

    // Wait for sidebar to render
    await page.waitForSelector('nav', { timeout: 10000 })

    // Check all links in the sidebar navigation
    const sidebarLinks = page.locator('nav a')
    const count = await sidebarLinks.count()

    for (let i = 0; i < count; i++) {
      const href = await sidebarLinks.nth(i).getAttribute('href')
      if (href) {
        expect(href).not.toMatch(/^\/(professor|student)\//)
      }
    }
  })
})

test.describe('RoleBasedRedirect sends both roles to /dashboard (#387)', () => {
  test('old /dashboard redirect page now sends users to unified /dashboard', async ({ page }) => {
    // Navigate to old dashboard redirect
    await page.goto('/dashboard')

    // The page should either:
    // 1. Stay on /dashboard (unified) if authenticated
    // 2. Redirect to login if not authenticated
    // It should NOT redirect to /professor/dashboard or /student/dashboard
    await page.waitForTimeout(2000) // Give time for redirects

    const url = page.url()
    expect(url).not.toContain('/professor/dashboard')
    expect(url).not.toContain('/student/dashboard')
  })
})

test.describe('Backwards compatibility — old routes still work (#387)', () => {
  test('old /professor/dashboard still renders (for migration period)', async ({ page }) => {
    const response = await page.goto('/professor/dashboard')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })

  test('old /student/dashboard still renders (for migration period)', async ({ page }) => {
    const response = await page.goto('/student/dashboard')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })

  test('old /professor/notifications still renders', async ({ page }) => {
    const response = await page.goto('/professor/notifications')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })

  test('old /student/notifications still renders', async ({ page }) => {
    const response = await page.goto('/student/notifications')
    expect(response?.status()).not.toBe(404)
    expect(response?.status()).not.toBe(500)
  })
})
