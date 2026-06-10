// API client for the professor analytics dashboard
//
// Mirrors the response schemas in backend/modules/analytics/schemas.py.
// All requests go through the Next.js proxy via buildApiUrl, matching the
// conventions in lib/api.ts.
import { buildApiUrl } from './api'
import { debugLog } from './debug'

// ---------------------------------------------------------------------------
// Types (mirroring backend/modules/analytics/schemas.py)
// ---------------------------------------------------------------------------

export interface StudentSummary {
  id: number
  full_name: string
  email: string
}

export interface SimulationSummary {
  id: number
  unique_id: string
  title: string
}

export interface GradeBucket {
  label: string
  lower_bound: number
  upper_bound: number
  count: number
}

export interface GradeDistribution {
  total_graded: number
  mean: number | null
  median: number | null
  std_dev: number | null
  min_grade: number | null
  max_grade: number | null
  buckets: GradeBucket[]
}

export interface CompletionFunnel {
  enrolled: number
  started: number
  completed: number
  submitted: number
  graded: number
}

export interface EngagementPoint {
  week_start: string
  active_students: number
  sessions_started: number
  submissions: number
  total_time_spent_minutes: number
}

export interface AtRiskStudent {
  student: StudentSummary
  risk_score: number
  risk_factors: string[]
  assignments_assigned: number
  assignments_completed: number
  assignments_overdue: number
  average_grade: number | null
  last_activity_at: string | null
}

export interface AssignmentPerformance {
  cohort_simulation_id: number
  simulation: SimulationSummary
  due_date: string | null
  is_required: boolean
  total_students: number
  not_started: number
  in_progress: number
  completed: number
  submitted: number
  graded: number
  overdue: number
  completion_rate: number
  average_grade: number | null
  average_time_spent_minutes: number | null
  average_attempts: number | null
}

export interface CohortAnalyticsOverview {
  cohort_id: number
  cohort_unique_id: string
  cohort_title: string
  generated_at: string
  enrolled_students: number
  pending_students: number
  total_assignments: number
  required_assignments: number
  funnel: CompletionFunnel
  grade_distribution: GradeDistribution
  average_completion_percentage: number
  average_time_spent_minutes: number
  overdue_instances: number
}

export interface CohortEngagementResponse {
  cohort_id: number
  weeks: number
  points: EngagementPoint[]
}

export interface AtRiskReportResponse {
  cohort_id: number
  generated_at: string
  threshold: number
  students: AtRiskStudent[]
}

export interface AssignmentAnalyticsResponse {
  cohort_id: number
  assignments: AssignmentPerformance[]
}

export interface AssignmentDetailResponse {
  assignment: AssignmentPerformance
  grade_distribution: GradeDistribution
  submissions_by_day: Record<string, number>
}

export interface CohortRollup {
  cohort_id: number
  cohort_unique_id: string
  title: string
  is_active: boolean
  enrolled_students: number
  assignments: number
  average_grade: number | null
  completion_rate: number
  overdue_instances: number
}

export interface ProfessorDashboardResponse {
  professor_id: number
  generated_at: string
  total_cohorts: number
  active_cohorts: number
  total_students: number
  total_assignments: number
  pending_grading: number
  cohorts: CohortRollup[]
}

export interface GradeExportRow {
  student_id: number
  student_name: string
  student_email: string
  simulation_title: string
  status: string
  grade: number | null
  ai_grade: number | null
  completion_percentage: number
  submitted_at: string | null
  graded_at: string | null
  is_overdue: boolean
  days_late: number
}

export interface GradeExportResponse {
  cohort_id: number
  generated_at: string
  rows: GradeExportRow[]
}

// ---------------------------------------------------------------------------
// Request helper
// ---------------------------------------------------------------------------

class AnalyticsApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'AnalyticsApiError'
    this.status = status
  }
}

async function analyticsRequest<T>(endpoint: string): Promise<T> {
  const url = buildApiUrl(endpoint)
  debugLog(`[analytics-api] GET ${url}`)

  const response = await fetch(url, {
    method: 'GET',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
  })

  if (!response.ok) {
    let detail = `Analytics request failed with status ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) {
        detail = body.detail
      }
    } catch {
      // Non-JSON error body; keep the generic message
    }
    throw new AnalyticsApiError(detail, response.status)
  }

  return response.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export const analyticsApi = {
  /**
   * Cross-cohort rollup for the professor analytics landing page.
   */
  async getDashboard(): Promise<ProfessorDashboardResponse> {
    return analyticsRequest<ProfessorDashboardResponse>('/professor/analytics/dashboard')
  },

  /**
   * Headline metrics, completion funnel, and grade distribution for a cohort.
   */
  async getCohortOverview(cohortId: number): Promise<CohortAnalyticsOverview> {
    return analyticsRequest<CohortAnalyticsOverview>(
      `/professor/analytics/cohorts/${cohortId}/overview`
    )
  },

  /**
   * Weekly engagement trend for a cohort.
   * @param weeks Number of trailing ISO weeks to include (1-26, default 8).
   */
  async getCohortEngagement(
    cohortId: number,
    weeks?: number
  ): Promise<CohortEngagementResponse> {
    const query = weeks ? `?weeks=${weeks}` : ''
    return analyticsRequest<CohortEngagementResponse>(
      `/professor/analytics/cohorts/${cohortId}/engagement${query}`
    )
  },

  /**
   * Per-assignment performance breakdown for a cohort.
   */
  async getAssignmentAnalytics(cohortId: number): Promise<AssignmentAnalyticsResponse> {
    return analyticsRequest<AssignmentAnalyticsResponse>(
      `/professor/analytics/cohorts/${cohortId}/assignments`
    )
  },

  /**
   * Deep-dive analytics for a single assignment within a cohort.
   */
  async getAssignmentDetail(
    cohortId: number,
    cohortSimulationId: number
  ): Promise<AssignmentDetailResponse> {
    return analyticsRequest<AssignmentDetailResponse>(
      `/professor/analytics/cohorts/${cohortId}/assignments/${cohortSimulationId}`
    )
  },

  /**
   * Students flagged by the at-risk heuristic, highest risk first.
   * @param threshold Minimum risk score (0-1) for inclusion, default 0.5.
   */
  async getAtRiskReport(
    cohortId: number,
    threshold?: number
  ): Promise<AtRiskReportResponse> {
    const query = threshold !== undefined ? `?threshold=${threshold}` : ''
    return analyticsRequest<AtRiskReportResponse>(
      `/professor/analytics/cohorts/${cohortId}/at-risk${query}`
    )
  },

  /**
   * Flat grade rows for every student x assignment cell in a cohort.
   */
  async getGradeExport(cohortId: number): Promise<GradeExportResponse> {
    return analyticsRequest<GradeExportResponse>(
      `/professor/analytics/cohorts/${cohortId}/grade-export`
    )
  },
}

// ---------------------------------------------------------------------------
// CSV helpers
// ---------------------------------------------------------------------------

const CSV_HEADERS = [
  'Student ID',
  'Student Name',
  'Email',
  'Simulation',
  'Status',
  'Grade',
  'AI Grade',
  'Completion %',
  'Submitted At',
  'Graded At',
  'Overdue',
  'Days Late',
] as const

function escapeCsvCell(value: string | number | boolean | null): string {
  if (value === null || value === undefined) {
    return ''
  }
  const text = String(value)
  if (text.includes(',') || text.includes('"') || text.includes('\n')) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

/**
 * Convert a grade export payload into a downloadable CSV string.
 */
export function gradeExportToCsv(data: GradeExportResponse): string {
  const lines: string[] = [CSV_HEADERS.join(',')]
  for (const row of data.rows) {
    lines.push(
      [
        escapeCsvCell(row.student_id),
        escapeCsvCell(row.student_name),
        escapeCsvCell(row.student_email),
        escapeCsvCell(row.simulation_title),
        escapeCsvCell(row.status),
        escapeCsvCell(row.grade),
        escapeCsvCell(row.ai_grade),
        escapeCsvCell(row.completion_percentage),
        escapeCsvCell(row.submitted_at),
        escapeCsvCell(row.graded_at),
        escapeCsvCell(row.is_overdue),
        escapeCsvCell(row.days_late),
      ].join(',')
    )
  }
  return lines.join('\n')
}

/**
 * Trigger a browser download of the cohort grade export as CSV.
 */
export function downloadGradeExport(data: GradeExportResponse): void {
  const csv = gradeExportToCsv(data)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `cohort-${data.cohort_id}-grades.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

export { AnalyticsApiError }
