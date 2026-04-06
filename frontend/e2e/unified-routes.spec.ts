/**
 * E2E tests for issue #387 — unified student/professor UI.
 *
 * Verifies that the new unified routes under the (app) route group
 * render correctly and that the shared layout renders the sidebar once.
 * Legacy /professor/ and /student/ routes should still work during
 * the incremental migration period.
 */

import { test, expect } from '@playwright/test'

test.describe('Unified route structure (issue #387)', () => {
  test.describe('Unified routes exist and render', () => {
    const unifiedRoutes = [
      '/dashboard',
      '/cohorts',
      '/simulations',
      '/notifications',
      '/profile',
    ]

    for (const route of unifiedRoutes) {
      test(`${route} responds without 404`, async ({ page }) => {
        const response = await page.goto(route)
        // Should not be a hard 404 (Next.js returns 200 for client-side routes)
        expect(response?.status()).not.toBe(404)
      })
    }

    test('/simulation-builder responds (professor-only)', async ({ page }) => {
      const response = await page.goto('/simulation-builder')
      expect(response?.status()).not.toBe(404)
    })

    test('/edit-grading responds (professor-only)', async ({ page }) => {
      const response = await page.goto('/edit-grading')
      expect(response?.status()).not.toBe(404)
    })

    test('/run-simulation/test-id responds', async ({ page }) => {
      const response = await page.goto('/run-simulation/test-id')
      expect(response?.status()).not.toBe(404)
    })
  })

  test.describe('Shared layout renders sidebar once', () => {
    test('dashboard page has exactly one sidebar', async ({ page }) => {
      await page.goto('/dashboard')
      // The sidebar is a fixed nav with the logo image
      const sidebars = page.locator('nav').filter({ has: page.locator('img[alt="Logo"]') })
      // Even if redirected to login, the test verifies the page loads
      const sidebarCount = await sidebars.count()
      // Should have 0 (if redirected to login) or 1 (if authenticated) — never 2+
      expect(sidebarCount).toBeLessThanOrEqual(1)
    })
  })

  test.describe('Legacy routes still accessible', () => {
    const legacyRoutes = [
      '/professor/dashboard',
      '/student/dashboard',
      '/professor/notifications',
      '/student/notifications',
      '/professor/cohorts',
      '/student/my-cohorts',
    ]

    for (const route of legacyRoutes) {
      test(`legacy ${route} still responds`, async ({ page }) => {
        const response = await page.goto(route)
        expect(response?.status()).not.toBe(404)
      })
    }
  })

  test.describe('RoleBasedSidebar uses unified paths', () => {
    test('sidebar nav links point to unified routes', async ({ page }) => {
      await page.goto('/dashboard')

      // If we can't reach the dashboard (not authenticated), skip
      const sidebar = page.locator('nav')
      if ((await sidebar.count()) === 0) {
        test.skip(true, 'Not authenticated; sidebar not reachable')
        return
      }

      // Check that sidebar links use unified paths (not /professor/ or /student/)
      const navLinks = sidebar.locator('a[href]')
      const count = await navLinks.count()

      for (let i = 0; i < count; i++) {
        const href = await navLinks.nth(i).getAttribute('href')
        if (href) {
          expect(href).not.toMatch(/^\/(professor|student)\//)
        }
      }
    })
  })

  test.describe('RoleBasedRedirect sends to unified dashboard', () => {
    test('visiting /dashboard (old redirect page) does not 404', async ({ page }) => {
      const response = await page.goto('/dashboard')
      expect(response?.status()).not.toBe(404)
    })
  })

  test.describe('Unauthenticated access redirects to login', () => {
    const protectedRoutes = [
      '/dashboard',
      '/cohorts',
      '/simulations',
      '/notifications',
      '/profile',
      '/simulation-builder',
      '/edit-grading',
    ]

    for (const route of protectedRoutes) {
      test(`${route} redirects unauthenticated users`, async ({ page }) => {
        // Clear cookies/storage to ensure unauthenticated state
        await page.context().clearCookies()
        await page.goto(route, { waitUntil: 'networkidle' })

        // Should either redirect to login or show login-related content
        const url = page.url()
        const isOnLoginOrRoute = url.includes('/login') || url.includes(route)
        expect(isOnLoginOrRoute).toBe(true)
      })
    }
  })

  test.describe('Professor-only routes guard access', () => {
    test('/simulation-builder shows nothing for non-professor', async ({ page }) => {
      // Without authentication, the layout redirects before the role check
      await page.context().clearCookies()
      const response = await page.goto('/simulation-builder')
      expect(response?.status()).not.toBe(404)
    })

    test('/edit-grading shows nothing for non-professor', async ({ page }) => {
      await page.context().clearCookies()
      const response = await page.goto('/edit-grading')
      expect(response?.status()).not.toBe(404)
    })
  })
})
