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

  // Mark message as read when selected
  useEffect(() => {
    if (!selectedMessage) return

    const isAlreadyRead = currentUser.role === 'professor'
      ? selectedMessage.professor_read
      : selectedMessage.student_read

    if (!isAlreadyRead) {
      markAsRead(selectedMessage.id)
    }
  }, [selectedMessage?.id])

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
        isMe: message.professor_id === currentUser.id
      }
    } else {
      return {
        name: message.professor?.full_name || 'Unknown Professor',
        email: message.professor?.email || '',
        isMe: message.student_id === currentUser.id
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
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl mx-4 h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-6 border-b flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-900 flex items-center">
            <MessageSquare className="h-5 w-5 mr-2" />
            Messages
          </h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-5 w-5 text-gray-500" />
          </Button>
        </div>

        <div className="flex-1 flex flex-col">
            {selectedMessage ? (
              <>
                {/* Message Header */}
                <div className="p-6 border-b">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-lg font-semibold text-gray-900">
                        {selectedMessage.subject}
                      </h3>
                      <div className="flex items-center space-x-4 mt-2 text-sm text-gray-600">
                        <div className="flex items-center">
                          <User className="h-4 w-4 mr-1" />
                          {getSenderInfo(selectedMessage).isMe ? 'You' : getSenderInfo(selectedMessage).name}
                        </div>
                        <div className="flex items-center">
                          <Calendar className="h-4 w-4 mr-1" />
                          {formatDate(selectedMessage.created_at)}
                        </div>
                        {selectedMessage.cohort && (
                          <div className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs">
                            {selectedMessage.cohort.course_code}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex space-x-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => fetchMessageThread(selectedMessage.id)}
                      >
                        <Reply className="h-4 w-4 mr-1" />
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
                        >
                          <Reply className="h-4 w-4 mr-1" />
                          Reply
                        </Button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Message Content */}
                <div className="flex-1 p-6 overflow-y-auto">
                  <div className="prose max-w-none">
                    <p className="text-gray-800 whitespace-pre-wrap">
                      {selectedMessage.message}
                    </p>
                  </div>
                </div>

                {/* Reply Section */}
                {!getSenderInfo(selectedMessage).isMe && (
                  <div className="p-6 border-t">
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
                        />
                      </div>
                      <div className="flex justify-end">
                        <Button
                          type="submit"
                          disabled={replying || !replyMessage.trim()}
                          className="bg-blue-600 hover:bg-blue-700"
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
                  <MessageSquare className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                  <p>Select a message to view</p>
                </div>
              </div>
            )}
          </div>

        {/* Thread Modal */}
        {showThread && threadData && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-60">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl mx-4 h-[70vh] flex flex-col">
              <div className="p-6 border-b flex items-center justify-between">
                <h3 className="text-lg font-semibold">Message Thread</h3>
                <Button variant="ghost" size="icon" onClick={() => setShowThread(false)}>
                  <X className="h-5 w-5 text-gray-500" />
                </Button>
              </div>
              <div className="flex-1 overflow-y-auto p-6">
                <div className="space-y-6">
                  {/* Original Message */}
                  <div className="border-l-4 border-blue-500 pl-4">
                    <div className="flex items-center space-x-2 mb-2">
                      <span className="font-medium text-sm text-gray-900">
                        {getSenderInfo(threadData).name}
                      </span>
                      <span className="text-xs text-gray-500">
                        {formatDate(threadData.created_at)}
                      </span>
                    </div>
                    <h4 className="font-semibold text-gray-900 mb-2">{threadData.subject}</h4>
                    <p className="text-gray-700 whitespace-pre-wrap">{threadData.message}</p>
                  </div>

                  {/* Replies */}
                  {threadData.replies.map((reply) => {
                    const replySenderInfo = getSenderInfo(reply)
                    return (
                      <div key={reply.id} className="border-l-4 border-gray-300 pl-4 ml-4">
                        <div className="flex items-center space-x-2 mb-2">
                          <span className="font-medium text-sm text-gray-900">
                            {replySenderInfo.name}
                          </span>
                          <span className="text-xs text-gray-500">
                            {formatDate(reply.created_at)}
                          </span>
                        </div>
                        <p className="text-gray-700 whitespace-pre-wrap">{reply.message}</p>
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
