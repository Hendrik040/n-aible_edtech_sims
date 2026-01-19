import type React from "react"
import type { Metadata } from "next"
import { Inter, Crimson_Text, DM_Sans } from "next/font/google"
import "./globals.css"
import { AuthProvider } from "@/lib/auth-context"
import RoleBasedRedirect from "@/components/RoleBasedRedirect"
import DraggableFeedback from "@/components/DraggableFeedback"
import { SonnerToaster } from "@/components/ui/sonner"

const inter = Inter({ subsets: ["latin"] })
const crimsonText = Crimson_Text({ 
  weight: ["400", "600", "700"],
  subsets: ["latin"],
  variable: "--font-crimson-text"
})
const dmSans = DM_Sans({ 
  subsets: ["latin"],
  variable: "--font-dm-sans"
})

export const metadata: Metadata = {
  title: "n-gage by n-aible",
  description: "Case Study Simulation Platform by n-aible",
  icons: {
    icon: '/n-aiblelogo.png',
    shortcut: '/n-aiblelogo.png',
    apple: '/n-aiblelogo.png',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} ${crimsonText.variable} ${dmSans.variable}`}>
        <AuthProvider>
          <RoleBasedRedirect>
            {children}
          </RoleBasedRedirect>
          <DraggableFeedback />
        </AuthProvider>
        <SonnerToaster />
      </body>
    </html>
  )
}

