import { NextRequest, NextResponse } from 'next/server'

/**
 * Validates and returns the allowed origin for CORS
 * Returns null if origin is not allowed or if same-origin request
 */
function getAllowedOrigin(request: NextRequest): string | null {
  const origin = request.headers.get('origin')
  
  // Same-origin requests don't need CORS
  if (!origin) {
    return null
  }

  // Get allowed origins from environment variable (comma-separated)
  const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',').map(o => o.trim()) || []
  
  // If no allowed origins configured, allow same-origin only (no CORS)
  if (allowedOrigins.length === 0) {
    return null
  }

  // Check if origin is in allowed list
  if (allowedOrigins.includes(origin)) {
    return origin
  }

  // Origin not allowed
  return null
}

export async function OPTIONS(request: NextRequest) {
  const allowedOrigin = getAllowedOrigin(request)
  
  const headers: Record<string, string> = {
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Cookie',
  }

  // Only set CORS headers if we have a valid origin
  if (allowedOrigin) {
    headers['Access-Control-Allow-Origin'] = allowedOrigin
    headers['Access-Control-Allow-Credentials'] = 'true'
  }

  return new NextResponse(null, {
    status: 200,
    headers,
  })
}

export async function GET(request: NextRequest) {
  try {
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/auth/me`, {
      method: 'GET',
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
        const errorResponse = NextResponse.json(
          { 
            error: errorData.detail || errorData.error || 'Unauthorized',
            details: errorData.detail ? (Array.isArray(errorData.detail) ? errorData.detail : [errorData.detail]) : undefined
          },
          { status: response.status }
        )
        
        // Add CORS headers if needed
        const allowedOrigin = getAllowedOrigin(request)
        if (allowedOrigin) {
          errorResponse.headers.set('Access-Control-Allow-Origin', allowedOrigin)
          errorResponse.headers.set('Access-Control-Allow-Credentials', 'true')
        }
        
        return errorResponse
      } else {
        const text = await response.text().catch(() => 'Unknown error')
        const errorResponse = NextResponse.json(
          { error: `Unauthorized: ${text.substring(0, 100)}` },
          { status: response.status }
        )
        
        // Add CORS headers if needed
        const allowedOrigin = getAllowedOrigin(request)
        if (allowedOrigin) {
          errorResponse.headers.set('Access-Control-Allow-Origin', allowedOrigin)
          errorResponse.headers.set('Access-Control-Allow-Credentials', 'true')
        }
        
        return errorResponse
      }
    }

    // Verify Content-Type before parsing JSON
    const contentType = response.headers.get('content-type')
    if (!contentType?.includes('application/json')) {
      const text = await response.text()
      console.error('Get current user API route: Non-JSON response:', text.substring(0, 200))
      const errorResponse = NextResponse.json(
        { error: 'Backend returned invalid response' },
        { status: 500 }
      )
      
      // Add CORS headers if needed
      const allowedOrigin = getAllowedOrigin(request)
      if (allowedOrigin) {
        errorResponse.headers.set('Access-Control-Allow-Origin', allowedOrigin)
        errorResponse.headers.set('Access-Control-Allow-Credentials', 'true')
      }
      
      return errorResponse
    }

    const data = await response.json()
    const nextResponse = NextResponse.json(data, { status: response.status })
    
    // Forward Set-Cookie headers from backend to preserve refreshed tokens/sessions
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
    
    // Add CORS headers if needed
    const allowedOrigin = getAllowedOrigin(request)
    if (allowedOrigin) {
      nextResponse.headers.set('Access-Control-Allow-Origin', allowedOrigin)
      nextResponse.headers.set('Access-Control-Allow-Credentials', 'true')
    }
    
    return nextResponse
  } catch (error) {
    console.error('Get current user API route: Unexpected error:', error)
    if (error instanceof Error) {
      console.error('Error stack:', error.stack)
    }
    
    const errorResponse = NextResponse.json(
      { error: 'Failed to get current user. Please try again.' },
      { status: 500 }
    )
    
    // Add CORS headers if needed
    const allowedOrigin = getAllowedOrigin(request)
    if (allowedOrigin) {
      errorResponse.headers.set('Access-Control-Allow-Origin', allowedOrigin)
      errorResponse.headers.set('Access-Control-Allow-Credentials', 'true')
    }
    
    return errorResponse
  }
}

