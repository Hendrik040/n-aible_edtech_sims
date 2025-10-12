import { NextRequest } from 'next/server'

// Ensure this runs as a Node.js function, not an edge function
export const runtime = 'nodejs'

/**
 * Dedicated API route for streaming chat responses
 * This route doesn't buffer the response like the generic proxy,
 * allowing Server-Sent Events (SSE) to work properly in production.
 */
export async function POST(request: NextRequest) {
  try {
    const baseUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')
    const backendUrl = `${baseUrl}/api/simulation/linear-chat-stream`

    // Get request body
    const body = await request.json()
    
    // Get cookies for authentication
    const cookies = request.cookies.getAll()
    const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ')

    // Forward the request to the backend
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': cookieHeader,
      },
      body: JSON.stringify(body),
    })

    if (!response.ok) {
      return new Response(
        JSON.stringify({ error: `Backend error: ${response.status}` }),
        { 
          status: response.status,
          headers: { 'Content-Type': 'application/json' }
        }
      )
    }

    // Create a new ReadableStream that forwards the backend stream
    const stream = new ReadableStream({
      async start(controller) {
        const reader = response.body?.getReader()
        if (!reader) {
          controller.close()
          return
        }

        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) {
              controller.close()
              break
            }
            controller.enqueue(value)
          }
        } catch (error) {
          controller.error(error)
        }
      },
    })

    // Return the streaming response with proper headers
    return new Response(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no', // Disable nginx buffering
      },
    })
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: 'Streaming proxy failed',
        details: error instanceof Error ? error.message : String(error)
      }),
      { 
        status: 500,
        headers: { 'Content-Type': 'application/json' }
      }
    )
  }
}

