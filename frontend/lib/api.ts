// Real API client for connecting to the backend
import { debugLog } from './debug'
import { User, LoginCredentials, RegisterData, TokenResponse } from './types'

const isProduction = process.env.NODE_ENV === 'production'

const getApiBaseUrl = () => {
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
 */
export const buildApiUrl = (endpoint: string): string => {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint.substring(1) : endpoint
  return `/api/proxy/${cleanEndpoint}`
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

/**
 * Helper function to make authenticated API requests
 * 
 * Handles:
 * - Automatic URL building via buildApiUrl (normalizes endpoints, routes through proxy)
 * - HttpOnly cookie credentials
 * - Error handling for auth failures (401) and network errors
 * - Silent auth error mode for checking authentication status without throwing
 */
const apiRequest = async (endpoint: string, options: RequestInit = {}, silentAuthError: boolean = false): Promise<Response> => {
  const headers: Record<string, string> = {}
  
  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  
  Object.assign(headers, options.headers as Record<string, string>)

  try {
    const response = await fetch(buildApiUrl(endpoint), {
      ...options,
      headers,
      credentials: 'include',
    })

    if (!response.ok) {
      const responseClone = response.clone()
      const errorData = await responseClone.json().catch(() => ({}))
      
      if (response.status === 401) {
        if (silentAuthError) {
          return response
        }
        const authErrorMessage = errorData.error || errorData.detail || "Authentication failed. Please log in again."
        throw new Error(authErrorMessage)
      }
      
      // Prioritize error field, then detail, then message, then provide helpful defaults
      let errorMessage = errorData.error || errorData.detail || errorData.message
      
      // If no error message found, provide helpful defaults based on status code
      if (!errorMessage) {
        if (response.status === 404) {
          errorMessage = `Endpoint not found. The requested resource may not be implemented yet.`
        } else if (response.status === 403) {
          errorMessage = `Access forbidden. You don't have permission to access this resource.`
        } else if (response.status >= 500) {
          errorMessage = `Server error. Please try again later.`
        } else {
          errorMessage = `Request failed with status ${response.status}`
        }
      }
      
      // Only log error details if they exist and are meaningful
      if (Object.keys(errorData).length > 0) {
        console.error('API Error Details:', errorData)
      } else {
        console.error(`API request failed: ${response.status} ${response.statusText} for ${endpoint}`)
      }
      
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

/**
 * API Client for backend communication
 * 
 * Authentication Flow:
 * - Login/Register use dedicated Next.js API routes (/api/auth/*) that handle cookie forwarding
 * - All other endpoints use the proxy pattern (via buildApiUrl)
 * - HttpOnly cookies are automatically included via credentials: 'include'
 */
export const apiClient = {
  apiRequest,
  
  // Auth methods - updated for new backend API
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
      const errorMessage = errorData.error || errorData.detail || errorData.message || 'Login failed'
      throw new Error(errorMessage)
    }
    
    return response.json()
  },

  register: async (data: RegisterData): Promise<User> => {
    debugLog('API register called with data:', { ...data, password: '[REDACTED]' })
    
    try {
    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
      credentials: 'include',
    })
    
    if (!response.ok) {
      let errorData: any = {}
      try {
        const contentType = response.headers.get('content-type')
        if (contentType?.includes('application/json')) {
          errorData = await response.json()
        } else {
          // If not JSON, try to get text response
          const text = await response.text()
          errorData = { error: text.trim() || `HTTP ${response.status}: ${response.statusText}` }
        }
      } catch (parseError) {
        // If parsing fails, create error from status
        if (response.status === 502) {
          errorData = { error: 'Backend server is unavailable. Please try again in a moment.' }
        } else {
          errorData = { error: `HTTP ${response.status}: ${response.statusText || 'Unknown error'}` }
        }
      }
      
      const errorMessage = errorData.error || errorData.detail || errorData.message || 
        (response.status === 502 ? 'Backend server is unavailable. Please try again in a moment.' : 'Registration failed')
      throw new Error(errorMessage)
    }
    
    return response.json()
    } catch (error) {
      console.error('Registration request failed:', error)
      // Handle network errors
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error('Unable to connect to server. Please check your connection and try again.')
      }
      throw error
    }
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

  clearAllCache: (): void => {
    if (typeof window !== 'undefined') {
      const itemsToClear = [
        'auth_token',
        'user_data',
        'session_data',
        'oauth_state',
        'google_oauth_data',
        'chatboxScenario',
        'sidebar_state'
      ]
      
      itemsToClear.forEach(item => {
        localStorage.removeItem(item)
      })
      
      sessionStorage.clear()
      console.log('All cache cleared successfully')
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
      debugLog('No current user found:', error)
      return null
    }
  },

  // Agent methods
  getAgents: async (): Promise<Agent[]> => {
    return []
  },

  getUserAgents: async (userId: number): Promise<Agent[]> => {
    return []
  },

  createAgent: async (agentData: any): Promise<Agent> => {
    throw new Error('Agent creation not implemented yet')
  },

  updateAgent: async (agentId: string, agentData: any): Promise<Agent> => {
    throw new Error('Agent update not implemented yet')
  },

  deleteAgent: async (agentId: string): Promise<void> => {
    throw new Error('Agent deletion not implemented yet')
  },

  // Simulation methods (formerly scenarios)
  getScenarios: async (): Promise<Scenario[]> => {
    const response = await apiRequest('/api/publishing/simulations/?status=active')
    return response.json()
  },

  getUserScenarios: async (userId: number): Promise<Scenario[]> => {
    const response = await apiRequest('/api/publishing/simulations/?status=active')
    return response.json()
  },

  createScenario: async (scenarioData: any): Promise<Scenario> => {
    throw new Error('Scenario creation not implemented yet')
  },

  updateScenario: async (scenarioId: string, scenarioData: any): Promise<Scenario> => {
    throw new Error('Scenario update not implemented yet')
  },

  deleteScenario: async (scenarioId: string): Promise<void> => {
    throw new Error('Scenario deletion not implemented yet')
  },

  updateScenarioStatus: async (scenarioId: number, status: string): Promise<any> => {
    const response = await apiRequest(`/api/publishing/simulations/${scenarioId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    })
    
    if (!response.ok) {
      throw new Error('Failed to update simulation status')
    }
    
    return response.json()
  },

  deleteDraftScenario: async (scenarioId: number): Promise<void> => {
    const response = await apiRequest(`/api/publishing/simulations/${scenarioId}`, {
      method: 'DELETE',
    })
    
    if (!response.ok) {
      throw new Error('Failed to delete draft simulation')
    }
    
    // 204 No Content has no body, so don't try to parse JSON
    if (response.status === 204) {
      return
    }
    
    return response.json()
  },

  getDraftScenario: async (scenarioId: number): Promise<any> => {
    const response = await apiRequest(`/api/publishing/simulations/drafts/${scenarioId}`, {
      method: 'GET',
    })
    
    if (!response.ok) {
      throw new Error('Failed to fetch draft scenario')
    }
    
    return response.json()
  },

  // Simulation methods
  // OPTIMIZED: Single API call instead of 3 separate calls (reduces DB queries by 67%)
  getSimulations: async (): Promise<any[]> => {
    try {
      // Single request to get ALL simulations regardless of status
      const response = await apiRequest('/api/publishing/simulations/?include_drafts=true', { method: 'GET' })
      
      if (!response.ok) {
        throw new Error('Failed to fetch simulations')
      }
      
      const allScenarios = await response.json()
      
      // Map to frontend format
      const mappedScenarios = allScenarios.map((scenario: any) => {
        const getDisplayStatus = (backendStatus: string, isDraft: boolean) => {
          if (backendStatus === 'draft') return 'Draft'
          if (backendStatus === 'active') return 'Active'
          if (backendStatus === 'archived') return 'Archived'
          if (backendStatus === 'creating') return 'Creating'
          return isDraft ? 'Draft' : 'Active'
        }
        
        return {
          id: scenario.id,
          title: scenario.title,
          description: scenario.description,
          status: getDisplayStatus(scenario.status, scenario.is_draft),
          date: new Date(scenario.created_at).toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric' 
          }),
          students: scenario.personas?.length || 0,
          created_at: scenario.created_at,
          is_draft: scenario.is_draft,
          published_version_id: scenario.published_version_id,
          unique_id: scenario.unique_id,
          original_status: scenario.status || 'draft'
        }
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

  /**
   * OPTIMIZATION: Get completion summary for all simulations in a cohort in ONE request.
   * Replaces N+1 calls to /simulations/{id}/instances with a single batched query.
   */
  getCohortCompletionSummary: async (cohortId: number): Promise<{
    cohort_id: number
    simulations: Array<{
      simulation_assignment_id: number
      simulation_id: number
      simulation_title: string
      completed_count: number
      graded_count: number
      total_students: number
    }>
  }> => {
    const response = await apiRequest(`/professor/cohorts/${cohortId}/completion-summary`)
    if (!response.ok) {
      throw new Error('Failed to fetch completion summary')
    }
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
  getNotifications: async (userRole: string, limit: number = 50, offset: number = 0, unreadOnly: boolean = false): Promise<any> => {
    // Use a raw fetch so we can gracefully swallow 404s without apiRequest throwing
    if (userRole !== 'professor' && userRole !== 'student' && userRole !== 'admin') {
      throw new Error('Invalid user role. Expected "professor", "student", or "admin"')
    }
    const endpoint = userRole === 'professor' ? '/professor/notifications' : '/student/notifications'
    const url = buildApiUrl(`${endpoint}?limit=${limit}&offset=${offset}&unread_only=${unreadOnly}`)
    const response = await fetch(url, { credentials: 'include' })
    if (response.status === 404) {
      return []
    }
    if (!response.ok) {
      throw new Error('Failed to fetch notifications')
    }
    return response.json()
  },

  getUnreadNotificationCount: async (userRole: string): Promise<number> => {
    if (userRole !== 'professor' && userRole !== 'student' && userRole !== 'admin') {
      throw new Error('Invalid user role. Expected "professor", "student", or "admin"')
    }
    const endpoint = userRole === 'professor' ? '/professor/notifications/unread-count' : '/student/notifications/unread-count'
    const url = buildApiUrl(endpoint)
    const response = await fetch(url, { credentials: 'include' })
    if (response.status === 404) {
      return 0
    }
    if (!response.ok) {
      throw new Error('Failed to fetch unread count')
    }
    const data = await response.json()
    // Some backends may return number directly; handle both shapes
    return typeof data === 'number' ? data : data.unread_count
  },

  markNotificationRead: async (userRole: string, notificationId: number): Promise<void> => {
    if (userRole !== 'professor' && userRole !== 'student' && userRole !== 'admin') {
      throw new Error('Invalid user role. Expected "professor", "student", or "admin"')
    }
    const endpoint = userRole === 'professor' ? `/professor/notifications/${notificationId}/mark-read` : `/student/notifications/${notificationId}/read`
    const response = await apiRequest(endpoint, { method: 'POST' })
    if (!response.ok) {
      throw new Error('Failed to mark notification as read')
    }
  },

  markAllNotificationsRead: async (userRole: string): Promise<void> => {
    if (userRole !== 'professor' && userRole !== 'student' && userRole !== 'admin') {
      throw new Error('Invalid user role. Expected "professor", "student", or "admin"')
    }
    const endpoint = userRole === 'professor' ? '/professor/notifications/mark-all-read' : '/student/notifications/mark-all-read'
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
      body: JSON.stringify({ cohort_assignment_id: cohortAssignmentId, student_id: 0 }),
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
    debugLog('API acceptInviteLink called with token:', token)
    try {
      const response = await apiRequest(`/invites/${token}/accept`, {
        method: 'POST'
      })
      if (!response.ok) {
        let errorMessage = 'Failed to accept invite link'
        try {
          const errorData = await response.clone().json()
          errorMessage = errorData.error || errorData.detail || errorData.message || errorMessage
        } catch {
          // If JSON parsing fails, use default message
        }
        debugLog('API acceptInviteLink error:', errorMessage, response.status)
        throw new Error(errorMessage)
      }
      const data = await response.json()
      debugLog('API acceptInviteLink success:', data)
      return data
    } catch (error) {
      debugLog('API acceptInviteLink exception:', error)
      throw error
    }
  },

  // Professor Grading Methods
  getSubmissionDetails: async (instanceId: number): Promise<any> => {
    const response = await apiRequest(`/professor/grading/instances/${instanceId}/submission`, {
      method: 'GET',
    })
    if (!response.ok) throw new Error('Failed to get submission details')
    return response.json()
  },

  submitProfessorReview: async (instanceId: number, review: { grade: number; feedback: string }): Promise<any> => {
    const response = await apiRequest(`/professor/grading/instances/${instanceId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(review)
    })
    if (!response.ok) throw new Error('Failed to submit professor review')
    return response.json()
  },

  getGradeHistory: async (instanceId: number): Promise<any[]> => {
    const response = await apiRequest(`/professor/grading/instances/${instanceId}/history`, {
      method: 'GET',
    })
    if (!response.ok) throw new Error('Failed to get grade history')
    return response.json()
  },

  revertToAIGrade: async (instanceId: number): Promise<any> => {
    const response = await apiRequest(`/professor/grading/instances/${instanceId}/review/revert`, {
      method: 'DELETE',
    })
    if (!response.ok) throw new Error('Failed to revert to AI grade')
    return response.json()
  },
}
