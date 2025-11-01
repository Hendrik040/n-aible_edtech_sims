"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"

export interface RoleChooserProps {
  selectedRole: "student" | "professor" | null
  onRoleSelect: (role: "student" | "professor") => void
  onContinue?: () => void
  isLoading?: boolean
  showContinueButton?: boolean
  variant?: "detailed" | "simple"
  className?: string
}

export default function RoleChooser({
  selectedRole,
  onRoleSelect,
  onContinue,
  isLoading = false,
  showContinueButton = false,
  variant = "detailed",
  className = ""
}: RoleChooserProps) {
  const isDetailed = variant === "detailed"
  const maxWidth = isDetailed ? "max-w-4xl" : "max-w-2xl"
  const iconSize = isDetailed ? "h-12 w-12" : "h-10 w-10"
  const titleSize = isDetailed ? "text-xl" : "text-lg"

  return (
    <div className={`min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4 relative pattern-grid overflow-hidden ${className}`}>
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" style={{animationDelay: '1s'}}></div>
      </div>
      
      <div className={`w-full ${maxWidth} relative z-10 animate-fade-scale`}>
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-24 h-16 mb-6 animate-scale-in">
            <img 
              src="/n-aiblelogo.png" 
              alt="Logo" 
              className={`${isDetailed ? "w-40 h-20" : "w-32 h-16"} opacity-95`} 
            />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">Choose Your Role</h1>
          <p className="text-gray-400 text-lg">How will you be using the platform?</p>
        </div>

        {/* Role Selection Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Student Card */}
          <div 
            className={`card-elevated cursor-pointer p-8 rounded-xl border-2 transition-all duration-300 backdrop-blur-sm ${
              selectedRole === "student" 
                ? "border-blue-500 bg-gradient-to-br from-blue-900/40 to-blue-800/20 shadow-lg shadow-blue-500/20 scale-105" 
                : "border-gray-600/60 bg-gray-900/30 hover:border-blue-400/60 hover:bg-gray-800/40"
            }`}
            onClick={() => onRoleSelect("student")}
          >
            <div className="text-center">
              <div className={`mx-auto mb-6 p-5 rounded-2xl bg-gradient-to-br from-blue-600/30 to-blue-500/20 shadow-lg ${selectedRole === "student" ? "scale-110" : ""} transition-transform duration-300`}>
                <svg className={`${iconSize} text-blue-300`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 14l9-5-9-5-9 5 9 5z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" />
                </svg>
              </div>
              <h3 className={`${titleSize} font-bold text-white mb-3 tracking-tight`}>Student</h3>
              <p className={`text-gray-300 ${isDetailed ? "mb-6 text-base" : "text-sm"}`}>
                Join cohorts and participate in simulations
              </p>
              
              {isDetailed && (
                <div className="space-y-3 text-sm">
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-blue-400 rounded-full shadow-lg shadow-blue-400/50"></div>
                    <span className="text-gray-200">Access assigned simulations</span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-blue-400 rounded-full shadow-lg shadow-blue-400/50"></div>
                    <span className="text-gray-200">Track your progress</span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-blue-400 rounded-full shadow-lg shadow-blue-400/50"></div>
                    <span className="text-gray-200">Receive notifications</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Professor Card */}
          <div 
            className={`card-elevated cursor-pointer p-8 rounded-xl border-2 transition-all duration-300 backdrop-blur-sm ${
              selectedRole === "professor" 
                ? "border-purple-500 bg-gradient-to-br from-purple-900/40 to-purple-800/20 shadow-lg shadow-purple-500/20 scale-105" 
                : "border-gray-600/60 bg-gray-900/30 hover:border-purple-400/60 hover:bg-gray-800/40"
            }`}
            onClick={() => onRoleSelect("professor")}
          >
            <div className="text-center">
              <div className={`mx-auto mb-6 p-5 rounded-2xl bg-gradient-to-br from-purple-600/30 to-purple-500/20 shadow-lg ${selectedRole === "professor" ? "scale-110" : ""} transition-transform duration-300`}>
                <svg className={`${iconSize} text-purple-300`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
              <h3 className={`${titleSize} font-bold text-white mb-3 tracking-tight`}>Professor</h3>
              <p className={`text-gray-300 ${isDetailed ? "mb-6 text-base" : "text-sm"}`}>
                Create simulations and manage cohorts
              </p>
              
              {isDetailed && (
                <div className="space-y-3 text-sm">
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-purple-400 rounded-full shadow-lg shadow-purple-400/50"></div>
                    <span className="text-gray-200">Build custom simulations</span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-purple-400 rounded-full shadow-lg shadow-purple-400/50"></div>
                    <span className="text-gray-200">Manage student cohorts</span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-purple-400 rounded-full shadow-lg shadow-purple-400/50"></div>
                    <span className="text-gray-200">Track learning analytics</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Continue Button */}
        {showContinueButton && (
          <div className="text-center">
            <Button
              onClick={onContinue}
              disabled={!selectedRole || isLoading}
              className="w-full max-w-md btn-gradient text-white border-0 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-[1.02] font-semibold py-3 px-8 rounded-xl disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
            >
              {isLoading ? "Processing..." : `Continue as ${selectedRole === "student" ? "Student" : selectedRole === "professor" ? "Professor" : "..."}`}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
