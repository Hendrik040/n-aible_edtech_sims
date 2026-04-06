"use client"

import React, { useState, useRef, useEffect } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { ArrowLeft, Upload, X, Plus, Target, Save } from "lucide-react"
import { apiClient } from "@/lib/api"

// Type definition for rubric configuration
interface RubricConfig {
  title: string;
  performanceLevels: Array<{ name: string; points: number }>;
  criteria: Array<{
    description: string;
    descriptions: Record<string, string>;
  }>;
}

const defaultRubricConfig: RubricConfig = {
  title: "Case Study Analysis",
  performanceLevels: [
    { name: "Outstanding", points: 25 },
    { name: "Excellent", points: 20 },
    { name: "Good", points: 15 },
    { name: "Fair", points: 10 },
    { name: "Poor", points: 5 }
  ],
  criteria: [
    {
      description: "Analysis of major issues in the case",
      descriptions: {
        "Outstanding": "Presents an extremely thorough and insightful analysis of all major issues.",
        "Excellent": "Presents a strong analysis of most of the major issues.",
        "Good": "Presents a good analysis but lacks depth in some areas.",
        "Fair": "Presents an adequate yet limited analysis.",
        "Poor": "The level of analysis lacks adequate depth."
      }
    }
  ]
};

export default function EditGradingPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { user, isLoading: authLoading } = useAuth()

  const isProfessor = user?.role === 'professor' || user?.role === 'admin'
  useEffect(() => {
    if (user && !isProfessor) {
      router.push('/dashboard')
    }
  }, [user, isProfessor, router])

  const simulationId = searchParams.get('id')
  const returnToInstanceId = searchParams.get('returnTo')

  // State
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [simulationTitle, setSimulationTitle] = useState("")

  // Grading state
  const [gradingPrompt, setGradingPrompt] = useState("")
  const [rubricConfig, setRubricConfig] = useState<RubricConfig>(defaultRubricConfig)
  const [strictnessLevel, setStrictnessLevel] = useState(3)
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([])
  const [existingGradingMaterials, setExistingGradingMaterials] = useState<any[]>([])
  const [uploadingFiles, setUploadingFiles] = useState<Set<string>>(new Set())
  const [processingMaterials, setProcessingMaterials] = useState<Set<number>>(new Set())

  const filesInputRef = useRef<HTMLInputElement>(null)

  // Load data
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (simulationId) {
      loadSimulationData()
    }
  }, [simulationId])

  // Check processing status periodically
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (simulationId && processingMaterials.size > 0) {
      const interval = setInterval(() => {
        loadGradingMaterials(parseInt(simulationId))
      }, 10000)
      return () => clearInterval(interval)
    }
  }, [simulationId, processingMaterials.size])

  const loadSimulationData = async () => {
    if (!simulationId) return

    try {
      setLoading(true)
      setError(null)

      // Load draft data
      const draftData = await apiClient.getDraftScenario(parseInt(simulationId))

      if (draftData) {
        setSimulationTitle(draftData.title || "")

        // Load grading prompt
        if (draftData.grading_prompt !== undefined) {
          setGradingPrompt(draftData.grading_prompt || "")
        }

        // Load rubric configuration
        if (draftData.rubric_title || draftData.rubric_criteria || draftData.rubric_performance_levels) {
          setRubricConfig(prev => ({
            ...prev,
            title: draftData.rubric_title || prev.title,
            performanceLevels: draftData.rubric_performance_levels || prev.performanceLevels,
            criteria: draftData.rubric_criteria || prev.criteria
          }))
        }

        // Load strictness level from grading_config
        const savedStrictness = draftData.grading_config?.strictness_level
        if (savedStrictness != null) {
          setStrictnessLevel(Math.max(1, Math.min(5, Number(savedStrictness))))
        }
      }

      // Load grading materials
      await loadGradingMaterials(parseInt(simulationId))

    } catch (err: any) {
      setError(err.message || "Failed to load simulation data")
    } finally {
      setLoading(false)
    }
  }

  const loadGradingMaterials = async (simId: number) => {
    try {
      const response = await apiClient.apiRequest(
        `/professor/simulations/${simId}/grading-materials`,
        { method: 'GET' }
      )

      if (response.ok) {
        const result = await response.json()
        const materials = result.materials || []
        setExistingGradingMaterials(materials)

        const stillProcessing = new Set<number>()
        materials.forEach((material: any) => {
          if (material.processing_status === 'pending' || material.processing_status === 'processing') {
            stillProcessing.add(material.id)
          }
        })
        setProcessingMaterials(stillProcessing)
      }
    } catch (error) {
      console.error("Error loading grading materials:", error)
    }
  }

  const uploadFileImmediately = async (file: File, simId: number) => {
    const fileKey = `${file.name}-${file.size}`

    try {
      setUploadingFiles(prev => new Set(prev).add(fileKey))

      const formData = new FormData()
      formData.append('file', file)

      const response = await apiClient.apiRequest(
        `/professor/simulations/${simId}/grading-materials`,
        { method: 'POST', body: formData }
      )

      if (response.ok) {
        const result = await response.json()
        if (result.material.processing_status !== 'completed') {
          setProcessingMaterials(prev => new Set(prev).add(result.material.id))
        }
        await loadGradingMaterials(simId)
      }
    } catch (error) {
      console.error(`Error uploading ${file.name}:`, error)
    } finally {
      setUploadingFiles(prev => {
        const newSet = new Set(prev)
        newSet.delete(fileKey)
        return newSet
      })
    }
  }

  const deleteGradingMaterial = async (materialId: number) => {
    try {
      const response = await apiClient.apiRequest(
        `/professor/grading-materials/${materialId}`,
        { method: 'DELETE' }
      )

      if (response.ok && simulationId) {
        await loadGradingMaterials(parseInt(simulationId))
      }
    } catch (error) {
      console.error(`Error deleting material ${materialId}:`, error)
    }
  }

  const handleSaveAndPublish = async () => {
    if (!simulationId) return

    setSaving(true)
    setError(null)

    try {
      // 1. Save grading config
      const saveResponse = await apiClient.apiRequest(
        `/api/publishing/simulations/save?simulation_id=${simulationId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            rubric_title: rubricConfig.title,
            rubric_criteria: rubricConfig.criteria,
            rubric_performance_levels: rubricConfig.performanceLevels,
            grading_prompt: gradingPrompt,
            strictness_level: strictnessLevel,
          })
        }
      )

      if (!saveResponse.ok) {
        throw new Error('Failed to save grading configuration')
      }

      // 2. Upload any pending files
      for (const file of uploadedFiles) {
        const formData = new FormData()
        formData.append('file', file)
        await apiClient.apiRequest(
          `/professor/simulations/${simulationId}/grading-materials`,
          { method: 'POST', body: formData }
        )
      }

      // 3. Publish
      const publishResponse = await apiClient.apiRequest(
        `/api/publishing/simulations/publish/${simulationId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            category: "Business",
            difficulty_level: "Intermediate",
            tags: [],
            estimated_duration: 60
          })
        }
      )

      if (!publishResponse.ok) {
        throw new Error('Failed to publish changes')
      }

      // 4. Redirect back
      if (returnToInstanceId) {
        router.push(`/cohorts?openGrading=${returnToInstanceId}`)
      } else {
        router.push('/cohorts')
      }

    } catch (err: any) {
      setError(err.message || 'Failed to save and publish')
    } finally {
      setSaving(false)
    }
  }

  const handleBack = () => {
    router.back()
  }

  if (authLoading || loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900"></div>
      </div>
    )
  }

  if (!isProfessor) return null

  return (
    <div>
      {/* Header */}
      <div className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={handleBack}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <ArrowLeft className="h-5 w-5" />
              </button>
              <div>
                <h1 className="text-xl font-semibold">Edit Grading Criteria</h1>
                <p className="text-sm text-gray-500">{simulationTitle}</p>
              </div>
            </div>
            <Button
              onClick={handleSaveAndPublish}
              disabled={saving}
              className="bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              <Save className="h-4 w-4 mr-2" />
              {saving ? "Saving..." : "Save & Publish"}
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-6xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        <div className="space-y-8">
          {/* Grading Materials Section */}
          <div className="bg-white rounded-lg border p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-medium">Grading Materials</h3>
                <p className="text-sm text-gray-500">Upload additional documents for grading reference</p>
              </div>
              <Button
                variant="outline"
                className="flex items-center gap-2"
                onClick={() => filesInputRef.current?.click()}
              >
                <Upload className="h-4 w-4" />
                Upload Files
              </Button>
              <input
                ref={filesInputRef}
                type="file"
                multiple
                accept=".pdf,.doc,.docx,.txt"
                className="hidden"
                onChange={async (e) => {
                  const files = Array.from(e.target.files || [])
                  if (files.length > 0 && simulationId) {
                    for (const file of files) {
                      await uploadFileImmediately(file, parseInt(simulationId))
                    }
                    e.target.value = ''
                  } else if (files.length > 0) {
                    setUploadedFiles(prev => [...prev, ...files])
                  }
                }}
              />
            </div>

            {/* Existing Materials */}
            {existingGradingMaterials.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-green-700">Uploaded Materials:</h4>
                {existingGradingMaterials.map((material) => (
                  <div key={material.id} className="flex items-center justify-between p-3 border rounded-lg bg-green-50">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 bg-green-100 rounded flex items-center justify-center">
                        <svg className="h-4 w-4 text-green-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <polyline points="14,2 14,8 20,8" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-medium">{material.filename}</p>
                        <p className="text-xs text-gray-500">
                          {material.file_size ? `${(material.file_size / 1024).toFixed(1)} KB` : 'Unknown size'} |
                          Status: <span className={
                            material.processing_status === 'completed' ? 'text-green-600' :
                            material.processing_status === 'processing' ? 'text-blue-600' :
                            'text-yellow-600'
                          }>
                            {material.processing_status === 'processing' ? 'Processing...' : material.processing_status}
                          </span>
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-gray-500 hover:text-red-600"
                      onClick={() => deleteGradingMaterial(material.id)}
                      disabled={material.processing_status === 'processing'}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {/* Pending Files */}
            {uploadedFiles.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium text-blue-700">Pending Upload:</h4>
                {uploadedFiles.map((file, index) => (
                  <div key={index} className="flex items-center justify-between p-3 border rounded-lg bg-blue-50">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 bg-blue-100 rounded flex items-center justify-center">
                        <svg className="h-4 w-4 text-blue-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <polyline points="14,2 14,8 20,8" />
                        </svg>
                      </div>
                      <div>
                        <p className="text-sm font-medium">{file.name}</p>
                        <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(0)} KB | Will be uploaded when saved</p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-gray-500 hover:text-red-600"
                      onClick={() => setUploadedFiles(prev => prev.filter((_, i) => i !== index))}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {/* Empty State */}
            {uploadedFiles.length === 0 && existingGradingMaterials.length === 0 && (
              <div className="text-center p-8 border-2 border-dashed rounded-lg border-gray-300">
                <p className="text-sm text-gray-500">No grading materials uploaded yet</p>
                <p className="text-xs text-gray-400 mt-1">Upload PDFs, documents, or text files for grading reference</p>
              </div>
            )}
          </div>

          {/* Grading Prompt Section */}
          <div className="bg-white rounded-lg border p-6 space-y-4">
            <div className="flex items-center gap-2">
              <Target className="h-5 w-5" />
              <h3 className="text-lg font-medium">Grading Prompt</h3>
            </div>
            <p className="text-sm text-gray-500">Enter instructions for the grading agent to customize how students are evaluated.</p>

            <div className="space-y-2">
              <Label htmlFor="grading-prompt">Grading Instructions</Label>
              <Textarea
                id="grading-prompt"
                value={gradingPrompt}
                onChange={(e) => setGradingPrompt(e.target.value)}
                placeholder="Enter instructions for the grading agent (e.g., 'Grade students based on their understanding of key concepts, application of theories, and quality of analysis...')"
                className="min-h-[120px] resize-y"
              />
            </div>
          </div>

          {/* Grading Strictness */}
          <div className="bg-white rounded-lg border p-6 space-y-4">
            <div className="flex items-center gap-2">
              <Target className="h-5 w-5" />
              <h3 className="text-lg font-medium">Grading Strictness</h3>
            </div>
            <p className="text-sm text-gray-500">
              Controls how demanding the AI grading agent is. Higher levels require students to provide
              more specific reasoning and evidence before scoring in the upper bands.
            </p>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">
                  Level {strictnessLevel} —{" "}
                  {["", "Introductory", "Moderate", "Rigorous", "Demanding", "Graduate"][strictnessLevel]}
                </span>
                <span className="text-xs text-gray-400">1 = most lenient · 5 = most strict</span>
              </div>
              <input
                type="range"
                min={1}
                max={5}
                step={1}
                value={strictnessLevel}
                onChange={(e) => setStrictnessLevel(Number(e.target.value))}
                className="w-full accent-emerald-600"
              />
              <div className="flex justify-between text-xs text-gray-400 px-0.5">
                <span>Introductory</span>
                <span>Moderate</span>
                <span>Rigorous</span>
                <span>Demanding</span>
                <span>Graduate</span>
              </div>
              <p className="text-xs text-gray-500 pt-1">
                {[
                  "",
                  "Suitable for students encountering the material for the first time.",
                  "Basic understanding with supporting reasoning reaches the 70–74 band.",
                  "Superficial or generic responses are capped at 65. Evidence required for 75+.",
                  "Only structured, evidence-backed responses with framework application score above 75.",
                  "Mastery, original thinking, and explicit engagement with tradeoffs required for 70+.",
                ][strictnessLevel]}
              </p>
            </div>
          </div>

          {/* Rubric Configuration */}
          <div className="bg-white rounded-lg border p-6 space-y-6">
            <div className="flex items-center gap-2">
              <Target className="h-5 w-5" />
              <h3 className="text-lg font-medium">Rubric Configuration</h3>
            </div>
            <p className="text-sm text-gray-500">Configure the rubric criteria and performance levels with point values.</p>

            {/* Rubric Title */}
            <div className="space-y-2">
              <Label htmlFor="rubric-title">Rubric Title</Label>
              <Input
                id="rubric-title"
                value={rubricConfig.title}
                onChange={(e) => setRubricConfig(prev => ({ ...prev, title: e.target.value }))}
                placeholder="e.g., Case Study Analysis"
              />
            </div>

            {/* Performance Levels */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-lg font-medium">Performance Levels</h4>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const newLevel = { name: `Level ${rubricConfig.performanceLevels.length + 1}`, points: 0 }
                    setRubricConfig(prev => ({
                      ...prev,
                      performanceLevels: [...prev.performanceLevels, newLevel]
                    }))
                  }}
                  className="flex items-center gap-2"
                >
                  <Plus className="h-4 w-4" />
                  Add Column
                </Button>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                {rubricConfig.performanceLevels.map((level, index) => (
                  <div key={index} className="space-y-2 relative">
                    {rubricConfig.performanceLevels.length > 1 && (
                      <button
                        type="button"
                        onClick={() => {
                          setRubricConfig(prev => ({
                            ...prev,
                            performanceLevels: prev.performanceLevels.filter((_, i) => i !== index)
                          }))
                        }}
                        className="absolute -top-2 -right-2 h-6 w-6 text-gray-500 hover:text-red-500"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    )}
                    <Label>Level Name</Label>
                    <Input
                      value={level.name}
                      onChange={(e) => {
                        const newName = e.target.value
                        const oldName = level.name
                        setRubricConfig(prev => {
                          const newLevels = prev.performanceLevels.map((lvl, i) =>
                            i === index ? { ...lvl, name: newName } : lvl
                          )
                          const newCriteria = prev.criteria.map(criterion => {
                            const descriptions = { ...criterion.descriptions }
                            if (oldName !== newName && descriptions[oldName] !== undefined) {
                              descriptions[newName] = descriptions[oldName]
                              delete descriptions[oldName]
                            }
                            return { ...criterion, descriptions }
                          })
                          return { ...prev, performanceLevels: newLevels, criteria: newCriteria }
                        })
                      }}
                      placeholder="e.g., Outstanding"
                    />
                    <Label>Points</Label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      value={level.points === 0 ? "" : level.points}
                      onChange={(e) => {
                        const newPoints = e.target.value === "" ? 0 : parseInt(e.target.value) || 0
                        const newLevels = [...rubricConfig.performanceLevels]
                        newLevels[index].points = newPoints
                        setRubricConfig(prev => ({ ...prev, performanceLevels: newLevels }))
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Rubric Table */}
            <div className="space-y-4">
              <div className="overflow-x-auto border border-gray-300 rounded-lg">
                <table className="w-full border-collapse min-w-[800px]">
                  <thead>
                    <tr className="bg-gray-50">
                      <th className="border-r border-gray-300 p-4 text-left font-medium w-[200px]">CRITERIA</th>
                      {rubricConfig.performanceLevels.map((level, index) => (
                        <th key={index} className="border-r border-gray-300 p-4 text-center font-medium w-[180px] last:border-r-0">
                          {level.name} ({level.points} pts)
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rubricConfig.criteria.map((criterion, criterionIndex) => (
                      <tr key={criterionIndex} className="border-b border-gray-300 last:border-b-0">
                        <td className="border-r border-gray-300 p-4 relative align-top">
                          {rubricConfig.criteria.length > 1 && (
                            <button
                              type="button"
                              onClick={() => {
                                setRubricConfig(prev => ({
                                  ...prev,
                                  criteria: prev.criteria.filter((_, i) => i !== criterionIndex)
                                }))
                              }}
                              className="absolute top-1 right-1 h-6 w-6 text-gray-500 hover:text-red-500"
                            >
                              <X className="h-4 w-4" />
                            </button>
                          )}
                          <Textarea
                            value={criterion.description}
                            onChange={(e) => {
                              const newCriteria = [...rubricConfig.criteria]
                              newCriteria[criterionIndex].description = e.target.value
                              setRubricConfig(prev => ({ ...prev, criteria: newCriteria }))
                            }}
                            placeholder="Description of what this criterion evaluates"
                            className="min-h-[100px] text-sm resize-none border-0 focus:ring-0"
                          />
                        </td>
                        {rubricConfig.performanceLevels.map((level, levelIndex) => (
                          <td key={levelIndex} className="border-r border-gray-300 p-4 align-top last:border-r-0">
                            <Textarea
                              value={(criterion.descriptions as Record<string, string>)[level.name] || ""}
                              onChange={(e) => {
                                const newCriteria = [...rubricConfig.criteria]
                                if (!newCriteria[criterionIndex].descriptions) {
                                  newCriteria[criterionIndex].descriptions = {}
                                }
                                (newCriteria[criterionIndex].descriptions as Record<string, string>)[level.name] = e.target.value
                                setRubricConfig(prev => ({ ...prev, criteria: newCriteria }))
                              }}
                              placeholder={`Description for ${level.name}`}
                              className="min-h-[100px] text-sm resize-none border-0 focus:ring-0"
                            />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Add Criteria Button */}
              <div className="flex justify-center">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    const newDescriptions: Record<string, string> = {}
                    rubricConfig.performanceLevels.forEach(level => {
                      newDescriptions[level.name] = ""
                    })
                    setRubricConfig(prev => ({
                      ...prev,
                      criteria: [...prev.criteria, { description: "", descriptions: newDescriptions }]
                    }))
                  }}
                  className="flex items-center gap-2"
                >
                  <Plus className="h-4 w-4" />
                  Add Criteria Row
                </Button>
              </div>

              {/* Total Points */}
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <span className="font-medium">Total Points:</span>
                <span className={`font-bold ${rubricConfig.performanceLevels.reduce((sum, l) => sum + l.points, 0) === 100 ? 'text-green-600' : 'text-red-600'}`}>
                  {rubricConfig.performanceLevels.reduce((sum, l) => sum + l.points, 0)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
