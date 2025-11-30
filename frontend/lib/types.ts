export interface User {
  id: number
  user_id: string | null
  email: string
  full_name: string | null
  username: string | null
  bio: string | null
  avatar_url: string | null
  role: string
  is_active: boolean
  is_verified: boolean
  created_at: string
  updated_at: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterData {
  email: string
  password: string
  full_name?: string
  username?: string
  role: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

