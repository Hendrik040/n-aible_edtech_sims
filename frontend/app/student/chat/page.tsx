"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { 
  MessageSquare,
  Send,
  BookOpen,
  Users,
  Trophy,
  Star,
  Clock,
  Play,
  Eye,
  ArrowLeft,
  Target,
  Brain,
  Zap
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"

export default function StudentChat() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  const [selectedSimulation, setSelectedSimulation] = useState<any>(null)
  const [message, setMessage] = useState("")
  const [chatHistory, setChatHistory] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)
  
  // Mock data - in real app, this would come from API
  const [availableSimulations] = useState([
    {
      id: 1,
      title: "Investment Portfolio Challenge",
      course: "Financial Management 401",
      instructor: "Dr. Michael Chen",
      status: "available",
      description: "Build and optimize a diversified investment portfolio using modern portfolio theory and risk management principles.",
      duration: "60-75 min",
      xpReward: "+400 XP",
      currentScene: 0,
      totalScenes: 4,
      progress: 0,
      is_draft: false,
      scenarios: [
        {
          id: 1,
          title: "Market Analysis",
          description: "Analyze current market conditions and identify investment opportunities.",
          status: "available"
        },
        {
          id: 2,
          title: "Portfolio Construction",
          description: "Build your initial portfolio based on risk tolerance and investment goals.",
          status: "locked"
        },
        {
          id: 3,
          title: "Risk Assessment",
          description: "Evaluate portfolio risk and implement risk management strategies.",
          status: "locked"
        },
        {
          id: 4,
          title: "Performance Optimization",
          description: "Optimize portfolio performance based on market changes.",
          status: "locked"
        }
      ]
    },
    {
      id: 2,
      title: "Risk Assessment Simulation",
      course: "Financial Management 401",
      instructor: "Dr. Michael Chen",
      status: "in_progress",
      description: "Navigate through various risk scenarios and make informed decisions.",
      duration: "30-45 min",
      xpReward: "+350 XP",
      currentScene: 2,
      totalScenes: 5,
      progress: 40,
      is_draft: false,
      scenarios: [
        {
          id: 5,
          title: "Market Volatility",
          description: "Assess market volatility and its impact on investments.",
          status: "completed"
        },
        {
          id: 6,
          title: "Credit Risk Analysis",
          description: "Evaluate credit risk in corporate bonds and loans.",
          status: "completed"
        },
        {
          id: 7,
          title: "Operational Risk",
          description: "Identify and mitigate operational risks in financial institutions.",
          status: "in_progress"
        },
        {
          id: 8,
          title: "Regulatory Risk",
          description: "Navigate regulatory changes and compliance requirements.",
          status: "locked"
        },
        {
          id: 9,
          title: "Crisis Management",
          description: "Develop crisis management strategies for financial institutions.",
          status: "locked"
        }
      ]
    }
  ])

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

  const handleStartSimulation = (simulation: any) => {
    // Safety check: prevent access to draft simulations
    if (simulation.is_draft) {
      alert('This simulation is not available yet. Please contact your instructor.')
      return
    }
    
    setSelectedSimulation(simulation)
    setChatHistory([
      {
        id: 1,
        type: "system",
        message: `Welcome to ${simulation.title}! You're about to begin an interactive business simulation. I'll guide you through realistic scenarios and help you make strategic decisions.`,
        timestamp: new Date().toISOString()
      },
      {
        id: 2,
        type: "system",
        message: `Let's start with the first scenario: ${simulation.scenarios[0]?.title || 'Introduction'}. ${simulation.scenarios[0]?.description || 'Begin your journey!'}`,
        timestamp: new Date().toISOString()
      }
    ])
  }

  const handleSendMessage = async () => {
    if (!message.trim() || !selectedSimulation) return

    const userMessage = {
      id: Date.now(),
      type: "user",
      message: message.trim(),
      timestamp: new Date().toISOString()
    }

    setChatHistory(prev => [...prev, userMessage])
    setMessage("")
    setIsLoading(true)

    // Simulate AI response
    setTimeout(() => {
      const aiResponse = {
        id: Date.now() + 1,
        type: "ai",
        message: "That's an interesting perspective! Let me help you analyze this scenario. Based on current market conditions, I'd recommend considering the following factors: risk tolerance, diversification, and market timing. What specific aspect would you like to explore further?",
        timestamp: new Date().toISOString()
      }
      setChatHistory(prev => [...prev, aiResponse])
      setIsLoading(false)
    }, 1500)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "available":
        return <Badge className="bg-green-100 text-green-800 text-xs">Available</Badge>
      case "in_progress":
        return <Badge className="bg-blue-100 text-blue-800 text-xs">In Progress</Badge>
      case "completed":
        return <Badge className="bg-gray-100 text-gray-800 text-xs">Completed</Badge>
      case "locked":
        return <Badge className="bg-gray-100 text-gray-600 text-xs">Locked</Badge>
      default:
        return <Badge className="bg-gray-100 text-gray-800 text-xs">{status}</Badge>
    }
  }

  const getScenarioStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <div className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center">
          <div className="w-2 h-2 bg-green-600 rounded-full"></div>
        </div>
      case "in_progress":
        return <div className="w-6 h-6 bg-blue-100 rounded-full flex items-center justify-center">
          <Play className="h-3 w-3 text-blue-600" />
        </div>
      case "locked":
        return <div className="w-6 h-6 bg-gray-100 rounded-full flex items-center justify-center">
          <div className="w-2 h-2 bg-gray-400 rounded-full"></div>
        </div>
      default:
        return <div className="w-6 h-6 bg-green-100 rounded-full flex items-center justify-center">
          <div className="w-2 h-2 bg-green-600 rounded-full"></div>
        </div>
    }
  }

  if (selectedSimulation) {
    return (
      <div className="min-h-screen bg-white">
        {/* Fixed Sidebar */}
        <RoleBasedSidebar currentPath="/student/chat" />

        {/* Main Content with left margin for sidebar */}
        <div className="ml-20 bg-white">
          {/* Chat Interface */}
          <div className="h-screen flex flex-col">
            {/* Header */}
            <div className="bg-white border-b border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSelectedSimulation(null)}
                    className="p-2"
                  >
                    <ArrowLeft className="h-4 w-4" />
                  </Button>
                  <div>
                    <h1 className="text-lg font-semibold text-black">{selectedSimulation.title}</h1>
                    <p className="text-sm text-gray-600">{selectedSimulation.course}</p>
                  </div>
                </div>
                
                <div className="flex items-center space-x-4">
                  <div className="text-right">
                    <p className="text-sm font-medium text-gray-900">Progress</p>
                    <p className="text-xs text-gray-600">{selectedSimulation.currentScene}/{selectedSimulation.totalScenes} scenes</p>
                  </div>
                  <div className="w-16 bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${selectedSimulation.progress}%` }}
                    ></div>
                  </div>
                </div>
              </div>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {chatHistory.map((msg) => (
                <div key={msg.id} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-3xl ${msg.type === 'user' ? 'order-2' : 'order-1'}`}>
                    <div className={`flex items-start space-x-2 ${msg.type === 'user' ? 'flex-row-reverse space-x-reverse' : ''}`}>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                        msg.type === 'user' ? 'bg-blue-600' : 'bg-gray-600'
                      }`}>
                        {msg.type === 'user' ? (
                          <span className="text-white text-sm font-medium">
                            {user?.full_name?.charAt(0) || 'U'}
                          </span>
                        ) : (
                          <Brain className="h-4 w-4 text-white" />
                        )}
                      </div>
                      <div className={`px-4 py-2 rounded-lg ${
                        msg.type === 'user' 
                          ? 'bg-blue-600 text-white' 
                          : 'bg-gray-100 text-gray-900'
                      }`}>
                        <p className="text-sm">{msg.message}</p>
                        <p className={`text-xs mt-1 ${
                          msg.type === 'user' ? 'text-blue-100' : 'text-gray-500'
                        }`}>
                          {new Date(msg.timestamp).toLocaleTimeString()}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              
              {isLoading && (
                <div className="flex justify-start">
                  <div className="max-w-3xl">
                    <div className="flex items-start space-x-2">
                      <div className="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center">
                        <Brain className="h-4 w-4 text-white" />
                      </div>
                      <div className="px-4 py-2 rounded-lg bg-gray-100">
                        <div className="flex space-x-1">
                          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                          <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Message Input */}
            <div className="bg-white border-t border-gray-200 p-4">
              <div className="flex space-x-2">
                <input
                  type="text"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Type your response..."
                  className="flex-1 px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-gray-200 focus:border-transparent"
                  disabled={isLoading}
                />
                <Button
                  onClick={handleSendMessage}
                  disabled={!message.trim() || isLoading}
                  className="bg-black text-white hover:bg-gray-800"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/student/chat" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 bg-white">
        {/* Main Content Area */}
        <div className="p-6">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-black mb-2">Interactive Simulations</h1>
            <p className="text-gray-600">Start an interactive business simulation and chat with AI-powered scenarios.</p>
          </div>

          {/* Available Simulations */}
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-black mb-4">Available Simulations</h2>
            
            <div className="space-y-4">
              {availableSimulations.map((simulation) => (
                <Card key={simulation.id} className="bg-white border border-gray-200 rounded-lg shadow-sm">
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="font-bold text-gray-900 text-lg mb-2">{simulation.title}</h3>
                        <div className="flex items-center space-x-4 text-sm text-gray-500 mb-3">
                          <span>{simulation.course}</span>
                          <span>{simulation.instructor}</span>
                          <span>{simulation.duration}</span>
                        </div>
                        <div className="flex items-center space-x-2 mb-3">
                          {getStatusBadge(simulation.status)}
                        </div>
                        <p className="text-gray-600 mb-4">{simulation.description}</p>
                      </div>
                      
                      <div className="text-right">
                        <div className="text-sm text-gray-600 mb-2">
                          {simulation.progress || 0}% completed
                        </div>
                        <div className="w-32 bg-gray-200 rounded-full h-2">
                          <div 
                            className="bg-gray-800 h-2 rounded-full transition-all duration-300"
                            style={{ width: `${simulation.progress || 0}%` }}
                          ></div>
                        </div>
                      </div>
                    </div>
                    
                    {/* Scenarios */}
                    <div className="mb-4">
                      <h4 className="text-sm font-medium text-gray-900 mb-2">Scenarios:</h4>
                      <div className="space-y-2">
                        {simulation.scenarios.map((scenario, index) => (
                          <div key={scenario.id} className="flex items-center space-x-3">
                            {getScenarioStatusIcon(scenario.status)}
                            <div className="flex-1">
                              <p className="text-sm font-medium text-gray-900">{scenario.title}</p>
                              <p className="text-xs text-gray-600">{scenario.description}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Star className="h-4 w-4 text-yellow-500" />
                        <span className="text-sm font-medium text-gray-900">{simulation.xpReward}</span>
                      </div>
                      
                      <Button
                        onClick={() => handleStartSimulation(simulation)}
                        className={simulation.is_draft 
                          ? "bg-gray-400 text-gray-600 cursor-not-allowed" 
                          : "bg-black text-white hover:bg-gray-800"}
                        disabled={simulation.status === "locked" || simulation.is_draft}
                      >
                        {simulation.is_draft ? (
                          <>
                            <Play className="h-4 w-4 mr-2" />
                            Draft - Not Available
                          </>
                        ) : simulation.status === "in_progress" ? (
                          <>
                            <Play className="h-4 w-4 mr-2" />
                            Continue
                          </>
                        ) : (
                          <>
                            <Play className="h-4 w-4 mr-2" />
                            Start Simulation
                          </>
                        )}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          {/* Quick Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card className="bg-white border border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mr-4">
                    <MessageSquare className="h-6 w-6 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">Active Chats</p>
                    <p className="text-2xl font-bold text-gray-900">2</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-white border border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mr-4">
                    <Target className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">Completed</p>
                    <p className="text-2xl font-bold text-gray-900">3</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-white border border-gray-200">
              <CardContent className="p-6">
                <div className="flex items-center">
                  <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mr-4">
                    <Zap className="h-6 w-6 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-1">XP Earned</p>
                    <p className="text-2xl font-bold text-gray-900">1,250</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
