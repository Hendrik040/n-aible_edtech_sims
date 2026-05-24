"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { usePathname } from "next/navigation"
import { MessageCircle, Minimize2, X } from "lucide-react"
import CannyFeedback from "./CannyFeedback"
import { useAuth } from "@/lib/auth-context"

/**
 * Floating, draggable feedback widget rendered site-wide for authenticated users.
 *
 * Renders a collapsible pill that expands into a Canny-backed feedback card.
 * The widget is intentionally suppressed on the student simulation runtime
 * route (`/student/run-simulation/*`) to prevent it from overlapping the chat
 * composer and causing mis-clicks on "Submit for Grading" — see issue #371.
 */
export default function DraggableFeedback() {
  const { user } = useAuth()
  const pathname = usePathname()
  const isOnSimulationRoute = pathname?.startsWith("/student/run-simulation/") ?? false
  const [isOpen, setIsOpen] = useState(false)
  
  // React state for committed position (used for rendering)
  const [position, setPosition] = useState({ x: 0, y: 0 }) 
  
  // Refs for drag logic (High Performance: No React Renders)
  const dragInfo = useRef({
    isDragging: false,
    startX: 0,
    startY: 0,
    initialX: 0, 
    initialY: 0,
    clickStartX: 0,
    clickStartY: 0
  })
  
  const lastPillPosition = useRef({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  const CARD_WIDTH = 400
  const CARD_HEIGHT = 600
  const PILL_WIDTH = 140 
  const PILL_HEIGHT = 50

  useEffect(() => {
    if (typeof window !== "undefined") {
      const initialX = window.innerWidth - PILL_WIDTH - 20
      const initialY = window.innerHeight - PILL_HEIGHT - 20
      setPosition({ x: initialX, y: initialY })
      lastPillPosition.current = { x: initialX, y: initialY }
    }
  }, [])

  /**
   * Drags the widget by mutating the container's style directly, bypassing
   * React re-renders for a smooth 60fps drag. Final position is committed to
   * React state in `handleMouseUp`.
   */
  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!dragInfo.current.isDragging || !containerRef.current) return

    const dx = e.clientX - dragInfo.current.startX
    const dy = e.clientY - dragInfo.current.startY
    
    // Track if we've moved significantly
    if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
      dragInfo.current.hasMoved = true
    }

    const newX = dragInfo.current.initialX + dx
    const newY = dragInfo.current.initialY + dy

    // Boundary check logic (can be loose during drag, strict on drop)
    const currentWidth = containerRef.current.offsetWidth
    const currentHeight = containerRef.current.offsetHeight
    
    const maxX = window.innerWidth - currentWidth
    const maxY = window.innerHeight - currentHeight
    
    const boundedX = Math.min(Math.max(0, newX), maxX)
    const boundedY = Math.min(Math.max(0, newY), maxY)

    // Update DOM directly
    containerRef.current.style.left = `${boundedX}px`
    containerRef.current.style.top = `${boundedY}px`
  }, [])

  /**
   * Ends an active drag: detaches window listeners and commits the final
   * DOM-driven position back into React state so subsequent renders stay
   * in sync with where the user dropped the widget.
   */
  const handleMouseUp = useCallback(() => {
    if (!dragInfo.current.isDragging) return
    
    dragInfo.current.isDragging = false
    window.removeEventListener("mousemove", handleMouseMove)
    window.removeEventListener("mouseup", handleMouseUp)
    document.body.style.cursor = ""

    // Commit final position to React state
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      setPosition({ x: rect.left, y: rect.top })
    }
  }, [handleMouseMove])

  /**
   * Starts a drag on left-click: records the pointer origin and the widget's
   * initial position so `handleMouseMove` can compute deltas, then attaches
   * window-level mousemove/mouseup listeners for the duration of the drag.
   */
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return 
    
    // Don't drag if clicking buttons/interactive elements (unless they are the handle)
    // We'll manage this by attaching handler carefully or checking target
    // For now, prevent text selection
    // e.preventDefault() -> We do this to prevent text selection, but it might block inputs inside Canny?
    // Canny is inside an iframe usually, but here we render it.
    // Actually, only the HEADER is draggable when open. Content is not.
    // So e.preventDefault() on header is fine.

    dragInfo.current = {
      isDragging: true,
      startX: e.clientX,
      startY: e.clientY,
      initialX: position.x,
      initialY: position.y,
      clickStartX: e.clientX,
      clickStartY: e.clientY
    }
    
    document.body.style.cursor = "grabbing"
    window.addEventListener("mousemove", handleMouseMove)
    window.addEventListener("mouseup", handleMouseUp)
  }

  /**
   * Expands the pill into the full feedback card, anchoring the card's
   * bottom-left corner to the pill's position so the expansion grows upward.
   * No-ops if the click was actually the tail end of a drag (>5px movement).
   */
  const handleOpen = (e: React.MouseEvent) => {
    // Use Mouse Coordinates to check for drag (more reliable than DOM position)
    const movedX = Math.abs(e.clientX - dragInfo.current.clickStartX)
    const movedY = Math.abs(e.clientY - dragInfo.current.clickStartY)
    
    if (movedX > 5 || movedY > 5) return // It was a drag

    // OPENING LOGIC
    lastPillPosition.current = { ...position }

    // Get exact current dimensions to anchor correctly
    const currentHeight = containerRef.current.offsetHeight
    
    let newX = position.x
    // Anchor to Bottom-Left:
    // New Top = Old Top - (New Height - Old Height)
    // This effectively keeps the bottom edge in place while expanding up.
    let newY = position.y - (CARD_HEIGHT - currentHeight)

    // Safety: If expanding up goes off-screen (top), shift down
    if (newY < 20) {
       newY = 20
    }
    
    // Safety: If expanding right goes off-screen (right), shift left
    if (newX + CARD_WIDTH > window.innerWidth) {
      newX = Math.max(0, window.innerWidth - CARD_WIDTH - 20)
    }

    setIsOpen(true)
    setPosition({ x: newX, y: newY })
  }

  /**
   * Collapses the card back to the pill and restores the pre-open position
   * captured in `lastPillPosition`, so the pill returns to exactly where the
   * user left it before expanding.
   */
  const handleClose = (e: React.MouseEvent) => {
    e.stopPropagation() // Stop event bubbling
    setIsOpen(false)
    setPosition(lastPillPosition.current)
  }

  if (!user) return null
  if (isOnSimulationRoute) return null

  return (
    <div
      ref={containerRef}
      style={{
        position: "fixed",
        left: position.x, // React controls this when idle
        top: position.y,
        width: isOpen ? CARD_WIDTH : "auto", 
        height: isOpen ? CARD_HEIGHT : "auto",
        zIndex: 9999,
        // Simplified, natural expansion
        transition: "all 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
      }}
      className={`
        flex flex-col overflow-hidden shadow-2xl
        ${isOpen 
          ? "rounded-xl bg-white border border-gray-200" 
          : "rounded-full bg-blue-600 hover:bg-blue-700 cursor-grab active:cursor-grabbing hover:scale-105"
        }
      `}
    >
       {/* 
        --------------------
        CLOSED STATE (PILL)
        --------------------
      */}
      {!isOpen && (
        <div 
          className="px-5 py-3 flex items-center gap-2 select-none text-white whitespace-nowrap"
          onMouseDown={handleMouseDown}
          onClick={handleOpen}
        >
           <MessageCircle className="h-5 w-5" />
           <span className="font-semibold text-sm">Feedback</span>
        </div>
      )}

      {/* 
        --------------------
        OPEN STATE (CARD)
        --------------------
      */}
      {isOpen && (
        <>
          {/* Header */}
          <div 
            className="p-4 border-b border-gray-200 bg-gray-50 flex items-center justify-between cursor-grab active:cursor-grabbing select-none"
            onMouseDown={handleMouseDown}
          >
            <h2 className="text-lg font-bold flex items-center gap-2 text-gray-900">
              <MessageCircle className="h-5 w-5 text-blue-600" />
              Give Us Feedback
            </h2>
            <div className="flex items-center gap-1" onMouseDown={(e) => e.stopPropagation()}>
              <button 
                onClick={handleClose}
                className="p-1.5 hover:bg-gray-200 rounded-lg transition-colors text-gray-500"
                title="Minimize"
              >
                <Minimize2 className="h-4 w-4" />
              </button>
            </div>
          </div>
          
          {/* Description */}
          <div className="px-4 pt-3 pb-0 bg-white transition-opacity duration-300 delay-150">
            <p className="text-xs text-gray-500 leading-relaxed">
              See something you don't like? We're running into a bug. Create a post or search among previous ones to upvote them, and we'll be working on those things.
            </p>
          </div>

          {/* Canny Embed */}
          <div className="flex-1 overflow-hidden relative bg-white transition-opacity duration-300 delay-200">
             <div className="absolute inset-0 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300">
               <CannyFeedback className="min-h-full p-2 bg-white" />
             </div>
          </div>
        </>
      )}
    </div>
  )
}
