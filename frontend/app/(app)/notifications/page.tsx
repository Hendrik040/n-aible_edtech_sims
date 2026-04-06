"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
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
  Send,
  Plus,
  Reply,
  Eye,
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
  cohortId?: number
  cohortTitle?: string
  instructorName?: string
  instructorEmail?: string
  expiresAt?: string
  invitationId?: number
  // Student assignment/grade/achievement fields
  simulationTitle?: string
  dueDate?: string
  xpReward?: string
  score?: string
  grade?: string
  xpEarned?: string
  rank?: string
  achievementTitle?: string
  achievementDescription?: string
}

export default function UnifiedNotifications() {
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
  const [markingRead, setMarkingRead] = useState<number | string | null>(null)

  // Messaging state
  const [showMessagingModal, setShowMessagingModal] = useState(false)
  const [showMessageViewer, setShowMessageViewer] = useState(false)

  // Fetch notifications (and invitations for students)
  const fetchNotifications = async () => {
    if (!user || !user.role) {
      setError('User not authenticated')
      return
    }
    try {
      setLoading(true)
      setError(null)

      // Fetch regular notifications for all roles
      const response = await apiClient.getNotifications(user.role, 100, 0, false)
      setNotifications(response.notifications || [])

      // For students, also fetch pending invitations
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

  // Mark notification as read
  const markAsRead = async (notificationId: number | string) => {
    if (!user || !user.role) return
    // Skip for synthetic invitation notifications
    if (typeof notificationId === 'string' && notificationId.startsWith('invitation-')) return
    try {
      setMarkingRead(notificationId)
      await apiClient.markNotificationRead(user.role, notificationId as number)

      // Update local state
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

  // Mark all notifications as read
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

  // Student invitation handlers
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

  // Get notification icon based on type (merged from both pages)
  const getNotificationIcon = (type: string) => {
    switch (type) {
      case 'invitation':
        return <UserPlus className="h-5 w-5 text-blue-600" />
      case 'invitation_response':
        return <UserPlus className="h-5 w-5 text-blue-600" />
      case 'assignment':
        return <BookOpen className="h-5 w-5 text-green-600" />
      case 'assignment_completion':
        return <BookOpen className="h-5 w-5 text-purple-600" />
      case 'grade':
        return <Trophy className="h-5 w-5 text-yellow-600" />
      case 'grade_submission':
        return <Trophy className="h-5 w-5 text-green-600" />
      case 'cohort_update':
        return <Users className="h-5 w-5 text-orange-600" />
      case 'reminder':
        return <Clock className="h-5 w-5 text-orange-600" />
      case 'achievement':
        return <Star className="h-5 w-5 text-purple-600" />
      case 'professor_message':
        return <MessageCircle className="h-5 w-5 text-indigo-600" />
      case 'student_reply':
        return <Reply className="h-5 w-5 text-teal-600" />
      case 'student_message':
        return <MessageCircle className="h-5 w-5 text-indigo-600" />
      case 'message_sent':
        return <MessageSquare className="h-5 w-5 text-green-600" />
      default:
        return <Bell className="h-5 w-5 text-gray-600" />
    }
  }

  // Get notification color based on type (from professor page)
  const getNotificationColor = (type: string) => {
    switch (type) {
      case 'invitation':
        return 'bg-blue-50 border-blue-200'
      case 'invitation_response':
        return 'bg-blue-50 border-blue-200'
      case 'assignment':
        return 'bg-green-50 border-green-200'
      case 'assignment_completion':
        return 'bg-purple-50 border-purple-200'
      case 'grade':
        return 'bg-yellow-50 border-yellow-200'
      case 'grade_submission':
        return 'bg-green-50 border-green-200'
      case 'cohort_update':
        return 'bg-orange-50 border-orange-200'
      case 'reminder':
        return 'bg-orange-50 border-orange-200'
      case 'achievement':
        return 'bg-purple-50 border-purple-200'
      case 'professor_message':
        return 'bg-indigo-50 border-indigo-200'
      case 'student_reply':
        return 'bg-teal-50 border-teal-200'
      case 'student_message':
        return 'bg-indigo-50 border-indigo-200'
      case 'message_sent':
        return 'bg-green-50 border-green-200'
      default:
        return 'bg-gray-50 border-gray-200'
    }
  }

  // Get type badge (from student page)
  const getTypeBadge = (type: string) => {
    switch (type) {
      case "invitation":
        return <Badge className="bg-blue-100 text-blue-800 text-xs">Invitation</Badge>
      case "invitation_response":
        return <Badge className="bg-blue-100 text-blue-800 text-xs">Invitation Response</Badge>
      case "assignment":
        return <Badge className="bg-green-100 text-green-800 text-xs">Assignment</Badge>
      case "assignment_completion":
        return <Badge className="bg-purple-100 text-purple-800 text-xs">Assignment</Badge>
      case "grade":
        return <Badge className="bg-yellow-100 text-yellow-800 text-xs">Grade</Badge>
      case "grade_submission":
        return <Badge className="bg-green-100 text-green-800 text-xs">Grade</Badge>
      case "reminder":
        return <Badge className="bg-orange-100 text-orange-800 text-xs">Reminder</Badge>
      case "achievement":
        return <Badge className="bg-purple-100 text-purple-800 text-xs">Achievement</Badge>
      case "cohort_update":
        return <Badge className="bg-orange-100 text-orange-800 text-xs">Cohort</Badge>
      case "professor_message":
        return <Badge className="bg-indigo-100 text-indigo-800 text-xs">Message</Badge>
      case "student_reply":
        return <Badge className="bg-teal-100 text-teal-800 text-xs">Reply</Badge>
      case "student_message":
        return <Badge className="bg-indigo-100 text-indigo-800 text-xs">Message</Badge>
      case "message_sent":
        return <Badge className="bg-green-100 text-green-800 text-xs">Sent</Badge>
      default:
        return <Badge className="bg-gray-100 text-gray-800 text-xs">{type}</Badge>
    }
  }

  // Get status badge (from student page)
  const getStatusBadge = (status?: string) => {
    if (!status) return null
    switch (status) {
      case "pending":
        return <Badge className="bg-yellow-100 text-yellow-800 text-xs">Pending</Badge>
      case "accepted":
        return <Badge className="bg-green-100 text-green-800 text-xs">Accepted</Badge>
      case "declined":
        return <Badge className="bg-red-100 text-red-800 text-xs">Declined</Badge>
      case "active":
        return <Badge className="bg-blue-100 text-blue-800 text-xs">Active</Badge>
      case "completed":
        return <Badge className="bg-gray-100 text-gray-800 text-xs">Completed</Badge>
      default:
        return <Badge className="bg-gray-100 text-gray-800 text-xs">{status}</Badge>
    }
  }

  // Format time ago
  const formatTimeAgo = (dateString?: string) => {
    if (!dateString) return ''
    const date = new Date(dateString)
    const now = new Date()
    const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)

    if (diffInSeconds < 60) return 'Just now'
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`
    if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)}d ago`

    return date.toLocaleDateString()
  }

  // Combine notifications with pending invitations for students
  const allNotifications: Notification[] = isStudent
    ? [
        ...notifications.map(notification => ({
          ...notification,
          isRead: notification.is_read,
          actions: notification.actions || []
        })),
        ...pendingInvitations.map(invitation => ({
          id: `invitation-${invitation.id}` as string,
          type: "invitation",
          title: `Invitation to ${invitation.cohort?.title || 'Cohort'}`,
          message: `${invitation.invited_by?.full_name || 'Professor'} has invited you to join their cohort.`,
          time: new Date(invitation.created_at).toLocaleDateString(),
          isRead: false,
          isNew: true,
          is_read: false,
          status: "pending",
          cohortId: invitation.cohort_id,
          cohortTitle: invitation.cohort?.title,
          instructorName: invitation.invited_by?.full_name,
          instructorEmail: invitation.invited_by?.email,
          expiresAt: invitation.expires_at ? new Date(invitation.expires_at).toLocaleDateString() : 'No expiry',
          actions: ["Accept", "Decline"],
          invitationId: invitation.id
        }))
      ]
    : notifications.map(n => ({ ...n, isRead: n.is_read }))

  // Filter notifications
  const filteredNotifications = allNotifications.filter(notification => {
    const matchesSearch = notification.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         notification.message.toLowerCase().includes(searchTerm.toLowerCase())

    const matchesType = typeFilter === "All Types" ||
                       notification.type === typeFilter ||
                       notification.type === typeFilter.toLowerCase()

    const matchesStatus = statusFilter === "All Status" ||
                         (notification.status && notification.status === statusFilter.toLowerCase()) ||
                         (statusFilter === "Unread" && !notification.isRead) ||
                         (statusFilter === "Read" && notification.isRead)

    return matchesSearch && matchesType && matchesStatus
  })

  // Get unique notification types for the filter dropdown
  const notificationTypes = isProfessor
    ? ["All Types", ...Array.from(new Set(notifications.map(n => n.type)))]
    : [
        "All Types",
        ...Array.from(new Set(allNotifications.map(n => n.type)))
      ]

  const unreadCount = allNotifications.filter(n => !n.isRead).length
  const newCount = allNotifications.filter(n => n.isNew).length

  // Professor-specific stat counts
  const invitationCount = isProfessor
    ? notifications.filter(n => n.type === 'invitation_response').length
    : allNotifications.filter(n => n.type === 'invitation').length

  const fourthStatCount = isProfessor
    ? notifications.filter(n => n.type === 'assignment_completion').length
    : allNotifications.filter(n => n.type === 'achievement').length

  // Load notifications on component mount
  useEffect(() => {
    if (user && !authLoading) {
      fetchNotifications()
    }
  }, [user, authLoading])

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Fixed Header Section */}
      <div className="flex-shrink-0 p-8 pb-4 animate-page-enter">
        {/* Header */}
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
            {isStudent && newCount > 0 && (
              <Badge className="bg-gradient-to-r from-red-100 to-red-50 text-red-800 text-xs font-semibold shadow-sm border border-red-200/60">{newCount} New</Badge>
            )}
            {isStudent && unreadCount > 0 && (
              <Badge className="bg-gradient-to-r from-blue-100 to-blue-50 text-blue-800 text-xs font-semibold shadow-sm border border-blue-200/60">{unreadCount} Unread</Badge>
            )}
            {unreadCount > 0 && (
              <Button
                onClick={markAllAsRead}
                variant="outline"
                className="flex items-center space-x-2 border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all"
              >
                <CheckCheck className="h-4 w-4" />
                <span>Mark all as read</span>
              </Button>
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
                  <p className="text-2xl font-bold text-gray-900">{invitationCount}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
            <CardContent className="p-6">
              <div className="flex items-center space-x-3">
                <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center shadow-sm">
                  {isProfessor
                    ? <BookOpen className="h-6 w-6 text-purple-600" />
                    : <Trophy className="h-6 w-6 text-purple-600" />
                  }
                </div>
                <div>
                  <p className="text-sm text-gray-600 font-medium">
                    {isProfessor ? "Assignments" : "Achievements"}
                  </p>
                  <p className="text-2xl font-bold text-gray-900">{fourthStatCount}</p>
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
                    {type === "All Types" ? type : type.replace(/_/g, ' ')}
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
                {isStudent && (
                  <>
                    <option value="Pending">Pending</option>
                    <option value="Active">Active</option>
                    <option value="Completed">Completed</option>
                  </>
                )}
              </select>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Scrollable Notifications Container */}
      <div className="flex-1 overflow-y-auto px-8 pb-8">
        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-red-800">{error}</p>
            <Button
              onClick={fetchNotifications}
              className="mt-2 bg-red-600 hover:bg-red-700 text-white"
              size="sm"
            >
              Retry
            </Button>
          </div>
        )}

        {/* Notifications List */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
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
                    notification.isNew
                      ? "border-blue-300/60 bg-gradient-to-r from-blue-50/80 to-blue-100/40 backdrop-blur-sm border-l-4"
                      : isUnread
                      ? `${getNotificationColor(notification.type)} border-l-4 border-opacity-60`
                      : 'bg-white/95 backdrop-blur-sm'
                  }`}
                  onClick={() => {
                    // Open message viewer for message notifications
                    if (notification.type === 'professor_message' || notification.type === 'student_reply' || notification.type === 'student_message' || notification.type === 'message_sent') {
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
                              <h3 className={`text-lg font-medium ${
                                isUnread ? 'text-gray-900' : 'text-gray-700'
                              }`}>
                                {notification.title}
                              </h3>
                              {getTypeBadge(notification.type)}
                              {notification.status && getStatusBadge(notification.status)}
                              {notification.isNew && (
                                <Badge className="bg-blue-100 text-blue-800 text-xs">New</Badge>
                              )}
                              {isUnread && !notification.isNew && (
                                <Badge variant="destructive" className="text-xs">
                                  New
                                </Badge>
                              )}
                              {isUnread && (
                                <div className="w-2 h-2 bg-blue-600 rounded-full"></div>
                              )}
                            </div>

                            <p className={`text-sm mb-3 ${
                              isUnread ? 'text-gray-600' : 'text-gray-500'
                            }`}>
                              {notification.message}
                            </p>

                            {/* Student invitation detail card */}
                            {notification.type === "invitation" && (
                              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-3">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <p className="text-sm font-medium text-blue-900">{notification.cohortTitle}</p>
                                    <p className="text-xs text-blue-700">Instructor: {notification.instructorName}</p>
                                    <p className="text-xs text-blue-700">Expires: {notification.expiresAt}</p>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Student assignment detail card */}
                            {notification.type === "assignment" && (
                              <div className="bg-green-50 border border-green-200 rounded-lg p-3 mb-3">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <p className="text-sm font-medium text-green-900">{notification.simulationTitle}</p>
                                    <p className="text-xs text-green-700">Course: {notification.cohortTitle}</p>
                                    <p className="text-xs text-green-700">Due: {notification.dueDate}</p>
                                  </div>
                                  <div className="text-right">
                                    <p className="text-sm font-semibold text-green-800">{notification.xpReward}</p>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Student grade detail card */}
                            {notification.type === "grade" && (
                              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-3">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <p className="text-sm font-medium text-yellow-900">{notification.simulationTitle}</p>
                                    <p className="text-xs text-yellow-700">Course: {notification.cohortTitle}</p>
                                    <p className="text-xs text-yellow-700">{notification.rank}</p>
                                  </div>
                                  <div className="text-right">
                                    <p className="text-lg font-bold text-yellow-800">{notification.score} ({notification.grade})</p>
                                    <p className="text-sm text-yellow-700">{notification.xpEarned}</p>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Student achievement detail card */}
                            {notification.type === "achievement" && (
                              <div className="bg-purple-50 border border-purple-200 rounded-lg p-3 mb-3">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <p className="text-sm font-medium text-purple-900">{notification.achievementTitle}</p>
                                    <p className="text-xs text-purple-700">{notification.achievementDescription}</p>
                                  </div>
                                  <div className="text-right">
                                    <p className="text-sm font-semibold text-purple-800">{notification.xpEarned}</p>
                                  </div>
                                </div>
                              </div>
                            )}

                            <div className="flex items-center space-x-4 text-xs text-gray-500">
                              <span className="flex items-center">
                                <Clock className="h-3 w-3 mr-1" />
                                {notification.created_at
                                  ? formatTimeAgo(notification.created_at)
                                  : notification.time || ''
                                }
                              </span>
                              <Badge variant="outline" className="text-xs">
                                {notification.type.replace(/_/g, ' ')}
                              </Badge>
                            </div>

                            {/* Action Buttons for student invitations */}
                            {(notification.actions && notification.actions.length > 0) && (
                              <div className="flex items-center space-x-3 mt-4">
                                {notification.actions.map((action: string, actionIndex: number) => {
                                  const isPrimary = action === "Accept" || action === "Start Simulation" || action === "Continue"
                                  return (
                                    <Button
                                      key={actionIndex}
                                      size="sm"
                                      variant={isPrimary ? "default" : "outline"}
                                      className={
                                        isPrimary
                                          ? "btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                                          : "border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all"
                                      }
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        if (action === "Accept") {
                                          handleAcceptInvitation(notification.invitationId || notification.id as number)
                                        } else if (action === "Decline") {
                                          handleDeclineInvitation(notification.invitationId || notification.id as number)
                                        } else {
                                          markAsRead(notification.id)
                                        }
                                      }}
                                    >
                                      {action}
                                    </Button>
                                  )
                                })}
                              </div>
                            )}
                          </div>

                          {isUnread && !(notification.actions && notification.actions.length > 0) && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={(e) => {
                                e.stopPropagation()
                                markAsRead(notification.id)
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

                          {isUnread && (notification.actions && notification.actions.length > 0) && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={(e) => {
                                e.stopPropagation()
                                markAsRead(notification.id)
                              }}
                              className="ml-4 flex-shrink-0 text-gray-500 hover:text-gray-700 transition-all"
                            >
                              Mark as Read
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

      {/* Messaging Modal - Outside scrollable container */}
      <MessagingModal
        isOpen={showMessagingModal}
        onClose={() => setShowMessagingModal(false)}
        currentUser={user}
      />

      {/* Message Viewer Modal - Outside scrollable container */}
      <MessageViewerModal
        isOpen={showMessageViewer}
        onClose={() => setShowMessageViewer(false)}
        currentUser={user}
      />
    </div>
  )
}
