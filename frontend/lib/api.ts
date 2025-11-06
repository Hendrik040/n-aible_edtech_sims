// Real API client for connecting to the backend
import { debugLog } from './debug'

const isProduction = process.env.NODE_ENV === 'production'

const getApiBaseUrl = () => {
  // Get backend URL from environment variable (required)
  // IMPORTANT: This should be your BACKEND URL, not the frontend URL
  // Example: 'https://your-backend.railway.app' or 'http://localhost:8000' (for local development)
  const apiUrl = process.env.NEXT_PUBLIC_API_URL
  if (!apiUrl) {
    throw new Error('NEXT_PUBLIC_API_URL environment variable is required. Please set it to your backend URL in your environment variables.')
  }
  return apiUrl
}

/**
 * Helper function to build API URLs
 * 
 * ALWAYS routes requests through Next.js API proxy (/api/proxy/[...path]) to avoid CORS and cookie issues
 * - The proxy forwards the path AS-IS to the backend, so backend routes must include their /api/ prefix
 * - This ensures consistent behavior between development and production
 * 
 * @param endpoint - API endpoint - must match backend route exactly (e.g., '/users/me', '/api/publishing/scenarios/', '/cohorts/')
 * @returns Full URL for the API request (always through proxy)
 * 
 * Examples:
 * - Frontend endpoint: '/api/publishing/scenarios/drafts/' (list all drafts)
 * - Proxy route: '/api/proxy/api/publishing/scenarios/drafts/' (proxy forwards to backend '/api/publishing/scenarios/drafts/')
 * 
 * - Frontend endpoint: '/professor/cohorts/2/invites'
 * - Proxy route: '/api/proxy/professor/cohorts/2/invites' (proxy forwards to backend '/professor/cohorts/2/invites')
 */
export const buildApiUrl = (endpoint: string): string => {
  // Normalize endpoint: remove leading slash only
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint.substring(1) : endpoint
  
  // ALWAYS use the Next.js API proxy to avoid CORS issues in both development and production
  return `/api/proxy/${cleanEndpoint}`
}

export interface User {
  id: number
  email: string
  full_name: string
  username: string
  bio?: string
  avatar_url?: string
  role: string
  public_agents_count: number
  public_tools_count: number
  total_downloads: number
  reputation_score: number
  profile_public: boolean
  allow_contact: boolean
  is_active: boolean
  is_verified: boolean
  created_at: string
  updated_at: string
}

export interface Agent {
  id: string
  name: string  
  description: string
  role: string
  personality: string
  expertise: string[]
  category?: string
  is_public?: boolean
  average_rating?: number
  backstory: string
  tags: string[]
  clone_count: number
  goal: string
  tools: string[]
  verbose: boolean
  allow_delegation: boolean
  reasoning: string
  is_template: boolean
  allow_remixes: boolean
  version: string
  version_notes: string
}

export interface Scenario {
  id: string
  title: string
  description: string
  difficulty: string
  category: string
  agents: Agent[]
  industry?: string
  source_type?: string
  challenge: string
  learning_objectives: string[]
  created_at: string
  clone_count: number
  is_template: boolean
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterData {
  email: string
  full_name: string
  username: string
  password: string
  bio?: string
  avatar_url?: string
  profile_public?: boolean
  allow_contact?: boolean
}

// SECURITY: Secure authentication using HttpOnly cookies
// Tokens are now handled server-side via secure cookies, not localStorage
// This prevents XSS attacks from accessing authentication tokens
// Client-side token management has been removed for security

/**
 * Helper function to make authenticated API requests
 * 
 * Handles:
 * - Automatic URL building via buildApiUrl (normalizes endpoints, routes through proxy in production)
 * - HttpOnly cookie credentials
 * - Error handling for auth failures (401) and network errors
 * - Silent auth error mode for checking authentication status without throwing
 * 
 * @param endpoint - API endpoint (will be normalized by buildApiUrl)
 * @param options - Fetch options
 * @param silentAuthError - If true, returns 401 response without throwing (for auth checks)
 * @returns Response object
 */
const apiRequest = async (endpoint: string, options: RequestInit = {}, silentAuthError: boolean = false): Promise<Response> => {
  const headers: Record<string, string> = {}
  
  // Only set Content-Type for non-FormData requests
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  
  // Merge with any provided headers
  Object.assign(headers, options.headers as Record<string, string>)

  try {
    const response = await fetch(buildApiUrl(endpoint), {
      ...options,
      headers,
      credentials: 'include', // Include HttpOnly cookies in requests
    })

    if (!response.ok) {
      // Clone the response to avoid consuming the body
      const responseClone = response.clone()
      const errorData = await responseClone.json().catch(() => ({}))
      
      // Handle specific authentication errors
      if (response.status === 401) {
        if (silentAuthError) {
          // Return the response without throwing for silent auth errors
          return response
        }
        throw new Error(errorData.detail || "Authentication failed. Please log in again.")
      }
      
      // Handle other HTTP errors
      const errorMessage = errorData.detail || errorData.message || `HTTP error! status: ${response.status}`
      console.error('API Error Details:', errorData)
      throw new Error(errorMessage)
    }

    return response
  } catch (error) {
    console.error('❌ API request failed:', error)
    console.error('❌ Error type:', typeof error)
    console.error('❌ Error message:', error instanceof Error ? error.message : String(error))
    
    // Handle network errors (server not running, CORS, etc.)
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      console.error('❌ Failed to fetch error detected - this usually means network/CORS issue')
      throw new Error("Unable to connect to the server. Please check if the backend is running and try again.")
    }
    
    // Re-throw other errors (including our custom authentication errors)
    throw error
  }
}

/**
 * API Client for backend communication
 * 
 * Authentication Flow:
 * - Login/Register use dedicated Next.js API routes (/api/auth/*) that handle cookie forwarding
 * - All other endpoints use the proxy pattern (via buildApiUrl) in production
 * - HttpOnly cookies are automatically included via credentials: 'include'
 * 
 * Endpoint Normalization:
 * - All endpoints are normalized by buildApiUrl (strips /api/ prefix, adds proxy route in production)
 * - Backend endpoints may have /api/ prefix or not - buildApiUrl handles both cases
 */
export const apiClient = {
  // Expose the raw apiRequest method for direct API calls
  apiRequest,
  
  // Auth methods
  login: async (credentials: LoginCredentials): Promise<{ user: User; access_token: string }> => {
    // Use dedicated Next.js API route for proper cookie handling
    // This route forwards to backend /users/login and sets HttpOnly cookies
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(credentials),
      credentials: 'include', // Include cookies
    })
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || errorData.message || 'Login failed')
    }
    
    const data = await response.json()
    // Token is now handled server-side via HttpOnly cookies
    return data
  },

  register: async (data: RegisterData): Promise<{ user: User; access_token: string }> => {
    // Log sanitized data (without password)
    const sanitizedData = { ...data, password: '[REDACTED]' }
    debugLog('API register called with data:', sanitizedData)
    
    try {
      // Use Next.js API route instead of direct backend call for proper cookie handling
      console.log('🔍 About to make registration request via Next.js API route')
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
        credentials: 'include', // Include cookies
      })
      
      console.log('✅ Registration response received:', response.status, response.statusText)
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || errorData.message || 'Registration failed')
      }
      
      const responseData = await response.json()
      console.log('✅ Registration data parsed successfully')
      // Token is now handled server-side via HttpOnly cookies
      return responseData
    } catch (error) {
      console.error('❌ Registration request failed:', error)
      throw error
    }
  },

  logout: async (): Promise<void> => {
    // Call server logout endpoint to clear HttpOnly cookies
    try {
      await apiRequest('/users/logout', { method: 'POST' })
    } catch (error) {
      // Continue with logout even if server call fails
      console.warn('Server logout failed, continuing with client logout:', error)
    }
  },

  // Clear all cached data
  clearAllCache: (): void => {
    if (typeof window !== 'undefined') {
      // Clear localStorage
      const itemsToClear = [
        'auth_token',
        'user_data',
        'session_data',
        'oauth_state',
        'google_oauth_data',
        'chatboxScenario', // From simulation builder
        'sidebar_state' // From sidebar component
      ]
      
      itemsToClear.forEach(item => {
        localStorage.removeItem(item)
      })
      
      // Clear sessionStorage
      sessionStorage.clear()
      
      // Note: HttpOnly cookies cannot be cleared via document.cookie
      // They are automatically cleared by the server when logout endpoint is called
      // Attempting to clear them here would fail silently, so we skip this
      
      console.log('All cache cleared successfully')
    }
  },

  getCurrentUser: async (): Promise<User | null> => {
    try {
      const response = await apiRequest('/users/me')
      const user = await response.json()
      return user
    } catch (error) {
      debugLog('No current user found:', error)
      return null
    }
  },

  // Agent methods
  getAgents: async (): Promise<Agent[]> => {
    // For now, return empty array since agents endpoint doesn't exist yet
    return []
  },

  getUserAgents: async (userId: number): Promise<Agent[]> => {
    // For now, return empty array since agents endpoint doesn't exist yet
    return []
  },

  createAgent: async (agentData: any): Promise<Agent> => {
    // For now, throw error since agents endpoint doesn't exist yet
    throw new Error('Agent creation not implemented yet')
  },

  updateAgent: async (agentId: string, agentData: any): Promise<Agent> => {
    // For now, throw error since agents endpoint doesn't exist yet
    throw new Error('Agent update not implemented yet')
  },

  deleteAgent: async (agentId: string): Promise<void> => {
    // For now, throw error since agents endpoint doesn't exist yet
    throw new Error('Agent deletion not implemented yet')
  },

  // Scenario methods
  getScenarios: async (): Promise<Scenario[]> => {
    const response = await apiRequest('/api/publishing/scenarios/?status=active')
    return response.json()
  },

  getUserScenarios: async (userId: number): Promise<Scenario[]> => {
    // For now, return all scenarios since user-specific scenarios endpoint doesn't exist
    // TODO: Add user-specific scenarios endpoint to backend
    const response = await apiRequest('/api/publishing/scenarios/?status=active')
    return response.json()
  },

  createScenario: async (scenarioData: any): Promise<Scenario> => {
    // For now, throw error since scenario creation endpoint doesn't exist yet
    throw new Error('Scenario creation not implemented yet')
  },

  updateScenario: async (scenarioId: string, scenarioData: any): Promise<Scenario> => {
    // For now, throw error since scenario update endpoint doesn't exist yet
    throw new Error('Scenario update not implemented yet')
  },

  deleteScenario: async (scenarioId: string): Promise<void> => {
    // For now, throw error since scenario deletion endpoint doesn't exist yet
    throw new Error('Scenario deletion not implemented yet')
  },

  updateScenarioStatus: async (scenarioId: number, status: string): Promise<any> => {
    const response = await apiRequest(`/api/publishing/scenarios/${scenarioId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    })
    
    if (!response.ok) {
      throw new Error('Failed to update scenario status')
    }
    
    return response.json()
  },

  deleteDraftScenario: async (scenarioId: number): Promise<any> => {
    const response = await apiRequest(`/api/publishing/scenarios/${scenarioId}`, {
      method: 'DELETE',
    })
    
    if (!response.ok) {
      throw new Error('Failed to delete draft scenario')
    }
    
    return response.json()
  },

  getDraftScenario: async (scenarioId: number): Promise<any> => {
    const response = await apiRequest(`/api/scenarios/drafts/${scenarioId}`, {
      method: 'GET',
    })
    
    if (!response.ok) {
      throw new Error('Failed to fetch draft scenario')
    }
    
    return response.json()
  },

  // Simulation methods - using available endpoints
  getSimulations: async (): Promise<any[]> => {
    try {
      // Fetch both published and draft scenarios using the main endpoint
      // This is simpler and avoids trailing slash issues with the separate /drafts/ endpoint
      const [publishedResponse, draftResponse] = await Promise.all([
        apiRequest('/api/publishing/scenarios/?status=active', { method: 'GET' }),
        apiRequest('/api/publishing/scenarios/?status=draft', { method: 'GET' })
      ])
      
      if (!publishedResponse.ok || !draftResponse.ok) {
        throw new Error('Failed to fetch simulations')
      }
      
      const publishedScenarios = await publishedResponse.json()
      const draftScenarios = await draftResponse.json()
      
      
      // Combine scenarios - don't deduplicate by title since users should see all their scenarios
      // The backend already filters by user, so we don't need to deduplicate here
      const allScenarios = [...publishedScenarios, ...draftScenarios]
      
      // Remove duplicates by ID (in case the same scenario appears in both lists)
      const uniqueScenarios = allScenarios.filter((scenario, index, self) => 
        index === self.findIndex(s => s.id === scenario.id)
      )
      
      const mappedScenarios = uniqueScenarios.map((scenario: any) => {
        // Map backend status to frontend display format
        const getDisplayStatus = (backendStatus: string, isDraft: boolean) => {
          if (backendStatus === 'draft') return 'Draft'
          if (backendStatus === 'active') return 'Active'
          if (backendStatus === 'archived') return 'Archived'
          if (backendStatus === 'creating') return 'Creating'
          // Fallback to is_draft for backwards compatibility
          return isDraft ? 'Draft' : 'Active'
        }
        
        const mappedScenario = {
          id: scenario.id,
          title: scenario.title,
          description: scenario.description,
          status: getDisplayStatus(scenario.status, scenario.is_draft),
          date: new Date(scenario.created_at).toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric' 
          }),
          students: scenario.personas?.length || 0, // Use personas count as student count for now
          created_at: scenario.created_at,
          is_draft: scenario.is_draft,
          published_version_id: scenario.published_version_id,
          unique_id: scenario.unique_id,
          // Preserve original status for filtering (important for "creating" status)
          original_status: scenario.status || 'draft'
        }
        
        
        return mappedScenario
      })
      
      return mappedScenarios
    } catch (error) {
      console.error('Failed to fetch simulations:', error)
      return []
    }
  },

  createSimulation: async (simulationData: any): Promise<any> => {
    const response = await apiRequest('/simulations/', {
      method: 'POST',
      body: JSON.stringify(simulationData),
    })
    return response.json()
  },

  getSimulation: async (simulationId: string): Promise<any> => {
    // For now, return simulation status since there's no direct GET endpoint
    const response = await apiRequest(`/simulations/${simulationId}/status/`)
    return response.json()
  },

  // User profile methods
  updateProfile: async (profileData: any): Promise<User> => {
    const response = await apiRequest('/users/me', {
      method: 'PUT',
      body: JSON.stringify(profileData),
    })
    return response.json()
  },

  changePassword: async (passwordData: { current_password: string; new_password: string }): Promise<{ message: string }> => {
    const response = await apiRequest('/users/change-password', {
      method: 'POST',
      body: JSON.stringify(passwordData),
    })
    return response.json()
  },

  // Cohort methods
  getCohorts: async (): Promise<any[]> => {
    const response = await apiRequest('/professor/cohorts/')
    return response.json()
  },

  getCohort: async (cohortId: string): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}`)
    return response.json()
  },

  getCohortStudents: async (cohortId: string): Promise<any[]> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/students`)
    return response.json()
  },

  removeStudentFromCohort: async (cohortId: string, studentId: number): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/students/${studentId}`, {
      method: 'DELETE',
    })
    return response.json()
  },

  removeMultipleStudentsFromCohort: async (cohortId: string, studentIds: number[]): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/students/remove`, {
      method: 'POST',
      body: JSON.stringify({ student_ids: studentIds }),
    })
    return response.json()
  },

  getCohortSimulations: async (cohortId: string): Promise<any[]> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/simulations`)
    return response.json()
  },

  assignSimulationToCohort: async (cohortId: number, simulationData: any): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/simulations`, {
      method: 'POST',
      body: JSON.stringify(simulationData),
    })
    return response.json()
  },

  removeSimulationFromCohort: async (cohortId: number, simulationAssignmentId: number): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/simulations/${simulationAssignmentId}`, {
      method: 'DELETE',
    })
    return response.json()
  },

  createCohort: async (cohortData: any): Promise<any> => {
    const response = await apiRequest('/professor/cohorts/', {
      method: 'POST',
      body: JSON.stringify(cohortData),
    })
    return response.json()
  },

  updateCohort: async (cohortId: string, cohortData: any): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}`, {
      method: 'PUT',
      body: JSON.stringify(cohortData),
    })
    return response.json()
  },

  deleteCohort: async (cohortId: string): Promise<void> => {
    await apiRequest(`/professor/cohorts/${cohortId}`, {
      method: 'DELETE',
    })
  },

  // Invitation methods
  inviteStudentsToCohort: async (cohortId: number, invitations: { email: string; message?: string }[]): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/invite`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(invitations)
    })
    if (!response.ok) {
      throw new Error('Failed to send invitations')
    }
    return response.json()
  },

  getCohortInvitations: async (cohortId: number): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/invitations`)
    if (!response.ok) {
      throw new Error('Failed to fetch cohort invitations')
    }
    return response.json()
  },

  // Notification methods
  getNotifications: async (limit: number = 50, offset: number = 0, unreadOnly: boolean = false): Promise<any> => {
    const user = await apiClient.getCurrentUser()
    if (!user) {
      throw new Error('User not authenticated')
    }
    const endpoint = user.role === 'professor' ? '/professor/notifications' : '/student/notifications'
    const response = await apiRequest(`${endpoint}?limit=${limit}&offset=${offset}&unread_only=${unreadOnly}`)
    if (!response.ok) {
      throw new Error('Failed to fetch notifications')
    }
    return response.json()
  },

  getUnreadNotificationCount: async (): Promise<number> => {
    const user = await apiClient.getCurrentUser()
    if (!user) {
      throw new Error('User not authenticated')
    }
    const endpoint = user.role === 'professor' ? '/professor/notifications/unread-count' : '/student/notifications/unread-count'
    const response = await apiRequest(endpoint)
    if (!response.ok) {
      throw new Error('Failed to fetch unread count')
    }
    const data = await response.json()
    return data.unread_count
  },

  markNotificationRead: async (notificationId: number): Promise<void> => {
    const user = await apiClient.getCurrentUser()
    if (!user) {
      throw new Error('User not authenticated')
    }
    const endpoint = user.role === 'professor' ? `/professor/notifications/${notificationId}/mark-read` : `/student/notifications/${notificationId}/read`
    const response = await apiRequest(endpoint, { method: 'POST' })
    if (!response.ok) {
      throw new Error('Failed to mark notification as read')
    }
  },

  markAllNotificationsRead: async (): Promise<void> => {
    const user = await apiClient.getCurrentUser()
    if (!user) {
      throw new Error('User not authenticated')
    }
    const endpoint = user.role === 'professor' ? '/professor/notifications/mark-all-read' : '/student/notifications/mark-all-read'
    const response = await apiRequest(endpoint, { method: 'POST' })
    if (!response.ok) {
      throw new Error('Failed to mark all notifications as read')
    }
  },

  // Student invitation response methods
  getPendingInvitations: async (): Promise<any> => {
    const response = await apiRequest('/student/invitations')
    if (!response.ok) {
      throw new Error('Failed to fetch pending invitations')
    }
    return response.json()
  },

  respondToInvitation: async (invitationId: number, action: 'accept' | 'decline'): Promise<any> => {
    const response = await apiRequest(`/student/invitations/${invitationId}/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    })
    if (!response.ok) {
      throw new Error('Failed to respond to invitation')
    }
    return response.json()
  },

  // Student cohort methods
  getStudentCohorts: async (): Promise<any> => {
    const response = await apiRequest('/student/cohorts', { method: 'GET' })
    if (!response.ok) throw new Error('Failed to get student cohorts')
    return response.json()
  },

  getStudentCohortSimulations: async (cohortUniqueId: string): Promise<any> => {
    const response = await apiRequest(`/student/cohorts/${cohortUniqueId}/simulations`, { method: 'GET' })
    if (!response.ok) throw new Error('Failed to get student cohort simulations')
    return response.json()
  },

  // Student simulation instance methods
  getStudentSimulationInstances: async (statusFilter?: string, cohortId?: number): Promise<any> => {
    const params = new URLSearchParams()
    if (statusFilter) params.append('status_filter', statusFilter)
    if (cohortId) params.append('cohort_id', cohortId.toString())
    
    const response = await apiRequest(`/student-simulation-instances?${params.toString()}`, {
      method: 'GET',
    })
    if (!response.ok) throw new Error('Failed to get student simulation instances')
    return response.json()
  },

  createStudentSimulationInstance: async (cohortAssignmentId: number): Promise<any> => {
    const response = await apiRequest('/student-simulation-instances', {
      method: 'POST',
      body: JSON.stringify({ cohort_assignment_id: cohortAssignmentId, student_id: 0 }), // student_id will be set by backend
    })
    if (!response.ok) throw new Error('Failed to create student simulation instance')
    return response.json()
  },

  startSimulationInstance: async (instanceId: number): Promise<any> => {
    const response = await apiRequest(`/student-simulation-instances/${instanceId}/start`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error('Failed to start simulation instance')
    return response.json()
  },

  completeSimulationInstance: async (instanceId: number): Promise<any> => {
    const response = await apiRequest(`/student-simulation-instances/${instanceId}/complete`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error('Failed to complete simulation instance')
    return response.json()
  },

  updateSimulationInstance: async (instanceId: number, updateData: any): Promise<any> => {
    const response = await apiRequest(`/student-simulation-instances/${instanceId}`, {
      method: 'PUT',
      body: JSON.stringify(updateData),
    })
    if (!response.ok) throw new Error('Failed to update simulation instance')
    return response.json()
  },

  getSimulationAssignmentInstances: async (assignmentId: number): Promise<any> => {
    const response = await apiRequest(`/student-simulation-instances/assignment/${assignmentId}/instances`, {
      method: 'GET',
    })
    if (!response.ok) throw new Error('Failed to get simulation assignment instances')
    return response.json()
  },

  startSimulationFromInstance: async (instanceId: number): Promise<any> => {
    const response = await apiRequest(`/student-simulation-instances/${instanceId}/start-simulation`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error('Failed to start simulation from instance')
    return response.json()
  },

  // Utility methods
  isAuthenticated: (): boolean => {
    // Authentication is now determined by server-side HttpOnly cookies
    // This method is deprecated - use the auth context's isAuthenticated instead
    console.warn('apiClient.isAuthenticated() is deprecated. Use the auth context instead.')
    return false
  },

  // Unified messaging methods
  sendMessage: async (messageData: any): Promise<any> => {
    const response = await apiRequest('/messages/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(messageData)
    })
    if (!response.ok) {
      throw new Error('Failed to send message')
    }
    return response.json()
  },

  getMessages: async (limit: number = 50, offset: number = 0): Promise<any> => {
    const params = new URLSearchParams({
      limit: limit.toString(),
      offset: offset.toString()
    })
    const response = await apiRequest(`/messages/?${params}`)
    if (!response.ok) {
      throw new Error('Failed to get messages')
    }
    return response.json()
  },

  getMessageThread: async (messageId: number): Promise<any> => {
    const response = await apiRequest(`/messages/${messageId}`)
    if (!response.ok) {
      throw new Error('Failed to get message thread')
    }
    return response.json()
  },

  replyToMessage: async (messageId: number, message: string): Promise<any> => {
    const response = await apiRequest(`/messages/${messageId}/reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    })
    if (!response.ok) {
      throw new Error('Failed to reply to message')
    }
    return response.json()
  },

  markMessageRead: async (messageId: number): Promise<void> => {
    const response = await apiRequest(`/messages/${messageId}/mark-read`, {
      method: 'POST'
    })
    if (!response.ok) {
      throw new Error('Failed to mark message as read')
    }
  },

  getUsers: async (): Promise<any> => {
    const response = await apiRequest('/messages/users/')
    if (!response.ok) {
      throw new Error('Failed to get users')
    }
    return response.json()
  },

  getMessagingCohorts: async (): Promise<any> => {
    const response = await apiRequest('/messages/cohorts/')
    if (!response.ok) {
      throw new Error('Failed to get cohorts')
    }
    return response.json()
  },

  // Invite link methods
  getInviteLinks: async (cohortId: number): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/invites`, {
      method: 'GET'
    })
    if (!response.ok) {
      throw new Error('Failed to fetch invite links')
    }
    return response.json()
  },

  deleteInviteLink: async (cohortId: number, inviteId: number): Promise<void> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/invites/${inviteId}`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error('Failed to delete invite link')
    }
  },

  clearExpiredInviteLinks: async (cohortId: number): Promise<{ deleted_count: number }> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/invites/clear-expired`, {
      method: 'DELETE'
    })
    if (!response.ok) {
      throw new Error('Failed to clear expired invite links')
    }
    return response.json()
  },

  generateInviteLink: async (cohortId: number, inviteData: { type: 'SINGLE_USE' | 'MULTI_USE'; max_uses?: number; expires_in_days?: number }): Promise<any> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/invites`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(inviteData)
    })
    if (!response.ok) {
      throw new Error('Failed to generate invite link')
    }
    return response.json()
  },

  validateInviteLink: async (token: string): Promise<any> => {
    const response = await apiRequest(`/invites/${token}`, {
      method: 'GET'
    })
    if (!response.ok) {
      throw new Error('Failed to validate invite link')
    }
    return response.json()
  },

  acceptInviteLink: async (token: string): Promise<any> => {
    const response = await apiRequest(`/invites/${token}/accept`, {
      method: 'POST'
    })
    if (!response.ok) {
      throw new Error('Failed to accept invite link')
    }
    return response.json()
  },
} 