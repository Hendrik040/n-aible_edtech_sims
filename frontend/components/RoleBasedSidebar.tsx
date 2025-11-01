"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"
import { 
  Home, 
  FileText, 
  Users,
  Play,
  BookOpen,
  Bell,
  Settings,
  MessageCircle,
  MessageSquare
} from "lucide-react"

interface RoleBasedSidebarProps {
  currentPath?: string
}

export default function RoleBasedSidebar({ currentPath = "/dashboard" }: RoleBasedSidebarProps) {
  const { user } = useAuth()
  const [unreadCount, setUnreadCount] = useState(0)
  
  // Determine user role and get appropriate navigation
  const isProfessor = user?.role === 'professor' || user?.role === 'admin'
  const isStudent = user?.role === 'student'
  
  // Fetch unread notification count
  useEffect(() => {
    const fetchUnreadCount = async () => {
      if (!user) return
      
      try {
        const response = await apiClient.getNotifications(50, 0, true) // unreadOnly = true
        const notifications = response.notifications || []
        setUnreadCount(notifications.length)
      } catch (error) {
        // Silently handle error
      }
    }

    fetchUnreadCount()
    
    // Refresh count every 30 seconds
    const interval = setInterval(fetchUnreadCount, 30000)
    return () => clearInterval(interval)
  }, [user])
  
  // Professor navigation items
  const professorNavItems = [
    { href: "/professor/dashboard", icon: Home, label: "Dashboard" },
    { href: "/professor/cohorts", icon: Users, label: "Cohorts" },
    { href: "/professor/simulation-builder", icon: FileText, label: "Simulation Builder" },
    { href: "/professor/test-simulations", icon: MessageSquare, label: "Test Simulations" },
    { href: "/professor/notifications", icon: Bell, label: "Notifications" },
  ]
  
  // Student navigation items
  const studentNavItems = [
    { href: "/student/dashboard", icon: Home, label: "Dashboard" },
    { href: "/student/simulations", icon: Play, label: "Simulations" },
    { href: "/student/my-cohorts", icon: BookOpen, label: "My Cohorts" },
    { href: "/student/notifications", icon: Bell, label: "Notifications" },
  ]
  
  // Get navigation items based on role
  const navItems = isProfessor ? professorNavItems : studentNavItems
  
  return (
    <div className="w-20 bg-gradient-to-b from-gray-900 via-black to-gray-900 flex flex-col items-center py-6 fixed left-0 top-0 h-full z-40 border-r border-gray-800/50 shadow-2xl">
      {/* Logo */}
      <div className="mb-8 animate-scale-in">
        <img src="/n-aiblelogo.png" alt="Logo" className="w-18 h-10 opacity-90 hover:opacity-100 transition-opacity" />
      </div>

      {/* Navigation Icons */}
      <nav className="flex flex-col space-y-4">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = currentPath === item.href
          const isNotificationButton = item.label === "Notifications"
          const showBadge = isNotificationButton && unreadCount > 0
          
          return (
            <Link 
              key={item.href}
              href={item.href} 
              className={`p-3 rounded-xl transition-all duration-300 group relative ${
                isActive 
                  ? "bg-gradient-to-br from-blue-600 to-blue-700 shadow-lg shadow-blue-500/30 scale-105" 
                  : "hover:bg-gray-800/80 hover:scale-105"
              }`}
              title={item.label}
            >
              <Icon className={`h-6 w-6 transition-all ${isActive ? "text-white" : "text-gray-300 group-hover:text-white"}`} />
              
              {/* Unread Notification Badge */}
              {showBadge && (
                <div className="absolute top-1 right-1 bg-red-500 text-white text-[10px] font-bold rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </div>
              )}
              
              {/* Enhanced Tooltip */}
              <div className="absolute left-full ml-3 px-3 py-2 bg-gray-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-300 pointer-events-none whitespace-nowrap z-[999] shadow-xl border border-gray-700">
                {item.label}
              </div>
            </Link>
          )
        })}
      </nav>
      
      {/* Feedback Button - Just the Animated Speech Bubble */}
      <div className="mt-auto mb-4">
        <a
          href="https://n-aible.canny.io/feedback"
          target="_blank"
          rel="noopener noreferrer"
          className="p-3 hover:bg-gray-800 rounded-lg transition-all duration-300 group relative block"
          title="Send Feedback"
        >
          <MessageCircle className="h-7 w-7 text-white animate-bounce" style={{animationDuration: '2s'}} />
          
          {/* Enhanced Tooltip */}
          <div className="absolute left-full ml-3 px-3 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-200 pointer-events-none whitespace-nowrap z-[999] shadow-xl">
            <div className="flex items-center gap-2">
              <span>💡</span>
              <span>Send Feedback</span>
            </div>
            <div className="text-xs text-blue-200 mt-1">Help us improve!</div>
          </div>
        </a>
      </div>
      
      {/* User Role Indicator */}
      <div className="mb-4 animate-scale-in">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold shadow-lg transition-all hover:scale-110 ${
          isProfessor 
            ? "bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-blue-500/30" 
            : isStudent 
            ? "bg-gradient-to-br from-green-600 to-green-700 text-white shadow-green-500/30" 
            : "bg-gradient-to-br from-gray-600 to-gray-700 text-white"
        }`}>
          {isProfessor ? "P" : isStudent ? "S" : "U"}
        </div>
      </div>
    </div>
  )
}
