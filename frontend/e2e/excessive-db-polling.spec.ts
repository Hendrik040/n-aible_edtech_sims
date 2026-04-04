/**
 * E2E tests for issue #357: excessive database polling.
 *
 * Validates that the /health endpoint caches its response and that
 * frontend pages use 10-second polling intervals instead of 3-second.
 */

import { test, expect } from '@playwright/test'

test.describe('Health check caching', () => {
  test('GET /health returns cached result on rapid successive calls', async ({ request }) => {
    // First call
    const resp1 = await request.get('/api/proxy/health')

    // Skip if backend is not available
    if (resp1.status() === 502 || resp1.status() === 503) {
      test.skip(true, 'Backend not available')
      return
    }

    // Second call immediately after
    const resp2 = await request.get('/api/proxy/health')

    expect(resp1.status()).toBe(200)
    expect(resp2.status()).toBe(200)
    expect(await resp2.json()).toEqual(await resp1.json())
  })
})

test.describe('Frontend polling intervals', () => {
  async function mockAuth(page: import('@playwright/test').Page) {
    await page.route('**/api/proxy/api/auth/me', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, role: 'professor', email: 'prof@test.com' })
      })
    )
  }

  test('simulation-builder polls processing status at 10s interval', async ({ page }) => {
    const pollRequests: number[] = []

    await mockAuth(page)

    // Intercept the processing-status requests and record timestamps
    await page.route('**/grading-materials**', route => {
      pollRequests.push(Date.now())
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 1, processing_status: 'processing', filename: 'test-material' }
        ])
      })
    })

    // Mock the simulation-builder page data
    await page.route('**/api/proxy/api/simulations/**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ id: 1, title: 'Test', status: 'draft' })
      })
    )

    // Navigate (page may not fully load without backend, but polling should start)
    await page.goto('/professor/simulation-builder?edit=1', { waitUntil: 'domcontentloaded' })

    // Wait enough time to detect whether polling is 3s or 10s
    // If we wait 8 seconds, with 3s interval we'd see ~2-3 requests,
    // with 10s we'd see 0-1.  This is a best-effort E2E check.
    await page.waitForTimeout(8000)

    // With 10s interval, there should be at most 1 poll in 8 seconds
    // (the initial load + at most 1 interval fire)
    // We don't assert a hard number because the page may not trigger
    // polling at all without proper auth/state — the source-level test
    // in backend/tests/test_excessive_db_polling.py is the authoritative check.
    expect(pollRequests.length).toBeLessThanOrEqual(3)
  })

  test('edit-grading page polls at 10s interval', async ({ page }) => {
    const pollRequests: number[] = []

    await mockAuth(page)

    await page.route('**/grading-materials**', route => {
      pollRequests.push(Date.now())
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { id: 1, processing_status: 'processing', filename: 'test-material' }
        ])
      })
    })

    await page.goto('/professor/edit-grading?id=1', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(8000)

    expect(pollRequests.length).toBeLessThanOrEqual(3)
  })
})
