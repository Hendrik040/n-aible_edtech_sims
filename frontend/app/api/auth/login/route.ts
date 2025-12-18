import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    
    // Validate backend URL is configured
    const backendUrl = process.env.NEXT_PUBLIC_API_URL
    if (!backendUrl) {
      console.error('Login API route: NEXT_PUBLIC_API_URL is not configured')
      return NextResponse.json(
        { error: 'Backend server configuration is missing. Please contact support.' },
        { status: 500 }
      )
    }
    
    const backendEndpoint = `${backendUrl.replace(/\/$/, '')}/api/auth/users/login`
    
    let response: Response
    try {
      response = await fetch(backendEndpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      credentials: 'include',
    })
    } catch (fetchError) {
      console.error('Login API route: Network error connecting to backend:', fetchError)
      console.error('Login API route: Backend URL attempted:', backendEndpoint)
      return NextResponse.json(
        { error: 'Backend server is unavailable. Please try again in a moment.' },
        { status: 503 }
      )
    }
    
    // Handle 502 Bad Gateway specifically
    if (response.status === 502) {
      console.error('Login API route: 502 Bad Gateway - Backend server unreachable')
      return NextResponse.json(
        { error: 'Backend server is unavailable. Please try again in a moment.' },
        { status: 502 }
      )
    }

    const contentType = response.headers.get('content-type')
    if (!contentType?.includes('application/json')) {
      const text = await response.text()
      console.error('Non-JSON response:', text.substring(0, 200))
      return NextResponse.json(
        { error: 'Backend returned invalid response' },
        { status: 500 }
      )
    }

    const data = await response.json()
    
    if (!response.ok) {
      console.error('Login API route: Backend error response:', data)
      // Prioritize error field, then detail (FastAPI standard), then message
      const errorMessage = data.error || data.detail || data.message || 'Login failed'
      return NextResponse.json(
        { 
          error: errorMessage,
          details: data.detail ? (Array.isArray(data.detail) ? data.detail : [data.detail]) : undefined
        },
        { status: response.status }
      )
    }
    
    const nextResponse = NextResponse.json(data, { status: response.status })

    // Selectively rewrite access_token cookie with frontend-appropriate attributes
    const cookies = response.headers.getSetCookie?.() || []
    if (cookies.length > 0) {
      cookies.forEach(cookie => {
        // Parse the cookie string to extract key-value and attributes
        const [cookiePart, ...attributes] = cookie.split(';')
        const [key, value] = cookiePart.split('=')
        
        if (key && value && key.trim() === 'access_token') {
          // Recreate cookie with correct attributes for frontend
          const isProduction = process.env.NODE_ENV === 'production'
          const maxAge = 30 * 60 // 30 minutes in seconds
          
          // Build cookie string with correct attributes
          let cookieString = `${key.trim()}=${value.trim()}`
          cookieString += `; Path=/`
          cookieString += `; HttpOnly`
          cookieString += `; SameSite=${isProduction ? 'None' : 'Lax'}`
          if (isProduction) {
            cookieString += `; Secure`
          }
          cookieString += `; Max-Age=${maxAge}`
          
          nextResponse.headers.append('Set-Cookie', cookieString)
        }
      })
    }
    
    return nextResponse
  } catch (error) {
    console.error('Login API route: Unexpected error:', error)
    if (error instanceof Error) {
      console.error('Error stack:', error.stack)
    }
    return NextResponse.json(
      { error: 'Failed to login. Please try again.' },
      { status: 500 }
    )
  }
}

