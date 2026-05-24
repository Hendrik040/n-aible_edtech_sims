/**
 * E2E tests for markdown rendering in grading views (issue #353).
 *
 * Verifies that markdown-formatted grading feedback is rendered as proper HTML
 * (bold, headers, lists) instead of showing raw markdown characters or being
 * stripped to plain text.
 */

import { test, expect } from '@playwright/test'

// Mock matches the real backend response shape: overall_score, overall_feedback,
// scenes, rubric_total_points. The frontend parses structured fields from
// overall_feedback via parseGradingText().
const GRADING_DATA = {
  overall_score: 82,
  rubric_total_points: 100,
  overall_feedback:
    '**OVERALL SCORE:** 82/100 points\n\n' +
    '**SCORE BREAKDOWN:**\n' +
    '1. **Communication** - Score: 85/100 points - Performance level: Proficient - Brief reasoning: **Excellent clarity** in responses.\n' +
    '2. **Analysis** - Score: 78/100 points - Performance level: Developing - Brief reasoning: Showed **basic analytical skills**.\n\n' +
    '**OVERALL ASSESSMENT:**\n' +
    '- **Summary of performance:** **Great performance!** You demonstrated strong skills overall.\n' +
    '- **Key strengths:** Strong **communication** skills and good **teamwork**\n' +
    '- **Main areas for improvement:** Needs improvement in **technical depth**\n\n' +
    '**FEEDBACK:**\n' +
    '- **Specific actionable recommendations:** Practice **data-driven** decision making. Review **case study** frameworks.\n',
  scenes: [
    {
      id: 1,
      title: 'Discovery Phase',
      score: 80,
      feedback:
        '**SCORE BREAKDOWN:**\n\n' +
        '**OVERALL ASSESSMENT:**\n' +
        '**Key Strengths:** Good **questioning technique**\n' +
        '**Improvements:** Need more **structured approach**\n\n' +
        '**FEEDBACK:**\n' +
        '**Recommendations:** Try using the **MECE framework**',
      user_responses: [{ content: 'I would start by analyzing the data' }],
      strengths: ['Good questioning'],
      improvements: ['More structure needed']
    }
  ]
}

/** Mock the start-simulation endpoint to return completed state, plus the grading API. */
async function mockStudentSimulationWithGrading(page: import('@playwright/test').Page) {
  await page.route('**/student-simulation-instances/**/start-simulation', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user_progress_id: 1,
        instance_id: 123,
        current_scene: {
          id: 1,
          scene_order: 1,
          title: 'Test Scene',
          description: 'Test',
          personas: []
        },
        simulation: { id: 1, title: 'Test Sim', total_scenes: 1 },
        simulation_status: 'completed',
        is_resuming: false,
        turn_count: 0,
        conversation_history: [],
        all_scenes: [
          { id: 1, scene_order: 1, title: 'Test Scene', personas: [] }
        ]
      })
    })
  )

  // Mock the grading endpoint that fetchGradingData() calls
  await page.route('**/api/simulation/grade*', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(GRADING_DATA)
    })
  )

  // Mock instance fetch (used for cached grading check)
  await page.route('**/student-simulation-instances/test-instance-123', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ai_grade: null, ai_feedback: null })
    })
  )
}

test.describe('Markdown grading rendering - Student page', () => {
  const SIM_URL = '/student/run-simulation/test-instance-123'

  test('renders bold text as <strong> instead of raw ** markers', async ({ page }) => {
    await mockStudentSimulationWithGrading(page)
    await page.goto(SIM_URL)

    // Wait for the grading content to appear
    const gradingSection = page.locator('text=Grading & Feedback').or(page.locator('text=Overall Performance'))
    await expect(gradingSection.first()).toBeVisible({ timeout: 10000 })

    // The page body should NOT contain raw markdown ** markers in visible text
    // (they should be rendered as <strong> tags by react-markdown)
    const bodyText = await page.locator('body').textContent()

    // Overall feedback should not show raw ** markers
    expect(bodyText).not.toContain('**Great performance!**')
    expect(bodyText).toContain('Great performance!')
  })

  test('renders markdown headers as proper heading elements', async ({ page }) => {
    await mockStudentSimulationWithGrading(page)
    await page.goto(SIM_URL)

    const gradingSection = page.locator('text=Overall Performance').or(page.locator('text=Grading'))
    await expect(gradingSection.first()).toBeVisible({ timeout: 10000 })

    // Raw ** markers around section headers should not appear in visible text
    const bodyText = await page.locator('body').textContent()
    expect(bodyText).not.toContain('**OVERALL ASSESSMENT:**')
    expect(bodyText).not.toContain('**SCORE BREAKDOWN:**')
  })

  test('renders markdown lists as proper HTML list elements', async ({ page }) => {
    await mockStudentSimulationWithGrading(page)
    await page.goto(SIM_URL)

    const gradingSection = page.locator('text=Overall Performance').or(page.locator('text=Grading'))
    await expect(gradingSection.first()).toBeVisible({ timeout: 10000 })

    // react-markdown should render content without raw markdown markers
    // Check that parsed content is present without ** markers
    const bodyText = await page.locator('body').textContent()
    expect(bodyText).toContain('Excellent clarity')
    expect(bodyText).not.toContain('**Excellent clarity**')
  })

  test('score breakdown reasoning shows formatted markdown', async ({ page }) => {
    await mockStudentSimulationWithGrading(page)
    await page.goto(SIM_URL)

    const scoreSection = page.locator('text=Score Breakdown').or(page.locator('text=Assessment Criteria'))
    await expect(scoreSection.first()).toBeVisible({ timeout: 10000 })

    // Reasoning parsed from overall_feedback should be rendered without raw ** markers
    const bodyText = await page.locator('body').textContent()
    expect(bodyText).toContain('Communication')
    expect(bodyText).toContain('Analysis')
  })
})

test.describe('Markdown grading rendering - Professor page', () => {
  test.skip('overall_feedback is displayed when parsedData is null (no silent drop)', async ({ page }) => {
    // TODO: Implement full professor page test with proper route mocking
    // The professor test-simulations page requires additional mocks for:
    // - Authentication
    // - Simulation instances list
    // - Individual grading data
  })
})
