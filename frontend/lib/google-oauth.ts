// Google OAuth utility functions
function getApiBaseUrl(): string {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL
  if (!apiUrl) {
    // Check if we're in production
    if (process.env.NODE_ENV === 'production') {
      throw new Error('NEXT_PUBLIC_API_URL environment variable is required in production')
    }
    // Only allow localhost fallback in development
    return 'http://localhost:8000'
  }
  return apiUrl
}

// Lazy evaluation to avoid build-time errors
const getApiBaseUrlLazy = () => getApiBaseUrl()

// Configuration constants
const OAUTH_TIMEOUT_MS = 3600000 // 1 hour timeout for better UX

export interface GoogleOAuthResponse {
  auth_url: string
  state: string
}

export interface AccountLinkingData {
  action: 'link_required'
  message: string
  existing_user: {
    id: number
    email: string
    full_name: string
    provider: string
  }
  google_data: {
    email: string
    name: string
    picture?: string
  }
  state: string
}

export interface OAuthUserData {
  google_id: string
  email: string
  full_name: string
  avatar_url?: string
}

export interface OAuthSuccessData {
  user: {
    id: number
    email: string
    full_name: string
    username: string
    bio?: string
    avatar_url?: string
    role: string
    published_scenarios: number
    total_simulations: number
    reputation_score: number
    profile_public: boolean
    allow_contact: boolean
    is_active: boolean
    is_verified: boolean
    provider: string
    created_at: string
    updated_at: string
  }
  access_token: string
  token_type: string
}

export interface OAuthError {
  error: string
  message?: string
}

export type OpenAuthResult = AccountLinkingData | OAuthSuccessData | OAuthError | null

export class GoogleOAuth {
  private static instance: GoogleOAuth
  private authWindow: Window | null = null
  private state: string | null = null

  static getInstance(): GoogleOAuth {
    if (!GoogleOAuth.instance) {
      GoogleOAuth.instance = new GoogleOAuth()
    }
    return GoogleOAuth.instance
  }

  async initiateLogin(): Promise<GoogleOAuthResponse> {
    try {
      const response = await fetch(`${getApiBaseUrlLazy()}/auth/google/login`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error('Failed to initiate Google OAuth')
      }

      const data = await response.json()
      this.state = data.state
      return data
    } catch (error) {
      console.error('Error initiating Google OAuth:', error)
      throw error
    }
  }

  async openAuthWindow(): Promise<OpenAuthResult> {
    try {
      const { auth_url } = await this.initiateLogin()
      
      // Open popup window
      this.authWindow = window.open(
        auth_url,
        'google-oauth',
        'width=500,height=600,scrollbars=yes,resizable=yes'
      )

      if (!this.authWindow) {
        throw new Error('Failed to open OAuth window. Please allow popups.')
      }

      // Wait for messages from the popup
      return new Promise((resolve, reject) => {
        // Start checking authentication status immediately
        console.log('Frontend: Starting immediate auth status checks')
        let pollAttempts = 0
        const maxPollAttempts = 20 // Maximum 20 attempts (10 seconds)
        
        const immediateCheck = setInterval(() => {
          pollAttempts++
          
          // Only log every 5th attempt to reduce noise
          if (pollAttempts % 5 === 0) {
            console.log(`Frontend: Auth status check attempt ${pollAttempts}/${maxPollAttempts}`)
          }
          
          // Stop polling after max attempts
          if (pollAttempts >= maxPollAttempts) {
            console.log('Frontend: Max polling attempts reached, stopping')
            clearInterval(immediateCheck)
            return
          }
          
          this.checkAuthStatusAfterPopup()
            .then((authResult) => {
              if (authResult) {
                console.log('Frontend: User authenticated during OAuth flow')
                clearInterval(immediateCheck)
                try {
                  this.authWindow?.close()
                } catch (e) {
                  // Silent fail for window close
                }
                resolve(authResult)
              }
            })
            .catch((error) => {
              // Stop polling on repeated errors
              if (pollAttempts > 5) {
                console.log('Frontend: Too many auth check failures, stopping polling')
                clearInterval(immediateCheck)
                return
              }
              // Only log errors occasionally to reduce noise
              if (pollAttempts % 3 === 0) {
                console.log('Frontend: Auth check in progress...')
              }
            })
        }, 1000) // Check every 1 second (reduced frequency)
        // Set a timeout to prevent hanging (1 hour timeout)
        const timeout = setTimeout(() => {
          console.log('Frontend: OAuth timeout reached')
          clearInterval(immediateCheck)
          window.removeEventListener('message', messageHandler)
          try {
            this.authWindow?.close()
          } catch (e) {
            // Ignore COOP errors when closing window
            console.log('Window close blocked by COOP policy')
          }
          reject(new Error('OAuth timeout - please try again'))
        }, OAUTH_TIMEOUT_MS) // 1 hour timeout

        // Check if popup is closed and also periodically check auth status
        const checkClosed = setInterval(() => {
          if (this.authWindow?.closed) {
            console.log('Frontend: Popup was closed, checking authentication status')
            clearInterval(checkClosed)
            clearTimeout(timeout)
            window.removeEventListener('message', messageHandler)
            
            // Wait a moment for the backend to process the OAuth callback
            setTimeout(() => {
              this.checkAuthStatusAfterPopup()
                .then((authResult) => {
                  if (authResult) {
                    console.log('Frontend: User is authenticated after popup close')
                    resolve(authResult)
                  } else {
                    console.log('Frontend: User is not authenticated after popup close')
                    reject(new Error('OAuth popup was closed without authentication'))
                  }
                })
                .catch((error) => {
                  console.log('Frontend: Error checking auth status:', error)
                  reject(new Error('OAuth popup was closed without authentication'))
                })
            }, 1000) // Wait 1 second for backend processing
          } else {
            // Popup is still open, periodically check if user got authenticated
            this.checkAuthStatusAfterPopup()
              .then((authResult) => {
                if (authResult) {
                  console.log('Frontend: User authenticated while popup was open')
                  clearInterval(checkClosed)
                  clearTimeout(timeout)
                  window.removeEventListener('message', messageHandler)
                  try {
                    this.authWindow?.close()
                  } catch (e) {
                    console.log('Window close blocked by COOP policy')
                  }
                  resolve(authResult)
                }
              })
              .catch((error) => {
                // Ignore errors during periodic checks
                console.log('Frontend: Periodic auth check failed (this is normal):', error)
              })
          }
        }, 1000) // Check every 1 second for faster response

        // Listen for messages from the popup
        const messageHandler = (event: MessageEvent) => {
          console.log('Frontend: Received message from popup:', event.data, 'Origin:', event.origin, 'Expected origin:', window.location.origin)
          
          if (event.origin !== window.location.origin) {
            console.log('Frontend: Message origin mismatch, ignoring')
            return
          }

          if (event.data.type === 'GOOGLE_OAUTH_SUCCESS') {
            console.log('Frontend: Received GOOGLE_OAUTH_SUCCESS, processing...')
            clearTimeout(timeout)
            clearInterval(checkClosed)
            clearInterval(immediateCheck)
            window.removeEventListener('message', messageHandler)
            try {
              this.authWindow?.close()
              console.log('Frontend: Popup closed successfully')
            } catch (e) {
              // Ignore COOP errors when closing window
              console.log('Window close blocked by COOP policy')
            }
            console.log('Frontend: Resolving with data:', event.data.data)
            console.log('Frontend: User role from popup:', event.data.data?.user?.role)
            resolve(event.data.data)
          } else if (event.data.type === 'GOOGLE_OAUTH_ROLE_SELECTION_REQUIRED') {
            // Don't close the popup - let the user select a role
            console.log('🎯 Role selection required, keeping popup open')
            // Don't resolve or reject - keep waiting for role selection
          } else if (event.data.type === 'GOOGLE_OAUTH_ACCOUNT_LINKING_REQUIRED') {
            // Don't close the popup - let the user handle account linking
            console.log('🎯 Account linking required, keeping popup open')
            // Don't resolve or reject - keep waiting for account linking
          } else if (event.data.type === 'GOOGLE_OAUTH_ERROR') {
            console.log('Frontend: Received GOOGLE_OAUTH_ERROR')
            clearTimeout(timeout)
            clearInterval(checkClosed)
            clearInterval(immediateCheck)
            window.removeEventListener('message', messageHandler)
            try {
              this.authWindow?.close()
            } catch (e) {
              // Ignore COOP errors when closing window
              console.log('Window close blocked by COOP policy')
            }
            reject(new Error(event.data.error))
          } else {
            console.log('Frontend: Unknown message type:', event.data.type)
          }
        }

        window.addEventListener('message', messageHandler)
      })
    } catch (error) {
      console.error('Error in Google OAuth flow:', error)
      throw error
    }
  }

  async linkAccount(action: 'link' | 'create_separate', existingUserId: number, googleData: OAuthUserData, state: string, role?: 'student' | 'professor'): Promise<any> {
    console.log('GoogleOAuth: linkAccount called with:', {
      action,
      existingUserId,
      role,
      googleDataEmail: googleData.email
    })
    try {
      const requestBody = {
        action,
        existing_user_id: existingUserId,
        google_data: googleData,
        state,
        role,
      }
      console.log('GoogleOAuth: Sending request body:', requestBody)
      
      const response = await fetch(`${getApiBaseUrlLazy()}/auth/google/link`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        const errorData = await response.json()
        console.error('Link account error response:', errorData)
        
        // Handle different error formats
        let errorMessage = 'Failed to link account'
        if (errorData.detail) {
          if (Array.isArray(errorData.detail)) {
            // Pydantic validation errors
            errorMessage = errorData.detail.map((err: any) => err.msg || err.message || err).join(', ')
          } else if (typeof errorData.detail === 'string') {
            errorMessage = errorData.detail
          } else {
            errorMessage = JSON.stringify(errorData.detail)
          }
        }
        
        throw new Error(errorMessage)
      }

      const data = await response.json()
      
      // SECURITY: Tokens are now handled server-side via secure cookies
      // No client-side token storage to prevent XSS attacks
      
      return data
    } catch (error) {
      console.error('Error linking account:', error)
      throw error
    }
  }

  // Check authentication status after popup closes
  private async checkAuthStatusAfterPopup(): Promise<OAuthSuccessData | null> {
    try {
      const apiUrl = `${getApiBaseUrlLazy()}/auth/auth/status`
      
      const response = await fetch(apiUrl, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      })

      if (response.ok) {
        const data = await response.json()
        
        if (data.authenticated && data.user) {
          console.log('Frontend: User is authenticated:', data.user.email)
          // Convert to OAuthSuccessData format
          return {
            user: {
              id: data.user.id,
              email: data.user.email,
              full_name: data.user.full_name,
              username: data.user.username || data.user.email.split('@')[0],
              bio: data.user.bio,
              avatar_url: data.user.avatar_url,
              role: data.user.role,
              published_scenarios: data.user.published_scenarios || 0,
              total_simulations: data.user.total_simulations || 0,
              reputation_score: data.user.reputation_score || 0,
              profile_public: data.user.profile_public || false,
              allow_contact: data.user.allow_contact || false,
              is_active: data.user.is_active,
              is_verified: data.user.is_verified,
              provider: data.user.provider,
              created_at: data.user.created_at,
              updated_at: data.user.updated_at
            },
            access_token: '', // Token is handled via HttpOnly cookies
            token_type: 'cookie'
          }
        } else {
          // Silent - user not authenticated yet
        }
      } else {
        // Silent - auth status request failed
      }
      return null
    } catch (error) {
      // Silent error handling to reduce console noise
      return null
    }
  }

  // Alternative method using redirect instead of popup
  async redirectToGoogle(): Promise<void> {
    try {
      const { auth_url } = await this.initiateLogin()
      window.location.href = auth_url
    } catch (error) {
      console.error('Error redirecting to Google:', error)
      throw error
    }
  }
}

// Helper function to handle OAuth callback (for redirect method)
export async function handleOAuthCallback(): Promise<OpenAuthResult> {
  const urlParams = new URLSearchParams(window.location.search)
  const code = urlParams.get('code')
  const state = urlParams.get('state')
  const error = urlParams.get('error')

  if (error) {
    throw new Error(`OAuth error: ${error}`)
  }

  if (!code || !state) {
    throw new Error('Missing authorization code or state')
  }

  try {
    // Build URL with properly encoded parameters
    const params = new URLSearchParams({
      code: code,
      state: state
    })
    const response = await fetch(`${getApiBaseUrlLazy()}/auth/google/callback?${params.toString()}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(errorData.detail || 'OAuth callback failed')
    }

    const data = await response.json()
    
    // SECURITY: Tokens are now handled server-side via secure cookies
    // No client-side token storage to prevent XSS attacks
    
    return data
  } catch (error) {
    console.error('Error handling OAuth callback:', error)
    throw error
  }
}
