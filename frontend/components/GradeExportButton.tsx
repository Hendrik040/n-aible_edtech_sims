"use client"

import { useState } from "react"
import { Download, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiClient } from "@/lib/api"

interface GradeExportButtonProps {
  cohortId: any
  cohortTitle: string
}

async function downloadGrades(cohortId: any) {
  const response = await apiClient.get(
    `/professor/grades/cohorts/${cohortId}/export`,
    { responseType: "blob" }
  )
  return response.data
}

export default function GradeExportButton({ cohortId, cohortTitle }: GradeExportButtonProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleExport = async () => {
    setIsLoading(true)

    const blob = await downloadGrades(cohortId)

    const url = window.URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `${cohortTitle}_grades.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    setIsLoading(false)
  }

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleExport}
      disabled={isLoading}
    >
      {isLoading ? (
        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
      ) : (
        <Download className="h-4 w-4 mr-2" />
      )}
      Export Grades
    </Button>
  )
}