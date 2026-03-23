import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    const backendUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL
    if (!backendUrl) {
      return NextResponse.json(
        { error: 'Backend server configuration is missing.' },
        { status: 500 }
      )
    }

    const endpoint = `${backendUrl.replace(/\/$/, '')}/api/auth/users/reset-password`

    let response: Response
    try {
      response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(10000),
      })
    } catch (fetchError) {
      console.error('reset-password route: network error:', fetchError)
      return NextResponse.json(
        { error: 'Backend server is unavailable. Please try again.' },
        { status: 503 }
      )
    }

    const data = await response.json().catch(() => ({}))

    if (!response.ok) {
      const errorMessage = data.detail || data.error || data.message || 'Request failed'
      return NextResponse.json({ error: errorMessage }, { status: response.status })
    }

    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('reset-password route: unexpected error:', error)
    return NextResponse.json({ error: 'Something went wrong. Please try again.' }, { status: 500 })
  }
}
