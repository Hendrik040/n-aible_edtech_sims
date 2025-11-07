import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    console.log('Register API route: Registration attempt for role:', body.role, 'email:', body.email?.replace(/(.{2}).*(@.*)/, '$1***$2'))
    
    const backendUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/users/register`
    console.log('Register API route: Calling backend at:', backendUrl)
    
    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      credentials: 'include', // Include cookies in request/response
    })

    console.log('Register API route: Backend response status:', response.status)

    const contentType = response.headers.get('content-type')
    if (!contentType?.includes('application/json')) {
      const text = await response.text()
      console.error('Register API route: Non-JSON response:', text.substring(0, 200))
      return NextResponse.json(
        { error: 'Backend returned invalid response', details: 'Backend server may not be running or encountered an error' },
        { status: 500 }
      )
    }

    const data = await response.json()
    
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || data.error || 'Registration failed' },
        { status: response.status }
      )
    }
    
    const nextResponse = NextResponse.json(data, { status: response.status })
    
    const setCookieHeaders = response.headers.getSetCookie?.() || []
    setCookieHeaders.forEach(cookie => {
      nextResponse.headers.append('Set-Cookie', cookie)
    })
    
    return nextResponse
  } catch (error) {
    console.error('Registration error:', error)
    return NextResponse.json(
      { error: 'Failed to register user', details: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    )
  }
}