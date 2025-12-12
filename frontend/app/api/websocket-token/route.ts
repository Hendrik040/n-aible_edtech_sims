import { NextRequest, NextResponse } from 'next/server'

/**
 * API route to get WebSocket token for authenticated users.
 * This allows us to get the token server-side (where cookies are accessible)
 * and pass it to the WebSocket connection.
 */
export async function GET(request: NextRequest) {
  try {
    // Get token from cookies (server-side can read HttpOnly cookies)
    const cookieHeader = request.headers.get('cookie') || ''
    
    if (!cookieHeader) {
      console.log('WebSocket token route - No cookie header found')
      return NextResponse.json(
        { error: 'No cookies found' },
        { status: 401 }
      )
    }
    
    // Parse cookies - handle multiple cookies separated by semicolons
    const cookies: Record<string, string> = {}
    cookieHeader.split(';').forEach(cookie => {
      const trimmed = cookie.trim()
      const equalIndex = trimmed.indexOf('=')
      if (equalIndex > 0) {
        const key = trimmed.substring(0, equalIndex).trim()
        const value = trimmed.substring(equalIndex + 1).trim()
        if (key && value) {
          cookies[key] = decodeURIComponent(value)
        }
      }
    })
    
    const token = cookies['access_token']
    
    if (!token) {
      console.log('WebSocket token route - No access_token found. Available cookies:', Object.keys(cookies))
      return NextResponse.json(
        { error: 'No access token found in cookies' },
        { status: 401 }
      )
    }
    
    return NextResponse.json({ token })
  } catch (error) {
    console.error('Error getting WebSocket token:', error)
    return NextResponse.json(
      { error: 'Failed to get token' },
      { status: 500 }
    )
  }
}

