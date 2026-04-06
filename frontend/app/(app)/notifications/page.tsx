"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
  Bell,
  CheckCircle,
  XCircle,
  Mail,
  Calendar,
  Users,
  BookOpen,
  Trophy,
  Star,
  ArrowRight,
  Filter,
  Search,
  Clock,
  UserPlus,
  MessageCircle,
  CheckCheck,
  MessageSquare,
  Reply,
  User
} from "lucide-react"
import MessagingModal from "@/components/MessagingModal"
import MessageViewerModal from "@/components/MessageViewerModal"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

interface Notification {
  id: number | string
  type: string
  title: string
  message: string
  data?: any
  is_read?: boolean
  isRead?: boolean
  isNew?: boolean
  created_at?: string
  time?: string
  status?: string
  actions?: string[]
  // Student invitation fields
  cohortTitle?: string
  instructorName?: string
  instructorEmail?: string
  expiresAt?: string
  invitationId?: number
  cohortId?: number
  // Student assignment/grade fields
  simulationTitle?: string
  dueDate?: string
  xpReward?: string
  score?: string
  grade?: string
  rank?: string
  xpEarned?: string
  achievementTitle?: string
  achievementDescription?: string
}

export default function NotificationsPage() {
  const router = useRouter()
  const { user, isLoading: authLoading } = useAuth()

  const isProfessor = user?.role === 'professor' || user?.role === 'admin'
  const isStudent = user?.role === 'student'

  const [notifications, setNotifications] = useState<Notification[]>([])
  const [pendingInvitations, setPendingInvitations] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState("")
  const [typeFilter, setTypeFilter] = useState("All Types")
  const [statusFilter, setStatusFilter] = useState("All Status")
  const [markingRead, setMarkingRead] = useState<number | null>(null)

  const [showMessagingModal, setShowMessagingModal] = useState(false)
  const [showMessageViewer, setShowMessageViewer] = useState(false)

  const fetchNotifications = async () => {
    if (!user || !user.role) {
      setError('User not authenticated')
      return
    }
    try {
      setLoading(true)
      setError(null)

      const response = await apiClient.getNotifications(user.role, 100, 0, false)
      setNotifications(response.notifications || [])

      // Students also fetch pending invitations
      if (isStudent) {
        const invitationsData = await apiClient.getPendingInvitations()
        setPendingInvitations(invitationsData.invitations || [])
      }
    } catch (err) {
      setError('Failed to load notifications')
      console.error('Error fetching notifications:', err)
    } finally {
      setLoading(false)
    }
  }

  const markAsRead = async (notificationId: number) => {
    if (!user || !user.role) return
    try {
      setMarkingRead(notificationId)
      await apiClient.markNotificationRead(user.role, notificationId)
      setNotifications(prev =>
        prev.map(notif =>
          notif.id === notificationId
            ? { ...notif, is_read: true, isRead: true }
            : notif
        )
      )
    } catch (error) {
      console.error('Failed to mark notification as read:', error)
    } finally {
      setMarkingRead(null)
    }
  }

  const markAllAsRead = async () => {
    if (!user || !user.role) return
    try {
      await apiClient.markAllNotificationsRead(user.role)
      setNotifications(prev =>
        prev.map(notif => ({ ...notif, is_read: true, isRead: true }))
      )
    } catch (error) {
      console.error('Failed to mark all notifications as read:', error)
    }
  }

  // Student-specific invitation handlers
  const handleAcceptInvitation = async (invitationId: number) => {
    try {
      await apiClient.respondToInvitation(invitationId, 'accept')
      fetchNotifications()
    } catch (error) {
      console.error('Error accepting invitation:', error)
      setError('Failed to accept invitation')
    }
  }

  const handleDeclineInvitation = async (invitationId: number) => {
    try {
      await apiClient.respondToInvitation(invitationId, 'decline')
      fetchNotifications()
    } catch (error) {
      console.error('Error declining invitation:', error)
      setError('Failed to decline invitation')
    }
  }

  const getNotificationIcon = (type: string) => {
    switch (type) {
      case 'invitation': case 'invitation_response':
        return <UserPlus className="h-5 w-5 text-blue-600" />
      case 'assignment': case 'assignment_completion':
        return <BookOpen className="h-5 w-5 text-purple-600" />
      case 'grade': case 'grade_submission':
        return <Trophy className="h-5 w-5 text-green-600" />
      case 'cohort_update':
        return <Users className="h-5 w-5 text-orange-600" />
      case 'reminder':
        return <Clock className="h-5 w-5 text-orange-600" />
      case 'achievement':
        return <Star className="h-5 w-5 text-purple-600" />
      case 'professor_message': case 'student_message':
        return <MessageCircle className="h-5 w-5 text-indigo-600" />
      case 'student_reply':
        return <Reply className="h-5 w-5 text-teal-600" />
      case 'message_sent':
        return <MessageSquare className="h-5 w-5 text-green-600" />
      default:
        return <Bell className="h-5 w-5 text-gray-600" />
    }
  }

  const getNotificationColor = (type: string) => {
    switch (type) {
      case 'invitation': case 'invitation_response':
        return 'bg-blue-50 border-blue-200'
      case 'assignment': case 'assignment_completion':
        return 'bg-purple-50 border-purple-200'
      case 'grade': case 'grade_submission':
        return 'bg-green-50 border-green-200'
      case 'cohort_update':
        return 'bg-orange-50 border-orange-200'
      case 'professor_message': case 'student_message':
        return 'bg-indigo-50 border-indigo-200'
      case 'student_reply':
        return 'bg-teal-50 border-teal-200'
      case 'message_sent':
        return 'bg-green-50 border-green-200'
      default:
        return 'bg-gray-50 border-gray-200'
    }
  }

  const formatTimeAgo = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)

    if (diffInSeconds < 60) return 'Just now'
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`
    if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)}d ago`

    return date.toLocaleDateString()
  }

  // Combine notifications with student invitations
  const allNotifications: Notification[] = [
    ...notifications.map(notification => ({
      ...notification,
      isRead: notification.is_read,
    })),
    ...(isStudent ? pendingInvitations.map((invitation: any) => ({
      id: `invitation-${invitation.id}` as any,
      type: "invitation",
      title: `Invitation to ${invitation.cohort?.title || 'Cohort'}`,
      message: `${invitation.invited_by?.full_name || 'Professor'} has invited you to join their cohort.`,
      time: new Date(invitation.created_at).toLocaleDateString(),
      isRead: false,
      isNew: true,
      status: "pending",
      cohortId: invitation.cohort_id,
      cohortTitle: invitation.cohort?.title,
      instructorName: invitation.invited_by?.full_name,
      instructorEmail: invitation.invited_by?.email,
      expiresAt: invitation.expires_at ? new Date(invitation.expires_at).toLocaleDateString() : 'No expiry',
      actions: ["Accept", "Decline"],
      invitationId: invitation.id
    })) : [])
  ]

  const filteredNotifications = allNotifications.filter(notification => {
    const matchesSearch = notification.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         notification.message.toLowerCase().includes(searchTerm.toLowerCase())

    const matchesType = typeFilter === "All Types" || notification.type === typeFilter ||
                       notification.type === typeFilter.toLowerCase()
    const matchesStatus = statusFilter === "All Status" ||
                         (statusFilter === "Unread" && !notification.isRead && !notification.is_read) ||
                         (statusFilter === "Read" && (notification.isRead || notification.is_read))

    return matchesSearch && matchesType && matchesStatus
  })

  const notificationTypes = ["All Types", ...Array.from(new Set(allNotifications.map(n => n.type)))]

  useEffect(() => {
    if (user && !authLoading) {
      fetchNotifications()
    }
  }, [user, authLoading])

  const unreadCount = allNotifications.filter(n => !n.isRead && !n.is_read).length

  return (
    <div className="h-screen bg-atmospheric relative pattern-dots overflow-hidden flex flex-col -ml-20">
      <div className="ml-20 h-full flex flex-col relative z-20 overflow-hidden">
        {/* Fixed Header Section */}
        <div className="flex-shrink-0 p-8 pb-4 animate-page-enter">
          <div className="flex items-center justify-between mb-10 stagger-1 animate-fade-scale">
            <div className="flex items-center space-x-4">
              <div>
                <h1 className="text-4xl font-bold text-black mb-2 tracking-tight">Notifications</h1>
                <p className="text-gray-600 text-lg">
                  {isProfessor
                    ? "Stay updated with student activities and cohort updates"
                    : "Stay updated with invitations, assignments, grades, and achievements."
                  }
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              {/* Professor: Mark all as read button */}
              {isProfessor && unreadCount > 0 && (
                <Button
                  onClick={markAllAsRead}
                  variant="outline"
                  className="flex items-center space-x-2 border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all"
                >
                  <CheckCheck className="h-4 w-4" />
                  <span>Mark all as read</span>
                </Button>
              )}
              {/* Student: New/Unread badges */}
              {isStudent && (
                <>
                  {allNotifications.filter(n => n.isNew).length > 0 && (
                    <Badge className="bg-gradient-to-r from-red-100 to-red-50 text-red-800 text-xs font-semibold shadow-sm border border-red-200/60">
                      {allNotifications.filter(n => n.isNew).length} New
                    </Badge>
                  )}
                  {unreadCount > 0 && (
                    <Badge className="bg-gradient-to-r from-blue-100 to-blue-50 text-blue-800 text-xs font-semibold shadow-sm border border-blue-200/60">
                      {unreadCount} Unread
                    </Badge>
                  )}
                </>
              )}
              <Button
                onClick={() => setShowMessagingModal(true)}
                className="btn-gradient-green text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
              >
                <MessageSquare className="h-4 w-4 mr-2" />
                Compose Message
              </Button>
            </div>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10 stagger-2 animate-fade-scale">
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center shadow-sm">
                    <Bell className="h-6 w-6 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 font-medium">Total</p>
                    <p className="text-2xl font-bold text-gray-900">{allNotifications.length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-red-100 to-red-50 rounded-xl flex items-center justify-center shadow-sm">
                    <Bell className="h-6 w-6 text-red-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 font-medium">Unread</p>
                    <p className="text-2xl font-bold text-gray-900">{unreadCount}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center shadow-sm">
                    <UserPlus className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 font-medium">Invitations</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {allNotifications.filter(n => n.type === 'invitation' || n.type === 'invitation_response').length}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center shadow-sm">
                    {isProfessor ? <BookOpen className="h-6 w-6 text-purple-600" /> : <Trophy className="h-6 w-6 text-purple-600" />}
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 font-medium">{isProfessor ? 'Assignments' : 'Achievements'}</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {isProfessor
                        ? allNotifications.filter(n => n.type === 'assignment_completion').length
                        : allNotifications.filter(n => n.type === 'achievement').length
                      }
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Search and Filter Bar */}
          <Card className="mb-8 card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md stagger-3 animate-fade-scale">
            <CardContent className="p-5">
              <div className="flex items-center space-x-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 h-5 w-5" />
                  <input
                    type="text"
                    placeholder="Search notifications..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-12 pr-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md"
                  />
                </div>

                <select
                  value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value)}
                  className="px-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md cursor-pointer"
                >
                  {notificationTypes.map((type) => (
                    <option key={type} value={type}>
                      {type.replace('_', ' ')}
                    </option>
                  ))}
                </select>

                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md cursor-pointer"
                >
                  <option value="All Status">All Status</option>
                  <option value="Unread">Unread</option>
                  <option value="Read">Read</option>
                </select>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Scrollable Notifications Container */}
        <div className="flex-1 overflow-y-auto px-8 pb-8">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-red-600">{error}</p>
              <Button onClick={fetchNotifications} className="mt-2 bg-red-600 hover:bg-red-700 text-white" size="sm">
                Retry
              </Button>
            </div>
          ) : filteredNotifications.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <Bell className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No notifications found</h3>
                <p className="text-gray-600">
                  {allNotifications.length === 0
                    ? isProfessor
                      ? "You'll receive notifications when students respond to invitations or complete assignments."
                      : "You don't have any notifications yet."
                    : "No notifications match your current filters."
                  }
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-5 stagger-4 animate-fade-scale">
              {filteredNotifications.map((notification, index) => {
                const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                const isUnread = !notification.isRead && !notification.is_read
                return (
                  <Card
                    key={notification.id}
                    className={`card-elevated rounded-xl shadow-md transition-all duration-300 hover:shadow-lg ${staggerClass} animate-fade-scale ${
                      isUnread
                        ? `${getNotificationColor(notification.type)} border-l-4 border-opacity-60`
                        : 'bg-white/95 backdrop-blur-sm'
                    }`}
                    onClick={() => {
                      if (['professor_message', 'student_reply', 'student_message', 'message_sent'].includes(notification.type)) {
                        setShowMessageViewer(true)
                      }
                    }}
                  >
                    <CardContent className="p-6">
                      <div className="flex items-start space-x-4">
                        <div className="flex-shrink-0 mt-1">
                          {getNotificationIcon(notification.type)}
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center space-x-2 mb-2">
                                <h3 className={`text-lg font-medium ${isUnread ? 'text-gray-900' : 'text-gray-700'}`}>
                                  {notification.title}
                                </h3>
                                {isUnread && (
                                  <Badge variant="destructive" className="text-xs">New</Badge>
                                )}
                              </div>

                              <p className={`text-sm mb-3 ${isUnread ? 'text-gray-600' : 'text-gray-500'}`}>
                                {notification.message}
                              </p>

                              {/* Student invitation details */}
                              {notification.type === "invitation" && (
                                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
                                  <p className="text-sm font-medium text-blue-900">{notification.cohortTitle}</p>
                                  <p className="text-xs text-blue-700">Instructor: {notification.instructorName}</p>
                                  <p className="text-xs text-blue-700">Expires: {notification.expiresAt}</p>
                                </div>
                              )}

                              <div className="flex items-center space-x-4 text-xs text-gray-500">
                                <span className="flex items-center">
                                  <Clock className="h-3 w-3 mr-1" />
                                  {notification.created_at ? formatTimeAgo(notification.created_at) : notification.time || ''}
                                </span>
                                <Badge variant="outline" className="text-xs">
                                  {notification.type.replace('_', ' ')}
                                </Badge>
                              </div>

                              {/* Student invitation action buttons */}
                              {notification.type === "invitation" && notification.actions && (
                                <div className="flex items-center space-x-3 mt-4">
                                  {notification.actions.map((action: string, idx: number) => {
                                    const isPrimary = action === "Accept"
                                    return (
                                      <Button
                                        key={idx}
                                        size="sm"
                                        variant={isPrimary ? "default" : "outline"}
                                        className={isPrimary
                                          ? "btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                                          : "border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all"
                                        }
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          if (action === "Accept") handleAcceptInvitation(notification.invitationId || notification.id as number)
                                          else if (action === "Decline") handleDeclineInvitation(notification.invitationId || notification.id as number)
                                        }}
                                      >
                                        {action}
                                      </Button>
                                    )
                                  })}
                                </div>
                              )}
                            </div>

                            {isUnread && notification.type !== "invitation" && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  markAsRead(notification.id as number)
                                }}
                                disabled={markingRead === notification.id}
                                className="ml-4 flex-shrink-0"
                              >
                                {markingRead === notification.id ? (
                                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600"></div>
                                ) : (
                                  <CheckCircle className="h-4 w-4" />
                                )}
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}
        </div>

        <MessagingModal
          isOpen={showMessagingModal}
          onClose={() => setShowMessagingModal(false)}
          currentUser={user}
        />

        <MessageViewerModal
          isOpen={showMessageViewer}
          onClose={() => setShowMessageViewer(false)}
          currentUser={user}
        />
      </div>
    </div>
  )
}
