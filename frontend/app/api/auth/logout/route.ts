import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Cookie': request.headers.get('cookie') || '',
      },
    })

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

