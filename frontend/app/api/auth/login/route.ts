import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    
    // Check if backend URL is configured
    const backendUrl = process.env.NEXT_PUBLIC_API_URL
    if (!backendUrl) {
      console.error('NEXT_PUBLIC_API_URL is not set')
      return NextResponse.json(
        { 
          error: 'Backend configuration error',
          detail: 'NEXT_PUBLIC_API_URL environment variable is not set. Please configure your backend URL.'
        },
        { status: 500 }
      )
    }
    
    const loginUrl = `${backendUrl.replace(/\/$/, '')}/users/login`
    
    let response: Response
    try {
      response = await fetch(loginUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
        credentials: 'include', // Include cookies in request/response
      })
    } catch (fetchError) {
      // Network error - backend is unreachable
      console.error('Network error connecting to backend:', fetchError)
      const errorMessage = fetchError instanceof Error ? fetchError.message : 'Unknown network error'
      return NextResponse.json(
        { 
          error: 'Backend connection failed',
          detail: `Unable to connect to backend at ${backendUrl}. Please check if the backend service is running.`,
          message: errorMessage
        },
        { status: 502 }
      )
    }
    
    // Check if response is ok before parsing
    if (!response.ok) {
      // Try to parse error response
      let errorData: any = {}
      try {
        const text = await response.text()
        if (text) {
          errorData = JSON.parse(text)
        }
      } catch (parseError) {
        // If parsing fails, use status text
        errorData = { detail: response.statusText || 'Unknown error' }
      }
      
      // Return error with appropriate status
      return NextResponse.json(
        { 
          error: errorData.detail || errorData.message || 'Login failed',
          detail: errorData.detail || errorData.message || `Backend returned ${response.status}: ${response.statusText}`
        },
        { status: response.status }
      )
    }
    
    // Parse successful response
    const data = await response.json()
    
    // Create NextResponse with the data
    const nextResponse = NextResponse.json(data, { status: response.status })
    
    // Forward all Set-Cookie headers from backend to browser
    const setCookieHeaders = response.headers.getSetCookie?.() || []
    setCookieHeaders.forEach(cookie => {
      nextResponse.headers.append('Set-Cookie', cookie)
    })
    
    return nextResponse
  } catch (error) {
    console.error('Login error:', error)
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    return NextResponse.json(
      { 
        error: 'Login request failed',
        detail: errorMessage
      },
      { status: 500 }
    )
  }
}
