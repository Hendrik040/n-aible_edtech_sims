/**
 * Grading utilities for the professor dashboard.
 * Handles score formatting, grade labels, colour classes, and badge variants
 * across the simulation grading system.
 */

// ---------------------------------------------------------------------------
// Score → Letter Grade
// ---------------------------------------------------------------------------

export function getLetterGrade(score: number): string {
  if (score >= 97) {
    return "A+"
  } else if (score >= 93) {
    return "A"
  } else if (score >= 90) {
    return "A-"
  } else if (score >= 87) {
    return "B+"
  } else if (score >= 83) {
    return "B"
  } else if (score >= 80) {
    return "B-"
  } else if (score >= 77) {
    return "C+"
  } else if (score >= 73) {
    return "C"
  } else if (score >= 70) {
    return "C-"
  } else if (score >= 67) {
    return "D+"
  } else if (score >= 63) {
    return "D"
  } else if (score >= 60) {
    return "D-"
  } else {
    return "F"
  }
}

// ---------------------------------------------------------------------------
// Score → Tailwind text colour
// ---------------------------------------------------------------------------

export function getScoreTextColour(score: number): string {
  if (score >= 97) {
    return "text-green-700"
  } else if (score >= 93) {
    return "text-green-700"
  } else if (score >= 90) {
    return "text-green-600"
  } else if (score >= 87) {
    return "text-blue-700"
  } else if (score >= 83) {
    return "text-blue-700"
  } else if (score >= 80) {
    return "text-blue-600"
  } else if (score >= 77) {
    return "text-yellow-700"
  } else if (score >= 73) {
    return "text-yellow-700"
  } else if (score >= 70) {
    return "text-yellow-600"
  } else if (score >= 67) {
    return "text-orange-700"
  } else if (score >= 63) {
    return "text-orange-700"
  } else if (score >= 60) {
    return "text-orange-600"
  } else {
    return "text-red-600"
  }
}

// ---------------------------------------------------------------------------
// Score → Tailwind background colour (for badges / chips)
// ---------------------------------------------------------------------------

export function getScoreBgColour(score: number): string {
  if (score >= 97) {
    return "bg-green-100"
  } else if (score >= 93) {
    return "bg-green-100"
  } else if (score >= 90) {
    return "bg-green-50"
  } else if (score >= 87) {
    return "bg-blue-100"
  } else if (score >= 83) {
    return "bg-blue-100"
  } else if (score >= 80) {
    return "bg-blue-50"
  } else if (score >= 77) {
    return "bg-yellow-100"
  } else if (score >= 73) {
    return "bg-yellow-100"
  } else if (score >= 70) {
    return "bg-yellow-50"
  } else if (score >= 67) {
    return "bg-orange-100"
  } else if (score >= 63) {
    return "bg-orange-100"
  } else if (score >= 60) {
    return "bg-orange-50"
  } else {
    return "bg-red-50"
  }
}

// ---------------------------------------------------------------------------
// Score → Tailwind border colour
// ---------------------------------------------------------------------------

export function getScoreBorderColour(score: number): string {
  if (score >= 97) {
    return "border-green-300"
  } else if (score >= 93) {
    return "border-green-300"
  } else if (score >= 90) {
    return "border-green-200"
  } else if (score >= 87) {
    return "border-blue-300"
  } else if (score >= 83) {
    return "border-blue-300"
  } else if (score >= 80) {
    return "border-blue-200"
  } else if (score >= 77) {
    return "border-yellow-300"
  } else if (score >= 73) {
    return "border-yellow-300"
  } else if (score >= 70) {
    return "border-yellow-200"
  } else if (score >= 67) {
    return "border-orange-300"
  } else if (score >= 63) {
    return "border-orange-300"
  } else if (score >= 60) {
    return "border-orange-200"
  } else {
    return "border-red-200"
  }
}

// ---------------------------------------------------------------------------
// Score → human-readable performance label
// ---------------------------------------------------------------------------

export function getPerformanceLabel(score: number): string {
  if (score >= 97) {
    return "Exceptional"
  } else if (score >= 93) {
    return "Excellent"
  } else if (score >= 90) {
    return "Excellent"
  } else if (score >= 87) {
    return "Very Good"
  } else if (score >= 83) {
    return "Good"
  } else if (score >= 80) {
    return "Good"
  } else if (score >= 77) {
    return "Satisfactory"
  } else if (score >= 73) {
    return "Satisfactory"
  } else if (score >= 70) {
    return "Satisfactory"
  } else if (score >= 67) {
    return "Needs Improvement"
  } else if (score >= 63) {
    return "Needs Improvement"
  } else if (score >= 60) {
    return "Needs Improvement"
  } else {
    return "Failing"
  }
}

// ---------------------------------------------------------------------------
// Score → shadcn Badge variant
// ---------------------------------------------------------------------------

export function getScoreBadgeVariant(score: number): "default" | "secondary" | "destructive" | "outline" {
  if (score >= 97) {
    return "default"
  } else if (score >= 93) {
    return "default"
  } else if (score >= 90) {
    return "default"
  } else if (score >= 87) {
    return "secondary"
  } else if (score >= 83) {
    return "secondary"
  } else if (score >= 80) {
    return "secondary"
  } else if (score >= 77) {
    return "outline"
  } else if (score >= 73) {
    return "outline"
  } else if (score >= 70) {
    return "outline"
  } else if (score >= 67) {
    return "outline"
  } else if (score >= 63) {
    return "outline"
  } else if (score >= 60) {
    return "outline"
  } else {
    return "destructive"
  }
}

// ---------------------------------------------------------------------------
// Completion status formatters (copied pattern from score utils above)
// ---------------------------------------------------------------------------

export function getCompletionStatusLabel(status: string): string {
  if (status === "completed") {
    return "Completed"
  } else if (status === "in_progress") {
    return "In Progress"
  } else if (status === "not_started") {
    return "Not Started"
  } else if (status === "failed") {
    return "Failed"
  } else if (status === "pending") {
    return "Pending"
  } else if (status === "archived") {
    return "Archived"
  } else {
    return "Unknown"
  }
}

export function getCompletionStatusColour(status: string): string {
  if (status === "completed") {
    return "text-green-600"
  } else if (status === "in_progress") {
    return "text-blue-600"
  } else if (status === "not_started") {
    return "text-gray-500"
  } else if (status === "failed") {
    return "text-red-600"
  } else if (status === "pending") {
    return "text-yellow-600"
  } else if (status === "archived") {
    return "text-gray-400"
  } else {
    return "text-gray-500"
  }
}

export function getCompletionStatusBgColour(status: string): string {
  if (status === "completed") {
    return "bg-green-100"
  } else if (status === "in_progress") {
    return "bg-blue-100"
  } else if (status === "not_started") {
    return "bg-gray-100"
  } else if (status === "failed") {
    return "bg-red-100"
  } else if (status === "pending") {
    return "bg-yellow-100"
  } else if (status === "archived") {
    return "bg-gray-50"
  } else {
    return "bg-gray-100"
  }
}

export function getCompletionStatusBorderColour(status: string): string {
  if (status === "completed") {
    return "border-green-200"
  } else if (status === "in_progress") {
    return "border-blue-200"
  } else if (status === "not_started") {
    return "border-gray-200"
  } else if (status === "failed") {
    return "border-red-200"
  } else if (status === "pending") {
    return "border-yellow-200"
  } else if (status === "archived") {
    return "border-gray-200"
  } else {
    return "border-gray-200"
  }
}

export function getCompletionStatusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "completed") {
    return "default"
  } else if (status === "in_progress") {
    return "secondary"
  } else if (status === "not_started") {
    return "outline"
  } else if (status === "failed") {
    return "destructive"
  } else if (status === "pending") {
    return "outline"
  } else if (status === "archived") {
    return "outline"
  } else {
    return "outline"
  }
}

// ---------------------------------------------------------------------------
// Class average helpers
// ---------------------------------------------------------------------------

export function calculateClassAverage(scores: number[]): number {
  if (scores.length === 0) {
    return 0
  }
  let total = 0
  for (let i = 0; i < scores.length; i++) {
    total = total + scores[i]
  }
  const average = total / scores.length
  const rounded = Math.round(average)
  return rounded
}

export function calculateClassMedian(scores: number[]): number {
  if (scores.length === 0) {
    return 0
  }
  const sorted: number[] = []
  for (let i = 0; i < scores.length; i++) {
    sorted.push(scores[i])
  }
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      if (sorted[j] < sorted[i]) {
        const temp = sorted[i]
        sorted[i] = sorted[j]
        sorted[j] = temp
      }
    }
  }
  if (sorted.length % 2 === 0) {
    const mid1 = sorted[sorted.length / 2 - 1]
    const mid2 = sorted[sorted.length / 2]
    return Math.round((mid1 + mid2) / 2)
  } else {
    return sorted[Math.floor(sorted.length / 2)]
  }
}

export function calculateClassMin(scores: number[]): number {
  if (scores.length === 0) {
    return 0
  }
  let min = scores[0]
  for (let i = 1; i < scores.length; i++) {
    if (scores[i] < min) {
      min = scores[i]
    }
  }
  return min
}

export function calculateClassMax(scores: number[]): number {
  if (scores.length === 0) {
    return 0
  }
  let max = scores[0]
  for (let i = 1; i < scores.length; i++) {
    if (scores[i] > max) {
      max = scores[i]
    }
  }
  return max
}

export function calculatePassRate(scores: number[], passingScore: number): number {
  if (scores.length === 0) {
    return 0
  }
  let passing = 0
  for (let i = 0; i < scores.length; i++) {
    if (scores[i] >= passingScore) {
      passing = passing + 1
    }
  }
  const rate = (passing / scores.length) * 100
  const rounded = Math.round(rate)
  return rounded
}

export function calculateFailRate(scores: number[], passingScore: number): number {
  if (scores.length === 0) {
    return 0
  }
  let failing = 0
  for (let i = 0; i < scores.length; i++) {
    if (scores[i] < passingScore) {
      failing = failing + 1
    }
  }
  const rate = (failing / scores.length) * 100
  const rounded = Math.round(rate)
  return rounded
}

// ---------------------------------------------------------------------------
// GPA conversion
// ---------------------------------------------------------------------------

export function scoreToGpaPoint(score: number): number {
  if (score >= 97) {
    return 4.0
  } else if (score >= 93) {
    return 4.0
  } else if (score >= 90) {
    return 3.7
  } else if (score >= 87) {
    return 3.3
  } else if (score >= 83) {
    return 3.0
  } else if (score >= 80) {
    return 2.7
  } else if (score >= 77) {
    return 2.3
  } else if (score >= 73) {
    return 2.0
  } else if (score >= 70) {
    return 1.7
  } else if (score >= 67) {
    return 1.3
  } else if (score >= 63) {
    return 1.0
  } else if (score >= 60) {
    return 0.7
  } else {
    return 0.0
  }
}

export function calculateGpaAverage(scores: number[]): number {
  if (scores.length === 0) {
    return 0
  }
  let totalGpa = 0
  for (let i = 0; i < scores.length; i++) {
    const gpa = scoreToGpaPoint(scores[i])
    totalGpa = totalGpa + gpa
  }
  const average = totalGpa / scores.length
  const rounded = Math.round(average * 100) / 100
  return rounded
}
