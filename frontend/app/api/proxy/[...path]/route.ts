import { NextRequest, NextResponse } from 'next/server'

// Ensure this runs as a Node.js function, not an edge function
export const runtime = 'nodejs'

/**
 * API Proxy Route - Forwards all authenticated requests to backend
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'GET')
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'POST')
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'PUT')
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'DELETE')
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const resolvedParams = await params
  return proxyRequest(request, resolvedParams.path, 'PATCH')
}

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string
) {
  try {
    // Reconstruct the full path - preserve trailing slash if present in original URL
    const path = pathSegments.join('/')
    const originalPath = request.nextUrl.pathname.replace('/api/proxy/', '')
    const hasTrailingSlash = originalPath.endsWith('/') && originalPath !== '/'
    const pathWithSlash = hasTrailingSlash && !path.endsWith('/') ? `${path}/` : path
    
    const backendUrl = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/${pathWithSlash}`
    
    // Get search params from the original request
    const searchParams = request.nextUrl.searchParams.toString()
    const fullUrl = searchParams ? `${backendUrl}?${searchParams}` : backendUrl
    
    
    // Prepare headers
    const headers: Record<string, string> = {}
    
    // Copy Content-Type from original request if present
    const originalContentType = request.headers.get('content-type')
    if (originalContentType) {
      // For FormData, we'll handle Content-Type in the body section
      if (!originalContentType.includes('multipart/form-data')) {
        headers['Content-Type'] = originalContentType
      }
    } else if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
      // Default to JSON for mutation requests without explicit content type
      headers['Content-Type'] = 'application/json'
    }
    
    // Get cookies from the incoming request
    const cookies = request.cookies.getAll()
    if (cookies.length > 0) {
      const cookieString = cookies.map(c => `${c.name}=${c.value}`).join('; ')
      headers['Cookie'] = cookieString
    }
    
    // Prepare fetch options
    const fetchOptions: RequestInit = {
      method,
      headers,
    }
    
    // Include body for POST, PUT, PATCH requests
    if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
      try {
        // Handle FormData (file uploads) differently from JSON/text
        if (originalContentType?.includes('multipart/form-data')) {
          // For FormData, convert stream to buffer to avoid duplex issues
          const chunks = []
          const reader = request.body?.getReader()
          if (reader) {
            try {
              while (true) {
                const { done, value } = await reader.read()
                if (done) break
                chunks.push(value)
              }
              const buffer = new Uint8Array(chunks.reduce((acc, chunk) => acc + chunk.length, 0))
              let offset = 0
              for (const chunk of chunks) {
                buffer.set(chunk, offset)
                offset += chunk.length
              }
              fetchOptions.body = buffer
            } catch (e) {
              console.error('Error reading stream:', e)
              // Fallback to text conversion
              const body = await request.text()
              fetchOptions.body = body
            }
          }
          // Don't set Content-Type header - let fetch handle the boundary
          delete headers['Content-Type']
          console.log('📁 Forwarding FormData request to backend:', fullUrl)
        } else {
          // For JSON/text data, convert to text
          const body = await request.text()
          if (body) {
            fetchOptions.body = body
          }
        }
      } catch (e) {
        // No body or invalid body, continue without it
        console.warn('Failed to process request body:', e)
      }
    }
    
    // Configure fetch to NOT follow redirects automatically to preserve cookies
    const fetchOptionsWithRedirect = {
      ...fetchOptions,
      redirect: 'manual' as RequestRedirect
    }
    
    let response = await fetch(fullUrl, fetchOptionsWithRedirect)
    
    // Handle redirects manually to preserve cookies
    if (response.status === 307 || response.status === 301 || response.status === 302) {
      const location = response.headers.get('location')
      if (location) {
        // Make a new request to the redirect URL with the same headers (including cookies)
        response = await fetch(location, fetchOptions)
      }
    }

    // If backend indicates method not allowed, retry once with a trailing slash
    // This helps when backend routes are defined with trailing slashes only
    if (response.status === 405 && !fullUrl.endsWith('/')) {
      try {
        const retryUrl = `${fullUrl}/`
        response = await fetch(retryUrl, fetchOptions)
      } catch (_) {
        // Ignore retry failure; original response will be handled below
      }
    }

    // Log 500 errors for debugging
    if (response.status === 500) {
      console.error(`Backend 500 error for ${method} ${fullUrl}`)
    }
    
    // Get response data
    const contentType = response.headers.get('content-type')
    let nextResponse: NextResponse
    
    if (contentType?.includes('application/json')) {
      // Read as text first to avoid consuming the stream
      const text = await response.text()
      try {
        const data = JSON.parse(text)
        nextResponse = NextResponse.json(data, { status: response.status })
      } catch (e) {
        // Invalid JSON, return as text (text variable already has the body)
        nextResponse = new NextResponse(text, { 
          status: response.status,
          headers: { 'Content-Type': 'text/plain' }
        })
      }
    } else {
      // Non-JSON response (text, HTML, etc.)
      const text = await response.text()
      nextResponse = new NextResponse(text, { 
        status: response.status,
        headers: { 'Content-Type': contentType || 'text/plain' }
      })
    }
    
    // Forward all Set-Cookie headers from backend to browser
    const setCookieHeaders = response.headers.getSetCookie?.() || []
    setCookieHeaders.forEach(cookie => {
      nextResponse.headers.append('Set-Cookie', cookie)
    })
    
    // Forward other important headers
    const headersToForward = ['cache-control', 'etag']
    headersToForward.forEach(headerName => {
      const value = response.headers.get(headerName)
      if (value) {
        nextResponse.headers.set(headerName, value)
      }
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
