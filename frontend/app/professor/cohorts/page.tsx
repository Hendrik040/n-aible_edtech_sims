"use client"

import { useState, useEffect, useRef } from "react"
import { debugLog } from "@/lib/debug"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import CohortEditModal, { CohortEditFormValues } from "@/components/CohortEditModal"
import {
  Search,
  Filter,
  Plus,
  Calendar,
  Users,
  BookOpen,
  LogOut,
  X,
  ChevronDown,
  Trash2,
  ArrowLeft,
  Copy,
  Settings,
  CheckCircle,
  Clock,
  Pencil,
  MoreVertical
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"
import InviteStudentsModal from "@/components/InviteStudentsModal"
import InviteLinkModal from "@/components/InviteLinkModal"
import ProfessorGradingModal from "@/components/ProfessorGradingModal"
import { useToast } from "@/hooks/use-toast"

export default function Cohorts() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  // State for cohorts data
  const [cohorts, setCohorts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // OPTIMIZATION: Prevent duplicate fetches (React StrictMode protection)
  const fetchInitiatedRef = useRef(false)
  
  const [activeFilter, setActiveFilter] = useState("All")
  const [searchTerm, setSearchTerm] = useState("")
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showSemesterDropdown, setShowSemesterDropdown] = useState(false)
  const [showYearDropdown, setShowYearDropdown] = useState(false)
  const [showStatusDropdown, setShowStatusDropdown] = useState(false)
  
  // Form state for create cohort modal
  const [formData, setFormData] = useState({
    cohortName: "",
    description: "",
    courseCode: "",
    semester: "",
    year: "",
    maxStudents: "",
    autoApprove: true,
    allowSelfEnrollment: false,
    isActive: true, // Add status field
    tags: [] as string[] // Array for tags
  })
  const [showEditModal, setShowEditModal] = useState(false)
  const [updatingCohort, setUpdatingCohort] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [cohortToDelete, setCohortToDelete] = useState<any>(null)
  const [showTagDropdown, setShowTagDropdown] = useState(false)
  
  // State for inline cohort details
  const [selectedCohort, setSelectedCohort] = useState<any>(null)
  const [cohortDetails, setCohortDetails] = useState<any>(null)
  const [cohortStudents, setCohortStudents] = useState<any[]>([])
  const [cohortSimulations, setCohortSimulations] = useState<any[]>([])
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [activeTab, setActiveTab] = useState('students')
  const [studentSearchTerm, setStudentSearchTerm] = useState('')
  const [studentFilter, setStudentFilter] = useState('all')
  
  // Simulation assignment state
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [availableScenarios, setAvailableScenarios] = useState<any[]>([])
  const [selectedScenario, setSelectedScenario] = useState<any>(null)
  const [dueDate, setDueDate] = useState("")
  const [isRequired, setIsRequired] = useState(true)
  const [assigning, setAssigning] = useState(false)
  const [deletingSimulation, setDeletingSimulation] = useState<number | null>(null)
  
  // Invite students modal state
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [showInviteLinkModal, setShowInviteLinkModal] = useState(false)
  
  // Student removal state
  const [removingStudentId, setRemovingStudentId] = useState<number | null>(null)
  const [studentMenuOpen, setStudentMenuOpen] = useState<number | null>(null)
  const [selectedStudents, setSelectedStudents] = useState<Set<number>>(new Set())
  const [showBulkRemoveModal, setShowBulkRemoveModal] = useState(false)
  const [removingBulk, setRemovingBulk] = useState(false)
  
  // Student progress view state
  const [showStudentProgressView, setShowStudentProgressView] = useState(false)
  const [selectedSimulation, setSelectedSimulation] = useState<any>(null)
  const [studentInstances, setStudentInstances] = useState<any[]>([])
  const [loadingInstances, setLoadingInstances] = useState(false)
  
  // Completion counts for each simulation
  const [simulationCompletionCounts, setSimulationCompletionCounts] = useState<Record<number, { completed: number, total: number }>>({})
  
  // Grading modal state
  const [showGradingModal, setShowGradingModal] = useState(false)
  const [selectedInstanceForGrading, setSelectedInstanceForGrading] = useState<number | null>(null)

  const { toast } = useToast()
  
  // Close all dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      // Check if click is inside any dropdown or button that opens a dropdown
      const isInsideDropdown = target.closest('[data-dropdown]') || 
                               target.closest('[data-dropdown-button]')
      
      if (!isInsideDropdown) {
        setStudentMenuOpen(null)
        setShowStatusDropdown(false)
        setShowSemesterDropdown(false)
        setShowYearDropdown(false)
        setShowTagDropdown(false)
      }
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [])

  // Clear selected students when tab changes or filters change
  useEffect(() => {
    setSelectedStudents(new Set())
  }, [activeTab, studentSearchTerm, studentFilter])
  
  // Fetch available scenarios for assignment
  const fetchAvailableScenarios = async () => {
    try {
      const scenarios = await apiClient.getScenarios()
      setAvailableScenarios(scenarios)
    } catch (error) {
      console.error('Failed to fetch scenarios:', error)
    }
  }

  // Handle simulation assignment
  const handleAssignSimulation = async () => {
    if (!selectedScenario || !selectedCohort) return
    
    try {
      setAssigning(true)
      
      // Create the assignment data
      const assignmentData = {
        simulation_id: selectedScenario.id,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
        is_required: isRequired
      }
      
      // Call the API to assign simulation to cohort
      await apiClient.assignSimulationToCohort(selectedCohort.id, assignmentData)
      
      // Refresh simulations data
      const updatedSimulations = await apiClient.getCohortSimulations(selectedCohort.unique_id)
      setCohortSimulations(updatedSimulations)
      
      // Close modal and reset form
      setShowAssignModal(false)
      setSelectedScenario(null)
      setDueDate("")
      setIsRequired(true)
      
    } catch (error) {
      console.error('Failed to assign simulation:', error)
      alert('Failed to assign simulation. Please try again.')
    } finally {
      setAssigning(false)
    }
  }

  // Handle simulation deletion
  const handleDeleteSimulation = async (simulationAssignmentId: number) => {
    if (!selectedCohort) return
    
    try {
      setDeletingSimulation(simulationAssignmentId)
      
      // Call the API to remove simulation from cohort
      await apiClient.removeSimulationFromCohort(selectedCohort.id, simulationAssignmentId)
      
      // Refresh simulations data
      const updatedSimulations = await apiClient.getCohortSimulations(selectedCohort.unique_id)
      setCohortSimulations(updatedSimulations)
      
    } catch (error) {
      console.error('Failed to delete simulation:', error)
      alert('Failed to delete simulation. Please try again.')
    } finally {
      setDeletingSimulation(null)
    }
  }

  // Handle viewing student progress for a simulation
  const handleViewStudentProgress = async (simulation: any) => {
    try {
      setLoadingInstances(true)
      setSelectedSimulation(simulation)
      setShowStudentProgressView(true)
      
      // Fetch student instances for this simulation assignment
      const instances = await apiClient.getSimulationAssignmentInstances(simulation.id)
      
      // Filter to only show instances from students currently in the cohort
      const approvedStudentIds = new Set(
        cohortStudents.filter(s => s.status === 'approved').map(s => s.student_id)
      )
      const currentStudentInstances = instances.filter((instance: any) => 
        approvedStudentIds.has(instance.student_id)
      )
      
      setStudentInstances(currentStudentInstances)
    } catch (error) {
      console.error('Failed to fetch student instances:', error)
      alert('Failed to load student progress data. Please try again.')
      setShowStudentProgressView(false)
    } finally {
      setLoadingInstances(false)
    }
  }

  // Handle removing a student from the cohort
  const handleRemoveStudent = async (studentId: number, studentName: string) => {
    if (!confirm(`Are you sure you want to remove ${studentName} from this cohort?`)) {
      return
    }
    
    try {
      setRemovingStudentId(studentId)
      setStudentMenuOpen(null)
      
      const cohortIdentifier = selectedCohort.unique_id ?? selectedCohort.id
      await apiClient.removeStudentFromCohort(cohortIdentifier, studentId)
      
      // Refresh the student list
      const students = await apiClient.getCohortStudents(selectedCohort.unique_id)
      setCohortStudents(students)
      
      // If viewing student progress, filter out the removed student immediately
      if (showStudentProgressView && studentInstances.length > 0) {
        const updatedInstances = studentInstances.filter(
          (instance: any) => instance.student_id !== studentId
        )
        setStudentInstances(updatedInstances)
      }
      
      // Refresh completion counts since total students changed
      if (cohortSimulations.length > 0) {
        await fetchSimulationCompletionCounts(cohortSimulations, students)
      }
      
      alert(`${studentName} has been removed from the cohort.`)
    } catch (error) {
      console.error('Failed to remove student:', error)
      alert('Failed to remove student. Please try again.')
    } finally {
      setRemovingStudentId(null)
    }
  }

  // Handle selecting/deselecting students
  const handleToggleStudent = (studentId: number) => {
    setSelectedStudents(prev => {
      const newSet = new Set(prev)
      if (newSet.has(studentId)) {
        newSet.delete(studentId)
      } else {
        newSet.add(studentId)
      }
      return newSet
    })
  }

  // Handle select all students
  const handleSelectAll = () => {
    const filteredStudents = cohortStudents?.filter(student => {
      const matchesSearch = student.student_name.toLowerCase().includes(studentSearchTerm.toLowerCase()) ||
                           student.student_email.toLowerCase().includes(studentSearchTerm.toLowerCase())
      
      if (studentFilter === 'all') return matchesSearch
      if (studentFilter === 'active') return student.status === 'approved' && matchesSearch
      if (studentFilter === 'pending') return student.status === 'pending' && matchesSearch
      if (studentFilter === 'inactive') return student.status === 'inactive' && matchesSearch
      return matchesSearch
    }) || []
    
    if (selectedStudents.size === filteredStudents.length) {
      setSelectedStudents(new Set())
    } else {
      setSelectedStudents(new Set(filteredStudents.map(s => s.student_id)))
    }
  }

  // Handle bulk removal
  const handleBulkRemove = async () => {
    if (selectedStudents.size === 0) return
    
    try {
      setRemovingBulk(true)
      const cohortIdentifier = selectedCohort.unique_id ?? selectedCohort.id
      const studentIds = Array.from(selectedStudents)
      
      await apiClient.removeMultipleStudentsFromCohort(cohortIdentifier, studentIds)
      
      // Refresh the student list
      const students = await apiClient.getCohortStudents(selectedCohort.unique_id)
      setCohortStudents(students)
      
      // Clear selection
      setSelectedStudents(new Set())
      setShowBulkRemoveModal(false)
      
      // Refresh completion counts since total students changed
      if (cohortSimulations.length > 0) {
        await fetchSimulationCompletionCounts(cohortSimulations, students)
      }
      
      alert(`${studentIds.length} student(s) have been removed from the cohort.`)
    } catch (error) {
      console.error('Failed to remove students:', error)
      alert('Failed to remove students. Please try again.')
    } finally {
      setRemovingBulk(false)
    }
  }

  // Handle going back to simulations list
  const handleBackToSimulations = async () => {
    setShowStudentProgressView(false)
    setSelectedSimulation(null)
    setStudentInstances([])
    
    // Refresh completion counts to show updated data
    if (cohortSimulations.length > 0) {
      await fetchSimulationCompletionCounts(cohortSimulations)
    }
  }

  // Fetch cohort details when a cohort is selected
  const fetchCohortDetails = async (cohortId: number | string) => {
    try {
      setLoadingDetails(true)
      // Find the cohort in the list to get its unique_id; if not present yet, fall back to using the id directly
      const cohort = cohorts.find(c => c.id === cohortId || c.unique_id === cohortId)
      const identifier = cohort ? cohort.unique_id : String(cohortId)
      const details = await apiClient.getCohort(identifier)
      setCohortDetails(details)
      
      // OPTIMIZATION: Use data already returned by getCohort() instead of making separate calls
      // This reduces requests from 4 to 1 when clicking a cohort
      const students = details.students || []
      const simulations = details.simulations || []
      
      setCohortStudents(students)
      setCohortSimulations(simulations)
      
      // Fetch completion counts for each simulation (pass students directly)
      await fetchSimulationCompletionCounts(simulations, students)
    } catch (error) {
      console.error('Failed to fetch cohort details:', error)
    } finally {
      setLoadingDetails(false)
    }
  }
  
  // Fetch completion counts for simulations
  // OPTIMIZATION: Uses batched endpoint instead of N+1 API calls
  const fetchSimulationCompletionCounts = async (simulations: any[], students?: any[]) => {
    try {
      // Get cohort ID from selected cohort
      if (!selectedCohort?.id) {
        console.warn('No cohort selected, skipping completion fetch')
        return
      }
      
      // Get total number of approved students for initial display
      const studentsToUse = students || cohortStudents
      const approvedStudentsCount = studentsToUse.filter(s => s.status === 'approved').length
      
      // Immediately set initial counts with correct totals (0 completed for now)
      const initialCounts: Record<number, { completed: number, total: number }> = {}
      simulations.forEach((simulation) => {
        initialCounts[simulation.id] = {
          completed: 0,
          total: approvedStudentsCount
        }
      })
      setSimulationCompletionCounts(initialCounts)
      
      // OPTIMIZATION: Single batched API call instead of N calls
      // This reduces requests from N to 1, saving ~300ms per simulation
      const summary = await apiClient.getCohortCompletionSummary(selectedCohort.id)
      
      // Build final counts object from batched response
      const finalCounts: Record<number, { completed: number, total: number }> = {}
      summary.simulations.forEach(sim => {
        finalCounts[sim.simulation_assignment_id] = {
          completed: sim.completed_count,
          total: sim.total_students
        }
      })
      
      // Update state once with all data
      setSimulationCompletionCounts(finalCounts)
    } catch (error) {
      console.error('Failed to fetch completion counts:', error)
    }
  }

  // Fetch cohorts data on component mount
  // OPTIMIZATION: Uses ref to prevent duplicate fetches in React StrictMode
  useEffect(() => {
    // Prevent duplicate fetches (StrictMode protection)
    if (fetchInitiatedRef.current) {
      return
    }

    const fetchCohorts = async () => {
      fetchInitiatedRef.current = true  // Mark as initiated before async calls
      
      try {
        setLoading(true)
        setError(null)
        const cohortsData = await apiClient.getCohorts()
        setCohorts(cohortsData)
        // OPTIMIZATION: Don't auto-load cohort details on mount
        // User clicks a cohort to see details - reduces initial requests from 9+ to 1
      } catch (err) {
        console.error('Error fetching cohorts:', err)
        setError(err instanceof Error ? err.message : 'Failed to load cohorts')
      } finally {
        setLoading(false)
      }
    }
    
    fetchCohorts()
  }, [])

  // Removed proactive refresh on page load to improve performance
  // The refresh can be triggered manually when needed

  // Listen for simulation status changes from dashboard
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'simulationStatusChanged' && e.newValue) {
        try {
          const changeData = JSON.parse(e.newValue)
          debugLog('Simulation status changed, refreshing cohorts data:', changeData)
          
          // Refresh cohorts data to get updated simulation statuses
          const refreshCohorts = async () => {
            try {
              const cohortsData = await apiClient.getCohorts()
              setCohorts(cohortsData)
              
              // If we have a selected cohort, refresh its simulation data too
              if (selectedCohort) {
                const updatedSimulations = await apiClient.getCohortSimulations(selectedCohort.unique_id)
                setCohortSimulations(updatedSimulations)
              }
            } catch (error) {
              console.warn('Failed to refresh cohorts data after simulation status change:', error)
            }
          }
          
          refreshCohorts()
          
          // Clear the notification
          localStorage.removeItem('simulationStatusChanged')
        } catch (error) {
          console.error('Failed to parse simulation status change notification:', error)
        }
      }
    }
    
    window.addEventListener('storage', handleStorageChange)
    
    return () => {
      window.removeEventListener('storage', handleStorageChange)
    }
  }, [selectedCohort])

  // Handle redirect when user is not authenticated
  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/")
    }
  }, [user, authLoading, router])
  
  // Show loading while auth is being checked
  if (authLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black mx-auto mb-4"></div>
          <p className="text-black">Loading...</p>
        </div>
      </div>
    )
  }

  // If no user, show redirecting message (navigation handled in useEffect)
  if (!user) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-black">Redirecting...</p>
        </div>
      </div>
    )
  }

  // Show loading while fetching cohorts
  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black mx-auto mb-4"></div>
          <p className="text-black">Loading cohorts...</p>
        </div>
      </div>
    )
  }

  // Show error if failed to load cohorts
  if (error) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-600 mb-4">{error}</p>
          <Button onClick={() => window.location.reload()}>
            Try Again
          </Button>
        </div>
      </div>
    )
  }

  const handleLogout = () => {
    logout()
    router.push("/")
  }

  const handleInputChange = (field: string, value: string | boolean) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }))
  }

  const handleOpenEditModal = () => {
    if (!cohortDetails) {
      alert('Please select a cohort before trying to edit it.')
      return
    }

    setShowEditModal(true)
  }

  const handleCloseEditModal = () => {
    setShowEditModal(false)
    setUpdatingCohort(false)
  }

  const handleUpdateCohort = async (formValues: CohortEditFormValues) => {
    if (!selectedCohort) {
      alert('Please select a cohort before trying to edit it.')
      return
    }

    try {
      setUpdatingCohort(true)
      const cohortIdentifier = selectedCohort.unique_id ?? selectedCohort.id

      const cohortData = {
        title: formValues.cohortName,
        description: formValues.description || null,
        course_code: formValues.courseCode || null,
        semester: formValues.semester || null,
        year: formValues.year ? parseInt(formValues.year) : null,
        max_students: formValues.maxStudents ? parseInt(formValues.maxStudents) : null,
        auto_approve: formValues.autoApprove,
        allow_self_enrollment: formValues.allowSelfEnrollment,
        is_active: formValues.isActive
      }

      const updatedCohort = await apiClient.updateCohort(String(cohortIdentifier), cohortData)
      const normalizedUpdatedCohort = {
        ...updatedCohort,
        unique_id: selectedCohort.unique_id ?? updatedCohort.unique_id ?? cohortIdentifier
      }

      setCohorts(prev => prev.map(cohort => (
        cohort.id === normalizedUpdatedCohort.id ? { ...cohort, ...normalizedUpdatedCohort } : cohort
      )))

      setSelectedCohort((prev: any) => {
        if (!prev) return prev
        return prev.id === normalizedUpdatedCohort.id ? { ...prev, ...normalizedUpdatedCohort } : prev
      })

      setCohortDetails((prev: any) => {
        if (!prev) return prev
        return prev.id === normalizedUpdatedCohort.id ? { ...prev, ...normalizedUpdatedCohort } : prev
      })

      toast({
        title: 'Cohort updated',
        description: 'Your changes have been saved.',
      })
      handleCloseEditModal()
    } catch (err) {
      console.error('Error updating cohort:', err)
      alert('Failed to update cohort. Please try again.')
    } finally {
      setUpdatingCohort(false)
    }
  }

  const handleSelectTag = (tag: string) => {
      setFormData(prev => ({
        ...prev,
      tags: [tag] // Only allow one tag at a time
      }))
    setShowTagDropdown(false)
  }

  const handleRemoveTag = (tagToRemove: string) => {
    setFormData(prev => ({
      ...prev,
      tags: prev.tags.filter(tag => tag !== tagToRemove)
    }))
  }

  const handleCohortClick = async (cohort: any) => {
    try {
      setLoadingDetails(true)
      setSelectedCohort(cohort)
      
      // Fetch detailed cohort data
      const [details, students, simulations] = await Promise.all([
        apiClient.getCohort(cohort.unique_id || cohort.id),
        apiClient.getCohortStudents(cohort.unique_id || cohort.id).catch(() => []),
        apiClient.getCohortSimulations(cohort.unique_id || cohort.id).catch(() => [])
      ])
      
      setCohortDetails(details)
      setCohortStudents(students)
      setCohortSimulations(simulations)
    } catch (err) {
      console.error('Error fetching cohort details:', err)
      setError('Failed to load cohort details')
    } finally {
      setLoadingDetails(false)
    }
  }

  const handleBackToList = () => {
    setSelectedCohort(null)
    setCohortDetails(null)
    setCohortStudents([])
    setCohortSimulations([])
  }

  const handleCreateCohort = async () => {
    // Validate required fields before making API call
    if (!formData.cohortName.trim()) {
      setError('Cohort name is required')
      return
    }
    
    try {
      setLoading(true)
      setError(null) // Clear any previous errors
      
      // Transform form data to match backend schema
      const cohortData = {
        title: formData.cohortName,
        description: formData.description || null,
        course_code: formData.courseCode || null,
        semester: formData.semester || null,
        year: formData.year ? parseInt(formData.year) : null,
        max_students: formData.maxStudents ? parseInt(formData.maxStudents) : null,
        auto_approve: formData.autoApprove,
        allow_self_enrollment: formData.allowSelfEnrollment,
        is_active: formData.isActive
      }
      
      const newCohort = await apiClient.createCohort(cohortData)
      
      // Add the new cohort with proper counts (they start at 0)
      const cohortWithCounts = {
        ...newCohort,
        student_count: 0,
        simulation_count: 0
      }
      
      setCohorts(prev => [...prev, cohortWithCounts])
      
      // Reset form and close modal
      setFormData({
        cohortName: "",
        description: "",
        courseCode: "",
        semester: "",
        year: "",
        maxStudents: "",
        autoApprove: true,
        allowSelfEnrollment: false,
        isActive: true,
        tags: []
      })
      setShowCreateModal(false)
    } catch (err) {
      console.error('Error creating cohort:', err)
      setError(err instanceof Error ? err.message : 'Failed to create cohort')
    } finally {
      setLoading(false)
    }
  }

  const handleCloseModal = () => {
    setShowCreateModal(false)
    setShowSemesterDropdown(false)
    setShowYearDropdown(false)
    setShowTagDropdown(false)
    setShowStatusDropdown(false)
    // Reset form when closing
    setFormData({
      cohortName: "",
      description: "",
      courseCode: "",
      semester: "",
      year: "",
      maxStudents: "",
      autoApprove: true,
      allowSelfEnrollment: false,
      isActive: true,
      tags: []
    })
  }

  const handleDeleteCohort = async () => {
    if (!cohortToDelete) return
    
    try {
      setLoading(true)
      setError(null)
      await apiClient.deleteCohort(cohortToDelete.unique_id || cohortToDelete.id.toString())
      setCohorts(prev => prev.filter(cohort => cohort.id !== cohortToDelete.id))
      setShowDeleteModal(false)
      setCohortToDelete(null)
    } catch (err) {
      console.error('Error deleting cohort:', err)
      setError(err instanceof Error ? err.message : 'Failed to delete cohort')
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteClick = (cohort: any, e: React.MouseEvent) => {
    e.preventDefault() // Prevent Link navigation
    e.stopPropagation() // Stop event bubbling
    setCohortToDelete(cohort)
    setShowDeleteModal(true)
  }

  // Filter cohorts based on active filter and search term
  const filteredCohorts = cohorts.filter(cohort => {
    const matchesSearch = cohort.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         (cohort.description && cohort.description.toLowerCase().includes(searchTerm.toLowerCase()))
    
    if (activeFilter === "All") {
      return matchesSearch
    } else if (activeFilter === "Active") {
      return cohort.is_active && matchesSearch
    } else if (activeFilter === "Draft") {
      return !cohort.is_active && matchesSearch
    }
    return matchesSearch
  })

  // Count cohorts by status
  const cohortCounts = {
    "All": cohorts.length,
    "Active": cohorts.filter(c => c.is_active).length,
    "Draft": cohorts.filter(c => !c.is_active).length
  }

  return (
    <div className="min-h-screen bg-atmospheric relative pattern-dots">
      {/* Fixed Sidebar */}
      <RoleBasedSidebar currentPath="/professor/cohorts" />

      {/* Main Content with left margin for sidebar */}
      <div className="ml-20 flex h-screen relative">
        {/* Middle Sidebar - Cohort Management */}
        <div className="w-96 bg-white/95 backdrop-blur-sm border-r border-gray-200/60 flex flex-col shadow-lg relative z-40 overflow-visible">
          {/* Header */}
          <div className="p-6 border-b border-gray-200/60 animate-page-enter relative z-50 overflow-visible">
            <div className="flex items-center justify-between mb-4 stagger-1 animate-fade-scale">
              <h1 className="text-3xl font-bold text-black tracking-tight">Cohorts</h1>
              <Button 
                onClick={() => setShowCreateModal(true)}
                className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold text-sm"
              >
                <Plus className="h-4 w-4 mr-2" />
                Create
              </Button>
            </div>
            
            {/* Search Bar */}
            <div className="relative mb-4 stagger-2 animate-fade-scale">
              <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search cohorts..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-12 pr-4 py-3 border border-gray-200/80 rounded-xl bg-white/80 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400/50 transition-all shadow-sm hover:shadow-md"
              />
            </div>
            
            {/* Filter Dropdown */}
            <div className="relative stagger-3 animate-fade-scale z-50 overflow-visible" data-dropdown>
              <Button 
                variant="outline" 
                data-dropdown-button
                onClick={(e) => {
                  e.stopPropagation()
                  setShowStatusDropdown(!showStatusDropdown)
                }}
                className="w-full bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-white/95 hover:border-gray-300 justify-start shadow-sm transition-all"
              >
                <Filter className="h-4 w-4 mr-2" />
                {activeFilter} ({cohortCounts[activeFilter as keyof typeof cohortCounts]})
                <ChevronDown className={`h-4 w-4 ml-auto transition-transform ${showStatusDropdown ? 'rotate-180' : ''}`} />
              </Button>
              
              {showStatusDropdown && (
                <div 
                  className="absolute z-[10000] w-full mt-1 bg-white/95 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-lg"
                  onClick={(e) => e.stopPropagation()}
                >
                  {Object.entries(cohortCounts).map(([filter, count]) => (
                    <button
                      key={filter}
                      onClick={(e) => {
                        e.stopPropagation()
                        setActiveFilter(filter)
                        setShowStatusDropdown(false)
                      }}
                      className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50/80 first:rounded-t-xl last:rounded-b-xl transition-all ${
                        activeFilter === filter
                          ? "bg-gradient-to-r from-slate-50 to-slate-100/50 text-black font-medium"
                          : "text-gray-700"
                      }`}
                    >
                      {filter} ({count})
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Cohort Listings */}
          <div className="flex-1 overflow-y-auto p-4 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-gray-100 hover:scrollbar-thumb-gray-400">
            <div className="space-y-4">
              {filteredCohorts.map((cohort, index) => {
                const staggerClass = index % 6 === 0 ? 'stagger-1' : index % 6 === 1 ? 'stagger-2' : index % 6 === 2 ? 'stagger-3' : index % 6 === 3 ? 'stagger-4' : index % 6 === 4 ? 'stagger-5' : 'stagger-6'
                return (
                <div 
                  key={cohort.id} 
                  onClick={() => handleCohortClick(cohort)}
                  className={`card-elevated border rounded-xl p-5 hover:shadow-lg transition-all duration-300 cursor-pointer ${staggerClass} animate-fade-scale ${
                    selectedCohort?.id === cohort.id 
                      ? 'border-slate-400/60 bg-gradient-to-br from-slate-50/60 to-slate-100/30 shadow-lg' 
                      : 'border-gray-200/60 bg-white/90 backdrop-blur-sm'
                  }`}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-gray-900 leading-tight hover:text-gray-700 mb-1">
                        {cohort.title}
                      </h3>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Badge className={`text-xs px-2 py-1 rounded-full transition-colors duration-200 ${
                        cohort.is_active 
                          ? 'bg-green-100 text-green-700 hover:bg-black hover:text-white' 
                          : 'bg-gray-100 text-gray-600 hover:bg-black hover:text-white'
                      }`}>
                        {cohort.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteClick(cohort, e)
                        }}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                        title="Delete cohort"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                    </div>
                    
                  <p className="text-sm text-gray-600 mb-4 leading-relaxed">
                    {cohort.description || 'No description provided'}
                    </p>
                    
                  {/* Stats and Date Row */}
                  <div className="flex items-center justify-between text-sm text-gray-600 mb-3">
                    <div className="flex items-center space-x-4">
                      <div className="flex items-center">
                        <Users className="h-4 w-4 mr-1.5" />
                        <span className="font-medium">{cohort.student_count || 0}</span>
                      </div>
                      <div className="flex items-center">
                        <BookOpen className="h-4 w-4 mr-1.5" />
                        <span className="font-medium">{cohort.simulation_count || 0}</span>
                      </div>
                    </div>
                    <div className="flex items-center">
                      <Calendar className="h-4 w-4 mr-1.5" />
                      <span>{new Date(cohort.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                    </div>
                    </div>
                    
                    {/* ID */}
                  <div className="text-xs text-gray-500 font-mono hover:bg-black hover:text-white px-2 py-1 rounded transition-colors duration-200 cursor-pointer">
                    ID: {cohort.unique_id || cohort.id}
                    </div>
                  </div>
                  )
                })}
            </div>
          </div>
        </div>

        {/* Main Content Area - Cohort Details or Empty State */}
        <div className="flex-1 bg-white/50 backdrop-blur-sm h-full relative">
          {selectedCohort && cohortDetails ? (
            <div className="h-full overflow-y-auto p-8 animate-page-enter">
              {/* Back Button */}
              <div className="mb-6 stagger-1 animate-fade-scale">
                <button
                  onClick={handleBackToList}
                  className="inline-flex items-center text-sm text-gray-600 hover:text-black transition-all px-3 py-2 rounded-lg hover:bg-white/50 backdrop-blur-sm"
                >
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Back to Cohorts
                </button>
              </div>

              {/* Cohort Header */}
              <div className="mb-8 stagger-2 animate-fade-scale">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h2 className="text-4xl font-bold text-black mb-3 tracking-tight">{cohortDetails.title}</h2>
                    <p className="text-gray-600 mb-4">{cohortDetails.description || 'No description provided'}</p>
                    
                    <div className="flex items-center space-x-4">
                      <Badge className="bg-gray-100 text-gray-700 text-xs px-2 py-1 hover:bg-black hover:text-white transition-colors duration-200 cursor-pointer">
                        ID: {cohortDetails.unique_id || cohortDetails.id}
                      </Badge>
                      <Badge className={`text-xs px-2 py-1 transition-colors duration-200 ${
                        cohortDetails.is_active 
                          ? 'bg-green-100 text-green-700 hover:bg-black hover:text-white' 
                          : 'bg-gray-100 text-gray-600 hover:bg-black hover:text-white'
                      }`}>
                        {cohortDetails.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                      <span className="text-sm text-gray-600">
                        Created {new Date(cohortDetails.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                      </span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex items-center space-x-3">
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={() => setShowInviteLinkModal(true)}
                      className="border-gray-300 text-gray-700 hover:bg-gray-50"
                    >
                      <Copy className="h-4 w-4 mr-2" />
                      Copy Invite Link
                    </Button>
                    <Button 
                      size="sm"
                      className="btn-gradient-green text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                      onClick={() => setShowInviteModal(true)}
                    >
                      <Users className="h-4 w-4 mr-2" />
                      Invite Students
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={handleOpenEditModal}
                      className="border-gray-300 text-gray-700 hover:bg-gray-50"
                    >
                      <Pencil className="h-4 w-4 mr-2" />
                      Edit Cohort
                    </Button>
                  </div>
                </div>
              </div>

              {/* Metrics Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8 stagger-1 animate-fade-scale">
                {/* Total Students */}
                <div className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl p-6 shadow-md">
                  <div className="flex items-center h-full">
                    {/* Left Section - Icon */}
                    <div className="w-12 h-12 bg-gradient-to-br from-slate-100 to-slate-50 rounded-xl flex items-center justify-center mr-4 flex-shrink-0 shadow-sm">
                      <Users className="h-6 w-6 text-slate-600" />
                    </div>
                    {/* Right Section - Text Stack */}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gray-600 font-medium truncate hover:whitespace-normal hover:overflow-visible transition-all duration-200">Total Students</div>
                      <div className="text-2xl font-bold text-gray-900 truncate hover:whitespace-normal hover:overflow-visible transition-all duration-200">{cohortStudents?.length || 0}</div>
                    </div>
                  </div>
                </div>

                {/* Active Students */}
                <div className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl p-6 shadow-md">
                  <div className="flex items-center h-full">
                    {/* Left Section - Icon */}
                    <div className="w-12 h-12 bg-gradient-to-br from-green-100 to-green-50 rounded-xl flex items-center justify-center mr-4 flex-shrink-0 shadow-sm">
                      <CheckCircle className="h-6 w-6 text-green-600" />
                    </div>
                    {/* Right Section - Text Stack */}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gray-600 font-medium truncate hover:whitespace-normal hover:overflow-visible transition-all duration-200">Active Students</div>
                      <div className="text-2xl font-bold text-gray-900 truncate hover:whitespace-normal hover:overflow-visible transition-all duration-200">
                        {cohortStudents?.filter(student => student.status === 'approved').length || 0}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Simulations */}
                <div className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl p-6 shadow-md">
                  <div className="flex items-center h-full">
                    {/* Left Section - Icon */}
                    <div className="w-12 h-12 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center mr-4 flex-shrink-0 shadow-sm">
                      <BookOpen className="h-6 w-6 text-purple-600" />
                    </div>
                    {/* Right Section - Text Stack */}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gray-600 font-medium truncate hover:whitespace-normal hover:overflow-visible transition-all duration-200">Simulations</div>
                      <div className="text-2xl font-bold text-gray-900 truncate hover:whitespace-normal hover:overflow-visible transition-all duration-200">{cohortSimulations?.length || 0}</div>
                    </div>
                  </div>
                </div>

                {/* Avg. Completion */}
                <div className="card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl p-6 shadow-md">
                  <div className="flex items-center h-full">
                    {/* Left Section - Icon */}
                    <div className="w-12 h-12 bg-gradient-to-br from-orange-100 to-orange-50 rounded-xl flex items-center justify-center mr-4 flex-shrink-0 shadow-sm">
                      <Clock className="h-6 w-6 text-orange-600" />
                    </div>
                    {/* Right Section - Text Stack */}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gray-600 font-medium truncate hover:whitespace-normal hover:overflow-visible transition-all duration-200">Avg. Completion</div>
                      <div className="text-2xl font-bold text-gray-900 truncate hover:whitespace-normal hover:overflow-visible transition-all duration-200">
                        {cohortSimulations.length > 0 
                          ? `${(cohortSimulations.reduce((sum, sim) => {
                              const counts = simulationCompletionCounts[sim.id] || { completed: 0, total: 0 };
                              return sum + (counts.total > 0 ? (counts.completed / counts.total) : 0);
                            }, 0) / cohortSimulations.length * 100).toFixed(0)}%`
                          : 'N/A'}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Tabs Navigation */}
              <div className="mb-8 stagger-2 animate-fade-scale">
                <div className="flex border-b border-gray-200/60">
                  {[
                    { id: 'students', label: 'Students' },
                    { id: 'simulations', label: 'Simulations' },
                    { id: 'analytics', label: 'Analytics' },
                    { id: 'settings', label: 'Settings' }
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`py-3 px-6 text-sm font-medium transition-colors ${
                        activeTab === tab.id
                          ? 'border-b-2 border-slate-600 text-slate-700'
                          : 'text-gray-600 hover:text-gray-900'
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tab Content */}
              {activeTab === 'students' && (
                <div>
                  {/* Search and Filter */}
                  <div className="flex items-center justify-between mb-6">
                    <div className="relative flex-1 max-w-md">
                      <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                      <input
                        type="text"
                        placeholder="Search students..."
                        value={studentSearchTerm}
                        onChange={(e) => setStudentSearchTerm(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-black focus:border-transparent"
                      />
                    </div>
                    <div className="flex items-center space-x-2">
                      <Filter className="h-4 w-4 text-gray-400" />
                      <select
                        value={studentFilter}
                        onChange={(e) => setStudentFilter(e.target.value)}
                        className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-black focus:border-transparent"
                      >
                        <option value="all">All Students</option>
                        <option value="active">Active</option>
                        <option value="pending">Pending</option>
                        <option value="inactive">Inactive</option>
                      </select>
                    </div>
                  </div>

                  {/* Bulk Actions Bar */}
                  {selectedStudents.size > 0 && (
                    <div className="mb-4 p-4 bg-gradient-to-r from-slate-50 to-slate-100/50 border border-gray-200/60 rounded-xl flex items-center justify-between shadow-sm">
                      <div className="flex items-center space-x-3">
                        <span className="text-sm font-medium text-gray-700">
                          {selectedStudents.size} student{selectedStudents.size !== 1 ? 's' : ''} selected
                        </span>
                      </div>
                      <Button
                        onClick={() => setShowBulkRemoveModal(true)}
                        className="bg-red-600 text-white hover:bg-red-700 text-sm shadow-md hover:shadow-lg transition-all"
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
                        Remove Selected
                      </Button>
                    </div>
                  )}

                  {/* Select All Checkbox Header */}
                  {cohortStudents && cohortStudents.length > 0 && (() => {
                    const filteredStudents = cohortStudents?.filter(student => {
                      const matchesSearch = student.student_name.toLowerCase().includes(studentSearchTerm.toLowerCase()) ||
                                           student.student_email.toLowerCase().includes(studentSearchTerm.toLowerCase())
                      
                      if (studentFilter === 'all') return matchesSearch
                      if (studentFilter === 'active') return student.status === 'approved' && matchesSearch
                      if (studentFilter === 'pending') return student.status === 'pending' && matchesSearch
                      if (studentFilter === 'inactive') return student.status === 'inactive' && matchesSearch
                      return matchesSearch
                    }) || []
                    
                    return filteredStudents.length > 0 ? (
                      <div className="mb-3 flex items-center space-x-2 pb-2 border-b border-gray-200">
                        <input
                          type="checkbox"
                          checked={filteredStudents.length > 0 && filteredStudents.every(s => selectedStudents.has(s.student_id))}
                          onChange={handleSelectAll}
                          className="h-4 w-4 text-slate-600 focus:ring-slate-500 border-gray-300 rounded cursor-pointer"
                        />
                        <label className="text-sm font-medium text-gray-700 cursor-pointer" onClick={handleSelectAll}>
                          Select All ({filteredStudents.length})
                        </label>
                      </div>
                    ) : null
                  })()}

                  {/* Student List */}
                  <div className="space-y-3">
                    {cohortStudents?.filter(student => {
                      const matchesSearch = student.student_name.toLowerCase().includes(studentSearchTerm.toLowerCase()) ||
                                           student.student_email.toLowerCase().includes(studentSearchTerm.toLowerCase())
                      
                      if (studentFilter === 'all') return matchesSearch
                      if (studentFilter === 'active') return student.status === 'approved' && matchesSearch
                      if (studentFilter === 'pending') return student.status === 'pending' && matchesSearch
                      if (studentFilter === 'inactive') return student.status === 'inactive' && matchesSearch
                      return matchesSearch
                    }).map((student, index) => (
                      <div key={student.id} className="flex items-center justify-between p-4 bg-white border border-gray-200 rounded-lg hover:shadow-sm transition-shadow">
                        <div className="flex items-center space-x-4">
                          {/* Checkbox */}
                          <input
                            type="checkbox"
                            checked={selectedStudents.has(student.student_id)}
                            onChange={() => handleToggleStudent(student.student_id)}
                            className="h-4 w-4 text-slate-600 focus:ring-slate-500 border-gray-300 rounded cursor-pointer"
                          />
                          {/* Avatar */}
                          <div className="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center">
                            <span className="text-sm font-medium text-gray-600">
                              {student.student_name.split(' ').map((n: string) => n[0]).join('').toUpperCase()}
                            </span>
                          </div>
                          
                          {/* Student Info */}
                          <div>
                            <h4 className="font-medium text-gray-900">{student.student_name}</h4>
                            <p className="text-sm text-gray-500">{student.student_email}</p>
                            <div className="flex items-center space-x-4 mt-1">
                              <span className="text-xs text-gray-500">
                                Completed: {Math.floor(Math.random() * 5)} | Pending: {Math.floor(Math.random() * 3)}
                              </span>
                            </div>
                          </div>
                        </div>
                        
                        <div className="flex items-center space-x-4">
                          {/* Status Badge */}
                          <Badge className={`text-xs px-2 py-1 ${
                            student.status === 'approved' 
                              ? 'bg-green-100 text-green-700' 
                              : student.status === 'pending'
                              ? 'bg-yellow-100 text-yellow-700'
                              : 'bg-gray-100 text-gray-600'
                          }`}>
                            {student.status === 'approved' ? 'Active' : student.status === 'pending' ? 'Pending' : 'Inactive'}
                          </Badge>
                          
                          {/* Joined Date */}
                          <span className="text-xs text-gray-500">
                            Joined {new Date(student.enrollment_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                          </span>
                          
                          {/* Options Menu */}
                          <div className="relative" data-dropdown>
                            <button 
                              data-dropdown-button
                              onClick={(e) => {
                                e.stopPropagation()
                                setStudentMenuOpen(studentMenuOpen === student.student_id ? null : student.student_id)
                              }}
                              disabled={removingStudentId === student.student_id}
                              className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-50"
                            >
                              {removingStudentId === student.student_id ? (
                                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600"></div>
                              ) : (
                                <MoreVertical className="h-4 w-4" />
                              )}
                            </button>
                            
                            {/* Dropdown Menu */}
                            {studentMenuOpen === student.student_id && (
                              <div 
                                className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg border border-gray-200 z-10"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    handleRemoveStudent(student.student_id, student.student_name)
                                  }}
                                  className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 rounded-md"
                                >
                                  Remove from Cohort
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                    
                    {cohortStudents?.length === 0 && (
                      <div className="text-center py-8">
                        <Users className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                        <p className="text-gray-500">No students enrolled in this cohort yet.</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'simulations' && (
                <div>
                  {!showStudentProgressView ? (
                    <>
                      {/* Header */}
                      <div className="flex items-center justify-between mb-6">
                        <h3 className="text-xl font-bold text-black">Assigned Simulations</h3>
                        <Button 
                          onClick={() => {
                            fetchAvailableScenarios()
                            setShowAssignModal(true)
                          }}
                          className="bg-black text-white hover:bg-gray-800 text-sm"
                        >
                          <BookOpen className="h-4 w-4 mr-2" />
                          Assign Simulation
                        </Button>
                      </div>

                  {/* Simulations List */}
                  <div className="space-y-4">
                    {cohortSimulations.length === 0 ? (
                      <div className="text-center py-8">
                        <BookOpen className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                        <p className="text-gray-500 mb-4">No simulations assigned yet</p>
                        <Button 
                          onClick={() => {
                            fetchAvailableScenarios()
                            setShowAssignModal(true)
                          }}
                          className="bg-black text-white hover:bg-gray-800"
                        >
                          <BookOpen className="h-4 w-4 mr-2" />
                          Assign First Simulation
                        </Button>
                      </div>
                    ) : (
                      cohortSimulations.map((simulation) => {
                        // Get real completion data from state
                        const completionData = simulationCompletionCounts[simulation.id] || { 
                          completed: 0, 
                          total: cohortStudents.filter(s => s.status === 'approved').length 
                        }
                        const completedStudents = completionData.completed
                        const totalStudents = completionData.total
                        const completionPercentage = totalStudents > 0 ? (completedStudents / totalStudents) * 100 : 0
                        
                        return (
                          <div 
                            key={simulation.id} 
                            className="bg-white border border-gray-200 rounded-lg shadow-sm p-6 cursor-pointer hover:border-gray-400 hover:shadow-md transition-all"
                            onClick={() => handleViewStudentProgress(simulation)}
                          >
                            <div className="flex items-start justify-between">
                              <div className="flex-1">
                                <div className="flex items-center justify-between mb-2">
                                  <h4 className="font-bold text-gray-900 text-lg">
                                    {simulation.simulation?.title || `Simulation ${simulation.simulation_id}`}
                                  </h4>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      handleDeleteSimulation(simulation.id)
                                    }}
                                    disabled={deletingSimulation === simulation.id}
                                    className="text-red-500 hover:text-red-700 disabled:opacity-50"
                                  >
                                    {deletingSimulation === simulation.id ? (
                                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-red-500"></div>
                                    ) : (
                                      <X className="h-4 w-4" />
                                    )}
                                  </button>
                                </div>
                                <div className="flex items-center space-x-4 text-sm text-gray-500 mb-3">
                                  <span>
                                    Assigned {new Date(simulation.assigned_at).toLocaleDateString('en-US', { 
                                      month: 'short', 
                                      day: 'numeric' 
                                    })}
                                  </span>
                                  {simulation.due_date && (
                                    <span>
                                      Due {new Date(simulation.due_date).toLocaleDateString('en-US', { 
                                        month: 'short', 
                                        day: 'numeric' 
                                      })}
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center space-x-2">
                                  {simulation.simulation?.is_draft ? (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                                      Draft
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                      Active
                                    </span>
                                  )}
                                  <span className={`text-xs px-2 py-1 rounded-full ${
                                    simulation.is_required 
                                      ? 'bg-red-100 text-red-800' 
                                      : 'bg-blue-100 text-blue-800'
                                  }`}>
                                    {simulation.is_required ? 'Required' : 'Optional'}
                                  </span>
                                </div>
                              </div>
                              
                              <div className="text-right">
                                <div className="text-sm text-gray-600 mb-2">
                                  {completedStudents}/{totalStudents} completed
                                </div>
                                <div className="w-32 bg-gray-200 rounded-full h-2">
                                  <div 
                                    className="bg-gray-800 h-2 rounded-full transition-all duration-300"
                                    style={{ width: `${completionPercentage}%` }}
                                  ></div>
                                </div>
                              </div>
                            </div>
                          </div>
                        )
                      })
                    )}
                    </div>
                    </>
                  ) : (
                    /* Student Progress View */
                    <div>
                      {/* Back Button and Header */}
                      <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center space-x-4">
                          <button
                            onClick={handleBackToSimulations}
                            className="inline-flex items-center text-sm text-gray-600 hover:text-black transition-colors"
                          >
                            <ArrowLeft className="h-4 w-4 mr-2" />
                            Back to Simulations
                          </button>
                          <h3 className="text-xl font-bold text-black">
                            {selectedSimulation?.simulation?.title || 'Simulation'} - Student Progress
                          </h3>
                        </div>
                      </div>

                      <div className="mb-6">
                        <p className="text-gray-600">
                          Viewing progress for {cohortStudents?.filter(s => s.status === 'approved').length || 0} enrolled students
                        </p>
                      </div>

                      {loadingInstances ? (
                        <div className="flex items-center justify-center py-8">
                          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900"></div>
                          <span className="ml-3 text-gray-600">Loading student progress...</span>
                        </div>
                      ) : studentInstances.length === 0 ? (
                        <div className="text-center py-8">
                          <Users className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                          <p className="text-gray-500">No student instances found. Students will see this simulation once they view their simulations page.</p>
                        </div>
                      ) : (
                        <>
                          {/* Student Progress Table */}
                          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                            <div className="overflow-x-auto">
                              <table className="w-full">
                                <thead className="bg-gray-50">
                                  <tr>
                                    <th className="text-left py-3 px-4 font-medium text-gray-900">Student</th>
                                    <th className="text-left py-3 px-4 font-medium text-gray-900">Status</th>
                                    <th className="text-left py-3 px-4 font-medium text-gray-900">Progress</th>
                                    <th className="text-left py-3 px-4 font-medium text-gray-900">Grade</th>
                                    <th className="text-left py-3 px-4 font-medium text-gray-900">Time Spent</th>
                                    <th className="text-left py-3 px-4 font-medium text-gray-900">Actions</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-200">
                                  {studentInstances.map((instance) => (
                                    <tr key={instance.id || `student-${instance.student_id}`} className="hover:bg-gray-50">
                                      <td className="py-4 px-4">
                                        <div>
                                          <div className="font-medium text-gray-900">{instance.student_name}</div>
                                          <div className="text-sm text-gray-500">{instance.student_email}</div>
                                        </div>
                                      </td>
                                      <td className="py-4 px-4">
                                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                          instance.status === 'completed' || instance.status === 'graded'
                                            ? 'bg-green-100 text-green-800'
                                            : instance.status === 'in_progress'
                                            ? 'bg-blue-100 text-blue-800'
                                            : instance.status === 'submitted'
                                            ? 'bg-yellow-100 text-yellow-800'
                                            : 'bg-gray-100 text-gray-800'
                                        }`}>
                                          {instance.status === 'completed' ? 'Completed' : 
                                           instance.status === 'graded' ? 'Graded' :
                                           instance.status === 'in_progress' ? 'In Progress' :
                                           instance.status === 'submitted' ? 'Submitted' : 'Not Started'}
                                        </span>
                                      </td>
                                      <td className="py-4 px-4">
                                        <div className="flex items-center">
                                          <div className="w-20 bg-gray-200 rounded-full h-2 mr-3">
                                            <div 
                                              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                                              style={{ width: `${instance.completion_percentage || 0}%` }}
                                            ></div>
                                          </div>
                                          <span className="text-sm text-gray-600">{instance.completion_percentage || 0}%</span>
                                        </div>
                                      </td>
                                      <td className="py-4 px-4">
                                        {instance.grade !== null ? (
                                          <div>
                                            <div className="font-medium text-gray-900">{instance.grade}%</div>
                                            {instance.graded_at && (
                                              <div className="text-xs text-gray-500">
                                                {new Date(instance.graded_at).toLocaleDateString()}
                                              </div>
                                            )}
                                          </div>
                                        ) : (
                                          <span className="text-gray-500">Not graded</span>
                                        )}
                                      </td>
                                      <td className="py-4 px-4">
                                        {instance.total_time_spent ? (
                                          <div>
                                            <div className="text-sm text-gray-900">{Math.floor(instance.total_time_spent / 60)} min</div>
                                            {instance.started_at && (
                                              <div className="text-xs text-gray-500">
                                                Started {new Date(instance.started_at).toLocaleDateString()}
                                              </div>
                                            )}
                                          </div>
                                        ) : (
                                          <span className="text-gray-500">-</span>
                                        )}
                                      </td>
                                      <td className="py-4 px-4">
                                        <div className="flex items-center justify-center">
                                          {instance.status !== 'completed' && instance.status !== 'submitted' && instance.status !== 'graded' ? (
                                            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                                              Waiting for submission
                                            </span>
                                          ) : instance.grade !== null ? (
                                            <button
                                              className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium bg-green-100 text-green-700 hover:bg-green-200 transition-colors cursor-pointer"
                                              onClick={(e) => {
                                                e.stopPropagation()
                                                setSelectedInstanceForGrading(instance.id)
                                                setShowGradingModal(true)
                                              }}
                                            >
                                              Graded
                                            </button>
                                          ) : (
                                            <button
                                              className="inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors cursor-pointer"
                                              onClick={(e) => {
                                                e.stopPropagation()
                                                setSelectedInstanceForGrading(instance.id)
                                                setShowGradingModal(true)
                                              }}
                                            >
                                              Ready for grading
                                            </button>
                                          )}
                                        </div>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>

                          {/* Summary Statistics */}
                          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mt-8">
                            <div className="bg-gray-50 rounded-lg p-4">
                              <div className="text-sm text-gray-600">Average Completion</div>
                              <div className="text-2xl font-bold text-gray-900">
                                {(studentInstances.reduce((sum, i) => sum + (i.completion_percentage || 0), 0) / studentInstances.length).toFixed(0)}%
                              </div>
                            </div>
                            <div className="bg-gray-50 rounded-lg p-4">
                              <div className="text-sm text-gray-600">Average Grade</div>
                              <div className="text-2xl font-bold text-gray-900">
                                {studentInstances.filter(i => i.grade !== null).length > 0
                                  ? (studentInstances.filter(i => i.grade !== null).reduce((sum, i) => sum + (i.grade || 0), 0) / studentInstances.filter(i => i.grade !== null).length).toFixed(1)
                                  : '-'}%
                              </div>
                            </div>
                            <div className="bg-gray-50 rounded-lg p-4">
                              <div className="text-sm text-gray-600">Completed</div>
                              <div className="text-2xl font-bold text-gray-900">
                                {studentInstances.filter(i => i.status === 'completed' || i.status === 'graded').length}/{studentInstances.length}
                              </div>
                            </div>
                            <div className="bg-gray-50 rounded-lg p-4">
                              <div className="text-sm text-gray-600">Avg. Time</div>
                              <div className="text-2xl font-bold text-gray-900">
                                {Math.floor(studentInstances.reduce((sum, i) => sum + (i.total_time_spent || 0), 0) / studentInstances.length / 60)} min
                              </div>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'analytics' && (
                <div className="stagger-3 animate-fade-scale">
                  <div className="text-center py-12">
                    <div className="w-16 h-16 bg-gradient-to-br from-slate-100 to-slate-50 rounded-xl flex items-center justify-center mx-auto mb-4 shadow-sm">
                      <Calendar className="h-8 w-8 text-slate-600" />
                    </div>
                    <h3 className="text-xl font-bold text-gray-900 mb-2">Analytics Coming Soon</h3>
                    <p className="text-gray-600">Detailed analytics and insights for this cohort will be available here.</p>
                  </div>
                </div>
              )}

              {activeTab === 'settings' && (
                <div className="stagger-3 animate-fade-scale">
                  <div className="text-center py-12">
                    <div className="w-16 h-16 bg-gradient-to-br from-gray-100 to-gray-50 rounded-xl flex items-center justify-center mx-auto mb-4 shadow-sm">
                      <Settings className="h-8 w-8 text-gray-600" />
                    </div>
                    <h3 className="text-xl font-bold text-gray-900 mb-2">Settings Coming Soon</h3>
                    <p className="text-gray-600">Cohort settings and configuration options will be available here.</p>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <Users className="h-16 w-16 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No cohort selected</h3>
                <p className="text-gray-500">Select a cohort from the list to view details</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create Cohort Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-scale overflow-y-auto">
          <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-lg mx-4 my-8 border border-gray-200/60 animate-scale-in">
            <div className="flex items-center justify-between p-6 border-b border-gray-200/60">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-blue-100 to-blue-50 rounded-xl flex items-center justify-center shadow-sm">
                  <Plus className="h-5 w-5 text-blue-600" />
                </div>
                <h2 className="text-xl font-bold text-gray-900 tracking-tight">Create New Cohort</h2>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors p-1.5 hover:bg-gray-100 rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-5 max-h-[calc(100vh-12rem)] overflow-y-auto">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Cohort Name
                  </label>
                  <input
                    type="text"
                    value={formData.cohortName}
                    onChange={(e) => setFormData({...formData, cohortName: e.target.value})}
                    className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                    placeholder="e.g., Business Strategy Fall 2024"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({...formData, description: e.target.value})}
                    className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md resize-none"
                    rows={3}
                    placeholder="Brief description of the cohort..."
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Course Code
                    </label>
                    <input
                      type="text"
                      value={formData.courseCode}
                      onChange={(e) => setFormData({...formData, courseCode: e.target.value})}
                      className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                      placeholder="e.g., BUS 101"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Max Students
                    </label>
                    <input
                      type="number"
                      value={formData.maxStudents}
                      onChange={(e) => setFormData({...formData, maxStudents: e.target.value})}
                      className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                      placeholder="30"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Semester
                    </label>
                    <select
                      value={formData.semester}
                      onChange={(e) => setFormData({...formData, semester: e.target.value})}
                      className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                    >
                      <option value="">Select Semester</option>
                      <option value="Fall">Fall</option>
                      <option value="Spring">Spring</option>
                      <option value="Summer">Summer</option>
                      <option value="Winter">Winter</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Year
                    </label>
                    <select
                      value={formData.year}
                      onChange={(e) => setFormData({...formData, year: e.target.value})}
                      className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                    >
                      <option value="">Select Year</option>
                      {Array.from({ length: 10 }, (_, i) => {
                        const year = new Date().getFullYear() + i;
                        return (
                          <option key={year} value={year.toString()}>
                            {year}
                          </option>
                        );
                      })}
                    </select>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="autoApprove"
                      checked={formData.autoApprove}
                      onChange={(e) => setFormData({...formData, autoApprove: e.target.checked})}
                      className="h-4 w-4 text-slate-600 focus:ring-slate-500 border-gray-300 rounded"
                    />
                    <label htmlFor="autoApprove" className="ml-2 text-sm text-gray-700">
                      Auto-approve student enrollments
                    </label>
                  </div>
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="allowSelfEnrollment"
                      checked={formData.allowSelfEnrollment}
                      onChange={(e) => setFormData({...formData, allowSelfEnrollment: e.target.checked})}
                      className="h-4 w-4 text-slate-600 focus:ring-slate-500 border-gray-300 rounded"
                    />
                    <label htmlFor="allowSelfEnrollment" className="ml-2 text-sm text-gray-700">
                      Allow self-enrollment
                    </label>
                  </div>
                </div>

                {/* Status Pills */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Status
                  </label>
                  <div className="flex space-x-2">
                    <button
                      type="button"
                      onClick={() => setFormData({...formData, isActive: true})}
                      className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                        formData.isActive
                          ? 'bg-green-100 text-green-800 border-2 border-green-300'
                          : 'bg-gray-100 text-gray-600 border-2 border-gray-200 hover:bg-gray-200'
                      }`}
                    >
                      Active
                    </button>
                    <button
                      type="button"
                      onClick={() => setFormData({...formData, isActive: false})}
                      className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                        !formData.isActive
                          ? 'bg-yellow-100 text-yellow-800 border-2 border-yellow-300'
                          : 'bg-gray-100 text-gray-600 border-2 border-gray-200 hover:bg-gray-200'
                      }`}
                    >
                      Draft
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex justify-end space-x-3 p-6 border-t border-gray-200/60 bg-gray-50/50">
                <Button
                  variant="outline"
                  onClick={() => setShowCreateModal(false)}
                  className="bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-gray-50/90 transition-all"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleCreateCohort}
                  className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                >
                  Create Cohort
                </Button>
              </div>
            </div>
          </div>
        )}

      <CohortEditModal
        isOpen={showEditModal}
        cohortDetails={cohortDetails}
        onClose={handleCloseEditModal}
        onSubmit={handleUpdateCohort}
        isSubmitting={updatingCohort}
      />

        {/* Delete Confirmation Modal */}
        {showDeleteModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
              <div className="p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Delete Cohort</h2>
                <p className="text-gray-600 mb-6">
                  Are you sure you want to delete "{cohortToDelete?.title}"? This action cannot be undone.
                </p>
                <div className="flex justify-end space-x-3">
                  <Button
                    variant="outline"
                    onClick={() => setShowDeleteModal(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleDeleteCohort}
                    className="bg-red-600 text-white hover:bg-red-700"
                  >
                    Delete
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Assign Simulation Modal */}
        {showAssignModal && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-scale overflow-y-auto">
            <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-md mx-4 my-8 border border-gray-200/60 animate-scale-in">
              <div className="flex items-center justify-between p-6 border-b border-gray-200/60">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-gradient-to-br from-purple-100 to-purple-50 rounded-xl flex items-center justify-center shadow-sm">
                    <BookOpen className="h-5 w-5 text-purple-600" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-900 tracking-tight">Assign Simulation</h2>
                </div>
                <button
                  onClick={() => setShowAssignModal(false)}
                  className="text-gray-400 hover:text-gray-600 transition-colors p-1.5 hover:bg-gray-100 rounded-lg"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="p-6 space-y-5 max-h-[calc(100vh-12rem)] overflow-y-auto">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Select Simulation
                  </label>
                  <select
                    value={selectedScenario?.id || ""}
                    onChange={(e) => {
                      const scenario = availableScenarios.find(s => s.id.toString() === e.target.value)
                      setSelectedScenario(scenario)
                    }}
                    className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400/50 transition-all shadow-sm hover:shadow-md cursor-pointer"
                  >
                    <option value="">Choose a simulation...</option>
                    {availableScenarios.filter(scenario => !scenario.is_draft && scenario.status !== 'Draft').map((scenario) => (
                      <option key={scenario.id} value={scenario.id}>
                        {scenario.title}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Due Date (Optional)
                  </label>
                  <input
                    type="datetime-local"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
                    className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-purple-500/20 focus:border-purple-400/50 transition-all shadow-sm hover:shadow-md"
                  />
                </div>

                <div className="flex items-center p-3 bg-gray-50/50 rounded-xl">
                  <input
                    type="checkbox"
                    id="isRequired"
                    checked={isRequired}
                    onChange={(e) => setIsRequired(e.target.checked)}
                    className="h-4 w-4 text-slate-600 focus:ring-slate-500 border-gray-300 rounded cursor-pointer"
                  />
                  <label htmlFor="isRequired" className="ml-2 text-sm text-gray-700 cursor-pointer">
                    Required assignment
                  </label>
                </div>
              </div>

              <div className="flex justify-end space-x-3 p-6 border-t border-gray-200/60 bg-gray-50/50">
                <Button
                  variant="outline"
                  onClick={() => setShowAssignModal(false)}
                  disabled={assigning}
                  className="bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-gray-50/90 transition-all"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleAssignSimulation}
                  disabled={!selectedScenario || assigning}
                  className="btn-gradient-purple text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                >
                  {assigning ? "Assigning..." : "Assign Simulation"}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Invite Students Modal */}
        {selectedCohort && (
          <InviteStudentsModal
            isOpen={showInviteModal}
            onClose={() => setShowInviteModal(false)}
            cohortId={selectedCohort.id}
            cohortTitle={selectedCohort.title}
            onSuccess={() => {
              // Refresh cohort details to show updated student count
              if (selectedCohort) {
                fetchCohortDetails(selectedCohort.id)
              }
            }}
          />
        )}

        {/* Invite Link Modal */}
        {selectedCohort && (
          <InviteLinkModal
            isOpen={showInviteLinkModal}
            onClose={() => setShowInviteLinkModal(false)}
            cohortId={selectedCohort.id}
            cohortTitle={selectedCohort.title}
          />
        )}

        {/* Professor Grading Modal */}
        {showGradingModal && selectedInstanceForGrading && (
          <ProfessorGradingModal
            isOpen={showGradingModal}
            onClose={() => {
              setShowGradingModal(false)
              setSelectedInstanceForGrading(null)
            }}
            instanceId={selectedInstanceForGrading}
            onGraded={async () => {
              // Refresh student instances after grading
              if (selectedSimulation) {
                try {
                  const instances = await apiClient.getSimulationAssignmentInstances(selectedSimulation.id)
                  const approvedStudentIds = new Set(
                    cohortStudents.filter(s => s.status === 'approved').map(s => s.student_id)
                  )
                  const currentStudentInstances = instances.filter((instance: any) => 
                    approvedStudentIds.has(instance.student_id)
                  )
                  setStudentInstances(currentStudentInstances)
                } catch (error) {
                  console.error('Failed to refresh student instances after grading:', error)
                  alert('Grade saved, but failed to refresh the list. Please reload the page.')
                }
              }
            }}
          />
        )}

        {/* Bulk Remove Confirmation Modal */}
        {showBulkRemoveModal && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-scale">
            <div className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-md mx-4 border border-gray-200/60 animate-scale-in">
              <div className="flex items-center justify-between p-6 border-b border-gray-200/60">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-gradient-to-br from-red-100 to-red-50 rounded-xl flex items-center justify-center shadow-sm">
                    <Trash2 className="h-5 w-5 text-red-600" />
                  </div>
                  <h2 className="text-xl font-bold text-gray-900 tracking-tight">Remove Students</h2>
                </div>
                <button
                  onClick={() => setShowBulkRemoveModal(false)}
                  className="text-gray-400 hover:text-gray-600 transition-colors p-1.5 hover:bg-gray-100 rounded-lg"
                  disabled={removingBulk}
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="p-6">
                <p className="text-gray-600 mb-4">
                  Are you sure you want to remove <span className="font-semibold text-gray-900">{selectedStudents.size}</span> student{selectedStudents.size !== 1 ? 's' : ''} from this cohort? This action cannot be undone.
                </p>
                <div className="max-h-48 overflow-y-auto mb-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
                  <ul className="space-y-1 text-sm text-gray-700">
                    {Array.from(selectedStudents).slice(0, 10).map(studentId => {
                      const student = cohortStudents.find(s => s.student_id === studentId)
                      return student ? (
                        <li key={studentId} className="flex items-center space-x-2">
                          <span className="w-2 h-2 bg-red-500 rounded-full"></span>
                          <span>{student.student_name} ({student.student_email})</span>
                        </li>
                      ) : null
                    })}
                    {selectedStudents.size > 10 && (
                      <li className="text-gray-500 italic">
                        ... and {selectedStudents.size - 10} more student{selectedStudents.size - 10 !== 1 ? 's' : ''}
                      </li>
                    )}
                  </ul>
                </div>
              </div>

              <div className="flex justify-end space-x-3 p-6 border-t border-gray-200/60 bg-gray-50/50">
                <Button
                  variant="outline"
                  onClick={() => setShowBulkRemoveModal(false)}
                  disabled={removingBulk}
                  className="bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-gray-50/90 transition-all"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleBulkRemove}
                  disabled={removingBulk}
                  className="bg-red-600 text-white hover:bg-red-700 border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                >
                  {removingBulk ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2 inline-block"></div>
                      Removing...
                    </>
                  ) : (
                    <>
                      <Trash2 className="h-4 w-4 mr-2" />
                      Remove {selectedStudents.size} Student{selectedStudents.size !== 1 ? 's' : ''}
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}

      </div>
  )
}
