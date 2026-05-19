/**
 * E2E test for issue #375 — the "Read documentation" card on the Professor
 * Dashboard must be a clickable external link that opens the docs site in a
 * new tab. Previously the card was rendered as a bare <Card> with no link
 * wrapper, so clicking it did nothing.
 *
 * The fix wraps the card in an <a target="_blank" rel="noopener noreferrer">
 * pointing at DOCUMENTATION_URL from frontend/lib/constants.ts.
 */

import { test, expect } from '@playwright/test'

const DASHBOARD_URL = '/professor/dashboard'

test.describe('Professor dashboard "Read documentation" card (issue #375)', () => {
  // Shared auth/navigation setup. If middleware redirects us away from the
  // dashboard, skip — the assertions below require the dashboard to render.
  test.beforeEach(async ({ page }) => {
    await page.goto(DASHBOARD_URL)
    if (!page.url().includes('/professor/dashboard')) {
      test.skip(true, 'Not authenticated in test env; dashboard not reachable.')
    }
  })

  test('renders as an external link with the documentation URL and safe rel attrs', async ({
    page,
  }) => {
    const link = page.getByTestId('read-documentation-link')
    await expect(link).toBeVisible({ timeout: 5000 })

    // Must be a real anchor pointing to an external https URL.
    const href = await link.getAttribute('href')
    expect(href).toBeTruthy()
    expect(href).toMatch(/^https?:\/\//)

    // Must open in a new tab with safe rel attributes.
    await expect(link).toHaveAttribute('target', '_blank')
    const rel = (await link.getAttribute('rel')) ?? ''
    expect(rel).toContain('noopener')
    expect(rel).toContain('noreferrer')

    // The card title should still be rendered inside the link wrapper.
    await expect(link.getByText('Read documentation')).toBeVisible()
  })

  test('regression: documentation card is not a bare, non-navigating <Card>', async ({
    page,
  }) => {
    // There must be exactly one "Read documentation" anchor wrapper — the old
    // broken behavior rendered the title without any enclosing <a>.
    const anchors = page.locator('a[data-testid="read-documentation-link"]')
    await expect(anchors).toHaveCount(1)
  })
})
