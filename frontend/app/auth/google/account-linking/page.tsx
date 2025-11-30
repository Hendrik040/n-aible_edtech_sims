"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { AccountLinkingDialog } from "@/components/AccountLinkingDialog"
import { AccountLinkingData } from "@/lib/google-oauth"
import { useAuth } from "@/lib/auth-context"

export default function AccountLinkingPage() {
  const router = useRouter()
  const { linkGoogleAccount } = useAuth()
  const [linkingData, setLinkingData] = useState<AccountLinkingData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Prevent automatic redirection when in popup context
  useEffect(() => {
    // Check if we're in a popup window
    const isPopup = window.opener !== null || window.parent !== window
    
    if (isPopup) {
      console.log('Account linking page: In popup context, preventing automatic redirection')
      // Don't redirect automatically when in popup - let the account linking complete
      return
    }
  }, [])

  useEffect(() => {
    const handleAccountLinking = () => {
      try {
        const urlParams = new URLSearchParams(window.location.search)
        const dataParam = urlParams.get('data')

        if (dataParam) {
          const data = JSON.parse(decodeURIComponent(dataParam))
          console.log('Account linking page: Received data:', data)
          setLinkingData(data)
        } else {
          console.error('Account linking page: No data parameter found')
          setError('No account linking data found')
        }
      } catch (error) {
        console.error('Account linking page: Error parsing data:', error)
        setError('Invalid account linking data')
      }
    }

    handleAccountLinking()
  }, [])

  const handleLinkAccount = async (action: 'link' | 'create_separate', role?: 'student' | 'professor') => {
    if (!linkingData) return
    
    setLoading(true)
    setError(null)
    
    try {
      console.log('Account linking page: Linking account with action:', action, 'role:', role)
      await linkGoogleAccount(action, linkingData.existing_user.id, linkingData.google_data, linkingData.state, role)
      
      // Close popup and notify parent window
      if (window.opener) {
        window.opener.postMessage({
          type: 'OAUTH_SUCCESS',
          action: 'account_linked',
          data: { action }
        }, '*')
        window.close()
      } else {
        // Fallback redirect if not in popup
        router.push('/dashboard')
      }
    } catch (error) {
      console.error('Account linking page: Error linking account:', error)
      setError(error instanceof Error ? error.message : 'Account linking failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  if (error) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center p-4">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-400 mb-4">Account Linking Error</h1>
          <p className="text-gray-300 mb-6">{error}</p>
          <button 
            onClick={() => window.close()}
            className="bg-white text-black px-4 py-2 rounded hover:bg-gray-100"
          >
            Close
          </button>
        </div>
      </div>
    )
  }

  if (!linkingData) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center p-4">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white mx-auto mb-4"></div>
          <p className="text-gray-300">Loading account linking data...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-black text-white flex items-center justify-center p-4">
      <AccountLinkingDialog
        isOpen={true}
        onClose={() => {
          console.log('Account linking dialog closed')
          if (window.opener) {
            window.close()
          } else {
            router.push('/')
          }
        }}
        linkingData={linkingData}
        onLinkAccount={handleLinkAccount}
        isLoading={loading}
      />
    </div>
  )
}
