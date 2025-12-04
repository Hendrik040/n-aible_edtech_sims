import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    // Validate backend URL is configured
    const backendUrl = process.env.NEXT_PUBLIC_API_URL
    if (!backendUrl) {
      console.error('Logout API route: NEXT_PUBLIC_API_URL is not configured')
      return NextResponse.json(
        { error: 'Backend server configuration is missing. Please contact support.' },
        { status: 500 }
      )
    }
    
    const backendEndpoint = `${backendUrl.replace(/\/$/, '')}/api/auth/users/logout`
    
    let response: Response
    try {
      response = await fetch(backendEndpoint, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Cookie': request.headers.get('cookie') || '',
      },
    })
    } catch (fetchError) {
      console.error('Logout API route: Network error connecting to backend:', fetchError)
      console.error('Logout API route: Backend URL attempted:', backendEndpoint)
      return NextResponse.json(
        { error: 'Backend server is unavailable. Please try again in a moment.' },
        { status: 503 }
      )
    }
    
    // Handle 502 Bad Gateway specifically
    if (response.status === 502) {
      console.error('Logout API route: 502 Bad Gateway - Backend server unreachable')
      return NextResponse.json(
        { error: 'Backend server is unavailable. Please try again in a moment.' },
        { status: 502 }
      )
    }

    // Check response status first
    if (!response.ok) {
      const contentType = response.headers.get('content-type')
      if (contentType?.includes('application/json')) {
        const errorData = await response.json().catch(() => ({}))
        console.error('Logout API route: Backend error response:', errorData)
        return NextResponse.json(
          { 
            error: errorData.detail || errorData.error || 'Logout failed',
            details: errorData.detail ? (Array.isArray(errorData.detail) ? errorData.detail : [errorData.detail]) : undefined
          },
          { status: response.status }
        )
      } else {
        const text = await response.text().catch(() => 'Unknown error')
        console.error('Logout API route: Non-JSON error response:', text.substring(0, 200))
        return NextResponse.json(
          { error: `Logout failed: ${text.substring(0, 100)}` },
          { status: response.status }
        )
      }
    }

    // Verify Content-Type before parsing JSON
    const contentType = response.headers.get('content-type')
    if (!contentType?.includes('application/json')) {
      const text = await response.text()
      console.error('Logout API route: Non-JSON response:', text.substring(0, 200))
      return NextResponse.json(
        { error: 'Backend returned invalid response' },
        { status: 500 }
      )
    }

    const data = await response.json()
    
    const nextResponse = NextResponse.json(data, { status: response.status })
    
    const setCookieHeaders = response.headers.getSetCookie?.() || []
    
    if (setCookieHeaders.length > 0) {
      setCookieHeaders.forEach(cookie => {
        nextResponse.headers.append('Set-Cookie', cookie)
      })
    } else {
      const setCookieHeader = response.headers.get('set-cookie')
      if (setCookieHeader) {
        const cookies = Array.isArray(setCookieHeader) ? setCookieHeader : [setCookieHeader]
        cookies.forEach(cookie => {
          nextResponse.headers.append('Set-Cookie', cookie)
        })
      }
    }
    
    return nextResponse
  } catch (error) {
    // Log full error details for server-side debugging
    console.error('Logout API route: Unexpected error:', error)
    if (error instanceof Error) {
      console.error('Error stack:', error.stack)
    }
    
    // Return generic error to client (don't expose internal error details)
    return NextResponse.json(
      { error: 'Failed to logout. Please try again.' },
      { status: 500 }
    )
  }
}

