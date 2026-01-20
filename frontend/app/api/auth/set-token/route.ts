import { NextRequest, NextResponse } from 'next/server'

/**
 * API Route to set the authentication cookie on the frontend domain.
 * 
 * This is needed because Google OAuth redirects to the backend, which sets
 * the cookie on the backend domain. For same-origin cookie access, we need
 * to set it on the frontend domain via this route.
 */
export async function POST(request: NextRequest) {
  try {
    const { token } = await request.json()
    
    if (!token) {
      return NextResponse.json(
        { error: 'Token is required' },
        { status: 400 }
      )
    }
    
    const response = NextResponse.json({ success: true })
    
    // Set the same cookie that the backend would set
    // This cookie will be on localhost:3000 (frontend domain)
    const isProduction = process.env.NODE_ENV === 'production'
    
    response.cookies.set({
      name: 'access_token',
      value: token,
      httpOnly: true,
      secure: isProduction,
      sameSite: 'lax',
      path: '/',
      maxAge: 60 * 60 * 6, // 6 hours (matches backend ACCESS_TOKEN_EXPIRE_MINUTES)
    })
    
    return response
  } catch (error) {
    console.error('Error setting token cookie:', error)
    return NextResponse.json(
      { error: 'Failed to set token' },
      { status: 500 }
    )
  }
}
