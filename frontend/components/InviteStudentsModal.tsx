"use client"

import { useState, useRef, KeyboardEvent, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { X, Mail, User } from "lucide-react"
import { apiClient } from "@/lib/api"

interface InviteStudentsModalProps {
  isOpen: boolean
  onClose: () => void
  cohortId: number
  cohortTitle: string
  onSuccess?: () => void
}

interface EmailPill {
  id: string
  email: string
}

interface Student {
  id: number
  full_name: string
  email: string
  role: string
}

export default function InviteStudentsModal({
  isOpen,
  onClose,
  cohortId,
  cohortTitle,
  onSuccess
}: InviteStudentsModalProps) {
  const [emailPills, setEmailPills] = useState<EmailPill[]>([])
  const [emailInput, setEmailInput] = useState("")
  const [personalMessage, setPersonalMessage] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  
  // Autocomplete state
  const [allStudents, setAllStudents] = useState<Student[]>([])
  const [filteredStudents, setFilteredStudents] = useState<Student[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Fetch all students when modal opens
  useEffect(() => {
    if (isOpen) {
      fetchStudents()
    }
  }, [isOpen])

  // Filter students based on input
  useEffect(() => {
    if (emailInput.trim().length > 0) {
      const searchTerm = emailInput.toLowerCase().trim()
      const filtered = allStudents.filter((student) => {
        // Only show students
        if (student.role !== 'student') return false
        
        // Check if already added
        if (emailPills.some(pill => pill.email === student.email)) return false
        
        // Filter by name or email
        return (
          student.full_name.toLowerCase().includes(searchTerm) ||
          student.email.toLowerCase().includes(searchTerm)
        )
      })
      setFilteredStudents(filtered.slice(0, 5)) // Show max 5 suggestions
      setShowDropdown(filtered.length > 0)
      setSelectedIndex(-1)
    } else {
      setShowDropdown(false)
      setFilteredStudents([])
      setSelectedIndex(-1)
    }
  }, [emailInput, allStudents, emailPills])

  // Handle click outside dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false)
      }
    }

    if (showDropdown) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showDropdown])

  const fetchStudents = async () => {
    try {
      const users = await apiClient.getUsers()
      setAllStudents(users)
    } catch (err) {
      // Silently fail - user can still manually enter emails
    }
  }

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    return emailRegex.test(email)
  }

  const addEmailPill = (email: string) => {
    const trimmedEmail = email.trim().toLowerCase()
    
    if (!trimmedEmail) return
    
    if (!validateEmail(trimmedEmail)) {
      setError("Please enter a valid email address")
      return
    }
    
    if (emailPills.some(pill => pill.email === trimmedEmail)) {
      setError("This email has already been added")
      return
    }
    
    const newPill: EmailPill = {
      id: Date.now().toString(),
      email: trimmedEmail
    }
    
    setEmailPills([...emailPills, newPill])
    setEmailInput("")
    setError(null)
  }

  const removeEmailPill = (id: string) => {
    setEmailPills(emailPills.filter(pill => pill.id !== id))
  }

  const selectStudent = (student: Student) => {
    addEmailPill(student.email)
    setShowDropdown(false)
    setSelectedIndex(-1)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (showDropdown && filteredStudents.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedIndex((prev) => 
          prev < filteredStudents.length - 1 ? prev + 1 : prev
        )
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedIndex((prev) => (prev > 0 ? prev - 1 : -1))
      } else if (e.key === "Enter") {
        e.preventDefault()
        if (selectedIndex >= 0 && selectedIndex < filteredStudents.length) {
          selectStudent(filteredStudents[selectedIndex])
        } else {
          addEmailPill(emailInput)
        }
      } else if (e.key === "Escape") {
        setShowDropdown(false)
        setSelectedIndex(-1)
      }
    } else if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      addEmailPill(emailInput)
    } else if (e.key === "Backspace" && emailInput === "" && emailPills.length > 0) {
      // Remove last pill if input is empty and backspace is pressed
      const lastPill = emailPills[emailPills.length - 1]
      removeEmailPill(lastPill.id)
    }
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault()
    const pastedText = e.clipboardData.getData("text")
    const emails = pastedText.split(/[,\n\s]+/).filter(email => email.trim())
    
    emails.forEach(email => {
      if (email.trim()) {
        addEmailPill(email.trim())
      }
    })
  }

  const handleSendInvites = async () => {
    if (emailPills.length === 0) {
      setError("Please add at least one email address")
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      const invitations = emailPills.map(pill => ({
        email: pill.email,
        message: personalMessage.trim() || undefined
      }))

      await apiClient.inviteStudentsToCohort(cohortId, invitations)
      
      // Reset form
      setEmailPills([])
      setEmailInput("")
      setPersonalMessage("")
      
      onSuccess?.()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send invitations")
    } finally {
      setIsLoading(false)
    }
  }

  const handleClose = () => {
    if (!isLoading) {
      setEmailPills([])
      setEmailInput("")
      setPersonalMessage("")
      setError(null)
      setShowDropdown(false)
      setSelectedIndex(-1)
      setFilteredStudents([])
      onClose()
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-scale">
      <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-md mx-4 border border-gray-200/60 animate-scale-in">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200/60">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center shadow-sm">
              <Mail className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900 tracking-tight">
                Invite Students
              </h2>
              <p className="text-sm text-gray-600 mt-0.5">to {cohortTitle}</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={isLoading}
            className="text-gray-400 hover:text-gray-600 disabled:opacity-50 transition-colors p-1.5 hover:bg-gray-100 rounded-lg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5">
          <p className="text-sm text-gray-600 leading-relaxed">
            Send email invitations to students to join this cohort.
          </p>

          {/* Email Input */}
          <div className="space-y-2 relative">
            <label className="text-sm font-medium text-gray-700">
              Email Addresses
            </label>
            <div className="min-h-[40px] border border-gray-200/80 rounded-xl p-3 flex flex-wrap gap-2 bg-white/80 backdrop-blur-sm focus-within:ring-2 focus-within:ring-green-500/20 focus-within:border-green-400/50 transition-all shadow-sm hover:shadow-md">
              {/* Email Pills */}
              {emailPills.map((pill) => (
                <div
                  key={pill.id}
                  className="inline-flex items-center gap-1.5 bg-gradient-to-r from-green-100 to-green-50 text-green-800 px-3 py-1.5 rounded-lg text-sm font-medium shadow-sm border border-green-200/60 animate-fade-scale"
                >
                  <Mail className="h-3.5 w-3.5" />
                  <span>{pill.email}</span>
                  <button
                    onClick={() => removeEmailPill(pill.id)}
                    disabled={isLoading}
                    className="text-green-700 hover:text-green-900 disabled:opacity-50 transition-colors ml-0.5"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
              
              {/* Input */}
              <input
                ref={inputRef}
                type="email"
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onPaste={handlePaste}
                placeholder={emailPills.length === 0 ? "Type a name or email to search..." : ""}
                disabled={isLoading}
                className="flex-1 min-w-[200px] border-none outline-none text-sm placeholder-gray-400 bg-transparent disabled:opacity-50"
              />
            </div>
            
            {/* Autocomplete Dropdown */}
            {showDropdown && filteredStudents.length > 0 && (
              <div
                ref={dropdownRef}
                className="absolute z-50 w-full mt-2 bg-white/95 backdrop-blur-md border border-gray-200/60 rounded-xl shadow-xl max-h-60 overflow-y-auto animate-fade-scale"
              >
                {filteredStudents.map((student, index) => (
                  <div
                    key={student.id}
                    onClick={() => selectStudent(student)}
                    className={`px-4 py-3 cursor-pointer flex items-center gap-3 transition-all ${
                      index === selectedIndex
                        ? 'bg-gradient-to-r from-green-50 to-green-100/50 border-l-2 border-green-500'
                        : 'hover:bg-gray-50/80'
                    }`}
                  >
                    <div className="flex items-center justify-center w-9 h-9 rounded-full bg-gradient-to-br from-gray-100 to-gray-50 shadow-sm">
                      <User className="h-4 w-4 text-gray-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-gray-900 truncate">
                        {student.full_name}
                      </p>
                      <p className="text-xs text-gray-500 truncate">
                        {student.email}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
            
            {error && (
              <p className="text-sm text-red-600 animate-fade-scale">{error}</p>
            )}
          </div>

          {/* Personal Message */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700">
              Personal Message (Optional)
            </label>
            <Textarea
              value={personalMessage}
              onChange={(e) => setPersonalMessage(e.target.value)}
              placeholder="Add a personal message to your invitation..."
              disabled={isLoading}
              rows={3}
              className="resize-none bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-green-500/20 focus:border-green-400/50 transition-all shadow-sm hover:shadow-md"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 p-6 border-t border-gray-200/60 bg-gray-50/50">
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={isLoading}
            className="bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-gray-50/90 transition-all"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSendInvites}
            disabled={isLoading || emailPills.length === 0}
            className="btn-gradient-green text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
          >
            {isLoading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                Sending...
              </>
            ) : (
              <>
                <Mail className="h-4 w-4 mr-2" />
                Send Invites
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
