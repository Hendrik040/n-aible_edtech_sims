import { User, LoginCredentials, RegisterData, TokenResponse } from './types'

const getApiBaseUrl = () => {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL
  if (!apiUrl) {
    throw new Error('NEXT_PUBLIC_API_URL environment variable is required.')
  }
  return apiUrl
}

const apiRequest = async (endpoint: string, options: RequestInit = {}): Promise<Response> => {
  const headers: Record<string, string> = {}
  
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  
  Object.assign(headers, options.headers as Record<string, string>)

  try {
    const response = await fetch(`${getApiBaseUrl()}${endpoint}`, {
      ...options,
      headers,
      credentials: 'include',
    })

    if (!response.ok) {
      const responseClone = response.clone()
      const errorData = await responseClone.json().catch(() => ({}))
      
      if (response.status === 401) {
        throw new Error(errorData.detail || "Authentication failed. Please log in again.")
      }
      
      const errorMessage = errorData.detail || errorData.message || `HTTP error! status: ${response.status}`
      throw new Error(errorMessage)
    }

    return response
  } catch (error) {
    console.error('API request failed:', error)
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      throw new Error("Unable to connect to the server. Please check if the backend is running and try again.")
    }
    throw error
  }
}

export const apiClient = {
  login: async (credentials: LoginCredentials): Promise<TokenResponse> => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(credentials),
      credentials: 'include',
    })
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || errorData.message || 'Login failed')
    }
    
    return response.json()
  },

  register: async (data: RegisterData): Promise<User> => {
    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
      credentials: 'include',
    })
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || errorData.message || 'Registration failed')
    }
    
    return response.json()
  },

  logout: async (): Promise<void> => {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
      })
    } catch (error) {
      console.warn('Server logout failed:', error)
    }
  },

  getCurrentUser: async (): Promise<User | null> => {
    try {
      const response = await fetch('/api/auth/me', {
        method: 'GET',
        credentials: 'include',
      })
      
      if (!response.ok) {
        return null
      }
      
      return response.json()
    } catch (error) {
      return null
    }
  },
}

