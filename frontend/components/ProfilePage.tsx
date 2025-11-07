"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient, User } from "@/lib/api"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { LogOut, RefreshCcw, ShieldCheck, User as UserIcon } from "lucide-react"

type ProfileRole = "student" | "professor"

interface ProfilePageProps {
  role: ProfileRole
}

interface ProfileFormState {
  full_name: string
  username: string
  bio: string
  avatar_url: string
  profile_public: boolean
  allow_contact: boolean
}

interface PasswordFormState {
  currentPassword: string
  newPassword: string
  confirmPassword: string
}

export function ProfilePage({ role }: ProfilePageProps) {
  const router = useRouter()
  const {
    user,
    isLoading: authLoading,
    logout,
    updateUser,
  } = useAuth()

  const [profileForm, setProfileForm] = useState<ProfileFormState>({
    full_name: "",
    username: "",
    bio: "",
    avatar_url: "",
    profile_public: false,
    allow_contact: false,
  })
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileMessage, setProfileMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)

  const [passwordForm, setPasswordForm] = useState<PasswordFormState>({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  })
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [passwordMessage, setPasswordMessage] = useState<{ type: "success" | "error"; text: string } | null>(null)

  const sidebarPath = role === "student" ? "/student/profile" : "/professor/profile"
  const heading = role === "student" ? "Student Profile" : "Professor Profile"
  const subtitle = role === "student"
    ? "Update your personal information and learning preferences."
    : "Manage your faculty details and platform preferences."

  const isProfessorUser = user?.role === "professor" || user?.role === "admin"
  const isStudentUser = user?.role === "student"

  // Sync local state with authenticated user
  useEffect(() => {
    if (!user) return

    setProfileForm({
      full_name: user.full_name || "",
      username: user.username || "",
      bio: user.bio || "",
      avatar_url: user.avatar_url || "",
      profile_public: user.profile_public ?? false,
      allow_contact: user.allow_contact ?? false,
    })
  }, [user])

  // Handle auth guards
  useEffect(() => {
    if (authLoading) return

    if (!user) {
      router.push("/")
      return
    }

    if (role === "student" && !isStudentUser) {
      router.push("/professor/dashboard")
    }

    if (role === "professor" && !isProfessorUser) {
      router.push("/student/dashboard")
    }
  }, [authLoading, isProfessorUser, isStudentUser, role, router, user])

  const handleLogout = async () => {
    try {
      await logout()
    } finally {
      router.replace("/login")
    }
  }

  const handleProfileChange = (field: keyof ProfileFormState, value: string | boolean) => {
    setProfileForm((prev) => ({
      ...prev,
      [field]: value,
    }))
  }

  const handleProfileSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!user) return

    setProfileSaving(true)
    setProfileMessage(null)

    try {
      const payload = {
        full_name: profileForm.full_name.trim(),
        username: profileForm.username.trim(),
        bio: profileForm.bio?.trim() || "",
        avatar_url: profileForm.avatar_url?.trim() || "",
        profile_public: profileForm.profile_public,
        allow_contact: profileForm.allow_contact,
      }

      const updatedUser = await apiClient.updateProfile(payload)
      setProfileForm({
        full_name: updatedUser.full_name || "",
        username: updatedUser.username || "",
        bio: updatedUser.bio || "",
        avatar_url: updatedUser.avatar_url || "",
        profile_public: updatedUser.profile_public ?? false,
        allow_contact: updatedUser.allow_contact ?? false,
      })
      updateUser(updatedUser as User)
      setProfileMessage({ type: "success", text: "Profile updated successfully." })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to update profile. Please try again."
      setProfileMessage({ type: "error", text: message })
    } finally {
      setProfileSaving(false)
    }
  }

  const handlePasswordSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!passwordForm.currentPassword || !passwordForm.newPassword) {
      setPasswordMessage({ type: "error", text: "Please provide your current and new password." })
      return
    }

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setPasswordMessage({ type: "error", text: "New passwords do not match." })
      return
    }

    if (passwordForm.newPassword.length < 6) {
      setPasswordMessage({ type: "error", text: "New password must be at least 6 characters." })
      return
    }

    setPasswordSaving(true)
    setPasswordMessage(null)

    try {
      await apiClient.changePassword({
        current_password: passwordForm.currentPassword,
        new_password: passwordForm.newPassword,
      })
      setPasswordMessage({ type: "success", text: "Password changed successfully." })
      setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to change password. Please try again."
      setPasswordMessage({ type: "error", text: message })
    } finally {
      setPasswordSaving(false)
    }
  }

  const avatarFallback = useMemo(() => {
    if (user?.full_name) {
      return user.full_name
        .split(" ")
        .map((part) => part.charAt(0).toUpperCase())
        .slice(0, 2)
        .join("") || "U"
    }

    if (user?.email) {
      return user.email.charAt(0).toUpperCase()
    }

    return "U"
  }, [user])

  if (authLoading || !user) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black mx-auto mb-4"></div>
          <p className="text-black">Loading...</p>
        </div>
      </div>
    )
  }

  const roleLabel = role === "student" ? "Student" : isProfessorUser && user.role === "admin" ? "Admin" : "Professor"

  return (
    <div className="min-h-screen bg-atmospheric relative pattern-dots">
      <RoleBasedSidebar currentPath={sidebarPath} />

      <div className="ml-20 relative min-h-screen">
        <header className="bg-white/80 backdrop-blur-sm border-b border-gray-200/60 px-6 py-5 sticky top-0 z-10 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-4xl font-bold text-black tracking-tight mb-1">{heading}</h1>
              <p className="text-sm text-gray-600 font-medium">{subtitle}</p>
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-right">
                <p className="text-sm font-semibold text-gray-900">{user.full_name || user.email}</p>
                {user.email ? (
                  <p className="text-xs text-gray-500">{user.email}</p>
                ) : null}
                <p className="text-xs text-gray-500">{roleLabel}</p>
              </div>
              <Avatar className="h-11 w-11 border border-gray-200 shadow-sm">
                {user.avatar_url ? (
                  <AvatarImage src={user.avatar_url} alt={user.full_name || "Profile"} />
                ) : null}
                <AvatarFallback className="bg-gradient-to-br from-blue-600 to-blue-500 text-white text-sm font-semibold">
                  {avatarFallback}
                </AvatarFallback>
              </Avatar>
              <Button variant="outline" size="sm" onClick={handleLogout} className="border-gray-300 text-gray-700 hover:bg-gray-50">
                <LogOut className="h-4 w-4 mr-2" />
                Logout
              </Button>
            </div>
          </div>
        </header>

        <main className="p-8 pb-24 max-w-5xl mx-auto space-y-8">
          <Card className="bg-white/90 backdrop-blur-sm border border-gray-200/70 shadow-md">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-xl text-gray-900">
                <UserIcon className="h-5 w-5 text-blue-600" />
                Personal Information
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-6" onSubmit={handleProfileSubmit}>
                <div className="flex flex-col md:flex-row md:items-center md:space-x-6 space-y-4 md:space-y-0">
                  <Avatar className="h-24 w-24 border-2 border-blue-200 shadow">
                    {profileForm.avatar_url ? (
                      <AvatarImage src={profileForm.avatar_url} alt={profileForm.full_name || "Profile"} />
                    ) : null}
                    <AvatarFallback className="bg-gradient-to-r from-blue-600 to-indigo-500 text-white text-2xl font-semibold">
                      {avatarFallback}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1">
                    <Label htmlFor="avatarUrl" className="text-sm font-medium text-gray-700">Avatar URL</Label>
                    <Input
                      id="avatarUrl"
                      type="url"
                      placeholder="https://example.com/avatar.jpg"
                      value={profileForm.avatar_url}
                      onChange={(event) => handleProfileChange("avatar_url", event.target.value)}
                      className="mt-2"
                    />
                    <p className="text-xs text-gray-500 mt-2">Paste the URL of an image to update your avatar.</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="md:col-span-2">
                    <Label htmlFor="email" className="text-sm font-medium text-gray-700">Email address</Label>
                    <Input
                      id="email"
                      type="email"
                      value={user.email}
                      readOnly
                      className="mt-2 bg-gray-50 text-gray-600 cursor-not-allowed"
                    />
                  </div>
                  <div>
                    <Label htmlFor="fullName" className="text-sm font-medium text-gray-700">Full name</Label>
                    <Input
                      id="fullName"
                      value={profileForm.full_name}
                      onChange={(event) => handleProfileChange("full_name", event.target.value)}
                      className="mt-2"
                      placeholder="Your name"
                      required
                    />
                  </div>
                  <div>
                    <Label htmlFor="username" className="text-sm font-medium text-gray-700">Username</Label>
                    <Input
                      id="username"
                      value={profileForm.username}
                      onChange={(event) => handleProfileChange("username", event.target.value)}
                      className="mt-2"
                      placeholder="Your username"
                      required
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="bio" className="text-sm font-medium text-gray-700">Bio</Label>
                  <Textarea
                    id="bio"
                    value={profileForm.bio}
                    onChange={(event) => handleProfileChange("bio", event.target.value)}
                    className="mt-2"
                    rows={4}
                    placeholder="Share a short introduction about yourself."
                  />
                  <p className="text-xs text-gray-500 mt-2">This information might be visible to your peers or cohorts depending on your privacy settings.</p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="flex items-center justify-between rounded-xl border border-gray-200/70 bg-gray-50/80 px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-gray-900 flex items-center gap-2">
                        <ShieldCheck className="h-4 w-4 text-blue-600" />
                        Make profile public
                      </p>
                      <p className="text-xs text-gray-500 mt-1">Allow other members to view your profile details.</p>
                    </div>
                    <Switch
                      checked={profileForm.profile_public}
                      onCheckedChange={(checked) => handleProfileChange("profile_public", checked)}
                    />
                  </div>
                  <div className="flex items-center justify-between rounded-xl border border-gray-200/70 bg-gray-50/80 px-4 py-3">
                    <div>
                      <p className="text-sm font-medium text-gray-900">Allow direct contact</p>
                      <p className="text-xs text-gray-500 mt-1">Let others reach out to you regarding cohorts or simulations.</p>
                    </div>
                    <Switch
                      checked={profileForm.allow_contact}
                      onCheckedChange={(checked) => handleProfileChange("allow_contact", checked)}
                    />
                  </div>
                </div>

                {profileMessage ? (
                  <div
                    className={`rounded-lg border px-4 py-3 text-sm ${
                      profileMessage.type === "success"
                        ? "border-green-200 bg-green-50 text-green-700"
                        : "border-red-200 bg-red-50 text-red-700"
                    }`}
                  >
                    {profileMessage.text}
                  </div>
                ) : null}

                <div className="flex items-center justify-end space-x-3">
                  <Button
                    type="button"
                    variant="outline"
                    className="border-gray-300 text-gray-700 hover:bg-gray-50"
                    onClick={() => {
                      if (!user) return
                      setProfileForm({
                        full_name: user.full_name || "",
                        username: user.username || "",
                        bio: user.bio || "",
                        avatar_url: user.avatar_url || "",
                        profile_public: user.profile_public ?? false,
                        allow_contact: user.allow_contact ?? false,
                      })
                      setProfileMessage(null)
                    }}
                  >
                    <RefreshCcw className="h-4 w-4 mr-2" />
                    Reset
                  </Button>
                  <Button
                    type="submit"
                    className="bg-black text-white hover:bg-gray-900"
                    disabled={profileSaving}
                  >
                    {profileSaving ? "Saving..." : "Save changes"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          <Card className="bg-white/90 backdrop-blur-sm border border-gray-200/70 shadow-md">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-xl text-gray-900">
                <ShieldCheck className="h-5 w-5 text-blue-600" />
                Security
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-5" onSubmit={handlePasswordSubmit}>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <Label htmlFor="currentPassword" className="text-sm font-medium text-gray-700">Current password</Label>
                    <Input
                      id="currentPassword"
                      type="password"
                      value={passwordForm.currentPassword}
                      onChange={(event) => setPasswordForm((prev) => ({ ...prev, currentPassword: event.target.value }))}
                      className="mt-2"
                      required
                    />
                  </div>
                  <div>
                    <Label htmlFor="newPassword" className="text-sm font-medium text-gray-700">New password</Label>
                    <Input
                      id="newPassword"
                      type="password"
                      value={passwordForm.newPassword}
                      onChange={(event) => setPasswordForm((prev) => ({ ...prev, newPassword: event.target.value }))}
                      className="mt-2"
                      required
                      minLength={6}
                    />
                  </div>
                </div>
                <div className="max-w-md">
                  <Label htmlFor="confirmPassword" className="text-sm font-medium text-gray-700">Confirm new password</Label>
                  <Input
                    id="confirmPassword"
                    type="password"
                    value={passwordForm.confirmPassword}
                    onChange={(event) => setPasswordForm((prev) => ({ ...prev, confirmPassword: event.target.value }))}
                    className="mt-2"
                    required
                    minLength={6}
                  />
                  <p className="text-xs text-gray-500 mt-2">Use at least 6 characters. A mix of letters, numbers, and symbols is recommended.</p>
                </div>

                {passwordMessage ? (
                  <div
                    className={`rounded-lg border px-4 py-3 text-sm ${
                      passwordMessage.type === "success"
                        ? "border-green-200 bg-green-50 text-green-700"
                        : "border-red-200 bg-red-50 text-red-700"
                    }`}
                  >
                    {passwordMessage.text}
                  </div>
                ) : null}

                <div className="flex items-center justify-end">
                  <Button
                    type="submit"
                    className="bg-black text-white hover:bg-gray-900"
                    disabled={passwordSaving}
                  >
                    {passwordSaving ? "Updating..." : "Update password"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </main>
      </div>
    </div>
  )
}

