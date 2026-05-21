"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { X, Copy, Check, Link2, Users, Calendar, Clock, AlertCircle, Plus, Trash2, Trash } from "lucide-react"
import { apiClient } from "@/lib/api"

interface InviteLinkModalProps {
  isOpen: boolean
  onClose: () => void
  cohortId: number
  cohortTitle: string
}

interface InviteLink {
  invite_id: number
  invite_url: string
  token: string
  invite_type: "SINGLE_USE" | "MULTI_USE"
  max_uses: number | null
  uses_count: number
  uses_left: number | null
  expires_at: string
  created_at: string
  is_expired: boolean
  is_used_up: boolean
  status: "active" | "expired" | "used"
}

export default function InviteLinkModal({
  isOpen,
  onClose,
  cohortId,
  cohortTitle
}: InviteLinkModalProps) {
  const [inviteLinks, setInviteLinks] = useState<InviteLink[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [inviteType, setInviteType] = useState<"SINGLE_USE" | "MULTI_USE">("MULTI_USE")
  const [maxUses, setMaxUses] = useState<string>("")
  const [expiresInDays, setExpiresInDays] = useState<string>("")
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [clearingExpired, setClearingExpired] = useState(false)

  // Load invite links when modal opens
  useEffect(() => {
    if (isOpen) {
      loadInviteLinks()
      setShowCreateForm(false)
    }
  }, [isOpen, cohortId])

  const loadInviteLinks = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await apiClient.getInviteLinks(cohortId)
      setInviteLinks(data.invites || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load invite links")
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    setIsGenerating(true)
    setError(null)
    
    try {
      const inviteData: any = {
        type: inviteType,
      }
      if (expiresInDays) {
        const days = parseInt(expiresInDays, 10)
        if (!Number.isFinite(days) || days < 1 || days > 90) {
          setError("Expiry must be between 1 and 90 days")
          setIsGenerating(false)
          return
        }
        inviteData.expires_in_days = days
      }
      
      if (inviteType === "MULTI_USE" && maxUses) {
        const uses = parseInt(maxUses)
        if (uses < 1) {
          setError("Max uses must be at least 1")
          setIsGenerating(false)
          return
        }
        inviteData.max_uses = uses
      }
      
      await apiClient.generateInviteLink(cohortId, inviteData)
      
      // Reset form and reload links
      setInviteType("MULTI_USE")
      setMaxUses("")
      setExpiresInDays("")
      setShowCreateForm(false)
      await loadInviteLinks()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate invite link")
    } finally {
      setIsGenerating(false)
    }
  }

  const handleCopy = async (inviteUrl: string, inviteId: number) => {
    try {
      await navigator.clipboard.writeText(inviteUrl)
      setCopiedId(inviteId)
      setTimeout(() => setCopiedId(null), 2000)
    } catch (err) {
      setError("Failed to copy link to clipboard")
    }
  }

  const handleDelete = async (inviteId: number) => {
    if (!confirm("Are you sure you want to delete this invite link? This action cannot be undone.")) {
      return
    }

    try {
      setDeletingId(inviteId)
      setError(null)
      await apiClient.deleteInviteLink(cohortId, inviteId)
      // Reload the list
      await loadInviteLinks()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete invite link")
    } finally {
      setDeletingId(null)
    }
  }

  const handleClearExpired = async () => {
    const expiredCount = inviteLinks.filter(inv => inv.is_expired || inv.is_used_up).length
    
    if (expiredCount === 0) {
      setError("No expired or used invite links to clear")
      return
    }

    if (!confirm(`Are you sure you want to delete ${expiredCount} expired or used invite link(s)? This action cannot be undone.`)) {
      return
    }

    try {
      setClearingExpired(true)
      setError(null)
      const result = await apiClient.clearExpiredInviteLinks(cohortId)
      // Reload the list
      await loadInviteLinks()
      // Show success message
      if (result.deleted_count > 0) {
        setError(null) // Clear any previous errors
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear expired invite links")
    } finally {
      setClearingExpired(false)
    }
  }

  const getStatusBadge = (invite: InviteLink) => {
    if (invite.is_expired) {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
          <Clock className="h-3 w-3 mr-1" />
          Expired
        </span>
      )
    }
    if (invite.is_used_up) {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">
          <AlertCircle className="h-3 w-3 mr-1" />
          Used Up
        </span>
      )
    }
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
        <Check className="h-3 w-3 mr-1" />
        Active
      </span>
    )
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-scale overflow-y-auto">
      <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-3xl mx-4 my-8 border border-gray-200/60 animate-scale-in max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200/60 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center shadow-sm">
              <Link2 className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-gray-900 tracking-tight">Invite Links</h2>
              <p className="text-sm text-gray-600">{cohortTitle}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors p-1.5 hover:bg-gray-100 rounded-lg"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Header Section */}
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold text-gray-900">
              {inviteLinks.length > 0 ? "Existing Invite Links" : "No invite links yet"}
            </h3>
            <div className="flex items-center gap-2">
              {/* Clear Expired Button - Only show if there are expired/used links */}
              {inviteLinks.length > 0 && inviteLinks.some(inv => inv.is_expired || inv.is_used_up) && (
                <Button
                  onClick={handleClearExpired}
                  disabled={clearingExpired}
                  variant="outline"
                  className="text-red-600 border-red-200 hover:bg-red-50 hover:border-red-300 transition-all text-sm font-medium"
                  size="sm"
                >
                  {clearingExpired ? (
                    <>
                      <div className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-red-600 mr-2"></div>
                      Clearing...
                    </>
                  ) : (
                    <>
                      <Trash className="h-3.5 w-3.5 mr-1.5" />
                      Clear Expired/Used
                    </>
                  )}
                </Button>
              )}
              <Button
                onClick={() => {
                  setShowCreateForm(!showCreateForm)
                  setError(null)
                }}
                className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold text-sm"
              >
                <Plus className="h-4 w-4 mr-2" />
                {showCreateForm ? "Cancel" : "Create New"}
              </Button>
            </div>
          </div>

          {/* Create Form */}
          {showCreateForm && (
            <div className="bg-gradient-to-br from-slate-50 to-slate-100/50 rounded-xl p-5 border border-gray-200/60 space-y-4">
              {/* Invite Type Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Invite Type
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setInviteType("SINGLE_USE")
                      setMaxUses("")
                    }}
                    className={`px-4 py-3 rounded-xl border-2 transition-all ${
                      inviteType === "SINGLE_USE"
                        ? "bg-blue-50 border-blue-400 text-blue-700 font-medium"
                        : "bg-white/80 border-gray-200 text-gray-600 hover:border-gray-300"
                    }`}
                  >
                    <div className="text-sm font-medium mb-1">Single Use</div>
                    <div className="text-xs text-gray-500">One-time use link</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setInviteType("MULTI_USE")}
                    className={`px-4 py-3 rounded-xl border-2 transition-all ${
                      inviteType === "MULTI_USE"
                        ? "bg-blue-50 border-blue-400 text-blue-700 font-medium"
                        : "bg-white/80 border-gray-200 text-gray-600 hover:border-gray-300"
                    }`}
                  >
                    <div className="text-sm font-medium mb-1">Multi Use</div>
                    <div className="text-xs text-gray-500">Can be used multiple times</div>
                  </button>
                </div>
              </div>

              {/* Max Uses (for MULTI_USE) */}
              {inviteType === "MULTI_USE" && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Maximum Uses (Optional)
                  </label>
                  <Input
                    type="number"
                    value={maxUses}
                    onChange={(e) => setMaxUses(e.target.value)}
                    placeholder="Leave empty for unlimited"
                    className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all"
                    min="1"
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Leave empty for unlimited uses until expiration
                  </p>
                </div>
              )}

              {/* Expiration */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Expires In (Days)
                </label>
                <Input
                  type="number"
                  value={expiresInDays}
                  onChange={(e) => setExpiresInDays(e.target.value)}
                  placeholder="Leave empty for no expiry"
                  className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all"
                  min="1"
                  max="90"
                />
                <p className="text-xs text-gray-500 mt-1">
                  Leave empty for no expiry, or enter 1-90 days
                </p>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                  <p className="text-sm text-red-700">{error}</p>
                </div>
              )}

              {/* Generate Button */}
              <Button
                onClick={handleGenerate}
                disabled={isGenerating}
                className="w-full btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
              >
                {isGenerating ? "Generating..." : "Generate Invite Link"}
              </Button>
            </div>
          )}

          {/* Invite Links List */}
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
            </div>
          ) : inviteLinks.length > 0 ? (
            <div className="bg-gray-50/50 rounded-xl border border-gray-200/60 p-4 max-h-[400px] overflow-y-auto">
              <div className="space-y-3">
                {inviteLinks.map((invite) => (
                <div
                  key={invite.invite_id}
                  className="bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl p-5 hover:shadow-md transition-all"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-3">
                          {getStatusBadge(invite)}
                          <span className="text-xs text-gray-500 font-medium">
                            {invite.invite_type === "SINGLE_USE" ? "Single Use" : "Multi Use"}
                          </span>
                        </div>
                        <Button
                          onClick={() => handleDelete(invite.invite_id)}
                          disabled={deletingId === invite.invite_id}
                          variant="ghost"
                          size="sm"
                          className="text-red-600 hover:text-red-700 hover:bg-red-50 h-8 w-8 p-0"
                          title="Delete invite link"
                        >
                          {deletingId === invite.invite_id ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-red-600"></div>
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </Button>
                      </div>
                      
                      {/* Invite URL */}
                      <div className="flex gap-2 mb-3">
                        <Input
                          value={invite.invite_url}
                          readOnly
                          className="flex-1 bg-gray-50 border-gray-200 text-gray-700 font-mono text-xs"
                        />
                        <Button
                          onClick={() => handleCopy(invite.invite_url, invite.invite_id)}
                          className="bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
                          size="sm"
                        >
                          {copiedId === invite.invite_id ? (
                            <Check className="h-4 w-4" />
                          ) : (
                            <Copy className="h-4 w-4" />
                          )}
                        </Button>
                      </div>

                      {/* Details Grid */}
                      <div className="grid grid-cols-3 gap-3 text-sm">
                        <div className="flex items-center gap-2">
                          <Users className="h-4 w-4 text-gray-400" />
                          <div>
                            <p className="text-xs text-gray-500">Uses</p>
                            <p className="font-medium text-gray-900">
                              {invite.invite_type === "SINGLE_USE" 
                                ? `${invite.uses_count}/1`
                                : invite.max_uses === null
                                  ? `${invite.uses_count}/∞`
                                  : `${invite.uses_count}/${invite.max_uses}`}
                            </p>
                            {invite.invite_type === "MULTI_USE" && invite.uses_left !== null && (
                              <p className="text-xs text-gray-500 mt-0.5">
                                {invite.uses_left === 0 
                                  ? "No uses remaining" 
                                  : invite.uses_left === 1
                                    ? "1 use remaining"
                                    : `${invite.uses_left} uses remaining`}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Clock className="h-4 w-4 text-gray-400" />
                          <div>
                            <p className="text-xs text-gray-500">Expires</p>
                            <p className="font-medium text-gray-900 text-xs">
                              {new Date(invite.expires_at).getFullYear() >= 9999 ? "Never" : new Date(invite.expires_at).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Calendar className="h-4 w-4 text-gray-400" />
                          <div>
                            <p className="text-xs text-gray-500">Created</p>
                            <p className="font-medium text-gray-900 text-xs">
                              {new Date(invite.created_at).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              </div>
            </div>
          ) : !showCreateForm ? (
            <div className="text-center py-12">
              <Link2 className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-500 mb-4">No invite links created yet</p>
              <Button
                onClick={() => setShowCreateForm(true)}
                className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
              >
                <Plus className="h-4 w-4 mr-2" />
                Create First Invite Link
              </Button>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="flex justify-end p-6 border-t border-gray-200/60 bg-gray-50/50 flex-shrink-0">
          <Button
            onClick={onClose}
            className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
          >
            Done
          </Button>
        </div>
      </div>
    </div>
  )
}

