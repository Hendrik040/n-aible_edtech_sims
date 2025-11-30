"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { X, Reply, Send, User, Calendar, MessageSquare } from "lucide-react"
import { apiClient } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"

interface MessageViewerModalProps {
  isOpen: boolean
  onClose: () => void
  currentUser: any
}

interface Message {
  id: number
  professor_id: number
  student_id: number
  subject: string
  message: string
  message_type: string
  professor_read: boolean
  student_read: boolean
  created_at: string
  professor: {
    id: number
    full_name: string
    email: string
  }
  student: {
    id: number
    full_name: string
    email: string
  }
  cohort?: {
    id: number
    title: string
    course_code: string
  }
  replies: Message[]
}

export default function MessageViewerModal({ isOpen, onClose, currentUser }: MessageViewerModalProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [selectedMessage, setSelectedMessage] = useState<Message | null>(null)
  const [showThread, setShowThread] = useState(false)
  const [threadData, setThreadData] = useState<Message | null>(null)
  const [replyMessage, setReplyMessage] = useState("")
  const [replying, setReplying] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isOpen) {
      fetchMessages()
    }
  }, [isOpen])

  const fetchMessages = async () => {
    try {
      setLoading(true)
      const data = await apiClient.getMessages(50, 0)
      setMessages(data || [])
      
      // Auto-select the first message if none is selected
      if (data && data.length > 0 && !selectedMessage) {
        setSelectedMessage(data[0])
      }
    } catch (error) {
      console.error('Error fetching messages:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchMessageThread = async (messageId: number) => {
    try {
      const data = await apiClient.getMessageThread(messageId)
      setThreadData(data)
      setShowThread(true)
    } catch (error) {
      console.error('Error fetching message thread:', error)
    }
  }

  const handleReply = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedMessage || !replyMessage.trim()) return

    try {
      setReplying(true)
      await apiClient.replyToMessage(selectedMessage.id, replyMessage)
      setReplyMessage("")
      
      // Refresh the thread
      await fetchMessageThread(selectedMessage.id)
      
      // Refresh messages list
      await fetchMessages()
    } catch (error) {
      console.error('Error replying to message:', error)
      alert('Failed to send reply.')
    } finally {
      setReplying(false)
    }
  }

  const markAsRead = async (messageId: number) => {
    try {
      await apiClient.markMessageRead(messageId)
      // Update local state
      setMessages(prev => prev.map(msg => 
        msg.id === messageId 
          ? { ...msg, [currentUser.role === 'professor' ? 'professor_read' : 'student_read']: true }
          : msg
      ))
    } catch (error) {
      console.error('Error marking message as read:', error)
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  const getSenderInfo = (message: Message) => {
    if (currentUser.role === 'professor') {
      return {
        name: message.student?.full_name || 'Unknown Student',
        email: message.student?.email || '',
        isMe: message.student_id === currentUser.id
      }
    } else {
      return {
        name: message.professor?.full_name || 'Unknown Professor',
        email: message.professor?.email || '',
        isMe: message.professor_id === currentUser.id
      }
    }
  }

  const isUnread = (message: Message) => {
    if (currentUser.role === 'professor') {
      return !message.professor_read
    } else {
      return !message.student_read
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-scale">
      <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-4xl mx-4 h-[80vh] flex flex-col border border-gray-200/60 animate-scale-in">
        {/* Header */}
        <div className="p-6 border-b border-gray-200/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-slate-100 to-slate-50 rounded-xl flex items-center justify-center shadow-sm">
              <MessageSquare className="h-5 w-5 text-slate-600" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 tracking-tight">Messages</h2>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} className="hover:bg-gray-100 rounded-lg">
            <X className="h-5 w-5 text-gray-500" />
          </Button>
        </div>

        <div className="flex-1 flex flex-col overflow-hidden">
            {selectedMessage ? (
              <>
                {/* Message Header */}
                <div className="p-6 border-b border-gray-200/60 bg-gray-50/30">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-gray-900 mb-2">
                        {selectedMessage.subject}
                      </h3>
                      <div className="flex items-center space-x-4 mt-2 text-sm text-gray-600">
                        <div className="flex items-center gap-1.5">
                          <User className="h-4 w-4" />
                          {getSenderInfo(selectedMessage).isMe ? 'You' : getSenderInfo(selectedMessage).name}
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Calendar className="h-4 w-4" />
                          {formatDate(selectedMessage.created_at)}
                        </div>
                        {selectedMessage.cohort && (
                          <div className="bg-gradient-to-r from-slate-100 to-slate-50 text-slate-800 px-2.5 py-1 rounded-lg text-xs font-medium border border-slate-200/60">
                            {selectedMessage.cohort.course_code}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex space-x-2 ml-4">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => fetchMessageThread(selectedMessage.id)}
                        className="bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-gray-50/90 transition-all"
                      >
                        <Reply className="h-4 w-4 mr-1.5" />
                        View Thread
                      </Button>
                      {!getSenderInfo(selectedMessage).isMe && (
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => {
                            // Focus on reply textarea
                            const textarea = document.getElementById('reply-message')
                            if (textarea) {
                              textarea.focus()
                            }
                          }}
                          className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                        >
                          <Reply className="h-4 w-4 mr-1.5" />
                          Reply
                        </Button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Message Content */}
                <div className="flex-1 p-6 overflow-y-auto bg-white/50">
                  <div className="prose max-w-none">
                    <p className="text-gray-800 whitespace-pre-wrap leading-relaxed">
                      {selectedMessage.message}
                    </p>
                  </div>
                </div>

                {/* Reply Section */}
                {!getSenderInfo(selectedMessage).isMe && (
                  <div className="p-6 border-t border-gray-200/60 bg-gray-50/30">
                    <form onSubmit={handleReply} className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Reply
                        </label>
                        <Textarea
                          id="reply-message"
                          value={replyMessage}
                          onChange={(e) => setReplyMessage(e.target.value)}
                          placeholder="Type your reply..."
                          rows={3}
                          required
                          className="bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md resize-none"
                        />
                      </div>
                      <div className="flex justify-end">
                        <Button
                          type="submit"
                          disabled={replying || !replyMessage.trim()}
                          className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                        >
                          {replying ? (
                            <>
                              <Send className="h-4 w-4 mr-2 animate-spin" />
                              Sending...
                            </>
                          ) : (
                            <>
                              <Send className="h-4 w-4 mr-2" />
                              Send Reply
                            </>
                          )}
                        </Button>
                      </div>
                    </form>
                  </div>
                )}
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-gray-500">
                <div className="text-center">
                  <div className="w-16 h-16 bg-gradient-to-br from-gray-100 to-gray-50 rounded-xl flex items-center justify-center mx-auto mb-4 shadow-sm">
                    <MessageSquare className="h-8 w-8 text-gray-400" />
                  </div>
                  <p className="text-gray-600 font-medium">Select a message to view</p>
                </div>
              </div>
            )}
          </div>

        {/* Thread Modal */}
        {showThread && threadData && (
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-60 animate-fade-scale">
            <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-3xl mx-4 h-[70vh] flex flex-col border border-gray-200/60 animate-scale-in">
              <div className="p-6 border-b border-gray-200/60 flex items-center justify-between bg-gray-50/30">
                <h3 className="text-lg font-bold text-gray-900 tracking-tight">Message Thread</h3>
                <Button variant="ghost" size="icon" onClick={() => setShowThread(false)} className="hover:bg-gray-100 rounded-lg">
                  <X className="h-5 w-5 text-gray-500" />
                </Button>
              </div>
              <div className="flex-1 overflow-y-auto p-6 bg-white/50">
                <div className="space-y-6">
                  {/* Original Message */}
                  <div className="border-l-4 border-blue-500 pl-4 animate-fade-scale">
                    <div className="flex items-center space-x-2 mb-2">
                      <span className="font-semibold text-sm text-gray-900">
                        {getSenderInfo(threadData).name}
                      </span>
                      <span className="text-xs text-gray-500">
                        {formatDate(threadData.created_at)}
                      </span>
                    </div>
                    <h4 className="font-bold text-gray-900 mb-2">{threadData.subject}</h4>
                    <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">{threadData.message}</p>
                  </div>

                  {/* Replies */}
                  {threadData.replies.map((reply) => {
                    const replySenderInfo = getSenderInfo(reply)
                    return (
                      <div key={reply.id} className="border-l-4 border-gray-300 pl-4 ml-4 animate-fade-scale">
                        <div className="flex items-center space-x-2 mb-2">
                          <span className="font-semibold text-sm text-gray-900">
                            {replySenderInfo.name}
                          </span>
                          <span className="text-xs text-gray-500">
                            {formatDate(reply.created_at)}
                          </span>
                        </div>
                        <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">{reply.message}</p>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
