"use client"

import { useEffect, useState } from "react"
import { MoonStar, SunMedium } from "lucide-react"
import { useTheme } from "next-themes"

import { cn } from "@/lib/utils"

interface ThemeToggleProps {
  className?: string
  compact?: boolean
}

export default function ThemeToggle({
  className,
  compact = false,
}: ThemeToggleProps) {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const isDark = mounted ? resolvedTheme === "dark" : true
  const nextTheme = isDark ? "light" : "dark"

  return (
    <button
      type="button"
      onClick={() => setTheme(nextTheme)}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/80 px-3 py-2 text-sm font-medium text-foreground shadow-lg backdrop-blur-md transition-all hover:bg-background",
        compact && "h-12 w-12 justify-center p-0",
        className
      )}
      aria-label={mounted ? `Switch to ${nextTheme} mode` : "Toggle theme"}
      title={mounted ? `Switch to ${nextTheme} mode` : "Toggle theme"}
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-foreground/10">
        {isDark ? <SunMedium className="h-4 w-4" /> : <MoonStar className="h-4 w-4" />}
      </span>
      {!compact && (
        <span>{mounted ? (isDark ? "Light mode" : "Dark mode") : "Theme"}</span>
      )}
    </button>
  )
}
