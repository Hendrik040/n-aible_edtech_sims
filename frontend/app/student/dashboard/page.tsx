"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { 
  Target,
  Star,
  Bell,
  Users,
  Shield,
  Trophy,
  Clock,
  BookOpen,
  TrendingUp,
  Crown,
  Play,
  Eye,
  MessageCircle,
  UserPlus,
  Calendar,
  ArrowRight,
  CheckCircle,
  Zap,
  X
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

export default function StudentDashboard() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  // Real data from API
  const [pendingInvitations, setPendingInvitations] = useState<any[]>([])
  const [activeCohorts, setActiveCohorts] = useState<any[]>([])
  const [recentSimulations, setRecentSimulations] = useState<any[]>([])
  const [notifications, setNotifications] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  
  // Load dismissed IDs from localStorage on mount
  const [dismissedInvitationIds, setDismissedInvitationIds] = useState<Set<number>>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('dismissedInvitations')
      return stored ? new Set(JSON.parse(stored)) : new Set()
    }
    return new Set()
  })
  
  const [dismissedNotificationIds, setDismissedNotificationIds] = useState<Set<number>>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('dismissedNotifications')
      return stored ? new Set(JSON.parse(stored)) : new Set()
    }
    return new Set()
  })
  
  // Placeholder achievements (keep for future implementation)
  const [achievements] = useState([
    {
      id: 1,
      title: "Strategic Thinker",
      description: "Scored 90+ on 3 strategy simulations",
      icon: Target,
      earnedDate: "Dec 10",
      color: "bg-yellow-100 text-yellow-800"
    },
    {
      id: 2,
      title: "Speed Runner",
      description: "Complete a simulation in under 30 minutes",
      icon: Zap,
      earnedDate: "Dec 8",
      color: "bg-yellow-100 text-yellow-800"
    },
    {
      id: 3,
      title: "Top Performer",
      description: "Rank #1 in any simulation",
      icon: Trophy,
      earnedDate: "Dec 10",
      color: "bg-yellow-100 text-yellow-800"
    },
    {
      id: 4,
      title: "Consistent Player",
      description: "Complete 10 simulations",
      icon: TrendingUp,
      progress: "7/10",
      color: "bg-yellow-100 text-yellow-800"
    }
  ])
  
  // Load real data from API
  useEffect(() => {
    if (user) {
      loadDashboardData()
    }
  }, [user])

  const loadDashboardData = async () => {
    try {
      setLoading(true)
      
      // Load pending invitations, cohorts, simulations, and notifications in parallel
      const [invitationsRes, cohortsRes, simulationsRes, notificationsRes] = await Promise.allSettled([
        apiClient.getPendingInvitations(),
        apiClient.getStudentCohorts(),
        apiClient.getStudentSimulationInstances(),
        apiClient.getNotifications(10, 0, false)
      ])

      // Handle pending invitations
      if (invitationsRes.status === 'fulfilled') {
        setPendingInvitations(invitationsRes.value.invitations || [])
      }

      // Handle cohorts
      if (cohortsRes.status === 'fulfilled') {
        const cohortsData = cohortsRes.value.cohorts || cohortsRes.value || []
        setActiveCohorts(Array.isArray(cohortsData) ? cohortsData : [])
      }

      // Handle simulations
      if (simulationsRes.status === 'fulfilled') {
        const allSims = simulationsRes.value.instances || simulationsRes.value || []
        
        // Show both in-progress and completed simulations, sorted by most recent activity
        const recentSims = (Array.isArray(allSims) ? allSims : [])
          .filter((sim: any) => 
            sim.status === 'in_progress' || 
            sim.status === 'completed' || 
            sim.status === 'graded'
          )
          .sort((a: any, b: any) => {
            // Sort by most recent activity (completed_at for completed, started_at for in-progress)
            const dateA = new Date(a.completed_at || a.started_at || 0).getTime()
            const dateB = new Date(b.completed_at || b.started_at || 0).getTime()
            return dateB - dateA
          })
          .slice(0, 5) // Get last 5
        setRecentSimulations(recentSims)
      }

      // Handle notifications
      if (notificationsRes.status === 'fulfilled') {
        setNotifications(notificationsRes.value.notifications || [])
      }
    } catch (error) {
      // Silently handle error
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
      // Reload dashboard data to reflect changes
      await loadDashboardData()
    } catch (error) {
      alert('Failed to accept invitation. Please try again.')
    }
  }

  const handleDeclineInvitation = async (invitationId: number) => {
    try {
      await apiClient.respondToInvitation(invitationId, 'decline')
      // Reload dashboard data to reflect changes
      await loadDashboardData()
    } catch (error) {
      alert('Failed to decline invitation. Please try again.')
    }
  }

  const handleDismissInvitation = (invitationId: number) => {
    // Just hide it from view without responding
    const newDismissed = new Set(dismissedInvitationIds).add(invitationId)
    setDismissedInvitationIds(newDismissed)
    // Persist to localStorage
    localStorage.setItem('dismissedInvitations', JSON.stringify(Array.from(newDismissed)))
  }

  const handleDismissNotification = async (notificationId: number) => {
    try {
      // Mark notification as read in the backend
      await apiClient.markNotificationRead(notificationId)
      // Hide it from view
      const newDismissed = new Set(dismissedNotificationIds).add(notificationId)
      setDismissedNotificationIds(newDismissed)
      // Persist to localStorage
      localStorage.setItem('dismissedNotifications', JSON.stringify(Array.from(newDismissed)))
    } catch (error) {
      // Still dismiss it locally even if API call fails
      const newDismissed = new Set(dismissedNotificationIds).add(notificationId)
      setDismissedNotificationIds(newDismissed)
      localStorage.setItem('dismissedNotifications', JSON.stringify(Array.from(newDismissed)))
    }
  }

  // Filter out dismissed items
  const visibleInvitations = pendingInvitations.filter(inv => !dismissedInvitationIds.has(inv.id))
  const visibleNotifications = notifications.filter(notif => !dismissedNotificationIds.has(notif.id))

  const avatarFallback = user?.full_name
    ? user.full_name
        .split(" ")
        .map((part) => part.charAt(0).toUpperCase())
        .slice(0, 2)
        .join("") || "S"
    : user?.email
    ? user.email.charAt(0).toUpperCase()
    : "S"

  return (
    <div className="min-h-screen bg-atmospheric relative pattern-dots">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/student/dashboard" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 relative">
        {/* Main Content Area */}
        <div className="p-8">
          {/* Welcome Section */}
          <div className="mb-10 stagger-1 animate-fade-scale">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-4xl font-bold text-black tracking-tight mb-1">Welcome back, {user?.full_name || 'Student'}!</h1>
                <p className="text-gray-600 text-lg">Ready to tackle some challenging business simulations?</p>
              </div>
              
              <div className="flex items-center space-x-4">
                <div className="text-right">
                  <div className="flex items-center space-x-2">
                    <Star className="h-5 w-5 text-yellow-500" />
                    <span className="font-semibold text-gray-900">Level 7 Strategist</span>
                  </div>
                  <div className="w-32 bg-gray-200 rounded-full h-2 mt-1">
                    <div className="bg-yellow-500 h-2 rounded-full" style={{ width: '83%' }}></div>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">1,250 / 1,500 XP</p>
                </div>
                
                {/* User Menu with Logout */}
                <div className="flex items-center space-x-3">
                  <Link
                    href="/student/profile"
                    title="View profile"
                    className="transition-transform hover:scale-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black rounded-full"
                  >
                    <Avatar className="h-9 w-9 border border-gray-200 shadow-sm">
                      {user?.avatar_url ? (
                        <AvatarImage src={user.avatar_url} alt={user.full_name || 'Student profile'} />
                      ) : null}
                      <AvatarFallback className="bg-gradient-to-br from-green-600 to-green-500 text-white text-sm font-semibold">
                        {avatarFallback}
                      </AvatarFallback>
                    </Avatar>
                  </Link>
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={handleLogout}
                    className="border-gray-300 text-gray-700 hover:bg-gray-50"
                  >
                    Logout
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {/* Notifications Section */}
          <div className="mb-8">
            <div className="flex items-center space-x-2 mb-4">
              <Bell className="h-5 w-5 text-gray-600" />
              <h2 className="text-lg font-semibold text-black">Notifications</h2>
            </div>
            
            {/* Show only the most recent notification/invitation */}
            {visibleInvitations.length > 0 ? (
              // Prioritize showing invitations first
              <Card className="bg-white border border-blue-200 mb-4">
                <CardContent className="p-4 relative">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute top-2 right-2 h-6 w-6 p-0 hover:bg-gray-100"
                    onClick={() => handleDismissInvitation(visibleInvitations[0].id)}
                  >
                    <X className="h-4 w-4 text-gray-500" />
                  </Button>
                  <div className="flex items-start justify-between pr-8">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <h3 className="font-semibold text-gray-900">
                          Invitation to {visibleInvitations[0].cohort_name || 'Cohort'}
                        </h3>
                        <Badge className="bg-blue-100 text-blue-800 text-xs">Invitation</Badge>
                      </div>
                      <p className="text-gray-600 text-sm mb-3">
                        {visibleInvitations[0].professor_name || 'A professor'} has invited you to join their cohort. 
                        {visibleInvitations[0].custom_message && ` Message: "${visibleInvitations[0].custom_message}"`}
                      </p>
                      <p className="text-xs text-gray-500">
                        {visibleInvitations[0].created_at ? new Date(visibleInvitations[0].created_at).toLocaleDateString() : 'Recently'}
                      </p>
                      {visibleInvitations.length > 1 && (
                        <p className="text-xs text-blue-600 mt-2">
                          +{visibleInvitations.length - 1} more invitation{visibleInvitations.length - 1 !== 1 ? 's' : ''}
                        </p>
                      )}
                    </div>
                    
                    <div className="flex space-x-2">
                      <Button 
                        size="sm"
                        className="bg-black text-white hover:bg-gray-800"
                        onClick={() => handleAcceptInvitation(visibleInvitations[0].id)}
                      >
                        Join Cohort
                      </Button>
                      <Button 
                        size="sm"
                        variant="outline"
                        className="border-gray-300 text-gray-700 hover:bg-gray-50"
                        onClick={() => handleDeclineInvitation(visibleInvitations[0].id)}
                      >
                        Decline
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ) : visibleNotifications.length > 0 ? (
              // Show most recent notification if no invitations
              <Card className="bg-white border border-gray-200 mb-4">
                <CardContent className="p-4 relative">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute top-2 right-2 h-6 w-6 p-0 hover:bg-gray-100"
                    onClick={() => handleDismissNotification(visibleNotifications[0].id)}
                  >
                    <X className="h-4 w-4 text-gray-500" />
                  </Button>
                  <div className="flex items-start justify-between pr-8">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-2">
                        <h3 className="font-semibold text-gray-900">{visibleNotifications[0].title}</h3>
                        {!visibleNotifications[0].is_read && (
                          <Badge className="bg-blue-100 text-blue-800 text-xs">New</Badge>
                        )}
                      </div>
                      <p className="text-gray-600 text-sm mb-3">{visibleNotifications[0].message}</p>
                      <p className="text-xs text-gray-500">
                        {visibleNotifications[0].created_at ? new Date(visibleNotifications[0].created_at).toLocaleDateString() : ''}
                      </p>
                      {visibleNotifications.length > 1 && (
                        <p className="text-xs text-blue-600 mt-2">
                          +{visibleNotifications.length - 1} more notification{visibleNotifications.length - 1 !== 1 ? 's' : ''}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card className="bg-white border border-gray-200">
                <CardContent className="p-6 text-center">
                  <Bell className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                  <p className="text-gray-600">No new notifications</p>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8 stagger-3 animate-fade-scale">
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Users className="h-6 w-6 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">Active Cohorts</p>
                    <p className="text-2xl font-bold text-gray-900">{activeCohorts.length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Shield className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Avg. Score</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {recentSimulations.length > 0 
                        ? Math.round(recentSimulations.reduce((sum: number, sim: any) => sum + (sim.final_score || 0), 0) / recentSimulations.length) + '%'
                        : 'N/A'}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Target className="h-6 w-6 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Completed</p>
                    <p className="text-2xl font-bold text-gray-900">{recentSimulations.length}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-gradient-to-br from-yellow-100 to-yellow-50 rounded-xl flex items-center justify-center mr-4 shadow-sm">
                    <Trophy className="h-6 w-6 text-yellow-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1 font-medium">Best Score</p>
                    <p className="text-2xl font-bold text-gray-900">
                      {recentSimulations.length > 0 
                        ? Math.max(...recentSimulations.map((sim: any) => sim.final_score || 0)) + '%'
                        : 'N/A'}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Recent Achievements */}
          <div className="mb-8 stagger-4 animate-fade-scale">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-black tracking-tight">Recent Achievements</h2>
              <Link href="#" className="text-sm text-gray-600 hover:text-black flex items-center">
                View All <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {achievements.map((achievement) => {
                const Icon = achievement.icon
                return (
                  <Card key={achievement.id} className="card-elevated bg-gradient-to-br from-yellow-50 to-yellow-100/50 border border-yellow-200/60 shadow-md">
                    <CardContent className="p-4">
                      <div className="flex items-start space-x-3">
                        <div className="w-10 h-10 bg-yellow-100 rounded-lg flex items-center justify-center">
                          <Icon className="h-5 w-5 text-yellow-600" />
                        </div>
                        <div className="flex-1">
                          <h3 className="font-semibold text-gray-900 text-sm">{achievement.title}</h3>
                          <p className="text-xs text-gray-600 mt-1">{achievement.description}</p>
                          {achievement.progress ? (
                            <p className="text-xs text-gray-500 mt-2">Progress: {achievement.progress}</p>
                          ) : (
                            <p className="text-xs text-gray-500 mt-2">Earned {achievement.earnedDate}</p>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          </div>

          {/* Active Cohorts */}
          <div className="mb-8 stagger-5 animate-fade-scale">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-black tracking-tight">Active Cohorts</h2>
              <Link href="/student/my-cohorts" className="text-sm text-gray-600 hover:text-black flex items-center">
                View All Cohorts <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </div>
            
            {activeCohorts.length === 0 ? (
              <Card className="bg-white border border-gray-200">
                <CardContent className="p-6 text-center">
                  <Users className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                  <p className="text-gray-600">No active cohorts yet</p>
                  <p className="text-sm text-gray-500 mt-1">Accept an invitation to join your first cohort</p>
                </CardContent>
              </Card>
            ) : (
            <div className="space-y-5">
              {activeCohorts.map((cohort, index) => {
                const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                return (
                <Card key={cohort.id} className={`card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${staggerClass} animate-fade-scale`}>
                  <CardHeader className="pb-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                          <CardTitle className="text-lg font-bold text-black">
                            {cohort.title || 'Cohort'}
                          </CardTitle>
                          <p className="text-sm text-gray-600 mt-1">
                            Instructor: {cohort.professor?.name || 'Instructor'}
                          </p>
                          {cohort.course_code && (
                            <p className="text-xs text-gray-500 mt-1">
                              {cohort.course_code} • {cohort.semester || ''} {cohort.year || ''}
                            </p>
                          )}
                          <p className="text-sm text-gray-600 mt-2">
                            {cohort.description || 'Active cohort for simulation assignments'}
                          </p>
                      </div>
                      <div className="flex items-center space-x-2">
                        <Badge className="bg-green-100 text-green-800 text-xs">Active</Badge>
                      </div>
                    </div>
                  </CardHeader>
                  
                  <CardContent>
                      {/* Joined Date */}
                    <div className="mb-4">
                        <div className="flex items-center space-x-2 text-sm text-gray-600">
                          <Calendar className="h-4 w-4" />
                          <span>
                            Joined {cohort.joined_at ? new Date(cohort.joined_at).toLocaleDateString() : 
                                    cohort.created_at ? new Date(cohort.created_at).toLocaleDateString() : 
                                    'Recently'}
                          </span>
                        </div>
                    </div>
                    
                    {/* Action Buttons */}
                    <div className="flex space-x-2">
                        <Link href="/student/simulations" className="flex-1">
                          <Button variant="outline" size="sm" className="w-full">
                        <BookOpen className="h-4 w-4 mr-2" />
                            View Simulations
                      </Button>
                        </Link>
                        <Button variant="outline" size="sm" className="flex-1" disabled>
                        <MessageCircle className="h-4 w-4 mr-2" />
                          Discussion (Coming Soon)
                      </Button>
                    </div>
                  </CardContent>
                </Card>
                )
              })}
            </div>
            )}
          </div>

          {/* Recent Simulations */}
          <div className="mb-8 stagger-6 animate-fade-scale">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-black tracking-tight">Recent Activity</h2>
              <Link href="/student/simulations" className="text-sm text-gray-600 hover:text-black flex items-center">
                View All <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </div>
            
            {recentSimulations.length === 0 ? (
              <Card className="bg-white border border-gray-200">
                <CardContent className="p-6 text-center">
                  <BookOpen className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                  <p className="text-gray-600">No completed simulations yet</p>
                  <p className="text-sm text-gray-500 mt-1">Start a simulation to see your progress here</p>
                </CardContent>
              </Card>
            ) : (
            <div className="space-y-5">
                {recentSimulations.map((simulation: any, index: number) => {
                  const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                  return (
                <Card key={simulation.id} className={`card-elevated bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${staggerClass} animate-fade-scale`}>
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                          <h3 className="font-bold text-gray-900 text-lg mb-2">
                            {simulation.cohort_assignment?.simulation?.title || 'Simulation'}
                          </h3>
                        <div className="flex flex-wrap items-center gap-2 text-sm text-gray-500 mb-3">
                            {simulation.cohort_assignment?.cohort?.title && (
                              <span className="flex items-center">
                                <Users className="h-3 w-3 mr-1" />
                                {simulation.cohort_assignment.cohort.title}
                              </span>
                            )}
                            {simulation.status === 'in_progress' && simulation.started_at && (
                              <span className="flex items-center">
                                <Clock className="h-3 w-3 mr-1" />
                                Started {new Date(simulation.started_at).toLocaleDateString()}
                              </span>
                            )}
                            {simulation.completed_at && (
                              <span className="flex items-center">
                                <CheckCircle className="h-3 w-3 mr-1" />
                                {new Date(simulation.completed_at).toLocaleDateString()}
                              </span>
                            )}
                            {simulation.started_at && simulation.completed_at && (
                              <span className="flex items-center">
                                <Clock className="h-3 w-3 mr-1" />
                                {Math.round((new Date(simulation.completed_at).getTime() - new Date(simulation.started_at).getTime()) / (1000 * 60))} min
                              </span>
                            )}
                            {simulation.cohort_assignment?.due_date && (
                              <span className={simulation.is_overdue ? 'text-red-600 font-semibold' : ''}>
                                {simulation.is_overdue ? '⚠️ ' : '📅 '}
                                Due {new Date(simulation.cohort_assignment.due_date).toLocaleDateString()}
                                {simulation.is_overdue && simulation.days_late ? ` (${simulation.days_late}d late)` : ''}
                              </span>
                            )}
                        </div>
                        <div className="flex items-center space-x-2">
                            {simulation.status === 'in_progress' ? (
                              <Badge className="bg-blue-100 text-blue-800 text-xs">
                                In Progress
                              </Badge>
                            ) : simulation.status === 'graded' ? (
                              <Badge className="bg-green-100 text-green-800 text-xs">
                                Graded
                              </Badge>
                            ) : simulation.status === 'completed' ? (
                              <Badge className="bg-purple-100 text-purple-800 text-xs">
                                Awaiting Grade
                              </Badge>
                            ) : simulation.status === 'submitted' ? (
                              <Badge className="bg-yellow-100 text-yellow-800 text-xs">
                                Submitted
                              </Badge>
                            ) : (
                              <Badge className="bg-gray-100 text-gray-800 text-xs">
                                {simulation.status}
                              </Badge>
                            )}
                            {(simulation.completion_percentage !== null && simulation.completion_percentage !== undefined) && (
                              <span className="text-xs text-gray-500">
                                {simulation.completion_percentage}% Complete
                          </span>
                            )}
                        </div>
                      </div>
                      
                      <div className="text-right">
                          {(simulation.grade !== null && simulation.grade !== undefined) && (
                        <div className="text-sm text-gray-600 mb-2">
                              Score: {simulation.grade}%
                        </div>
                          )}
                          <Link 
                            href={`/student/run-simulation/${simulation.unique_id}`} 
                            className="text-sm text-blue-600 hover:text-blue-800"
                          >
                            {simulation.status === 'in_progress' ? 'Continue' : 'View Results'}
                        </Link>
                      </div>
                    </div>
                  </CardContent>
                </Card>
                  )
                })}
            </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
