"use client"

import ReactMarkdown from "react-markdown"

interface MarkdownRendererProps {
  content: string | null | undefined
  className?: string
}

/**
 * Renders markdown content as formatted HTML using react-markdown.
 * Wraps output in Tailwind prose classes for consistent typography.
 */
export default function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  if (!content) return null

  return (
    <div className={`prose prose-sm max-w-none ${className ?? ""}`}>
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  )
}
