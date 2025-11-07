import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    const backendResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/users/forgot-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      credentials: 'include',
    })

    const contentType = backendResponse.headers.get('content-type') || ''
    const payload = contentType.includes('application/json')
      ? await backendResponse.json()
      : { detail: await backendResponse.text() }

    return NextResponse.json(payload, { status: backendResponse.status })
  } catch (error) {
    console.error('Forgot password error:', error)
    return NextResponse.json(
      { detail: 'Failed to reset password. Please try again.' },
      { status: 500 }
    )
  }
}

