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

    // Get the set-cookie header from backend response
    // Get all Set-Cookie headers using getSetCookie() with fallback
    const setCookieHeaders = 
      (response.headers as unknown as { getSetCookie?: () => string[] }).getSetCookie?.() ??
      (response.headers.get('set-cookie') ? [response.headers.get('set-cookie') as string] : [])
    
    const data = await response.json()
    console.log('Register API route: Response data received')
    // Forward all Set-Cookie headers from backend to browser
    const setCookieHeaders = response.headers.getSetCookie?.() || []
    const nextResponse = NextResponse.json(data, { status: response.status })
    
    // If backend set a cookie, forward it to the browser
    // Forward all cookies to the client
    for (const cookie of setCookieHeaders) {
      nextResponse.headers.append('set-cookie', cookie)
    }
    
    return nextResponse
    console.error('Error message:', error instanceof Error ? error.message : String(error))
    return NextResponse.json(
      { error: 'Failed to register user', details: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    )
  }
}
