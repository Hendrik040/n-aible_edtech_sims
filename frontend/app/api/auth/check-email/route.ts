import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/users/check-email`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    const contentType = response.headers.get('content-type')
    if (!contentType?.includes('application/json')) {
      const text = await response.text()
      console.error('Email check: Non-JSON response:', text.substring(0, 200))
      return NextResponse.json(
        { error: 'Backend returned invalid response', exists: false },
        { status: 500 }
      )
    }

    const data = await response.json()
    
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || data.error || 'Failed to check email', exists: false },
        { status: response.status }
      )
    }
    
    return NextResponse.json(data, { status: response.status })
  } catch (error) {
    console.error('Email check error:', error)
    return NextResponse.json(
      { error: 'Failed to check email', exists: false },
      { status: 500 }
    )
  }
}
