"use client"

import { useState, useEffect, useMemo } from "react"
import Link from "next/link"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"
import { 
  Home, 
  Users,
  Play,
  BookOpen,
  Bell,
  Megaphone
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
    // Initialize Canny Changelog
    // @ts-ignore
    if (typeof window !== 'undefined') {
      // @ts-ignore
      if (typeof window.Canny !== 'function') {
        // @ts-ignore
        window.Canny = function() {
          // @ts-ignore
          (window.Canny.q = window.Canny.q || []).push(arguments);
        };
      }

      if (!document.getElementById('canny-jssdk')) {
        const script = document.createElement('script');
        script.type = 'text/javascript';
        script.async = true;
        script.id = 'canny-jssdk';
        script.src = 'https://canny.io/sdk.js';
        const firstScript = document.getElementsByTagName('script')[0];
        firstScript?.parentNode?.insertBefore(script, firstScript);
      }

      // Runtime check for Canny App ID
      const cannyAppId = process.env.NEXT_PUBLIC_CANNY_APP_ID;
      if (!cannyAppId) {
        console.error('Missing environment variable: NEXT_PUBLIC_CANNY_APP_ID. Canny changelog will not initialize.');
        return;
      }

      // @ts-ignore
      window.Canny('initChangelog', {
        appID: cannyAppId,
        position: 'right', // Open to the right of the sidebar
        align: 'bottom',   // Align with the bottom (trigger location)
        theme: 'auto',
      });
    }

    const fetchUnreadCount = async () => {
      if (!user || !user.role) return
      
      try {
        const response = await apiClient.getNotifications(user.role, 50, 0, true) // unreadOnly = true
        // Response is now an array directly (or empty array on 404)
        const notifications = Array.isArray(response) ? response : (response.notifications || [])
        setUnreadCount(notifications.length)
      } catch (error) {
        // Silently handle error - notifications endpoint may not be implemented yet
        setUnreadCount(0)
      }
    }

    fetchUnreadCount()
    
    // Only refresh when tab becomes visible (not constant polling)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchUnreadCount()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [user])
  
  // Professor navigation items
  const professorNavItems = [
    { href: "/professor/dashboard", icon: Home, label: "Dashboard" },
    { href: "/professor/cohorts", icon: Users, label: "Cohorts" },
    { href: "/professor/notifications", icon: Bell, label: "Notifications" },
  ]
  
  // Student navigation items
  const studentNavItems = [
    { href: "/student/dashboard", icon: Home, label: "Dashboard" },
    { href: "/student/simulations", icon: Play, label: "Simulations" },
    { href: "/student/my-cohorts", icon: BookOpen, label: "My Cohorts" },
    { href: "/student/notifications", icon: Bell, label: "Notifications" },
    // { href: "/student/chat", icon: MessageSquare, label: "Chat" }, // Hidden for now
  ]
  
  // Get navigation items based on role
  const navItems = isProfessor ? professorNavItems : studentNavItems
  
  const profileHref = isProfessor
    ? '/professor/profile'
    : isStudent
    ? '/student/profile'
    : '/dashboard'

  // Get user initials
  const userInitials = useMemo(() => {
    if (user?.full_name) {
      return user.full_name
        .split(" ")
        .map((part: string) => part.charAt(0).toUpperCase())
        .slice(0, 2)
        .join("") || "U"
    }

    if (user?.email) {
      return user.email.charAt(0).toUpperCase()
    }

    return "U"
  }, [user])

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
      
      {/* Changelog Section */}
      <div className="mt-auto mb-4">
        {/* Changelog Button */}
        <button
          data-canny-changelog
          className="p-3 hover:bg-gray-800 rounded-lg transition-all duration-300 group relative block"
          title="What's New"
        >
          <div className="relative">
            <Megaphone className="h-6 w-6 text-white" />
          </div>
          
          {/* Tooltip */}
          <div className="absolute left-full ml-3 px-3 py-2 bg-gray-900/95 backdrop-blur-sm text-white text-xs font-medium rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-300 pointer-events-none whitespace-nowrap z-[999] shadow-xl border border-gray-700">
            What's New
          </div>
        </button>
      </div>

      
      {/* User Role Indicator */}
      <div className="mb-4 animate-scale-in">
        <Link href={profileHref} title="View profile" className="group block">
          <div
            className={`w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold shadow-lg transition-all duration-200 group-hover:scale-110 group-hover:shadow-xl ${
              isProfessor
                ? "bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-blue-500/30"
                : isStudent
                ? "bg-gradient-to-br from-green-600 to-green-700 text-white shadow-green-500/30"
                : "bg-gradient-to-br from-gray-600 to-gray-700 text-white"
            }`}
            aria-label="View profile"
          >
            {userInitials}
          </div>
        </Link>
      </div>
    </div>
  )
}
