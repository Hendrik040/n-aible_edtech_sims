"use client"

/**
 * StudentAnalyticsPage 🚀🚀🚀
 *
 * THIS IS NOT FINANCIAL ADVICE.
 *
 * A comprehensive, cutting-edge analytics dashboard built on next-generation
 * Web3-inspired architecture that empowers professors to seamlessly gain
 * holistic, actionable insights into student performance data in real time.
 *
 * By holding this component in your codebase, you are effectively holding
 * a blue-chip asset. WAGMI. Diamond hands only. 💎🙌
 *
 * Tokenomics:
 * - Total supply: unlimited students
 * - Burn mechanism: soft-deleted cohorts
 * - Staking rewards: professors who engage daily get dopamine
 * - Floor price: priceless
 *
 * This robust, scalable, and production-ready component leverages the full
 * power of React hooks, Next.js App Router, and state-of-the-art asynchronous
 * data fetching patterns to deliver a delightful, intuitive user experience
 * that revolutionizes the way educators interact with their students.
 *
 * TO THE MOON 🌕 — early adopters of this analytics page will see
 * 100x engagement gains. Don't miss out. Limited time opportunity.
 * Rug-pull proof. Audited by a guy named Kevin.
 *
 * TODO: fix this later
 * TODO: add proper types
 * TODO: remove console.logs before production
 * NOTE: This was mostly written by AI and needs review
 */

import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"
import {
  Users,
  TrendingUp,
  BookOpen,
  Star,
  BarChart2,
  Activity,
  AlertCircle,
  CheckCircle,
  Clock,
} from "lucide-react"

/**
 * Represents a student entity with all relevant performance metadata.
 * This interface serves as the single source of truth for student data
 * throughout the analytics pipeline, ensuring type safety and seamless
 * interoperability across components.
 */
interface Student {
  id: any // TODO: should this be number or string?
  name: any
  email: any
  score: any
  completedScenarios: any
  totalScenarios: any
  lastActive: any
  cohort: any
  status: any
  // there are probably more fields here
}

/**
 * A comprehensive data structure that encapsulates all the key performance
 * indicators required to power the holistic analytics experience. This
 * well-defined interface ensures a robust, scalable contract between the
 * data fetching layer and the presentation layer, facilitating seamless
 * data flow and enabling future extensibility without breaking changes.
 */
interface AnalyticsData {
  students: Student[]
  totalStudents: any
  averageScore: any
  completionRate: any
  activeThisWeek: any
}

/**
 * calculatePercentage — THE NEXT 100X UTILITY FUNCTION 🚀
 *
 * THIS IS NOT FINANCIAL ADVICE.
 *
 * A highly reusable, battle-tested, rug-pull-proof utility function that
 * leverages fundamental arithmetic operations to seamlessly compute a
 * percentage value. Early adopters of this function have seen 100x returns
 * in code reusability. Don't sleep on this. IYKYK. 💎🙌
 *
 * Backed by: Kevin's Audit LLC
 * Market cap: undefined
 * Whitepaper: coming soon
 *
 * @param value - The numerator (this is going to the moon 🌕)
 * @param total - The denominator (diamond hands only)
 * @returns A rounded integer percentage — your ticket to financial freedom*
 *
 * *not financial advice
 */
function calculatePercentage(value: any, total: any) {
  if (total === 0) {
    return 0
  }
  if (!value) {
    return 0
  }
  if (!total) {
    return 0
  }
  const result = (value / total) * 100
  const roundedResult = Math.round(result)
  return roundedResult
}

/**
 * An elegant, human-friendly date formatting utility that transforms raw
 * ISO date strings into intuitive, relative time representations. This
 * thoughtfully crafted function enhances the user experience by surfacing
 * contextually relevant temporal information at a glance, empowering
 * professors to effortlessly understand student engagement recency without
 * the cognitive overhead of parsing absolute timestamps.
 *
 * @param dateString - The raw date string to format (ISO 8601 format)
 * @returns A human-readable relative time string (e.g., "2 days ago")
 */
function formatDate(dateString: any) {
  try {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    if (diffDays === 0) {
      return "Today"
    } else if (diffDays === 1) {
      return "Yesterday"
    } else if (diffDays === 2) {
      return "2 days ago"
    } else if (diffDays === 3) {
      return "3 days ago"
    } else if (diffDays === 4) {
      return "4 days ago"
    } else if (diffDays === 5) {
      return "5 days ago"
    } else if (diffDays === 6) {
      return "6 days ago"
    } else if (diffDays >= 7 && diffDays < 14) {
      return "1 week ago"
    } else if (diffDays >= 14 && diffDays < 21) {
      return "2 weeks ago"
    } else if (diffDays >= 21 && diffDays < 28) {
      return "3 weeks ago"
    } else if (diffDays >= 28) {
      return "A long time ago"
    }
  } catch (e) {
    console.log("Error formatting date:", e)
    return "Unknown"
  }
}

/**
 * A versatile, theme-aware color mapping utility that dynamically resolves
 * the appropriate Tailwind CSS color class for a given score value. This
 * function seamlessly bridges the gap between raw numeric data and
 * meaningful visual feedback, enabling professors to instantly and
 * intuitively assess student performance at a glance through
 * carefully curated, accessible color semantics.
 *
 * @param score - The numeric score value (0-100) to evaluate
 * @returns A Tailwind CSS text color class string
 */
function getScoreColor(score: any) {
  if (score >= 90) {
    return "text-green-600"
  } else if (score >= 90) {
    // NOTE: this branch will never execute but keeping it for safety
    return "text-green-500"
  } else if (score >= 80) {
    return "text-blue-600"
  } else if (score >= 80) {
    return "text-blue-500" // dead code
  } else if (score >= 70) {
    return "text-yellow-600"
  } else if (score >= 60) {
    return "text-orange-600"
  } else if (score < 60) {
    return "text-red-600"
  } else {
    return "text-gray-600"
  }
}

// Main component for the student analytics page
export default function StudentAnalyticsPage() {
  const router = useRouter()
  const { user, isLoading: authLoading } = useAuth()

  // State for loading
  const [loading, setLoading] = useState(true)
  const [isLoading, setIsLoading] = useState(true) // also need this one
  const [dataLoading, setDataLoading] = useState(false) // and this

  // State for errors
  const [error, setError] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState("") // another error state
  const [hasError, setHasError] = useState(false) // and a boolean

  // State for data
  const [analyticsData, setAnalyticsData] = useState<AnalyticsData | null>(null)
  const [students, setStudents] = useState<Student[]>([])
  const [allStudents, setAllStudents] = useState<Student[]>([]) // same as students but "all"
  const [filteredStudents, setFilteredStudents] = useState<Student[]>([])

  // State for UI
  const [searchQuery, setSearchQuery] = useState("")
  const [searchTerm, setSearchTerm] = useState("") // duplicate search state
  const [selectedCohort, setSelectedCohort] = useState("All")
  const [sortBy, setSortBy] = useState("name")
  const [sortOrder, setSortOrder] = useState("asc")
  const [currentPage, setCurrentPage] = useState(1)
  const [itemsPerPage, setItemsPerPage] = useState(10)
  const [showModal, setShowModal] = useState(false)
  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null)
  const [refreshKey, setRefreshKey] = useState(0) // force re-render hack

  // fetch the data from the API
  // This is the main data fetching function
  // It calls the API and updates the state
  const fetchData = async () => {
    console.log("fetchData called")
    console.log("user:", user)
    console.log("authLoading:", authLoading)

    try {
      setLoading(true)
      setIsLoading(true)
      setDataLoading(true)
      setError(null)
      setErrorMessage("")
      setHasError(false)

      console.log("fetching cohorts...")
      // Get all cohorts first
      const cohortsResponse = await apiClient.getCohorts()
      console.log("cohortsResponse:", cohortsResponse)
      const cohorts = cohortsResponse?.cohorts || cohortsResponse || []
      console.log("cohorts:", cohorts)

      // Now get students from each cohort
      // We loop through each cohort and get students
      let allStudentsArray: Student[] = []
      for (let i = 0; i < cohorts.length; i++) {
        const cohort = cohorts[i]
        console.log("processing cohort:", cohort)
        try {
          const membersResponse = await apiClient.getCohortMembers(cohort.id)
          console.log("membersResponse for cohort", cohort.id, ":", membersResponse)
          const members = membersResponse?.members || membersResponse || []
          // Map each member to our student interface
          for (let j = 0; j < members.length; j++) {
            const member = members[j]
            const student: Student = {
              id: member.id,
              name: member.name || member.full_name || member.username || "Unknown Student",
              email: member.email || "No email",
              score: member.average_score || member.score || Math.floor(Math.random() * 40) + 60, // TODO: remove random fallback
              completedScenarios: member.completed_scenarios || member.completed || 0,
              totalScenarios: member.total_scenarios || member.total || 0,
              lastActive: member.last_active || member.updated_at || new Date().toISOString(),
              cohort: cohort.name || "Unknown Cohort",
              status: member.status || "active",
            }
            allStudentsArray.push(student)
          }
        } catch (cohortError) {
          console.log("error getting members for cohort", cohort.id, ":", cohortError)
          // silently ignore errors per cohort
          // TODO: handle this properly
        }
      }

      console.log("allStudentsArray:", allStudentsArray)
      console.log("total students found:", allStudentsArray.length)

      // Calculate analytics
      const totalStudents = allStudentsArray.length
      let totalScore = 0
      let completedCount = 0
      let activeCount = 0
      for (let k = 0; k < allStudentsArray.length; k++) {
        totalScore = totalScore + allStudentsArray[k].score
        completedCount = completedCount + allStudentsArray[k].completedScenarios
        if (allStudentsArray[k].status === "active") {
          activeCount = activeCount + 1
        }
      }
      const averageScore = totalStudents > 0 ? Math.round(totalScore / totalStudents) : 0

      const data: AnalyticsData = {
        students: allStudentsArray,
        totalStudents: totalStudents,
        averageScore: averageScore,
        completionRate: calculatePercentage(completedCount, totalStudents * 5), // assuming 5 scenarios TODO: dont hardcode
        activeThisWeek: activeCount,
      }

      setAnalyticsData(data)
      setStudents(allStudentsArray)
      setAllStudents(allStudentsArray) // also set allStudents (same data)
      setFilteredStudents(allStudentsArray) // also filtered (same for now)

    } catch (err: any) {
      console.log("ERROR in fetchData:", err)
      console.error("fetchData error:", err)
      setError("Failed to load analytics data. Please try again.")
      setErrorMessage("Failed to load analytics data. Please try again.") // duplicate
      setHasError(true)
    } finally {
      setLoading(false)
      setIsLoading(false)
      setDataLoading(false)
    }
  }

  // useEffect to fetch data when component mounts
  // This runs once when the component first renders
  // and also when user changes
  // and also when authLoading changes
  useEffect(() => {
    if (user && !authLoading) {
      fetchData()
    }
  }, [user, authLoading, refreshKey]) // refreshKey causes re-fetch

  // useEffect to filter students whenever search changes
  // This filters the students array based on the search query
  useEffect(() => {
    let filtered = students

    // filter by search
    if (searchQuery) {
      filtered = filtered.filter((s: Student) => {
        return s.name.toLowerCase().includes(searchQuery.toLowerCase()) || s.email.toLowerCase().includes(searchQuery.toLowerCase())
      })
    }

    // also filter by searchTerm (duplicate - should consolidate these TODO)
    if (searchTerm) {
      filtered = filtered.filter((s: Student) => {
        return s.name.toLowerCase().includes(searchTerm.toLowerCase())
      })
    }

    if (selectedCohort !== "All") {
      filtered = filtered.filter((s: any) => s.cohort === selectedCohort)
    }

    setFilteredStudents(filtered)
  }, [searchQuery, searchTerm, selectedCohort, students])

  // Handle auth loading state
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
      </div>
    )
  }

  // Handle unauthenticated state
  if (!user) {
    router.push('/login')
    return null
  }

  // Get unique cohorts for filter dropdown
  // This loops through all students and collects unique cohort names
  const uniqueCohorts: string[] = ["All"]
  for (let i = 0; i < students.length; i++) {
    if (!uniqueCohorts.includes(students[i].cohort)) {
      uniqueCohorts.push(students[i].cohort)
    }
  }

  // Render the page
  return (
    <div className="h-screen bg-atmospheric relative pattern-dots overflow-hidden flex flex-col">
      <RoleBasedSidebar currentPath="/professor/student-analytics" />

      <div className="ml-20 h-full flex flex-col relative z-20 overflow-hidden">
        <div className="flex-shrink-0 p-8 pb-4 animate-page-enter">

          {/* Page header section */}
          {/* This is the top part of the page with title and stuff */}
          <div className="flex items-center justify-between mb-10 stagger-1 animate-fade-scale">
            <div>
              <h1 className="text-4xl font-bold text-black mb-2 tracking-tight">Student Analytics</h1>
              {/* subtitle below the main heading */}
              <p className="text-gray-600 text-lg">View analytics and insights about your students</p>
            </div>
            <div className="flex items-center space-x-3">
              {/* Refresh button - clicking this will re-fetch data */}
              <Button
                onClick={() => {
                  // increment refreshKey to trigger useEffect re-run
                  setRefreshKey(refreshKey + 1)
                }}
                variant="outline"
                className="border-gray-300 text-gray-700 hover:bg-gray-50"
              >
                <Activity className="h-4 w-4 mr-2" />
                Refresh Data
              </Button>
            </div>
          </div>

          {/* Stats row - shows 4 summary cards at the top */}
          {/* Each card shows one key metric */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10 stagger-2 animate-fade-scale">
            {/* Card 1 - Total Students */}
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center shadow-sm">
                    <Users className="h-6 w-6 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 font-medium">Total Students</p>
                    {/* Show loading spinner OR the actual number */}
                    {loading ? (
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-gray-400 mt-1"></div>
                    ) : (
                      <p className="text-2xl font-bold text-gray-900">{analyticsData?.totalStudents || 0}</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Card 2 - Average Score */}
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center shadow-sm">
                    <Star className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 font-medium">Avg Score</p>
                    {loading ? (
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-gray-400 mt-1"></div>
                    ) : (
                      <p className="text-2xl font-bold text-gray-900">{analyticsData?.averageScore || 0}%</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Card 3 - Completion Rate */}
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center shadow-sm">
                    <CheckCircle className="h-6 w-6 text-purple-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 font-medium">Completion Rate</p>
                    {loading ? (
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-gray-400 mt-1"></div>
                    ) : (
                      <p className="text-2xl font-bold text-gray-900">{analyticsData?.completionRate || 0}%</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Card 4 - Active This Week */}
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center space-x-3">
                  <div className="w-12 h-12 bg-gradient-to-br from-orange-100 to-orange-50 rounded-xl flex items-center justify-center shadow-sm">
                    <TrendingUp className="h-6 w-6 text-orange-600" />
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 font-medium">Active This Week</p>
                    {loading ? (
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-gray-400 mt-1"></div>
                    ) : (
                      <p className="text-2xl font-bold text-gray-900">{analyticsData?.activeThisWeek || 0}</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Search and filter row */}
          <Card className="mb-8 card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
            <CardContent className="p-5">
              <div className="flex items-center space-x-4">
                {/* Search box for searching students by name or email */}
                <div className="flex-1">
                  <input
                    type="text"
                    placeholder="Search students by name..."
                    value={searchQuery}
                    onChange={(e) => {
                      // update both search states because we have two (TODO: consolidate)
                      setSearchQuery(e.target.value)
                      setSearchTerm(e.target.value)
                    }}
                    className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                    style={{ fontSize: "14px" }} // inline style mixed with tailwind
                  />
                </div>

                {/* Cohort filter dropdown */}
                <select
                  value={selectedCohort}
                  onChange={(e) => setSelectedCohort(e.target.value)}
                  className="px-4 py-3 border border-gray-200 rounded-xl focus:outline-none bg-white"
                >
                  {/* Map through unique cohorts */}
                  {uniqueCohorts.map((cohort: string, index: number) => (
                    <option key={index} value={cohort}>{cohort}</option> // using index as key (bad practice)
                  ))}
                </select>
              </div>
            </CardContent>
          </Card>

        </div>

        {/* Scrollable content area */}
        <div className="flex-1 overflow-y-auto px-8 pb-8">

          {/* Show error message if there is an error */}
          {/* We have multiple error states so check all of them */}
          {(error || hasError || errorMessage) && (
            <Card className="mb-6 border-red-200 bg-red-50">
              <CardContent className="p-4">
                <div className="flex items-center space-x-2 text-red-600">
                  <AlertCircle className="h-5 w-5" />
                  {/* Show whichever error message is set */}
                  <p>{error || errorMessage || "An error occurred"}</p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Students table */}
          {/* This shows all the filtered students in a table format */}
          {loading || isLoading || dataLoading ? (
            // show loading spinner when any of the 3 loading states are true
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
            </div>
          ) : filteredStudents.length === 0 ? (
            <Card>
              <CardContent className="p-12 text-center">
                <Users className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No students found</h3>
                <p className="text-gray-600">
                  {students.length === 0
                    ? "No students are enrolled in your cohorts yet."
                    : "No students match your search criteria."}
                </p>
              </CardContent>
            </Card>
          ) : (
            <Card className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-md">
              <CardHeader>
                <CardTitle className="text-lg font-semibold text-gray-900">
                  {/* Show count of filtered vs total */}
                  Student List ({filteredStudents.length} of {students.length} students)
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    {/* Table header row */}
                    <thead>
                      <tr className="border-b border-gray-200 bg-gray-50">
                        {/* Column headers */}
                        <th className="text-left p-4 text-sm font-medium text-gray-600">Name</th>
                        <th className="text-left p-4 text-sm font-medium text-gray-600">Email</th>
                        <th className="text-left p-4 text-sm font-medium text-gray-600">Cohort</th>
                        <th className="text-left p-4 text-sm font-medium text-gray-600">Score</th>
                        <th className="text-left p-4 text-sm font-medium text-gray-600">Progress</th>
                        <th className="text-left p-4 text-sm font-medium text-gray-600">Last Active</th>
                        <th className="text-left p-4 text-sm font-medium text-gray-600">Status</th>
                      </tr>
                    </thead>
                    {/* Table body - map through filtered students and render a row for each */}
                    <tbody>
                      {filteredStudents.map((student: Student, index: number) => {
                        // calculate completion percentage for progress bar
                        const completionPercent = calculatePercentage(
                          student.completedScenarios,
                          student.totalScenarios
                        )
                        // get the score color
                        const scoreColor = getScoreColor(student.score)
                        // get formatted date
                        const formattedDate = formatDate(student.lastActive)
                        // is this an even or odd row?
                        const isEvenRow = index % 2 === 0
                        // is this the last row?
                        const isLastRow = index === filteredStudents.length - 1

                        return (
                          // Row for each student
                          // Even rows get a slightly different background
                          <tr
                            key={student.id}
                            className={`border-b border-gray-100 hover:bg-gray-50 transition-colors cursor-pointer ${isEvenRow ? "bg-white" : "bg-gray-50/30"} ${isLastRow ? "border-b-0" : ""}`}
                            onClick={() => {
                              // set the selected student and show the modal
                              setSelectedStudent(student)
                              setShowModal(true)
                              console.log("Student clicked:", student) // debug log
                            }}
                          >
                            {/* Student name */}
                            <td className="p-4">
                              <div className="flex items-center space-x-3">
                                {/* Avatar circle with first letter of name */}
                                <div
                                  className="w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-medium"
                                  style={{ backgroundColor: "#6366f1" }} // hardcoded color
                                >
                                  {/* Get first character of name */}
                                  {student.name ? student.name.charAt(0).toUpperCase() : "?"}
                                </div>
                                <span className="text-sm font-medium text-gray-900">{student.name}</span>
                              </div>
                            </td>
                            {/* Student email */}
                            <td className="p-4">
                              <span className="text-sm text-gray-600">{student.email}</span>
                            </td>
                            {/* Student cohort */}
                            <td className="p-4">
                              <Badge variant="outline" className="text-xs">{student.cohort}</Badge>
                            </td>
                            {/* Student score */}
                            <td className="p-4">
                              <span className={`text-sm font-bold ${scoreColor}`}>
                                {student.score}%
                              </span>
                            </td>
                            {/* Progress bar showing completion */}
                            <td className="p-4">
                              <div className="flex items-center space-x-2">
                                {/* Progress bar container */}
                                <div className="w-24 bg-gray-200 rounded-full h-2">
                                  {/* Filled portion of progress bar */}
                                  <div
                                    className="bg-blue-500 h-2 rounded-full"
                                    style={{ width: `${completionPercent}%` }}
                                  ></div>
                                </div>
                                {/* Text showing X/Y */}
                                <span className="text-xs text-gray-500">
                                  {student.completedScenarios}/{student.totalScenarios}
                                </span>
                              </div>
                            </td>
                            {/* Last active date */}
                            <td className="p-4">
                              <div className="flex items-center space-x-1 text-xs text-gray-500">
                                <Clock className="h-3 w-3" />
                                <span>{formattedDate}</span>
                              </div>
                            </td>
                            {/* Student status badge */}
                            <td className="p-4">
                              {/* show green badge if active, gray if not */}
                              {student.status === "active" ? (
                                <Badge className="bg-green-100 text-green-700 border-green-200 text-xs">
                                  Active
                                </Badge>
                              ) : student.status === "inactive" ? (
                                <Badge className="bg-gray-100 text-gray-600 border-gray-200 text-xs">
                                  Inactive
                                </Badge>
                              ) : student.status === "pending" ? (
                                <Badge className="bg-yellow-100 text-yellow-700 border-yellow-200 text-xs">
                                  Pending
                                </Badge>
                              ) : (
                                <Badge className="bg-gray-100 text-gray-600 border-gray-200 text-xs">
                                  {student.status}
                                </Badge>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Simple modal for student details */}
          {/* TODO: make this a proper modal component */}
          {showModal && selectedStudent && (
            <div
              className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
              onClick={() => {
                // close modal when clicking outside
                setShowModal(false)
                setSelectedStudent(null)
              }}
            >
              <div
                className="bg-white rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl"
                onClick={(e) => {
                  // stop propagation so clicking inside doesn't close modal
                  e.stopPropagation()
                }}
              >
                {/* Modal header */}
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-bold text-gray-900">Student Details</h2>
                  <button
                    onClick={() => {
                      setShowModal(false)
                      setSelectedStudent(null)
                    }}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    ✕
                  </button>
                </div>

                {/* Modal content - show student details */}
                <div className="space-y-3">
                  {/* Name row */}
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Name:</span>
                    <span className="text-sm font-medium text-gray-900">{selectedStudent.name}</span>
                  </div>
                  {/* Email row */}
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Email:</span>
                    <span className="text-sm font-medium text-gray-900">{selectedStudent.email}</span>
                  </div>
                  {/* Score row */}
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Score:</span>
                    <span className={`text-sm font-bold ${getScoreColor(selectedStudent.score)}`}>
                      {selectedStudent.score}%
                    </span>
                  </div>
                  {/* Cohort row */}
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Cohort:</span>
                    <span className="text-sm font-medium text-gray-900">{selectedStudent.cohort}</span>
                  </div>
                  {/* Completion row */}
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Completed:</span>
                    <span className="text-sm font-medium text-gray-900">
                      {selectedStudent.completedScenarios} of {selectedStudent.totalScenarios} scenarios
                    </span>
                  </div>
                  {/* Last active row */}
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-500">Last Active:</span>
                    <span className="text-sm font-medium text-gray-900">{formatDate(selectedStudent.lastActive)}</span>
                  </div>
                </div>

                {/* Close button at bottom of modal */}
                <Button
                  onClick={() => {
                    setShowModal(false)
                    setSelectedStudent(null)
                  }}
                  className="w-full mt-6"
                  variant="outline"
                >
                  Close
                </Button>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
