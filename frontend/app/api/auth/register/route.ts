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
      // Handle FastAPI validation errors (array format) or simple string errors
      let errorMessage = 'Registration failed'
      if (Array.isArray(data.detail)) {
        // FastAPI validation errors come as an array
        errorMessage = data.detail.map((err: any) => 
          err.msg || err.message || JSON.stringify(err)
        ).join('. ')
      } else {
        errorMessage = data.detail || data.error || data.message || 'Registration failed'
      }
      console.error('Registration error from backend:', errorMessage, 'Full data:', data)
      return NextResponse.json(
        { 
          detail: errorMessage,
          error: errorMessage,
          message: errorMessage
        },
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
    const errorMessage = error instanceof Error ? error.message : String(error)
    return NextResponse.json(
      { 
        detail: errorMessage,
        error: 'Failed to register user',
        message: errorMessage
      },
      { status: 500 }
    )
  }
}
