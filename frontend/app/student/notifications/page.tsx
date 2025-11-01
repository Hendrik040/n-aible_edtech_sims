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
  MessageSquare,
  Reply,
  User
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import MessagingModal from "@/components/MessagingModal"
import MessageViewerModal from "@/components/MessageViewerModal"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

export default function StudentNotifications() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  const [searchTerm, setSearchTerm] = useState("")
  const [typeFilter, setTypeFilter] = useState("All Types")
  const [statusFilter, setStatusFilter] = useState("All Status")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Real data from API
  const [notifications, setNotifications] = useState<any[]>([])
  const [pendingInvitations, setPendingInvitations] = useState<any[]>([])
  
  // Messaging state
  const [showMessagingModal, setShowMessagingModal] = useState(false)
  const [showMessageViewer, setShowMessageViewer] = useState(false)

  // Fetch notifications and invitations
  const fetchNotifications = async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Fetch regular notifications
      const notificationsData = await apiClient.getNotifications(100, 0, false)
      setNotifications(notificationsData.notifications || [])
      
      // Fetch pending invitations
      const invitationsData = await apiClient.getPendingInvitations()
      setPendingInvitations(invitationsData.invitations || [])
      
    } catch (error) {
      console.error('Error fetching notifications:', error)
      setError('Failed to load notifications')
    } finally {
      setLoading(false)
    }
  }


  // Handle redirect when user is not authenticated or not a student
  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/")
    } else if (!authLoading && user && user.role !== 'student' && user.role !== 'admin') {
      // Redirect professors to their dashboard
      router.push("/professor/dashboard")
    } else if (!authLoading && user && user.role === 'student') {
      // Fetch notifications when user is authenticated as student
      fetchNotifications()
    }
  }, [user, authLoading, router])


  // Show loading while auth is being checked
  if (authLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black mx-auto mb-4"></div>
          <p className="text-black">Loading...</p>
        </div>
      </div>
    )
  }

  // If no user, show redirecting message
  if (!user) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-black">Redirecting...</p>
        </div>
      </div>
    )
  }

  const handleLogout = () => {
    logout()
    router.push("/")
  }

  const handleAcceptInvitation = async (invitationId: number) => {
    try {
      await apiClient.respondToInvitation(invitationId, 'accept')
      // Refresh notifications after accepting
      fetchNotifications()
    } catch (error) {
      console.error('Error accepting invitation:', error)
      setError('Failed to accept invitation')
    }
  }

  const handleDeclineInvitation = async (invitationId: number) => {
    try {
      await apiClient.respondToInvitation(invitationId, 'decline')
      // Refresh notifications after declining
      fetchNotifications()
    } catch (error) {
      console.error('Error declining invitation:', error)
      setError('Failed to decline invitation')
    }
  }

  const handleMarkAsRead = async (notificationId: number) => {
    try {
      await apiClient.markNotificationRead(notificationId)
      // Update local state
      setNotifications(prev => prev.map(notif => 
        notif.id === notificationId 
          ? { ...notif, is_read: true, isRead: true }
          : notif
      ))
    } catch (error) {
      console.error('Error marking notification as read:', error)
    }
  }

  // Combine notifications and invitations for display
  const allNotifications = [
    ...notifications.map(notification => ({
      ...notification,
      isRead: notification.is_read, // Map is_read to isRead for consistency
      actions: notification.actions || [] // Ensure actions array exists
    })),
    ...pendingInvitations.map(invitation => ({
      id: `invitation-${invitation.id}`,
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
    }))
  ]

  // Filter notifications based on search and filters
  const filteredNotifications = allNotifications.filter(notification => {
    const matchesSearch = notification.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         notification.message.toLowerCase().includes(searchTerm.toLowerCase())
    
    const matchesType = typeFilter === "All Types" || 
                       notification.type === typeFilter.toLowerCase()
    
    const matchesStatus = statusFilter === "All Status" || 
                         notification.status === statusFilter.toLowerCase() ||
                         (statusFilter === "Unread" && !notification.isRead) ||
                         (statusFilter === "Read" && notification.isRead)
    
    return matchesSearch && matchesType && matchesStatus
  })

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "invitation":
        return <UserPlus className="h-5 w-5 text-blue-600" />
      case "assignment":
        return <BookOpen className="h-5 w-5 text-green-600" />
      case "grade":
        return <Trophy className="h-5 w-5 text-yellow-600" />
      case "reminder":
        return <Clock className="h-5 w-5 text-orange-600" />
      case "achievement":
        return <Star className="h-5 w-5 text-purple-600" />
      case "professor_message":
        return <MessageCircle className="h-5 w-5 text-indigo-600" />
      case "student_reply":
        return <Reply className="h-5 w-5 text-teal-600" />
      case "student_message":
        return <MessageCircle className="h-5 w-5 text-indigo-600" />
      case "message_sent":
        return <MessageSquare className="h-5 w-5 text-green-600" />
      default:
        return <Bell className="h-5 w-5 text-gray-600" />
    }
  }

  const getTypeBadge = (type: string) => {
    switch (type) {
      case "invitation":
        return <Badge className="bg-blue-100 text-blue-800 text-xs">Invitation</Badge>
      case "assignment":
        return <Badge className="bg-green-100 text-green-800 text-xs">Assignment</Badge>
      case "grade":
        return <Badge className="bg-yellow-100 text-yellow-800 text-xs">Grade</Badge>
      case "reminder":
        return <Badge className="bg-orange-100 text-orange-800 text-xs">Reminder</Badge>
      case "achievement":
        return <Badge className="bg-purple-100 text-purple-800 text-xs">Achievement</Badge>
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

  const getStatusBadge = (status: string) => {
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

  const unreadCount = allNotifications.filter(n => !n.isRead).length
  const newCount = allNotifications.filter(n => n.isNew).length

  return (
    <div className="h-screen bg-atmospheric relative pattern-dots overflow-hidden">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/student/notifications" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 h-full overflow-y-auto relative z-20">
        {/* Main Content Area */}
        <div className="p-8 animate-page-enter min-h-full">
          {/* Header */}
          <div className="mb-10 stagger-1 animate-fade-scale">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-4">
                <div>
                  <h1 className="text-4xl font-bold text-black mb-2 tracking-tight">Notifications</h1>
                  <p className="text-gray-600 text-lg">Stay updated with invitations, assignments, grades, and achievements.</p>
                </div>
              </div>
              
              <div className="flex items-center space-x-4">
                {newCount > 0 && (
                  <Badge className="bg-gradient-to-r from-red-100 to-red-50 text-red-800 text-xs font-semibold shadow-sm border border-red-200/60">{newCount} New</Badge>
                )}
                {unreadCount > 0 && (
                  <Badge className="bg-gradient-to-r from-blue-100 to-blue-50 text-blue-800 text-xs font-semibold shadow-sm border border-blue-200/60">{unreadCount} Unread</Badge>
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
          </div>

          {/* Search and Filters */}
          <div className="flex items-center space-x-4 mb-8 stagger-2 animate-fade-scale">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search notifications..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-12 pr-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md"
              />
            </div>
            
            <div className="relative">
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="px-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md cursor-pointer"
              >
                <option value="All Types">All Types</option>
                <option value="Invitation">Invitations</option>
                <option value="Assignment">Assignments</option>
                <option value="Grade">Grades</option>
                <option value="Reminder">Reminders</option>
                <option value="Achievement">Achievements</option>
              </select>
            </div>
            
            <div className="relative">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md cursor-pointer"
              >
                <option value="All Status">All Status</option>
                <option value="Unread">Unread</option>
                <option value="Read">Read</option>
                <option value="Pending">Pending</option>
                <option value="Active">Active</option>
                <option value="Completed">Completed</option>
              </select>
            </div>
          </div>

          {/* Summary Statistics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10 stagger-3 animate-fade-scale">
              <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
                <CardContent className="p-6">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                      <Bell className="h-6 w-6 text-blue-600" />
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1 font-medium">Total</p>
                      <p className="text-2xl font-bold text-gray-900">{allNotifications.length}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
                <CardContent className="p-6">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-gradient-to-br from-red-100 to-red-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                      <Bell className="h-6 w-6 text-red-600" />
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1 font-medium">Unread</p>
                      <p className="text-2xl font-bold text-gray-900">{unreadCount}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
                <CardContent className="p-6">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                      <UserPlus className="h-6 w-6 text-green-600" />
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1 font-medium">Invitations</p>
                      <p className="text-2xl font-bold text-gray-900">{allNotifications.filter(n => n.type === 'invitation').length}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
                <CardContent className="p-6">
                  <div className="flex items-center">
                    <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                      <Trophy className="h-6 w-6 text-purple-600" />
                    </div>
                    <div>
                      <p className="text-sm text-gray-600 mb-1 font-medium">Achievements</p>
                      <p className="text-2xl font-bold text-gray-900">{allNotifications.filter(n => n.type === 'achievement').length}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>


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

          {/* Loading State */}
          {loading && (
            <div className="mb-6 p-8 text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-600 mx-auto mb-4"></div>
              <p className="text-gray-600">Loading notifications...</p>
            </div>
          )}

          {/* Notifications List */}
          {!loading && (
            <div className="mb-6 stagger-4 animate-fade-scale">
              <h2 className="text-xl font-bold text-black mb-6">Notifications ({filteredNotifications.length})</h2>
              
              {filteredNotifications.length === 0 ? (
                <div className="text-center py-12">
                  <Bell className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">No notifications</h3>
                  <p className="text-gray-600">You don't have any notifications yet.</p>
                </div>
              ) : (
                <div className="space-y-5">
              {filteredNotifications.map((notification, index) => {
                const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                return (
                <Card 
                  key={notification.id} 
                  className={`card-elevated border rounded-xl shadow-md ${staggerClass} animate-fade-scale ${
                    notification.isNew 
                      ? "border-blue-300/60 bg-gradient-to-r from-blue-50/80 to-blue-100/40 backdrop-blur-sm" 
                      : notification.isRead 
                      ? "border-gray-200/60 bg-white/95 backdrop-blur-sm" 
                      : "border-gray-300/60 bg-gray-50/90 backdrop-blur-sm"
                  }`}
                  onClick={() => {
                    // Open message viewer for message notifications
                    if (notification.type === 'professor_message' || notification.type === 'student_reply' || notification.type === 'student_message' || notification.type === 'message_sent') {
                      setShowMessageViewer(true)
                    }
                  }}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start space-x-4">
                      <div className="flex-shrink-0">
                        {getTypeIcon(notification.type)}
                      </div>
                      
                      <div className="flex-1">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center space-x-3">
                            <h3 className="font-semibold text-gray-900">{notification.title}</h3>
                            {getTypeBadge(notification.type)}
                            {getStatusBadge(notification.status)}
                            {notification.isNew && (
                              <Badge className="bg-blue-100 text-blue-800 text-xs">New</Badge>
                            )}
                            {!notification.isRead && (
                              <div className="w-2 h-2 bg-blue-600 rounded-full"></div>
                            )}
                          </div>
                          <p className="text-xs text-gray-500">{notification.time}</p>
                        </div>
                        
                        <p className="text-gray-600 mb-3">{notification.message}</p>
                        
                        {/* Notification-specific details */}
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
                        
                        {/* Action Buttons */}
                        <div className="flex items-center space-x-3 mt-4">
                          {(notification.actions || []).map((action: string, index: number) => {
                            const isPrimary = action === "Accept" || action === "Start Simulation" || action === "Continue"
                            return (
                              <Button
                                key={index}
                                size="sm"
                                variant={isPrimary ? "default" : "outline"}
                                className={
                                  isPrimary 
                                    ? "btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold" 
                                    : "border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all"
                                }
                                onClick={() => {
                                  if (action === "Accept") {
                                    handleAcceptInvitation(notification.invitationId || notification.id)
                                  } else if (action === "Decline") {
                                    handleDeclineInvitation(notification.invitationId || notification.id)
                                  } else {
                                    handleMarkAsRead(notification.id)
                                  }
                                }}
                              >
                                {action}
                              </Button>
                            )
                          })}
                          
                          {!notification.isRead && (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleMarkAsRead(notification.id)}
                              className="text-gray-500 hover:text-gray-700 transition-all"
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
          )}

          {/* Messaging Modal */}
          <MessagingModal
            isOpen={showMessagingModal}
            onClose={() => setShowMessagingModal(false)}
            currentUser={user}
          />

          {/* Message Viewer Modal */}
          <MessageViewerModal
            isOpen={showMessageViewer}
            onClose={() => setShowMessageViewer(false)}
            currentUser={user}
          />
        </div>
      </div>
    </div>
  )
}
