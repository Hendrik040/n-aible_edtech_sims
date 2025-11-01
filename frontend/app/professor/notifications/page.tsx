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


  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
      </div>
    )
  }

  if (!user) {
    router.push('/login')
    return null
  }

  const unreadCount = notifications.filter(n => !n.is_read).length

  return (
    <div className="h-screen bg-atmospheric relative pattern-dots overflow-hidden">
      <RoleBasedSidebar currentPath="/professor/notifications" />
      
      <div className="ml-20 h-full overflow-y-auto relative z-20">
        <div className="p-8 animate-page-enter min-h-full">
        {/* Header */}
        <div className="flex items-center justify-between mb-10 stagger-1 animate-fade-scale">
          <div className="flex items-center space-x-4">
            <div>
              <h1 className="text-4xl font-bold text-black mb-2 tracking-tight">Notifications</h1>
              <p className="text-gray-600 text-lg">Stay updated with student activities and cohort updates</p>
            </div>
          </div>
          <div className="flex items-center space-x-3">
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
                    <p className="text-2xl font-bold text-gray-900">{notifications.length}</p>
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
                      {notifications.filter(n => n.type === 'invitation_response').length}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
            
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center shadow-sm">
                    <BookOpen className="h-6 w-6 text-purple-600" />
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
                    {type}
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
          <div className="space-y-5 stagger-4 animate-fade-scale">
            {filteredNotifications.map((notification, index) => {
              const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
              return (
              <Card 
                key={notification.id} 
                className={`card-elevated rounded-xl shadow-md transition-all duration-300 hover:shadow-lg ${staggerClass} animate-fade-scale ${
                  !notification.is_read 
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
                            onClick={() => markAsRead(notification.id)}
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
