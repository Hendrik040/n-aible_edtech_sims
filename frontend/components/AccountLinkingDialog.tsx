"use client"

import React, { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { User, Mail, Shield, Link as LinkIcon, Plus } from 'lucide-react'
import { AccountLinkingData } from '@/lib/google-oauth'

interface AccountLinkingDialogProps {
  isOpen: boolean
  onClose: () => void
  linkingData: AccountLinkingData
  onLinkAccount: (action: 'link' | 'create_separate', role?: 'student' | 'professor') => Promise<void>
  isLoading?: boolean
}

export function AccountLinkingDialog({
  isOpen,
  onClose,
  linkingData,
  onLinkAccount,
  isLoading = false
}: AccountLinkingDialogProps) {
  const [selectedAction, setSelectedAction] = useState<'link' | 'create_separate' | null>(null)
  const [selectedRole, setSelectedRole] = useState<'student' | 'professor' | null>(null)

  const handleLink = async () => {
    if (selectedAction) {
      if (selectedAction === 'create_separate' && !selectedRole) {
        return // Don't proceed without role selection
      }
      console.log('AccountLinkingDialog: Calling onLinkAccount with:', {
        action: selectedAction,
        role: selectedRole,
        existingUserId: linkingData.existing_user.id
      })
      await onLinkAccount(selectedAction, selectedRole || undefined)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[95vw] max-w-4xl max-h-[90vh] overflow-y-auto bg-white/95 backdrop-blur-md border border-gray-200/60 rounded-2xl shadow-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3 text-xl font-bold tracking-tight">
            <div className="w-10 h-10 bg-gradient-to-br from-slate-100 to-slate-50 rounded-xl flex items-center justify-center shadow-sm">
              <Shield className="h-5 w-5 text-slate-600" />
            </div>
            Account Linking Required
          </DialogTitle>
          <DialogDescription className="text-gray-600 leading-relaxed">
            {linkingData.message}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Existing Account */}
          <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 bg-gradient-to-br from-slate-100 to-slate-50 rounded-xl flex items-center justify-center shadow-sm">
                  <User className="h-5 w-5 text-slate-600" />
                </div>
                <h3 className="text-lg font-bold text-gray-900 tracking-tight">Existing Account</h3>
              </div>
              <div className="space-y-3 pl-13">
                <div className="flex items-center gap-2">
                  <Mail className="h-4 w-4 text-gray-500" />
                  <span className="font-medium text-gray-900">{linkingData.existing_user.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4 text-gray-500" />
                  <span className="text-gray-700">{linkingData.existing_user.full_name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="bg-gray-50 border-gray-200/60">
                    {linkingData.existing_user.provider === 'password' ? 'Email/Password' : 'Google OAuth'}
                  </Badge>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Google Account */}
          <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md">
            <CardContent className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center shadow-sm">
                  <img src="/google-icon.svg" alt="Google" className="h-5 w-5" />
                </div>
                <h3 className="text-lg font-bold text-gray-900 tracking-tight">Google Account</h3>
              </div>
              <div className="space-y-3 pl-13">
                <div className="flex items-center gap-2">
                  <Mail className="h-4 w-4 text-gray-500" />
                  <span className="font-medium text-gray-900">{linkingData.google_data.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4 text-gray-500" />
                  <span className="text-gray-700">{linkingData.google_data.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="bg-blue-50 border-blue-200/60 text-blue-800">Google OAuth</Badge>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Action Selection */}
          <div className="space-y-4">
            <h3 className="font-semibold text-gray-900">Choose an option:</h3>
            
            <div className="space-y-3">
              {/* Link Accounts Option */}
              <Card 
                className={`cursor-pointer transition-all duration-200 ${
                  selectedAction === 'link' 
                    ? 'ring-2 ring-slate-500 bg-gradient-to-br from-slate-50 to-slate-100/50 shadow-lg border-slate-300' 
                    : 'hover:bg-gray-50/80 border-gray-200/60'
                } card-elevated rounded-xl`}
                onClick={() => setSelectedAction('link')}
              >
                <CardContent className="p-5">
                  <div className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="action"
                      value="link"
                      checked={selectedAction === 'link'}
                      onChange={() => setSelectedAction('link')}
                      className="h-4 w-4 text-slate-600 focus:ring-slate-500 cursor-pointer"
                    />
                    <div className="w-8 h-8 bg-gradient-to-br from-slate-100 to-slate-50 rounded-lg flex items-center justify-center shadow-sm">
                      <LinkIcon className="h-4 w-4 text-slate-600" />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900 mb-1">Link Google Account</h4>
                      <p className="text-sm text-gray-600 leading-relaxed">
                        Connect your Google account to your existing account. You'll be able to sign in with either method.
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Create Separate Account Option */}
              <Card 
                className={`cursor-pointer transition-all duration-200 ${
                  selectedAction === 'create_separate' 
                    ? 'ring-2 ring-green-500 bg-gradient-to-br from-green-50 to-green-100/50 shadow-lg border-green-300' 
                    : 'hover:bg-gray-50/80 border-gray-200/60'
                } card-elevated rounded-xl`}
                onClick={() => setSelectedAction('create_separate')}
              >
                <CardContent className="p-5">
                  <div className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="action"
                      value="create_separate"
                      checked={selectedAction === 'create_separate'}
                      onChange={() => setSelectedAction('create_separate')}
                      className="h-4 w-4 text-green-600 focus:ring-green-500 cursor-pointer"
                    />
                    <div className="w-8 h-8 bg-gradient-to-br from-green-100 to-green-50 rounded-lg flex items-center justify-center shadow-sm">
                      <Plus className="h-4 w-4 text-green-600" />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-semibold text-gray-900 mb-1">Create Separate Account</h4>
                      <p className="text-sm text-gray-600 leading-relaxed">
                        Create a new account with your Google credentials. Your existing account will remain separate.
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>

          {/* Role Selection for Separate Account */}
          {selectedAction === 'create_separate' && (
            <div className="space-y-4 animate-fade-scale">
              <h3 className="font-semibold text-gray-900">Choose your role for the new account:</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Student Role */}
                <Card 
                  className={`cursor-pointer transition-all duration-200 ${
                    selectedRole === 'student' 
                      ? 'ring-2 ring-blue-500 bg-gradient-to-br from-blue-50 to-blue-100/50 shadow-lg border-blue-300' 
                      : 'hover:bg-gray-50/80 border-gray-200/60'
                  } card-elevated rounded-xl`}
                  onClick={() => setSelectedRole('student')}
                >
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3">
                      <input
                        type="radio"
                        name="role"
                        value="student"
                        checked={selectedRole === 'student'}
                        onChange={() => setSelectedRole('student')}
                        className="h-4 w-4 text-blue-600 focus:ring-blue-500 cursor-pointer"
                      />
                      <div className="flex-1">
                        <h4 className="font-semibold text-gray-900 mb-1">Student</h4>
                        <p className="text-sm text-gray-600 leading-relaxed">
                          Join cohorts and participate in simulations
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Professor Role */}
                <Card 
                  className={`cursor-pointer transition-all duration-200 ${
                    selectedRole === 'professor' 
                      ? 'ring-2 ring-purple-500 bg-gradient-to-br from-purple-50 to-purple-100/50 shadow-lg border-purple-300' 
                      : 'hover:bg-gray-50/80 border-gray-200/60'
                  } card-elevated rounded-xl`}
                  onClick={() => setSelectedRole('professor')}
                >
                  <CardContent className="p-5">
                    <div className="flex items-center gap-3">
                      <input
                        type="radio"
                        name="role"
                        value="professor"
                        checked={selectedRole === 'professor'}
                        onChange={() => setSelectedRole('professor')}
                        className="h-4 w-4 text-purple-600 focus:ring-purple-500 cursor-pointer"
                      />
                      <div className="flex-1">
                        <h4 className="font-semibold text-gray-900 mb-1">Professor</h4>
                        <p className="text-sm text-gray-600 leading-relaxed">
                          Create cohorts and design simulations
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200/60">
            <Button variant="outline" onClick={onClose} disabled={isLoading} className="bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-gray-50/90 transition-all">
              Cancel
            </Button>
            <Button 
              onClick={handleLink} 
              disabled={!selectedAction || isLoading || (selectedAction === 'create_separate' && !selectedRole)}
              className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold min-w-[120px]"
            >
              {isLoading ? 'Processing...' : 'Continue'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
