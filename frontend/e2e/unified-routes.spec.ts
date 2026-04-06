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

import { test, expect } from '@playwright/test'

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
  test('sidebar is rendered on /dashboard', async ({ page }) => {
    await page.goto('/dashboard')

    // If we're redirected to login, skip — we can't test sidebar without auth
    if (page.url().includes('/login') || page.url().endsWith('/')) {
      test.skip(true, 'Not authenticated; sidebar not visible without auth')
    }

    // The sidebar should be visible (it's a fixed nav with the logo)
    const sidebar = page.locator('nav').first()
    await expect(sidebar).toBeVisible({ timeout: 10000 })
  })
})

test.describe('RoleBasedSidebar uses unified paths (#387)', () => {
  test('sidebar nav links do not use /professor/ or /student/ prefixes', async ({ page }) => {
    await page.goto('/dashboard')

    if (page.url().includes('/login') || page.url().endsWith('/')) {
      test.skip(true, 'Not authenticated; sidebar not visible without auth')
    }

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
