import { NextRequest, NextResponse } from 'next/server'

// Ensure this runs as a Node.js function, not an edge function
export const runtime = 'nodejs'

/**
 * API Proxy Route - Forwards all authenticated requests to backend
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'GET')
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'POST')
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'PUT')
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'DELETE')
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'PATCH')
}

async function proxyRequest(request: NextRequest, pathSegments: string[], method: string) {
  try {
    // Build path from segments
    let path = pathSegments.join('/')
    
    // FastAPI requires trailing slashes for certain endpoints
    // Add trailing slash for known FastAPI routes that need it
    const endpointsNeedingSlash = [
      'api/publishing/scenarios',
      'api/scenarios',
      'api/cohorts',
      'professor/cohorts'
    ]
    
    if (endpointsNeedingSlash.includes(path) && !path.endsWith('/')) {
      path = `${path}/`
    }

    // Debug logging
    console.log('[PROXY] path segments:', pathSegments)
    console.log('[PROXY] final path:', path)

    const baseUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')
    const backendUrl = `${baseUrl}/${path}`

    const searchParams = request.nextUrl.searchParams.toString()
    const fullUrl = searchParams ? `${backendUrl}?${searchParams}` : backendUrl
    
    console.log('[PROXY] fullUrl:', fullUrl)

    // ---------------- HEADERS ----------------
    const headers: Record<string, string> = {}
    const originalContentType = request.headers.get('content-type')
    if (originalContentType) {
      headers['Content-Type'] = originalContentType
    } else if (['POST', 'PUT', 'PATCH'].includes(method)) {
      headers['Content-Type'] = 'application/json'
    }

    const cookies = request.cookies.getAll()
    if (cookies.length > 0) {
      headers['Cookie'] = cookies.map(c => `${c.name}=${c.value}`).join('; ')
    }

    // ---------------- FETCH OPTIONS ----------------
    const fetchOptions: RequestInit = { method, headers }

    // ✅ FIXED BODY HANDLING (preserve binary form-data)
    // request.body is already a Web ReadableStream, which is compatible with fetch()
    // When using streams, we need to specify duplex: 'half' for Node.js fetch
    const hasBody = ['POST', 'PUT', 'PATCH'].includes(method) && request.body
    if (hasBody) {
      fetchOptions.body = request.body
      // @ts-ignore - duplex is not in TypeScript types yet but is required by Node.js
      fetchOptions.duplex = 'half'
    }

    // Only use manual redirects for requests with bodies (to preserve stream)
    // GET requests can follow redirects automatically
    if (hasBody) {
      fetchOptions.redirect = 'manual'
    }

    let response = await fetch(fullUrl, fetchOptions)

    // ---------------- HANDLE REDIRECTS ----------------
    // Handle all redirects (301, 302, 307, 308)
    if ([301, 302, 307, 308].includes(response.status)) {
      const location = response.headers.get('location')
      if (location) {
        const redirectUrl = location.startsWith('http')
          ? location
          : `${baseUrl}${location}`
        console.log(`[PROXY] Following redirect from ${fullUrl} → ${redirectUrl}`)
        
        // For requests with bodies, use manual redirect
        if (hasBody) {
          // Note: Don't include body in redirect - streams can only be read once
          const redirectOptions = { 
            method: response.status === 307 || response.status === 308 ? method : 'GET',
            headers: { ...headers }
          }
          // Remove Content-Type for GET redirects
          if (response.status !== 307 && response.status !== 308) {
            delete redirectOptions.headers['Content-Type']
          }
          response = await fetch(redirectUrl, redirectOptions)
        } else {
          // For GET requests, just fetch the redirect location
          response = await fetch(redirectUrl, { method, headers })
        }
      }
    }

    // ---------------- HANDLE RESPONSE ----------------
    const contentType = response.headers.get('content-type')
    let nextResponse: NextResponse

    if (contentType?.includes('application/json')) {
      const text = await response.text()
      try {
        const data = JSON.parse(text)
        nextResponse = NextResponse.json(data, { status: response.status })
      } catch {
        nextResponse = new NextResponse(text, {
          status: response.status,
          headers: { 'Content-Type': 'text/plain' }
        })
      }
    } else {
      // ✅ Handle binary & non-JSON responses correctly
      const arrayBuffer = await response.arrayBuffer()
      nextResponse = new NextResponse(arrayBuffer, {
        status: response.status,
        headers: { 'Content-Type': contentType || 'application/octet-stream' }
      })
    }

    // ---------------- FORWARD COOKIES & HEADERS ----------------
    const setCookieHeaders = response.headers.getSetCookie?.() || []
    setCookieHeaders.forEach(cookie => {
      nextResponse.headers.append('Set-Cookie', cookie)
    })

    const headersToForward = ['cache-control', 'etag']
    headersToForward.forEach(headerName => {
      const value = response.headers.get(headerName)
      if (value) nextResponse.headers.set(headerName, value)
    })

    return nextResponse
  } catch (error) {
    console.error('Proxy error:', error)
    return NextResponse.json(
      {
        error: 'Proxy request failed',
        details: error instanceof Error ? error.message : String(error),
        method,
        path: pathSegments.join('/')
      },
      { status: 500 }
    )
  }
}
