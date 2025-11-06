import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    // Forward cookies from the incoming request to the backend
    const cookieHeader = request.headers.get('cookie') || ''
    
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/auth/auth/status`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Cookie': cookieHeader, // Forward the cookies to the backend
      },
      credentials: 'include', // Include cookies in request/response
    })

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Auth status check error:', error)
    return NextResponse.json(
      { error: 'Failed to check auth status' },
      { status: 500 }
    )
  }
}
