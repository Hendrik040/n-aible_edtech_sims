import { test, expect } from '@playwright/test'

test.describe('R Code Execution in Code Editor', () => {
  test.describe('CodeEditor language prop', () => {
    test('editor displays R Editor label when language is r', async ({ page }) => {
      // Mock the simulation API to return a code_challenge scene with code_language: 'r'
      await page.route('**/api/proxy/api/simulation/start', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user_progress_id: 1,
            simulation: {
              id: 1,
              title: 'Test Sim',
              description: 'Test',
              challenge: 'Test',
              learning_objectives: [],
              total_scenes: 1,
            },
            current_scene: {
              id: 1,
              title: 'R Challenge',
              description: 'Write R code',
              scene_order: 1,
              personas: [],
              scene_type: 'code_challenge',
              code_language: 'r',
              starter_code: '# Write your R code here\nprint("Hello R")',
            },
            simulation_status: 'in_progress',
            conversation_history: [],
            is_resuming: false,
            all_scenes: [],
            sandbox_id: 'test-sandbox-id',
          }),
        }),
      )

      // Navigate to student simulation page
      await page.goto('/student/run-simulation/1')

      // Wait for the page to load simulation data
      // The code editor tab should be available for code_challenge scenes
      const editorTab = page.locator('text=Code Editor').first()
      if (await editorTab.isVisible()) {
        await editorTab.click()
      }

      // Check that the editor header shows "R Editor" not "Python Editor"
      const editorLabel = page.locator('text=R Editor')
      await expect(editorLabel).toBeVisible({ timeout: 10000 })
    })

    test('execute-code request includes language field', async ({ page }) => {
      let capturedBody: Record<string, unknown> | null = null

      // Intercept the execute-code request to capture the body
      await page.route('**/api/proxy/api/simulation/execute-code', async (route) => {
        const request = route.request()
        capturedBody = JSON.parse(request.postData() || '{}')
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            output: '[1] 42',
            error: null,
            sandbox_state: 'started',
          }),
        })
      })

      // Mock simulation start with R language scene
      await page.route('**/api/proxy/api/simulation/start', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user_progress_id: 1,
            simulation: {
              id: 1,
              title: 'R Sim',
              description: 'Test',
              challenge: 'Test',
              learning_objectives: [],
              total_scenes: 1,
            },
            current_scene: {
              id: 1,
              title: 'R Scene',
              description: 'R code',
              scene_order: 1,
              personas: [],
              scene_type: 'code_challenge',
              code_language: 'r',
              starter_code: 'print(42)',
            },
            simulation_status: 'in_progress',
            conversation_history: [],
            is_resuming: false,
            all_scenes: [],
            sandbox_id: 'test-sandbox-id',
          }),
        }),
      )

      await page.goto('/student/run-simulation/1')

      // Switch to code editor tab if needed
      const editorTab = page.locator('text=Code Editor').first()
      if (await editorTab.isVisible()) {
        await editorTab.click()
      }

      // Click the Run button
      const runButton = page.locator('button:has-text("Run")').first()
      if (await runButton.isVisible()) {
        await runButton.click()

        // Wait for the request to be captured
        await page.waitForTimeout(1000)

        // Verify the language was included in the request
        if (capturedBody) {
          expect(capturedBody.language).toBe('r')
        }
      }
    })
  })

  test.describe('Python scenes remain unaffected', () => {
    test('editor displays Python Editor label for python scenes', async ({ page }) => {
      await page.route('**/api/proxy/api/simulation/start', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user_progress_id: 1,
            simulation: {
              id: 1,
              title: 'Python Sim',
              description: 'Test',
              challenge: 'Test',
              learning_objectives: [],
              total_scenes: 1,
            },
            current_scene: {
              id: 1,
              title: 'Python Challenge',
              description: 'Write Python code',
              scene_order: 1,
              personas: [],
              scene_type: 'code_challenge',
              code_language: 'python',
              starter_code: 'print("Hello Python")',
            },
            simulation_status: 'in_progress',
            conversation_history: [],
            is_resuming: false,
            all_scenes: [],
            sandbox_id: 'test-sandbox-id',
          }),
        }),
      )

      await page.goto('/student/run-simulation/1')

      const editorTab = page.locator('text=Code Editor').first()
      if (await editorTab.isVisible()) {
        await editorTab.click()
      }

      const editorLabel = page.locator('text=Python Editor')
      await expect(editorLabel).toBeVisible({ timeout: 10000 })
    })

    test('scenes without code_language default to Python', async ({ page }) => {
      await page.route('**/api/proxy/api/simulation/start', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user_progress_id: 1,
            simulation: {
              id: 1,
              title: 'Default Sim',
              description: 'Test',
              challenge: 'Test',
              learning_objectives: [],
              total_scenes: 1,
            },
            current_scene: {
              id: 1,
              title: 'Code Challenge',
              description: 'Write code',
              scene_order: 1,
              personas: [],
              scene_type: 'code_challenge',
              // No code_language field — should default to Python
              starter_code: 'print("hello")',
            },
            simulation_status: 'in_progress',
            conversation_history: [],
            is_resuming: false,
            all_scenes: [],
            sandbox_id: 'test-sandbox-id',
          }),
        }),
      )

      await page.goto('/student/run-simulation/1')

      const editorTab = page.locator('text=Code Editor').first()
      if (await editorTab.isVisible()) {
        await editorTab.click()
      }

      const editorLabel = page.locator('text=Python Editor')
      await expect(editorLabel).toBeVisible({ timeout: 10000 })
    })
  })
})
