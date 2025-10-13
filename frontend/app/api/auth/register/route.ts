import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    // Log safe metadata only - never log passwords or sensitive data
    console.log('Register API route: Registration attempt for role:', body.role, 'email:', body.email?.replace(/(.{2}).*(@.*)/, '$1***$2'))
    
    const backendUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/users/register`
    console.log('Register API route: Calling backend at:', backendUrl)
    
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    console.log('Register API route: Backend response status:', response.status)

    const data = await response.json()
    console.log('Register API route: Response data received')
    
    // Create NextResponse with the data
    const nextResponse = NextResponse.json(data, { status: response.status })
    
    // Forward all Set-Cookie headers from backend to browser
    // Node 18 compatibility: getSetCookie may return empty array, fallback to raw headers
    const setCookieHeaders = response.headers.getSetCookie?.() || []
    if (setCookieHeaders.length > 0) {
      setCookieHeaders.forEach(cookie => {
        nextResponse.headers.append('Set-Cookie', cookie)
      })
    } else {
      // Fallback for Node 18: use raw() method to access set-cookie headers
      const rawHeaders = response.headers.raw?.()
      const cookies = rawHeaders?.['set-cookie'] || []
      cookies.forEach(cookie => {
        nextResponse.headers.append('Set-Cookie', cookie)
      })
    }
    
    return nextResponse
  } catch (error) {
    console.error('Registration error:', error)
    console.error('Error message:', error instanceof Error ? error.message : String(error))
    return NextResponse.json(
      { error: 'Failed to register user', details: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    )
  }
}
