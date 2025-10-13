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
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import MessagingModal from "@/components/MessagingModal"
import MessageViewerModal from "@/components/MessageViewerModal"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

interface Notification {
  id: number
  type: string
  title: string
  message: string
  data?: any
  is_read: boolean
  created_at: string
}

export default function ProfessorNotifications() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState("")
  const [typeFilter, setTypeFilter] = useState("All Types")
  const [statusFilter, setStatusFilter] = useState("All Status")
  const [markingRead, setMarkingRead] = useState<number | null>(null)
  
  // Messaging state
  const [showMessagingModal, setShowMessagingModal] = useState(false)
  const [showMessageViewer, setShowMessageViewer] = useState(false)

  // Fetch notifications
  const fetchNotifications = async () => {
    try {
      setLoading(true)
      const response = await apiClient.getNotifications(100, 0, false)
      setNotifications(response.notifications || [])
    } catch (err) {
      setError('Failed to load notifications')
      console.error('Error fetching notifications:', err)
    } finally {
      setLoading(false)
    }
  }


  // Mark notification as read
  const markAsRead = async (notificationId: number) => {
    try {
      setMarkingRead(notificationId)
      await apiClient.markNotificationRead(notificationId)
      
      // Update local state
      setNotifications(prev => 
        prev.map(notif => 
          notif.id === notificationId 
            ? { ...notif, is_read: true }
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
    try {
      await apiClient.markAllNotificationsRead()
      setNotifications(prev => 
        prev.map(notif => ({ ...notif, is_read: true }))
      )
    } catch (error) {
      console.error('Failed to mark all notifications as read:', error)
    }
  }

  // Get notification icon based on type
  const getNotificationIcon = (type: string) => {
    switch (type) {
      case 'invitation_response':
        return <UserPlus className="h-5 w-5 text-blue-600" />
      case 'assignment_completion':
        return <BookOpen className="h-5 w-5 text-purple-600" />
      case 'grade_submission':
        return <Trophy className="h-5 w-5 text-green-600" />
      case 'cohort_update':
        return <Users className="h-5 w-5 text-orange-600" />
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

  // Get notification color based on type
  const getNotificationColor = (type: string) => {
    switch (type) {
      case 'invitation_response':
        return 'bg-blue-50 border-blue-200'
      case 'assignment_completion':
        return 'bg-purple-50 border-purple-200'
      case 'grade_submission':
        return 'bg-green-50 border-green-200'
      case 'cohort_update':
        return 'bg-orange-50 border-orange-200'
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

  // Format time ago
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

  // Filter notifications
  const filteredNotifications = notifications.filter(notification => {
    const matchesSearch = notification.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         notification.message.toLowerCase().includes(searchTerm.toLowerCase())
    
    const matchesType = typeFilter === "All Types" || notification.type === typeFilter
    const matchesStatus = statusFilter === "All Status" || 
                         (statusFilter === "Unread" && !notification.is_read) ||
                         (statusFilter === "Read" && notification.is_read)
    
    return matchesSearch && matchesType && matchesStatus
  })

  // Get unique notification types
  const notificationTypes = ["All Types", ...Array.from(new Set(notifications.map(n => n.type)))]

  // Load notifications on component mount
  useEffect(() => {
    if (user && !authLoading) {
      fetchNotifications()
    }
  }, [user, authLoading])

  // Handle redirect for unauthenticated users
  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login')
    }
  }, [user, authLoading, router])

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
      </div>
    )
  }

  if (!user) {
    return null
  }

  const unreadCount = notifications.filter(n => !n.is_read).length

  return (
    <div className="min-h-screen bg-gray-50">
      <RoleBasedSidebar currentPath="/professor/notifications" />
      
      <div className="ml-20 p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Notifications</h1>
            <p className="text-gray-600">Stay updated with student activities and cohort updates</p>
          </div>
          <div className="flex items-center space-x-3">
            {unreadCount > 0 && (
              <Button
                onClick={markAllAsRead}
                variant="outline"
                className="flex items-center space-x-2"
              >
                <CheckCheck className="h-4 w-4" />
                <span>Mark all as read</span>
              </Button>
            )}
            <Button
              onClick={() => setShowMessagingModal(true)}
              className="bg-blue-600 hover:bg-blue-700"
            >
              <MessageSquare className="h-4 w-4 mr-2" />
              Compose Message
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-blue-100 rounded-lg">
                    <Bell className="h-5 w-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Total</p>
                    <p className="text-2xl font-bold text-gray-900">{notifications.length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-red-100 rounded-lg">
                    <Bell className="h-5 w-5 text-red-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Unread</p>
                    <p className="text-2xl font-bold text-gray-900">{unreadCount}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-green-100 rounded-lg">
                    <UserPlus className="h-5 w-5 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Invitations</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {notifications.filter(n => n.type === 'invitation_response').length}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-purple-100 rounded-lg">
                    <BookOpen className="h-5 w-5 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Assignments</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {notifications.filter(n => n.type === 'assignment_completion').length}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>


        {/* Search and Filter Bar */}
        <Card className="mb-6">
          <CardContent className="p-4">
            <div className="flex items-center space-x-4">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 h-4 w-4" />
                <input
                  type="text"
                  placeholder="Search notifications..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {notificationTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
              
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="All Status">All Status</option>
                <option value="Unread">Unread</option>
                <option value="Read">Read</option>
              </select>
            </div>
          </CardContent>
        </Card>

        {/* Notifications List */}
        {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <p className="text-red-600">{error}</p>
            </div>
          ) : filteredNotifications.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <Bell className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No notifications found</h3>
                <p className="text-gray-600">
                  {notifications.length === 0 
                    ? "You'll receive notifications when students respond to invitations or complete assignments."
                    : "No notifications match your current filters."
                  }
                </p>
              </CardContent>
            </Card>
          ) : (
          <div className="space-y-4">
            {filteredNotifications.map((notification) => (
              <Card 
                key={notification.id} 
                className={`transition-all duration-200 hover:shadow-md ${
                  !notification.is_read 
                    ? `${getNotificationColor(notification.type)} border-l-4` 
                    : 'bg-white'
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
                              notification.is_read ? 'text-gray-700' : 'text-gray-900'
                            }`}>
                              {notification.title}
                            </h3>
                            {!notification.is_read && (
                              <Badge variant="destructive" className="text-xs">
                                New
                              </Badge>
                            )}
                          </div>
                          
                          <p className={`text-sm mb-3 ${
                            notification.is_read ? 'text-gray-500' : 'text-gray-600'
                          }`}>
                            {notification.message}
                          </p>
                          
                          <div className="flex items-center space-x-4 text-xs text-gray-500">
                            <span className="flex items-center">
                              <Clock className="h-3 w-3 mr-1" />
                              {formatTimeAgo(notification.created_at)}
                            </span>
                            <Badge variant="outline" className="text-xs">
                              {notification.type.replace('_', ' ')}
                            </Badge>
                          </div>
                        </div>
                        
                        {!notification.is_read && (
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
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
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
  )
}
