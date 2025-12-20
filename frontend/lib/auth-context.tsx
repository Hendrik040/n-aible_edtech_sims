"use client"

import React, { createContext, useContext, ReactNode, useEffect, useState } from 'react'
import { apiClient, User, RegisterData } from './api'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  register: (data: RegisterData) => Promise<void>
  refreshUser: () => Promise<void>
  updateUser: (user: User | null) => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const logout = async () => {
    try {
      await apiClient.logout()
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      setUser(null)
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('user')
        sessionStorage.clear()
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

  useEffect(() => {
    const initializeAuth = async () => {
      try {
        const currentUser = await apiClient.getCurrentUser()
        if (currentUser) {
          if (typeof window !== 'undefined') {
            sessionStorage.setItem('user', JSON.stringify(currentUser))
          }
          setUser(currentUser)
        } else {
          if (typeof window !== 'undefined') {
            sessionStorage.removeItem('user')
          }
          setUser(null)
        }
      } catch (error) {
        if (typeof window !== 'undefined') {
          sessionStorage.removeItem('user')
        }
        setUser(null)
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
      const user = await apiClient.register(data)
      if (typeof window !== 'undefined') {
        sessionStorage.setItem('user', JSON.stringify(user))
      }
      setUser(user)
    } catch (error) {
      console.error('Registration failed:', error)
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const isAuthenticated = !!user

  return (
    <AuthContext.Provider value={{ 
      user, 
      isLoading, 
      isAuthenticated, 
      login, 
      logout, 
      register,
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




