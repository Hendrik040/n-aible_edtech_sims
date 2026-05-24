"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"

export default function GoogleCallbackPage() {
  const router = useRouter()
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing')
  const [message, setMessage] = useState('Processing authentication...')
  
  useEffect(() => {
    const handleCallback = async () => {
      try {
        const urlParams = new URLSearchParams(window.location.search)
        const token = urlParams.get('token')
        const userData = urlParams.get('user')

        console.log('Frontend callback: Received token and user data')

        if (token && userData) {
          // Set the auth cookie on the frontend domain
          // This is necessary because the backend sets it on its domain during redirect
          console.log('Frontend callback: Setting auth cookie on frontend domain')
          
          try {
            const cookieResponse = await fetch('/api/auth/set-token', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ token }),
              credentials: 'include',
            })
            
            if (!cookieResponse.ok) {
              console.warn('Frontend callback: Failed to set cookie, but continuing...')
            } else {
              console.log('Frontend callback: Cookie set successfully on frontend domain')
            }
          } catch (cookieError) {
            console.warn('Frontend callback: Error setting cookie:', cookieError)
          }

          // Parse user data
          const responseData = JSON.parse(decodeURIComponent(userData))
          const user = responseData.user
          console.log('Frontend callback: User data:', user)

          // Store user data in sessionStorage for immediate access
          sessionStorage.setItem('user', JSON.stringify(user))
          console.log('Frontend callback: Stored user in sessionStorage')

          // Check if this is a popup window
          if (window.opener && !window.opener.closed) {
            // This is a popup - redirect the opener window directly
            console.log('Frontend callback: Running in popup, redirecting opener')
            setStatus('success')
            setMessage('Authentication successful! Redirecting...')
            
            // Determine dashboard URL based on user role
            const dashboardUrl = user.role === 'admin'
              ? '/admin/dashboard'
              : user.role === 'professor'
                ? '/professor/dashboard'
                : user.role === 'student'
                  ? '/student/dashboard'
                  : '/dashboard'

            try {
              // Navigate the opener window directly (works even with cross-origin restrictions)
              // This is a navigation, not script communication, so COOP doesn't block it
              window.opener.location.href = dashboardUrl
              console.log('Frontend callback: Redirected opener to', dashboardUrl)
            } catch (e) {
              console.log('Frontend callback: Could not redirect opener, trying postMessage')
              try {
                window.opener.postMessage({ type: 'GOOGLE_OAUTH_SUCCESS', user }, window.location.origin)
              } catch (e2) {
                console.log('Frontend callback: postMessage also failed, opener will use polling')
              }
            }
            
            // Close popup after short delay
            setTimeout(() => {
              window.close()
            }, 500)
          } else {
            // Not a popup - redirect directly (fallback for direct navigation)
            console.log('Frontend callback: Not a popup, redirecting directly')
            setStatus('success')
            setMessage('Authentication successful! Redirecting...')
            
            const dashboardUrl = user.role === 'admin'
              ? '/admin/dashboard'
              : user.role === 'professor'
                ? '/professor/dashboard'
                : user.role === 'student'
                  ? '/student/dashboard'
                  : '/dashboard'

            setTimeout(() => {
              window.location.href = dashboardUrl
            }, 500)
          }
        } else {
          console.error('Frontend callback: Missing token or user data')
          setStatus('error')
          setMessage('Authentication failed. Redirecting to login...')
          setTimeout(() => router.push('/'), 2000)
        }
      } catch (error) {
        console.error('Frontend callback: Error handling callback:', error)
        setStatus('error')
        setMessage('Authentication error. Redirecting to login...')
        setTimeout(() => router.push('/'), 2000)
      }
    }

    handleCallback()
  }, [router])
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center">
      <div className="text-center">
        {status === 'processing' && (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
            <p className="text-white">{message}</p>
          </>
        )}
        {status === 'success' && (
          <>
            <div className="w-12 h-12 mx-auto mb-4 bg-green-500/20 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-green-400">{message}</p>
          </>
        )}
        {status === 'error' && (
          <>
            <div className="w-12 h-12 mx-auto mb-4 bg-red-500/20 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <p className="text-red-400">{message}</p>
          </>
        )}
      </div>
    </div>
  )
}