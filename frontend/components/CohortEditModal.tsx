"use client"

import { useEffect, useState } from "react"
import { Pencil, X } from "lucide-react"
import { Button } from "@/components/ui/button"

export interface CohortEditFormValues {
  cohortName: string
  description: string
  courseCode: string
  semester: string
  year: string
  maxStudents: string
  autoApprove: boolean
  allowSelfEnrollment: boolean
  isActive: boolean
}

interface CohortEditModalProps {
  isOpen: boolean
  cohortDetails: any | null
  onClose: () => void
  onSubmit: (values: CohortEditFormValues) => Promise<void> | void
  isSubmitting?: boolean
}

const defaultFormValues: CohortEditFormValues = {
  cohortName: "",
  description: "",
  courseCode: "",
  semester: "",
  year: "",
  maxStudents: "",
  autoApprove: true,
  allowSelfEnrollment: false,
  isActive: true,
}

export function CohortEditModal({
  isOpen,
  cohortDetails,
  onClose,
  onSubmit,
  isSubmitting = false,
}: CohortEditModalProps) {
  const [formValues, setFormValues] = useState<CohortEditFormValues>(defaultFormValues)

  useEffect(() => {
    if (isOpen && cohortDetails) {
      setFormValues({
        cohortName: cohortDetails.title || "",
        description: cohortDetails.description || "",
        courseCode: cohortDetails.course_code || "",
        semester: cohortDetails.semester || "",
        year: cohortDetails.year ? String(cohortDetails.year) : "",
        maxStudents: cohortDetails.max_students ? String(cohortDetails.max_students) : "",
        autoApprove: cohortDetails.auto_approve ?? true,
        allowSelfEnrollment: cohortDetails.allow_self_enrollment ?? false,
        isActive: cohortDetails.is_active ?? true,
      })
    }

    if (!isOpen) {
      setFormValues(defaultFormValues)
    }
  }, [isOpen, cohortDetails])

  if (!isOpen) {
    return null
  }

  const handleChange = (field: keyof CohortEditFormValues, value: string | boolean) => {
    setFormValues(prev => ({
      ...prev,
      [field]: value,
    }))
  }

  const handleSubmit = async () => {
    if (!formValues.cohortName.trim()) {
      alert("Cohort name is required")
      return
    }

    await onSubmit(formValues)
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-scale overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="bg-white/95 backdrop-blur-md rounded-2xl shadow-2xl w-full max-w-lg mx-4 my-8 border border-gray-200/60 animate-scale-in"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between p-6 border-b border-gray-200/60">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-slate-100 to-slate-50 rounded-xl flex items-center justify-center shadow-sm">
              <Pencil className="h-5 w-5 text-slate-600" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 tracking-tight">Edit Cohort</h2>
          </div>
          <button
            onClick={onClose}
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
              value={formValues.cohortName}
              onChange={(e) => handleChange("cohortName", e.target.value)}
              className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              placeholder="e.g., Business Strategy Fall 2024"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              value={formValues.description}
              onChange={(e) => handleChange("description", e.target.value)}
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
                value={formValues.courseCode}
                onChange={(e) => handleChange("courseCode", e.target.value)}
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
                value={formValues.maxStudents}
                onChange={(e) => handleChange("maxStudents", e.target.value)}
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
                value={formValues.semester}
                onChange={(e) => handleChange("semester", e.target.value)}
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
                value={formValues.year}
                onChange={(e) => handleChange("year", e.target.value)}
                className="w-full px-4 py-3 bg-white/80 backdrop-blur-sm border border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              >
                <option value="">Select Year</option>
                {Array.from({ length: 10 }, (_, i) => {
                  const year = new Date().getFullYear() + i
                  return (
                    <option key={year} value={year.toString()}>
                      {year}
                    </option>
                  )
                })}
              </select>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center">
              <input
                type="checkbox"
                id="editAutoApprove"
                checked={formValues.autoApprove}
                onChange={(e) => handleChange("autoApprove", e.target.checked)}
                className="h-4 w-4 text-slate-600 focus:ring-slate-500 border-gray-300 rounded"
              />
              <label htmlFor="editAutoApprove" className="ml-2 text-sm text-gray-700">
                Auto-approve student enrollments
              </label>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="editAllowSelfEnrollment"
                checked={formValues.allowSelfEnrollment}
                onChange={(e) => handleChange("allowSelfEnrollment", e.target.checked)}
                className="h-4 w-4 text-slate-600 focus:ring-slate-500 border-gray-300 rounded"
              />
              <label htmlFor="editAllowSelfEnrollment" className="ml-2 text-sm text-gray-700">
                Allow self-enrollment
              </label>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Status
            </label>
            <div className="flex space-x-2">
              <button
                type="button"
                onClick={() => handleChange("isActive", true)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                  formValues.isActive
                    ? "bg-green-100 text-green-800 border-2 border-green-300"
                    : "bg-gray-100 text-gray-600 border-2 border-gray-200 hover:bg-gray-200"
                }`}
              >
                Active
              </button>
              <button
                type="button"
                onClick={() => handleChange("isActive", false)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                  !formValues.isActive
                    ? "bg-yellow-100 text-yellow-800 border-2 border-yellow-300"
                    : "bg-gray-100 text-gray-600 border-2 border-gray-200 hover:bg-gray-200"
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
            onClick={onClose}
            disabled={isSubmitting}
            className="bg-white/80 backdrop-blur-sm border-gray-200/80 hover:bg-gray-50/90 transition-all"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting}
            className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
          >
            {isSubmitting ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default CohortEditModal

