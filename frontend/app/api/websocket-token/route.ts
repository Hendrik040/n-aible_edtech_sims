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
    const cookies = cookieHeader.split(';').reduce((acc, cookie) => {
      const [key, value] = cookie.trim().split('=')
      if (key && value) {
        acc[key] = value
      }
      return acc
    }, {} as Record<string, string>)
    
    const token = cookies['access_token']
    
    if (!token) {
      return NextResponse.json(
        { error: 'No access token found' },
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

