"use client"

import React, { createContext, useContext, ReactNode, useEffect } from 'react'
import { apiClient, User, LoginCredentials, RegisterData } from './api'
import { GoogleOAuth, AccountLinkingData, OAuthSuccessData, OAuthUserData, OAuthError } from './google-oauth'

// Define proper types for Google OAuth responses
export interface GoogleOAuthSuccessData {
  user: User
  access_token?: string
  message?: string
}

export interface AuthError {
  error: string
  message?: string
}

export type GoogleOAuthResult = AccountLinkingData | GoogleOAuthSuccessData | OAuthError

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  register: (data: RegisterData) => Promise<void>
  loginWithGoogle: () => Promise<GoogleOAuthResult>
  linkGoogleAccount: (action: 'link' | 'create_separate', existingUserId: number, googleData: AccountLinkingData['google_data'], state: string, role?: 'student' | 'professor') => Promise<void>
  clearCache: () => void
  refreshUser: () => Promise<void>
  updateUser: (user: User | null) => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = React.useState<User | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  const logout = async () => {
    try {
      await apiClient.logout()
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      // Clear all client-side storage
      setUser(null)
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('user')
        sessionStorage.clear()
        // Also clear any logout markers
        localStorage.removeItem('logout')
      }
      
      // Broadcast logout to other tabs
      try {
        const channel = new BroadcastChannel('auth-logout')
        channel.postMessage({ type: 'logout' })
        channel.close()
      } catch (error) {
        // Fallback to localStorage for older browsers
        localStorage.setItem('logout', Date.now().toString())
      }
    }
  }

  const refreshUser = async () => {
    try {
      const currentUser = await apiClient.getCurrentUser()
      setUser(currentUser)
    } catch (error) {
      console.error('Failed to refresh user state:', error)
    }
  }

  const updateUser = (updatedUser: User | null) => {
    setUser(updatedUser)
  }

  // Initialize auth state on mount
  useEffect(() => {
    const initializeAuth = async () => {
      try {
        // Always validate authentication via API call, even if sessionStorage has data
        // This ensures the cookie is still valid and prevents stale state after logout
        if (process.env.NODE_ENV === 'development') {
          console.log('Checking authentication status...')
        }
        
        // Check authentication by attempting to fetch current user
        // This relies on HttpOnly cookies for authentication
        // Add retry logic to handle race condition where cookie isn't available immediately
        let currentUser = null
        let retries = 3
        
        while (retries > 0 && !currentUser) {
          try {
            currentUser = await apiClient.getCurrentUser()
            if (currentUser) break
          } catch (error) {
            console.log(`Auth check attempt ${4 - retries} failed, retrying...`)
          }
          
          // Wait briefly before retry to allow cookie to be set
          if (retries > 1) {
            await new Promise(resolve => setTimeout(resolve, 500))
          }
          retries--
        }
        
        if (currentUser) {
          if (process.env.NODE_ENV === 'development') {
            console.log('User authenticated successfully:', currentUser.email)
          }
          // Update sessionStorage with validated user data
          if (typeof window !== 'undefined') {
            sessionStorage.setItem('user', JSON.stringify(currentUser))
          }
          setUser(currentUser)
        } else {
          if (process.env.NODE_ENV === 'development') {
            console.log('No authenticated user found')
          }
          // Clear any stale sessionStorage data if authentication fails
          if (typeof window !== 'undefined') {
            sessionStorage.removeItem('user')
          }
          setUser(null)
        }
      } catch (error) {
        if (process.env.NODE_ENV === 'development') {
          console.log('Auth initialization failed:', error)
        }
        // Clear invalid token and stale storage
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('user')
        }
        setUser(null)
        // Don't call apiClient.logout() here as it might cause infinite loops
        // The cookie is already invalid, so just clear local state
      } finally {
        setIsLoading(false)
      }
    }
    
    initializeAuth()
  }, [])

  const login = async (email: string, password: string) => {
    setIsLoading(true)
    try {
      const response = await apiClient.login({ email, password })
      // Store user in sessionStorage for immediate access (like OAuth flow)
      if (typeof window !== 'undefined' && response.user) {
        sessionStorage.setItem('user', JSON.stringify(response.user))
      }
      setUser(response.user)
    } catch (error) {
      console.error('Login failed:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const register = async (data: RegisterData) => {
    setIsLoading(true)
    try {
      const response = await apiClient.register(data)
      setUser(response.user)
    } catch (error) {
      console.error('Registration failed:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const loginWithGoogle = async (): Promise<GoogleOAuthResult> => {
    console.log('Auth Context: Starting Google OAuth flow')
    setIsLoading(true)
    try {
      const googleOAuth = GoogleOAuth.getInstance()
      console.log('Auth Context: Opening auth window')
      const result = await googleOAuth.openAuthWindow()
      console.log('Auth Context: Received result from OAuth:', result)
      
      // Handle null result
      if (!result) {
        console.log('Auth Context: No result received from OAuth')
        throw new Error('OAuth authentication failed - no result received')
      }
      
      if ('action' in result && result.action === 'link_required') {
        console.log('Auth Context: Account linking required')
        // Return the linking data instead of throwing an error
        return result as AccountLinkingData
      } else if ('user' in result) {
        console.log('Auth Context: Direct login success, processing user data')
        // Direct login success - convert OAuthSuccessData to GoogleOAuthSuccessData
        const oauthResult = result as OAuthSuccessData
        const successResult: GoogleOAuthSuccessData = {
          user: {
            id: oauthResult.user.id,
            email: oauthResult.user.email,
            full_name: oauthResult.user.full_name,
            username: oauthResult.user.username,
            bio: oauthResult.user.bio,
            avatar_url: oauthResult.user.avatar_url,
            role: oauthResult.user.role,
            public_agents_count: 0, // Default values for missing properties
            public_tools_count: 0,
            total_downloads: 0,
            reputation_score: oauthResult.user.reputation_score,
            profile_public: oauthResult.user.profile_public,
            allow_contact: oauthResult.user.allow_contact,
            is_active: oauthResult.user.is_active,
            is_verified: oauthResult.user.is_verified,
            created_at: oauthResult.user.created_at,
            updated_at: oauthResult.user.updated_at
          },
          access_token: oauthResult.access_token,
          message: 'Login successful'
        }
        console.log('Auth Context: Setting user state:', successResult.user)
        console.log('Auth Context: User role from OAuth result:', successResult.user.role)
        setUser(successResult.user)
        // Token is now handled server-side via HttpOnly cookies
        console.log('Auth Context: Google OAuth completed successfully')
        return successResult
      } else {
        console.log('Auth Context: Unexpected result structure:', result)
        // Fallback for unexpected result structure
        throw new Error('Unexpected OAuth result structure')
      }
    } catch (error) {
      console.error('Auth Context: Google login failed:', error)
      throw error
    } finally {
      console.log('Auth Context: Setting loading to false')
      setIsLoading(false)
    }
  }

  const linkGoogleAccount = async (action: 'link' | 'create_separate', existingUserId: number, googleData: AccountLinkingData['google_data'], state: string, role?: 'student' | 'professor') => {
    console.log('Auth Context: linkGoogleAccount called with role:', role)
    setIsLoading(true)
    try {
      const googleOAuth = GoogleOAuth.getInstance()
      // Convert googleData to OAuthUserData format
      const oauthUserData: OAuthUserData = {
        google_id: '', // Will be set by backend
        email: googleData.email,
        full_name: googleData.name,
        avatar_url: googleData.picture
      }
      const result = await googleOAuth.linkAccount(action, existingUserId, oauthUserData, state, role)
      console.log('Auth Context: linkAccount result user role:', result.user.role)
      setUser(result.user)
      // Token is now handled server-side via HttpOnly cookies
    } catch (error) {
      console.error('Account linking failed:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const clearCache = () => {
    console.log('Manually clearing all cache...')
    apiClient.clearAllCache()
    setUser(null)
  }

  const isAuthenticated = !!user

  // Multi-tab logout synchronization
  useEffect(() => {
    if (!user) return

    // Handle logout from other tabs
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'logout' && e.newValue) {
        setUser(null)
      }
    }

    const handleBroadcastMessage = (e: MessageEvent) => {
      if (e.data?.type === 'logout') {
        setUser(null)
      }
    }

    window.addEventListener('storage', handleStorageChange)

    // Listen for broadcast channel messages
    let broadcastChannel: BroadcastChannel | null = null
    try {
      broadcastChannel = new BroadcastChannel('auth-logout')
      broadcastChannel.addEventListener('message', handleBroadcastMessage)
    } catch (error) {
      // BroadcastChannel not supported
    }

    return () => {
      window.removeEventListener('storage', handleStorageChange)
      if (broadcastChannel) {
        broadcastChannel.removeEventListener('message', handleBroadcastMessage)
        broadcastChannel.close()
      }
    }
  }, [user])

  return (
    <AuthContext.Provider value={{ 
      user, 
      isLoading, 
      isAuthenticated, 
      login, 
      logout, 
      register, 
      loginWithGoogle, 
      linkGoogleAccount,
      clearCache,
      refreshUser,
      updateUser
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
