"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { 
  X, 
  Search, 
  UserPlus, 
  Paperclip, 
  Music,
  Check,
  ChevronDown
} from "lucide-react"
import { apiClient } from "@/lib/api"

interface MessagingModalProps {
  isOpen: boolean
  onClose: () => void
  currentUser: any
}

interface User {
  id: number
  full_name: string
  email: string
  role: string
}

interface Cohort {
  id: number
  title: string
  course_code: string
}

export default function MessagingModal({ isOpen, onClose, currentUser }: MessagingModalProps) {
  const [selectedCourse, setSelectedCourse] = useState<string>("")
  const [sendIndividual, setSendIndividual] = useState(false)
  const [recipients, setRecipients] = useState<User[]>([])
  const [subject, setSubject] = useState("")
  const [message, setMessage] = useState("")
  const [includeTranslation, setIncludeTranslation] = useState(false)
  const [sending, setSending] = useState(false)
  
  // Search and selection state
  const [searchTerm, setSearchTerm] = useState("")
  const [showUserDropdown, setShowUserDropdown] = useState(false)
  const [availableUsers, setAvailableUsers] = useState<User[]>([])
  const [availableCohorts, setAvailableCohorts] = useState<Cohort[]>([])
  const [showCohortDropdown, setShowCohortDropdown] = useState(false)

  // Fetch users and cohorts
  useEffect(() => {
    if (isOpen) {
      fetchUsers()
      fetchCohorts()
    }
  }, [isOpen])

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }
    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [isOpen])

  const fetchUsers = async () => {
    try {
      const data = await apiClient.getUsers()
      setAvailableUsers(data || [])
    } catch (error) {
      console.error('Error fetching users:', error)
      setAvailableUsers([])
    }
  }

  const fetchCohorts = async () => {
    try {
      const data = await apiClient.getMessagingCohorts()
      setAvailableCohorts(data || [])
    } catch (error) {
      console.error('Error fetching cohorts:', error)
      setAvailableCohorts([])
    }
  }

  const filteredUsers = availableUsers.filter(user =>
    user.full_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.email.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const addRecipient = (user: User) => {
    if (!recipients.find(r => r.id === user.id)) {
      setRecipients([...recipients, user])
    }
    setSearchTerm("")
    setShowUserDropdown(false)
  }

  const removeRecipient = (userId: number) => {
    setRecipients(recipients.filter(r => r.id !== userId))
  }

  const handleSend = async () => {
    if (!subject.trim() || !message.trim() || recipients.length === 0) {
      return
    }

    try {
      setSending(true)
      
      // Send message to each recipient
      for (const recipient of recipients) {
        const messageData = {
          recipient_id: recipient.id,
          cohort_id: selectedCourse ? parseInt(selectedCourse) : null,
          subject: subject,
          message: message,
          message_type: 'general'
        }
        
        await apiClient.sendMessage(messageData)
      }
      
      // Reset form
      setRecipients([])
      setSubject("")
      setMessage("")
      setSelectedCourse("")
      setSendIndividual(false)
      setIncludeTranslation(false)
      
      onClose()
    } catch (error) {
      console.error('Error sending message:', error)
    } finally {
      setSending(false)
    }
  }

  if (!isOpen) return null

  return (
    <div 
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] animate-fade-scale" 
      onClick={onClose}
      style={{ left: 0, right: 0, top: 0, bottom: 0 }}
    >
      <div 
        className="fixed inset-0 flex items-center justify-center py-8 px-4 pointer-events-none"
        style={{ left: 0, right: 0, top: 0, bottom: 0 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div 
          className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-2xl max-h-[calc(100vh-4rem)] overflow-hidden border border-gray-200/60 animate-scale-in flex flex-col pointer-events-auto"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200/60 flex-shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center shadow-sm">
                <Search className="h-5 w-5 text-purple-600" />
              </div>
              <h2 className="text-xl font-bold text-gray-900 tracking-tight">Compose Message</h2>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="h-8 w-8 p-0 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* Content */}
          <div className="p-6 space-y-6 overflow-y-auto flex-1 min-h-0">
            {/* Course Selection */}
            <div>
              <Label htmlFor="course" className="text-sm font-medium text-gray-700 mb-2 block">
                Course
              </Label>
              <div className="relative">
                <select
                  id="course"
                  value={selectedCourse}
                  onChange={(e) => setSelectedCourse(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400/50 appearance-none transition-all shadow-sm hover:shadow-md"
                >
                  <option value="">Select Course</option>
                  {availableCohorts.map((cohort) => (
                    <option key={cohort.id} value={cohort.id}>
                      {cohort.course_code} - {cohort.title}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
              </div>
            </div>

            {/* Individual Message Option */}
            <div className="flex items-center space-x-2 p-3 bg-gray-50/50 rounded-xl">
              <input
                type="checkbox"
                id="individual"
                checked={sendIndividual}
                onChange={(e) => setSendIndividual(e.target.checked)}
                className="h-4 w-4 text-slate-600 focus:ring-slate-500 border-gray-300 rounded cursor-pointer"
              />
              <Label htmlFor="individual" className="text-sm text-gray-700 cursor-pointer">
                Send an individual message to each recipient
              </Label>
            </div>

            {/* Recipients */}
            <div>
              <Label htmlFor="recipients" className="text-sm font-medium text-gray-700 mb-2 block">
                To <span className="text-red-500">*</span>
              </Label>
              <div className="relative">
                <div className="flex items-center space-x-2 border border-gray-200/80 rounded-xl p-3 bg-white/80 backdrop-blur-sm focus-within:ring-2 focus-within:ring-purple-500/20 focus-within:border-purple-400/50 transition-all shadow-sm hover:shadow-md">
                  <Search className="h-4 w-4 text-gray-400" />
                  <Input
                    id="recipients"
                    placeholder="Insert or Select Names"
                    value={searchTerm}
                    onChange={(e) => {
                      setSearchTerm(e.target.value)
                      setShowUserDropdown(true)
                    }}
                    onFocus={() => setShowUserDropdown(true)}
                    className="flex-1 border-0 focus:ring-0 p-0 bg-transparent"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0 hover:bg-gray-100 rounded-lg"
                  >
                    <UserPlus className="h-4 w-4" />
                  </Button>
                </div>
                
                {/* Selected Recipients */}
                {recipients.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-3">
                    {recipients.map((recipient) => (
                      <Badge
                        key={recipient.id}
                        variant="secondary"
                        className="flex items-center space-x-1 bg-gradient-to-r from-purple-100 to-purple-50 text-purple-800 border border-purple-200/60 px-3 py-1.5"
                      >
                        <span>{recipient.full_name}</span>
                        <button
                          onClick={() => removeRecipient(recipient.id)}
                          className="ml-1 hover:text-red-600 transition-colors"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}

                {/* User Dropdown */}
                {showUserDropdown && searchTerm && (
                  <div className="absolute z-10 w-full mt-2 bg-white/95 backdrop-blur-md border border-gray-200/60 rounded-xl shadow-xl max-h-60 overflow-y-auto animate-fade-scale">
                    {filteredUsers.map((user) => (
                      <button
                        key={user.id}
                        onClick={() => addRecipient(user)}
                        className="w-full px-4 py-3 text-left hover:bg-gray-50/80 flex items-center justify-between transition-all first:rounded-t-xl last:rounded-b-xl"
                      >
                        <div>
                          <div className="font-semibold text-gray-900">{user.full_name}</div>
                          <div className="text-sm text-gray-500">{user.email}</div>
                        </div>
                        <Badge variant="outline" className="text-xs bg-gray-50">
                          {user.role}
                        </Badge>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Subject */}
            <div>
              <Label htmlFor="subject" className="text-sm font-medium text-gray-700 mb-2 block">
                Subject
              </Label>
              <Input
                id="subject"
                placeholder="Insert Subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400/50 transition-all shadow-sm hover:shadow-md"
              />
            </div>

            {/* Message */}
            <div>
              <Label htmlFor="message" className="text-sm font-medium text-gray-700 mb-2 block">
                Message <span className="text-red-500">*</span>
              </Label>
              <Textarea
                id="message"
                placeholder="Type your message here..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={6}
                className="bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400/50 transition-all shadow-sm hover:shadow-md resize-none"
              />
            </div>

            {/* Translation Option */}
            <div className="flex items-center space-x-2 p-3 bg-gray-50/50 rounded-xl">
              <button
                onClick={() => setIncludeTranslation(!includeTranslation)}
                className={`h-5 w-5 rounded-full border-2 flex items-center justify-center transition-all ${
                  includeTranslation 
                    ? 'bg-gradient-to-br from-green-500 to-green-600 border-green-600 text-white shadow-sm' 
                    : 'border-gray-300 hover:border-gray-400'
                }`}
              >
                {includeTranslation && <Check className="h-3 w-3" />}
              </button>
              <Label className="text-sm text-gray-700 cursor-pointer">
                Include translated version of this message
              </Label>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between p-6 border-t border-gray-200/60 bg-gray-50/50 flex-shrink-0">
            <div className="flex items-center space-x-3">
              <Button variant="ghost" size="sm" className="h-9 w-9 p-0 hover:bg-gray-100 rounded-lg">
                <Paperclip className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="sm" className="h-9 w-9 p-0 hover:bg-gray-100 rounded-lg">
                <Music className="h-4 w-4" />
              </Button>
            </div>
            
            <div className="flex items-center space-x-3">
              <Button
                variant="outline"
                onClick={onClose}
                disabled={sending}
                className="bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-gray-50/90 transition-all"
              >
                Cancel
              </Button>
              <Button
                onClick={handleSend}
                disabled={sending || !subject.trim() || !message.trim() || recipients.length === 0}
                className="btn-gradient-purple text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
              >
                {sending ? 'Sending...' : 'Send'}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
