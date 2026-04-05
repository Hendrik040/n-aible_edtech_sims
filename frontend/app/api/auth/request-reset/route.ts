import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()

    const backendUrl = process.env.NEXT_PUBLIC_API_URL
    if (!backendUrl) {
      console.error('Request-reset API route: NEXT_PUBLIC_API_URL is not configured')
      return NextResponse.json(
        { error: 'Backend server configuration is missing. Please contact support.' },
        { status: 500 }
      )
    }

    const backendEndpoint = `${backendUrl.replace(/\/$/, '')}/api/auth/users/request-reset`

    let response: Response
    try {
      response = await fetch(backendEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } catch (fetchError) {
      console.error('Request-reset API route: Network error:', fetchError)
      return NextResponse.json(
        { error: 'Backend server is unavailable. Please try again in a moment.' },
        { status: 503 }
      )
    }

    const contentType = response.headers.get('content-type')
    if (!contentType?.includes('application/json')) {
      const text = await response.text()
      console.error('Request-reset: non-JSON response:', text.substring(0, 200))
      return NextResponse.json(
        { error: 'Backend returned invalid response' },
        { status: 500 }
      )
    }

    const data = await response.json()

    if (!response.ok) {
      const errorMessage = data.error || data.detail || data.message || 'Unable to send reset email'
      return NextResponse.json({ error: errorMessage }, { status: response.status })
    }

    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Request-reset API route: Unexpected error:', error)
    return NextResponse.json(
      { error: 'Failed to process request. Please try again.' },
      { status: 500 }
    )
  }
}
