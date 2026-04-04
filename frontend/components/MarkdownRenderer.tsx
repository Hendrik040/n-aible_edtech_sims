"use client"

import ReactMarkdown from "react-markdown"

interface MarkdownRendererProps {
  content: string | null | undefined
  className?: string
}

export default function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  if (!content) return null

  return (
    <div className={`prose prose-sm max-w-none ${className ?? ""}`}>
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  )
}
