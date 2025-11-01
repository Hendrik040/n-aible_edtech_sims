"use client"

import { useState, useEffect } from "react"
import { useParams, useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { 
  CheckCircle,
  XCircle,
  Clock,
  Users,
  Calendar,
  BookOpen,
  Mail,
  User,
  ArrowLeft
} from "lucide-react"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

interface InvitationData {
  invitation: {
    id: number
    cohort_id: number
    professor_id: number
    student_email: string
    status: string
    message: string
    expires_at: string
    created_at: string
  }
  cohort: {
    id: number
    title: string
    description: string
    course_code: string
    semester: string
    year: number
  }
  professor: {
    id: number
    full_name: string
    email: string
  }
}

export default function InvitationPage() {
  const params = useParams()
  const router = useRouter()
  const { user, isLoading: authLoading } = useAuth()
  const token = params.token as string

  const [invitationData, setInvitationData] = useState<InvitationData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [responding, setResponding] = useState(false)
  const [responseMessage, setResponseMessage] = useState<string | null>(null)

  // Fetch invitation data
  useEffect(() => {
    const fetchInvitation = async () => {
      if (!token) return

      try {
        setLoading(true)
        const response = await apiClient.getInvitationByToken(token)
        setInvitationData(response)
      } catch (error: any) {
        console.error("Error fetching invitation:", error)
        setError(error.response?.data?.detail || "Invitation not found or expired")
      } finally {
        setLoading(false)
      }
    }

    fetchInvitation()
  }, [token])

  // Handle invitation response
  const handleResponse = async (action: 'accept' | 'decline') => {
    if (!token) return

    setResponding(true)
    setError(null)

    try {
      const response = await apiClient.respondToInvitationByToken(token, action)

      setResponseMessage(response.message)
      
      // If accepted and user is logged in, redirect to cohorts
      if (action === 'accept' && user) {
        setTimeout(() => {
          router.push('/student/my-cohorts')
        }, 2000)
      }
    } catch (error: any) {
      console.error("Error responding to invitation:", error)
      setError(error.response?.data?.detail || "Failed to respond to invitation")
    } finally {
      setResponding(false)
    }
  }

  // Show loading
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading invitation...</p>
        </div>
      </div>
    )
  }

  // Show error if invitation not found
  if (error && !invitationData) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Card className="w-full max-w-md mx-4">
          <CardHeader className="text-center">
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <XCircle className="h-8 w-8 text-red-600" />
            </div>
            <CardTitle className="text-xl text-gray-900">Invitation Not Found</CardTitle>
          </CardHeader>
          <CardContent className="text-center">
            <p className="text-gray-600 mb-6">{error}</p>
            <Button 
              onClick={() => router.push('/')}
              className="bg-blue-700 text-white hover:bg-blue-800"
            >
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Home
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Show success message after responding
  if (responseMessage) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Card className="w-full max-w-md mx-4">
          <CardHeader className="text-center">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircle className="h-8 w-8 text-green-600" />
            </div>
            <CardTitle className="text-xl text-gray-900">Response Recorded</CardTitle>
          </CardHeader>
          <CardContent className="text-center">
            <p className="text-gray-600 mb-6">{responseMessage}</p>
            {user ? (
              <Button 
                onClick={() => router.push('/student/my-cohorts')}
                className="bg-blue-700 text-white hover:bg-blue-800"
              >
                View My Cohorts
              </Button>
            ) : (
              <div className="space-y-3">
                <Button 
                  onClick={() => router.push('/login')}
                  className="w-full bg-blue-700 text-white hover:bg-blue-800"
                >
                  Login to Continue
                </Button>
                <Button 
                  variant="outline"
                  onClick={() => router.push('/signup')}
                  className="w-full"
                >
                  Create Account
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!invitationData) return null

  const { invitation, cohort, professor } = invitationData
  const expiresAt = new Date(invitation.expires_at)
  const isExpired = expiresAt < new Date()
  
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-2xl">
        <CardHeader className="text-center border-b border-gray-200">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Users className="h-8 w-8 text-blue-600" />
          </div>
          <CardTitle className="text-2xl text-gray-900 mb-2">
            You're Invited to Join a Cohort!
          </CardTitle>
          <p className="text-gray-600">
            {professor.full_name} has invited you to join their educational cohort
          </p>
        </CardHeader>

        <CardContent className="p-6">
          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
              <div className="flex">
                <XCircle className="h-5 w-5 text-red-400 mt-0.5" />
                <div className="ml-3">
                  <p className="text-sm font-medium text-red-800">{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Cohort Information */}
          <div className="bg-white border border-gray-200 rounded-lg p-6 mb-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Cohort Details</h3>
            
            <div className="space-y-4">
              <div className="flex items-start">
                <BookOpen className="h-5 w-5 text-gray-400 mt-0.5 mr-3" />
                <div>
                  <p className="font-medium text-gray-900">{cohort.title}</p>
                  {cohort.description && (
                    <p className="text-sm text-gray-600 mt-1">{cohort.description}</p>
                  )}
                </div>
              </div>

              {cohort.course_code && (
                <div className="flex items-center">
                  <Calendar className="h-5 w-5 text-gray-400 mr-3" />
                  <div>
                    <p className="text-sm text-gray-600">Course Code</p>
                    <p className="font-medium text-gray-900">{cohort.course_code}</p>
                  </div>
                </div>
              )}

              {cohort.semester && cohort.year && (
                <div className="flex items-center">
                  <Clock className="h-5 w-5 text-gray-400 mr-3" />
                  <div>
                    <p className="text-sm text-gray-600">Term</p>
                    <p className="font-medium text-gray-900">{cohort.semester} {cohort.year}</p>
                  </div>
                </div>
              )}

              <div className="flex items-start">
                <User className="h-5 w-5 text-gray-400 mt-0.5 mr-3" />
                <div>
                  <p className="text-sm text-gray-600">Instructor</p>
                  <p className="font-medium text-gray-900">{professor.full_name}</p>
                  <p className="text-sm text-gray-600">{professor.email}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Personal Message */}
          {invitation.message && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
              <div className="flex">
                <Mail className="h-5 w-5 text-blue-400 mt-0.5 mr-3" />
                <div>
                  <p className="text-sm font-medium text-blue-900">Personal Message</p>
                  <p className="text-sm text-blue-800 mt-1">{invitation.message}</p>
                </div>
              </div>
            </div>
          )}

          {/* Invitation Status */}
          <div className="flex items-center justify-between py-4 border-t border-gray-200">
            <div className="flex items-center">
              <Clock className="h-4 w-4 text-gray-400 mr-2" />
              <span className="text-sm text-gray-600">
                {isExpired ? 'Expired' : 'Expires'} on {expiresAt.toLocaleDateString()}
              </span>
            </div>
            <Badge variant={isExpired ? "destructive" : "default"}>
              {isExpired ? 'Expired' : invitation.status}
            </Badge>
          </div>

          {/* Action Buttons */}
          {!isExpired && invitation.status === 'pending' && (
            <div className="flex items-center justify-center space-x-4 pt-6">
              <Button
                variant="outline"
                onClick={() => handleResponse('decline')}
                disabled={responding}
                className="px-8"
              >
                {responding ? 'Processing...' : 'Decline'}
              </Button>
              <Button
                onClick={() => handleResponse('accept')}
                disabled={responding}
                className="btn-gradient-green text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold px-8"
              >
                {responding ? 'Processing...' : 'Accept Invitation'}
              </Button>
            </div>
          )}

          {/* Already Responded */}
          {invitation.status !== 'pending' && (
            <div className="text-center pt-6">
              <p className="text-gray-600 mb-4">
                You have already {invitation.status} this invitation.
              </p>
              {user ? (
                <Button 
                  onClick={() => router.push('/student/my-cohorts')}
                  className="bg-blue-700 text-white hover:bg-blue-800"
                >
                  View My Cohorts
                </Button>
              ) : (
                <Button 
                  onClick={() => router.push('/login')}
                  className="bg-blue-700 text-white hover:bg-blue-800"
                >
                  Login to Continue
                </Button>
              )}
            </div>
          )}

          {/* Login Prompt for Non-Authenticated Users */}
          {!user && !authLoading && invitation.status === 'pending' && !isExpired && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mt-6">
              <p className="text-sm text-yellow-800 text-center">
                You can respond to this invitation without logging in, but you'll need to create an account or log in to access the cohort materials.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
