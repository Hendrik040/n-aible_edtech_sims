"use client"

import React, { useState, useRef, useEffect } from "react"
import { debugLog } from "@/lib/debug"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Progress } from "@/components/ui/progress"
import { Upload, Info, Users, Activity, Sparkles, X, Check } from "lucide-react"
import Link from "next/link"
import PersonaCard from "@/components/PersonaCard";
import SceneCard from "@/components/SceneCard";
import RoleBasedSidebar from "@/components/RoleBasedSidebar";
import SimulationBuilderProgress from "@/components/SimulationBuilderProgress"
import PDFProgressTrackerHTTP from "@/components/PDFProgressTrackerHTTP"
import { usePDFParsingWithProgress } from "@/hooks/usePDFParsingWithProgress"
import { apiClient, buildApiUrl } from "@/lib/api"


// Simple Modal component
function Modal({ isOpen, onClose, children }: { isOpen: boolean; onClose: () => void; children: React.ReactNode }) {
 React.useEffect(() => {
   if (isOpen) {
     document.body.classList.add('overflow-hidden');
   } else {
     document.body.classList.remove('overflow-hidden');
   }
   return () => {
     document.body.classList.remove('overflow-hidden');
   };
 }, [isOpen]);
 if (!isOpen) return null;
 return (
   <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900 bg-opacity-60">
     <div className="bg-white rounded-lg shadow-lg w-[760px] h-[80vh] flex flex-col relative p-0 resize-none">
       <button
         className="absolute top-4 right-4 text-gray-400 text-2xl font-bold hover:text-gray-600 z-10"
         onClick={onClose}
         aria-label="Close edit window"
       >
         &times;
       </button>
       {children}
     </div>
   </div>
 );
}

function PersonaModal({ isOpen, onClose, children }: { isOpen: boolean; onClose: () => void; children: React.ReactNode }) {
 React.useEffect(() => {
   if (isOpen) {
     document.body.classList.add('overflow-hidden');
   } else {
     document.body.classList.remove('overflow-hidden');
   }
   return () => {
     document.body.classList.remove('overflow-hidden');
   };
 }, [isOpen]);
 if (!isOpen) return null;
 return (
   <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900 bg-opacity-60">
     <div className="bg-white rounded-lg shadow-lg w-[760px] h-[80vh] flex flex-col relative p-0 resize-none">
       <button
         className="absolute top-4 right-4 text-gray-400 text-2xl font-bold hover:text-gray-600 z-10"
         onClick={onClose}
         aria-label="Close edit window"
       >
         &times;
       </button>
       {children}
     </div>
   </div>
 );
}

function SceneModal({ isOpen, onClose, children }: { isOpen: boolean; onClose: () => void; children: React.ReactNode }) {
 React.useEffect(() => {
   if (isOpen) {
     document.body.classList.add('overflow-hidden');
   } else {
     document.body.classList.remove('overflow-hidden');
   }
   return () => {
     document.body.classList.remove('overflow-hidden');
   };
 }, [isOpen]);
 if (!isOpen) return null;
 return (
   <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900 bg-opacity-60">
     <div className="bg-white rounded-lg shadow-lg w-[1000px] h-[80vh] flex flex-col relative p-0 resize-none">
       <button
         className="absolute top-4 right-4 text-gray-400 text-2xl font-bold hover:text-gray-600 z-10"
         onClick={onClose}
         aria-label="Close edit window"
       >
         &times;
       </button>
       {children}
     </div>
   </div>
 );
}


export default function ScenarioBuilder() {
  const router = useRouter()
  const { user, logout, isLoading: authLoading } = useAuth()
  
  // PDF parsing with progress tracking
  const { 
    parsePDFWithProgress, 
    isLoading: isParsingWithProgress, 
    sessionId, 
    error: parsingError, 
    result: parsingResult,
    reset: resetParsing 
  } = usePDFParsingWithProgress()
  
  // All hooks must be called before any conditional returns
  const [uploadedFile, setUploadedFile] = useState<File | null>(null)
 const fileInputRef = useRef<HTMLInputElement>(null)
 const [teachingNotesFile, setTeachingNotesFile] = useState<File | null>(null)
 const teachingNotesInputRef = useRef<HTMLInputElement>(null)
 const [name, setName] = useState("")
 const [description, setDescription] = useState("")
 const [studentRole, setStudentRole] = useState("")
 const [learningOutcomes, setLearningOutcomes] = useState("")
 const [autofillLoading, setAutofillLoading] = useState(false)
 const [autofillError, setAutofillError] = useState<string | null>(null)
 const [autofillResult, setAutofillResult] = useState<any>(null)
 const [autofillStep, setAutofillStep] = useState<string>("")
 const [autofillProgress, setAutofillProgress] = useState(0)
 const [autofillMaxAttempts, setAutofillMaxAttempts] = useState(60)
 const [isDragOver, setIsDragOver] = useState(false)
 const [uploadedFiles, setUploadedFiles] = useState<File[]>([]); // For the "Upload Files" button
 const filesInputRef = useRef<HTMLInputElement>(null);
 const [personas, setPersonas] = useState<any[]>([]);
 const [editingIdx, setEditingIdx] = useState<number | null>(null);
 const [tempPersonas, setTempPersonas] = useState<any[]>([]); // Track temporary personas that haven't been saved yet

 // Timeline/Tasks state
 const [tasks, setTasks] = useState<any[]>([]);
 const [editingTaskIdx, setEditingTaskIdx] = useState<number | null>(null);
 const [scenes, setScenes] = useState<any[]>([]);
 const [editingSceneIdx, setEditingSceneIdx] = useState<number | null>(null);

 // Save status state
 const [isSaved, setIsSaved] = useState(false);
 const [isPublished, setIsPublished] = useState(false);
 const [isSaving, setIsSaving] = useState(false);
 const [isPublishing, setIsPublishing] = useState(false);
  const [savedScenarioId, setSavedScenarioId] = useState<number | null>(null);
  const [completionStatus, setCompletionStatus] = useState<{ [key: string]: boolean } | null>(null);
  const [aiEnhancementComplete, setAiEnhancementComplete] = useState(false);
  
  // Database boolean fields for completion tracking
  const [dbCompletionFields, setDbCompletionFields] = useState({
    nameCompleted: false,
    descriptionCompleted: false,
    studentRoleCompleted: false,
    personasCompleted: false,
    scenesCompleted: false,
    imagesCompleted: false,
    learningOutcomesCompleted: false,
    aiEnhancementCompleted: false
  });

 // Authentication logic - must be after all hooks
 useEffect(() => {
   if (!authLoading && !user) {
     router.push("/")
   }
 }, [user, authLoading, router])

 // Load draft data if editing
 useEffect(() => {
   const loadDraftData = async () => {
     try {
       // Check if we're editing a draft by looking at URL parameters
       const urlParams = new URLSearchParams(window.location.search)
       const editId = urlParams.get('edit')
       
       if (editId) {
         debugLog("Loading draft data for editing ID:", editId)
         
         // Fetch draft data directly from the database
         const draftData = await apiClient.getDraftScenario(parseInt(editId))
         debugLog("Fetched draft data:", draftData)
         
         if (draftData && draftData.id) {
           // Load the draft data into the form
           setName(draftData.title || "")
           setDescription(draftData.description || "")
           
           // Load completion status if available
           if (draftData.completion_status) {
             setCompletionStatus(draftData.completion_status)
             debugLog("Loaded completion status:", draftData.completion_status)
           }
           
           // Load database boolean completion fields
          setDbCompletionFields({
            nameCompleted: draftData.name_completed || false,
            descriptionCompleted: draftData.description_completed || false,
            studentRoleCompleted: draftData.student_role_completed || false,
            personasCompleted: draftData.personas_completed || false,
            scenesCompleted: draftData.scenes_completed || false,
            imagesCompleted: draftData.images_completed || false,
            learningOutcomesCompleted: draftData.learning_outcomes_completed || false,
            aiEnhancementCompleted: draftData.ai_enhancement_completed || false
          });
           
           // Handle learning objectives - check if it's an array or string
           if (Array.isArray(draftData.learning_objectives)) {
             setLearningOutcomes(draftData.learning_objectives.join("\n"))
           } else if (typeof draftData.learning_objectives === 'string') {
             setLearningOutcomes(draftData.learning_objectives)
           } else {
             setLearningOutcomes("")
           }
           
           // Load scenes first to extract personas
           if (draftData.scenes && draftData.scenes.length > 0) {
             console.log("DEBUG: Raw draftData.scenes:", draftData.scenes);
             // Transform scenes to ensure they have the correct structure for SceneCard
             const transformedScenes = draftData.scenes.map((scene: any) => ({
               ...scene,
               sequence_order: scene.scene_order, // Map scene_order to sequence_order for compatibility
               successMetric: scene.success_metric, // Map success_metric to successMetric for compatibility
               // Ensure personas_involved is an array of names
               personas_involved: scene.personas_involved || []
             }))
             console.log("DEBUG: Transformed scenes:", transformedScenes);
             setScenes(transformedScenes)
             
             // Extract all unique personas from scenes (these have the full data)
             const allScenePersonas: any[] = []
             const seenPersonaIds = new Set()
             
             draftData.scenes.forEach((scene: any) => {
               if (scene.personas && scene.personas.length > 0) {
                 scene.personas.forEach((persona: any) => {
                   if (!seenPersonaIds.has(persona.id)) {
                     seenPersonaIds.add(persona.id)
                     allScenePersonas.push(persona)
                   }
                 })
               }
             })
             
             // Use scene personas if available, otherwise fall back to global personas
             if (allScenePersonas.length > 0) {
               debugLog("Using scene personas:", JSON.stringify(allScenePersonas, null, 2))
               // Transform personas to match PersonaCard expected structure
               const transformedPersonas = allScenePersonas.map((persona: any) => ({
                 name: persona.name,
                 position: persona.role,
                 description: persona.background,
                 primaryGoals: Array.isArray(persona.primary_goals) ? persona.primary_goals.join(", ") : persona.primary_goals || "",
                 traits: persona.personality_traits || {},
                 imageUrl: persona.image_url
               }))
               debugLog("Transformed scene personas:", JSON.stringify(transformedPersonas, null, 2))
               setPersonas(transformedPersonas)
             } else if (draftData.personas && draftData.personas.length > 0) {
               debugLog("Using global personas:", draftData.personas)
               // Transform global personas to match PersonaCard expected structure
               const transformedPersonas = draftData.personas.map((persona: any) => ({
                 name: persona.name,
                 position: persona.role,
                 description: persona.background,
                 primaryGoals: Array.isArray(persona.primary_goals) ? persona.primary_goals.join(", ") : persona.primary_goals || "",
                 traits: persona.personality_traits || {},
                 imageUrl: persona.image_url
               }))
               debugLog("Transformed global personas:", JSON.stringify(transformedPersonas, null, 2))
               setPersonas(transformedPersonas)
             }
           } else {
             // Load personas from global data if no scenes
             if (draftData.personas && draftData.personas.length > 0) {
               // Transform global personas to match PersonaCard expected structure
               const transformedPersonas = draftData.personas.map((persona: any) => ({
                 name: persona.name,
                 position: persona.role,
                 description: persona.background,
                 primaryGoals: Array.isArray(persona.primary_goals) ? persona.primary_goals.join(", ") : persona.primary_goals || "",
                 traits: persona.personality_traits || {},
                 imageUrl: persona.image_url
               }))
               setPersonas(transformedPersonas)
             }
           }
           
           // Set the saved scenario ID for updating
           setSavedScenarioId(draftData.id)
           setIsSaved(true) // Mark as already saved
           
           debugLog("Draft data loaded successfully")
         } else {
           throw new Error("Invalid draft data received")
         }
       } else if (!editId) {
         debugLog("No draft ID found - creating new simulation")
         // Ensure form is clean for new simulation
         setName("")
         setDescription("")
         setLearningOutcomes("")
         setPersonas([])
         setScenes([])
         setSavedScenarioId(null)
         setIsSaved(false)
       }
     } catch (error) {
       console.error("Failed to load draft data:", error)
       const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred'
       alert(`Failed to load draft simulation: ${errorMessage}`)
     }
   }

  if (user && !authLoading) {
    loadDraftData()
  }
}, [user, authLoading])
 
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

 // Save and Publish handlers
 const handleSave = async (): Promise<number | null> => {
   // Prevent duplicate save requests
   if (isSaving) {
     debugLog("Save already in progress, ignoring duplicate request")
     return null;
   }
   
   // Allow saving if we have form data OR autofillResult
   if (!autofillResult && !name && !description && !learningOutcomes && personas.length === 0 && scenes.length === 0) {
     alert("No scenario data to save. Please upload and process a PDF first or create a scenario manually.");
     return null;
   }

  // Build payload using the latest user-edited state
  const payload = {
    // Use form data first, fallback to autofillResult if available
    title: name || (autofillResult?.title || ""),
    description: description || (autofillResult?.description || ""),
    learning_outcomes: learningOutcomes || (autofillResult?.learning_outcomes || ""),
    student_role: studentRole || (autofillResult?.student_role || ""),
    key_figures: autofillResult?.key_figures || [],
    // Use the latest scenes and personas state
    scenes: normalizeScenes(scenes),
    // Map frontend persona fields to backend expected fields
    personas: personas.map(persona => ({
      ...persona,
      role: persona.position,        // Map position → role
      background: persona.description, // Map description → background
      primary_goals: persona.primaryGoals, // Map primaryGoals → primary_goals
      personality_traits: persona.traits  // Map traits → personality_traits
    })),
    // Add completion tracking - only mark as complete when all sections are actually done
    completion_status: {
      name_completed: !!name?.trim() || !!autofillResult,
      description_completed: !!description?.trim() || !!autofillResult,
      student_role_completed: !!studentRole?.trim() || !!autofillResult,
      personas_completed: personas?.length > 0 || !!autofillResult,
      scenes_completed: scenes?.length > 0 || !!autofillResult,
      images_completed: scenes?.some(scene => scene.image_url) || !!autofillResult,
      learning_outcomes_completed: learningOutcomes?.length > 0 || (!!autofillResult && !isParsingWithProgress),
      ai_enhancement_completed: aiEnhancementComplete || (!!autofillResult && learningOutcomes?.length > 0 && !isParsingWithProgress && !parsingError)
    }
  };

  // Debug log to check scenes state before saving
  debugLog("Scenes state before save:", scenes);
  debugLog("Personas state before save:", personas);
  
  // Debug: Log persona traits specifically
  personas.forEach((persona, index) => {
    debugLog(`Persona ${index} (${persona.name}) traits being sent:`, persona.traits);
  });
  
  // Debug: Log the full payload structure
  debugLog("Full payload being sent:", JSON.stringify(payload, null, 2));

   setIsSaving(true);
   try {
     debugLog("Sending to save endpoint:", {
       keys: Object.keys(payload),
       title: payload.title,
       key_figures_count: payload.key_figures?.length || 0,
       scenes_count: payload.scenes?.length || 0
     });
     
     // Build endpoint with scenario_id if updating an existing scenario
    const endpoint = savedScenarioId 
      ? `/api/publishing/scenarios/save?scenario_id=${savedScenarioId}`
      : "/api/publishing/scenarios/save";
     
     debugLog("Save endpoint:", endpoint)
     debugLog("savedScenarioId:", savedScenarioId)
     debugLog("Payload keys:", Object.keys(payload))
     debugLog("Payload structure:", {
       title: payload.title,
       key_figures_count: payload.key_figures?.length,
       scenes_count: payload.scenes?.length,
       learning_outcomes_count: payload.learning_outcomes?.length
     });
     
     const response = await apiClient.apiRequest(endpoint, {
       method: "POST",
       body: JSON.stringify(payload),
     });

     debugLog("Save response status:", response.status);
     debugLog("Save response ok:", response.ok);

     if (response.ok) {
       const result = await response.json();
       setIsSaved(true);
       setSavedScenarioId(result.scenario_id); // Store the scenario ID
       debugLog("Scenario saved:", result);
       
       // Reset save status after 3 seconds to show it's temporary
       setTimeout(() => {
         setIsSaved(false);
       }, 3000);
       
       return result.scenario_id;
     } else {
       const errorText = await response.text();
       console.error("Failed to save scenario:", response.status, errorText);
       alert(`Failed to save scenario (${response.status}): ${errorText}`);
       return null;
     }
   } catch (error) {
     console.error("Error saving scenario:", error);
     const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
     alert(`Error saving scenario: ${errorMessage}`);
     return null;
   } finally {
     setIsSaving(false);
   }
 };

 const handlePublish = async () => {
   // Check if we have scenario data (either from autofill or from draft editing)
   if (!autofillResult && !isSaved) {
     alert("No scenario data to publish. Please save the scenario first.");
     return;
   }

   setIsPublishing(true);
   try {
     // First save if not already saved
     let scenarioId = savedScenarioId;
     if (!isSaved || !scenarioId) {
       scenarioId = await handleSave();
     }
     
     if (!scenarioId) {
       alert("Failed to save scenario. Cannot publish.");
       return;
     }
     
     // Actually publish the scenario
     const publishData = {
       category: autofillResult?.industry || "Business",
       difficulty_level: "Intermediate",
       tags: ["case-study", "management", "teamwork"],
       estimated_duration: 60
     };
     
           const response = await apiClient.apiRequest(`/api/publishing/scenarios/publish/${scenarioId}`, {
       method: "POST",
       body: JSON.stringify(publishData),
     });

     if (response.ok) {
       const result = await response.json();
       setIsPublished(true);
       debugLog("Scenario published:", result);
       
       // Reset publish status after 3 seconds
       setTimeout(() => {
         setIsPublished(false);
       }, 3000);
     } else {
       console.error("Failed to publish scenario");
       alert("Failed to publish scenario. Please try again.");
     }
   } catch (error) {
     console.error("Error publishing scenario:", error);
     alert("Error publishing scenario. Please try again.");
   } finally {
     setIsPublishing(false);
   }
 };

 // Reset save status when content changes
 const markAsUnsaved = () => {
   setIsSaved(false);
   setIsPublished(false);
 };

 // Handle Play Scenario - save first if needed, then navigate to chatbox
 const handlePlayScenario = async () => {
   if (!autofillResult) {
     alert("No scenario data to play. Please upload and process a PDF first.");
     return;
   }

   let scenarioId = savedScenarioId;
   
   // Only allow play if scenario is already saved
   if (!scenarioId) {
     alert("Please save the scenario before playing.");
     return;
   }

   // Store scenario ID for chatbox
   const chatboxData = {
     scenario_id: scenarioId,
     title: autofillResult.title || "Untitled Scenario"
   };
   
   localStorage.setItem("chatboxScenario", JSON.stringify(chatboxData));
   
  // Navigate to chatbox
  window.open("/professor/test-simulations", "_blank");
 };

 // Transform our scenario data to chatbox format
 const transformTochatboxFormat = (scenarioData: any) => {
   const characters = scenarioData.key_figures?.map((figure: any) => ({
     name: figure.name,
     role: figure.role,
     personality_profile: {
       strengths: [],
       motivations: figure.primary_goals || [],
       leadership_style: figure.background || "",
       key_quote: `As ${figure.role}, I focus on achieving our objectives.`,
       decision_making_approach: "Strategic and analytical",
       risk_tolerance: "Medium",
       communication_style: "Professional and direct",
       background: figure.background || "",
       correlation: figure.correlation || ""
     }
   })) || [];

   const phases = scenarioData.scenes?.map((scene: any, index: number) => ({
     phase: index + 1,
     title: scene.title,
     duration: `${scene.estimated_duration || 30} minutes`,
     goal: scene.user_goal || "Complete the phase objectives",
     activities: [scene.description || "Analyze the situation and make decisions"],
     deliverables: [
       "Analysis summary",
       "Strategic recommendations",
       "Decision rationale"
     ]
   })) || [
     {
       phase: 1,
       title: "Initial Analysis",
       duration: "30 minutes",
       goal: "Analyze the business situation and identify key challenges",
       activities: ["Review case study materials", "Identify stakeholders", "Assess current situation"],
       deliverables: ["Situation analysis", "Stakeholder map", "Problem identification"]
     }
   ];

   return {
     case_study: {
       title: scenarioData.title,
       description: scenarioData.description,
       industry: "Business",
       primary_challenge: "Strategic decision making",
       learning_outcomes: (scenarioData.learning_outcomes || []).map((outcome: string) => ({
         outcome: outcome.replace(/^\d+\.\s*/, ''), // Remove numbering
         description: `Students will ${outcome.toLowerCase()}`
       })),
       characters: characters,
       simulation_timeline: {
         total_duration: `${phases.length * 30} minutes`,
         phases: phases
       },
       teaching_notes: {
         preparation_required: "Students should review the case study materials thoroughly",
         key_concepts: [
           "Strategic analysis",
           "Decision making", 
           "Business problem solving"
         ]
       }
     }
   };
 };

 // Placeholder handlers for personas and timeline
 const handleAddPersona = () => {
   const newPersona = {
     id: `temp-persona-${Date.now()}`,
     name: "New Persona",
     position: "",
     description: "",
     traits: {
       analytical: 5,
       creative: 5,
       assertive: 5,
       collaborative: 5,
       detail_oriented: 5,
       risk_taking: 5,
       empathetic: 5,
       decisive: 5
     },
     defaultTraits: {
       analytical: 5,
       creative: 5,
       assertive: 5,
       collaborative: 5,
       detail_oriented: 5,
       risk_taking: 5,
       empathetic: 5,
       decisive: 5
     },
     primaryGoals: "",
     isTemp: true // Mark as temporary
   };
   
   // Add to temporary personas at the top
   setTempPersonas(tempPersonas => [newPersona, ...tempPersonas]);
   setEditingIdx(0); // Open the new persona for editing (it's at index 0 now)
 }
 const handleAddScene = () => {
   const newScene = {
     id: `scene-${Date.now()}`,
     title: "New Scene",
     description: "",
     personas_involved: [],
     user_goal: "",
     sequence_order: scenes.length + 1,
     image_url: "",
     timeout_turns: 15 // Use timeout_turns, not max_turns
   };
   setScenes(scenes => [...scenes, newScene]);
   setEditingSceneIdx(scenes.length); // Open the new scene for editing
 }


 // Handler to clear the uploaded file and open the file picker
 const handleChooseDifferentFile = (e: React.MouseEvent) => {
   e.preventDefault();
   setUploadedFile(null);
   if (fileInputRef.current) fileInputRef.current.value = "";
 }


 const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
   const file = e.target.files?.[0]
   if (file) setUploadedFile(file)
 }

 const handleTeachingNotesFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
   const file = e.target.files?.[0]
   if (file) setTeachingNotesFile(file)
 }

 const handleTeachingNotesDragOver = (e: React.DragEvent) => {
   e.preventDefault()
 }

 const handleTeachingNotesDragLeave = (e: React.DragEvent) => {
   e.preventDefault()
 }

 const handleTeachingNotesDrop = (e: React.DragEvent) => {
   e.preventDefault()
   
   const files = Array.from(e.dataTransfer.files)
   const file = files[0] // Take the first file
  
   if (file) {
     setTeachingNotesFile(file)
     if (teachingNotesInputRef.current) {
       teachingNotesInputRef.current.value = ""
     }
   }
 }


 const handleDragOver = (e: React.DragEvent) => {
   e.preventDefault()
   setIsDragOver(true)
 }


 const handleDragLeave = (e: React.DragEvent) => {
   e.preventDefault()
   setIsDragOver(false)
 }


 const handleDrop = (e: React.DragEvent) => {
   e.preventDefault()
   setIsDragOver(false)
  
   const files = Array.from(e.dataTransfer.files)
   const file = files[0] // Take the first file
  
   if (file) {
     setUploadedFile(file)
     // Clear the file input value to ensure it updates
     if (fileInputRef.current) {
       fileInputRef.current.value = ""
     }
   } else {
     alert("Please drop a PDF file")
   }
 }


 // Handler for "Upload Files" button
 const handleFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
   if (e.target.files) {
     const filesArray = Array.from(e.target.files);
     setUploadedFiles(filesArray);
     debugLog("Context files selected:", filesArray.map(f => f.name));
   }
 };
 const handleUploadFilesClick = () => {
   filesInputRef.current?.click();
 };


 // Handler to remove a file from uploadedFiles
 const handleRemoveFile = (idx: number) => {
   setUploadedFiles(files => files.filter((_, i) => i !== idx));
 };


 const handleAutofillWithProgress = async () => {
  if (!uploadedFile) return;
  
  // Reset AI enhancement completion state when starting new autofill
  setAiEnhancementComplete(false);
  
  try {
    // Include teaching notes as context files if available
    const contextFiles = [...uploadedFiles];
    if (teachingNotesFile) {
      contextFiles.push(teachingNotesFile);
    }
    
    const result = await parsePDFWithProgress({
      file: uploadedFile,
      contextFiles: contextFiles,
      saveToDb: false
    });

    if (result.success && result.data) {
      // Process the result similar to the original handleAutofill
      const aiData = result.data;
      debugLog("AI Result:", aiData);
      
      // Set the title
      if (aiData.title) {
        debugLog("Setting title:", aiData.title);
        setName(aiData.title);
      }
      
      // Set the description
      if (aiData.description) {
        const formattedDescription = formatDescription(aiData.description);
        setDescription(formattedDescription);
      }
      
      // Set the student role
      if (aiData.student_role) {
        debugLog("Setting student role:", aiData.student_role);
        setStudentRole(aiData.student_role);
      }
      
      // Set the learning outcomes
      if (aiData.learning_outcomes && Array.isArray(aiData.learning_outcomes)) {
        const formattedOutcomes = formatLearningOutcomes(aiData.learning_outcomes);
        setLearningOutcomes(formattedOutcomes);
      }
      
      // Process personas from key_figures
      if (aiData.key_figures && Array.isArray(aiData.key_figures)) {
        const studentRole = aiData.student_role?.toLowerCase() || '';
        
        const filteredFigures = aiData.key_figures.filter((figure: any) => {
          const figureName = figure.name?.toLowerCase() || '';
          const figureRole = figure.role?.toLowerCase() || '';
          
          // Skip if this figure matches the student role exactly
          if (studentRole && (figureName.includes(studentRole) || figureRole.includes(studentRole))) {
            return false;
          }
          
          // Skip if this figure has a role that suggests they're the main protagonist
          const protagonistRoles = ['protagonist', 'main character', 'lead', 'principal', 'central figure'];
          if (protagonistRoles.some(role => figureRole.includes(role))) {
            return false;
          }
          
          return true;
        });
        
        const newPersonas = filteredFigures.map((figure: any, index: number) => {
          // Format goals properly
          let formattedGoals = 'Goals not specified in the case study.';
          if (Array.isArray(figure.primary_goals) && figure.primary_goals.length > 0) {
            formattedGoals = figure.primary_goals.map((goal: string) => `• ${goal}`).join('\n');
          } else if (typeof figure.primary_goals === 'string' && figure.primary_goals.trim()) {
            const goals = figure.primary_goals.split(/[;\n]/).map((goal: string) => goal.trim()).filter((goal: string) => goal.length > 0);
            if (goals.length > 1) {
              formattedGoals = goals.map((goal: string) => `• ${goal}`).join('\n');
            } else {
              formattedGoals = `• ${figure.primary_goals}`;
            }
          }
          
          return {
            id: `persona-${Date.now()}-${index}`,
            name: figure.name || `Person ${index + 1}`,
            position: figure.role || 'Unknown',
            description: formatDescription(figure.background || figure.correlation || 'No background information available.'),
            primaryGoals: formattedGoals,
            traits: {
              analytical: figure.personality_traits?.analytical || 5,
              creative: figure.personality_traits?.creative || 5,
              assertive: figure.personality_traits?.assertive || 5,
              collaborative: figure.personality_traits?.collaborative || 5,
              detail_oriented: figure.personality_traits?.detail_oriented || 5,
              risk_taking: figure.personality_traits?.risk_taking || 5,
              empathetic: figure.personality_traits?.empathetic || 5,
              decisive: figure.personality_traits?.decisive || 5
            },
            defaultTraits: {
              analytical: 5,
              creative: 5,
              assertive: 5,
              collaborative: 5,
              detail_oriented: 5,
              risk_taking: 5,
              empathetic: 5,
              decisive: 5
            }
          };
        });
        
        setPersonas(newPersonas);
      } else {
        setPersonas([]);
      }
      
      // Process scenes from AI results
      if (aiData.scenes && Array.isArray(aiData.scenes)) {
        const processedScenes = aiData.scenes
          .sort((a: any, b: any) => (a.sequence_order || 0) - (b.sequence_order || 0))
          .map((scene: any, index: number) => ({
            id: `scene-${Date.now()}-${index}`,
            title: scene.title || `Scene ${index + 1}`,
            description: scene.description || '',
            personas_involved: scene.personas_involved || [],
            user_goal: scene.user_goal || '',
            sequence_order: scene.sequence_order || index + 1,
            image_url: scene.image_url || '',
            successMetric: scene.successMetric || '',
            timeout_turns: scene.timeout_turns !== undefined && scene.timeout_turns !== null ? scene.timeout_turns : 15
          }));
        
        setScenes(processedScenes);
      } else {
        setScenes([]);
      }
      
      setAutofillResult(result);
      markAsUnsaved();
    }
  } catch (err: any) {
    console.error("Autofill with progress error:", err);
    setAutofillError(err.message || "Unknown error occurred during autofill");
  }
};

const handleFieldUpdate = (fieldName: string, fieldValue: any) => {
  console.log('Updating field:', fieldName, fieldValue);
  
  switch (fieldName) {
    case 'title':
      setName(fieldValue);
      markAsUnsaved();
      break;
    case 'description':
      const formattedDescription = formatDescription(fieldValue);
      setDescription(formattedDescription);
      markAsUnsaved();
      break;
    case 'student_role':
      // Update student role in autofillResult
      setAutofillResult((prev: any) => ({
        ...prev,
        student_role: fieldValue
      }));
      markAsUnsaved();
      break;
    case 'personas':
      // Filter out personas that match the student role
      const filteredFigures = fieldValue.filter((figure: any) => {
        const figureName = (figure.name || '').toLowerCase();
        const figureRole = (figure.role || '').toLowerCase();
        const studentRole = (fieldValue.student_role || '').toLowerCase();
        
        // Skip if this figure matches the student role exactly
        if (studentRole && (figureName.includes(studentRole) || figureRole.includes(studentRole))) {
          return false;
        }
        
        // Skip if this figure has a role that suggests they're the main protagonist
        const protagonistRoles = ['protagonist', 'main character', 'lead', 'principal', 'central figure'];
        if (protagonistRoles.some(role => figureRole.includes(role))) {
          return false;
        }
        
        return true;
      });
      
      const newPersonas = filteredFigures.map((figure: any, index: number) => {
        // Format goals properly
        let formattedGoals = 'Goals not specified in the case study.';
        if (Array.isArray(figure.primary_goals) && figure.primary_goals.length > 0) {
          formattedGoals = figure.primary_goals.map((goal: string) => `• ${goal}`).join('\n');
        } else if (typeof figure.primary_goals === 'string' && figure.primary_goals.trim()) {
          formattedGoals = figure.primary_goals;
        }
        
        return {
          id: `persona-${index}`,
          name: figure.name || `Persona ${index + 1}`,
          role: figure.role || 'Unknown Role',
          background: figure.background || 'Background not specified in the case study.',
          goals: formattedGoals,
          personality: figure.personality_traits ? Object.entries(figure.personality_traits)
            .map(([trait, value]) => `${trait}: ${value}/10`)
            .join(', ') : 'Personality traits not specified in the case study.',
          correlation: figure.correlation || 'Correlation not specified in the case study.',
          isMainCharacter: figure.is_main_character || false
        };
      });
      
      setPersonas(newPersonas);
      markAsUnsaved();
      break;
    case 'scenes':
      if (Array.isArray(fieldValue)) {
        const formattedScenes = fieldValue.map((scene: any, index: number) => ({
          id: `scene-${index}`,
          title: scene.title || `Scene ${index + 1}`,
          description: scene.description || 'Description not provided.',
          personasInvolved: scene.personas_involved || [],
          userGoal: scene.user_goal || 'Goal not specified.',
          sequenceOrder: scene.sequence_order || index + 1,
          imageUrl: scene.image_url || '',
          successMetric: scene.success_metric || 'Success metric not specified.',
          goal: scene.goal || 'Goal not specified.',
          // Preserve all other AI-generated fields
          ...scene
        }));
        console.log('Scenes updated with images:', formattedScenes.map(s => ({ 
          title: s.title, 
          imageUrl: s.imageUrl,
          hasImage: !!s.imageUrl 
        })));
        setScenes(formattedScenes);
        markAsUnsaved();
      }
      break;
          case 'learning_outcomes':
            if (Array.isArray(fieldValue)) {
              setLearningOutcomes(formatLearningOutcomes(fieldValue as string[]));
              markAsUnsaved();
            }
            break;
          case 'ai_enhancement_complete':
            // Mark AI enhancement as complete when backend signals completion
            console.log('AI enhancement completed by backend');
            setAiEnhancementComplete(true);
            markAsUnsaved();
            break;
          default:
            console.log('Unknown field:', fieldName);
  }
};

const handleAutofill = async () => {
   if (!uploadedFile) return;
   setAutofillLoading(true);
   setAutofillError(null);
   setAutofillResult(null);
   setAutofillStep("Processing PDF and context files...");
   setAutofillProgress(25);
  
   try {
     const formData = new FormData();
     formData.append("file", uploadedFile);
     
     // Attach context files if any were uploaded via the bottom button
     if (uploadedFiles.length > 0) {
       uploadedFiles.forEach((file) => {
         formData.append("context_files", file);
       });
     }
     debugLog("handleAutofill: PDF file to upload:", uploadedFile.name);
     debugLog("handleAutofill: Context files to upload:", uploadedFiles.map(f => f.name));
     
     setAutofillStep("Sending files to backend...");
     setAutofillProgress(50);
     
     const response = await fetch(buildApiUrl("/api/parse-pdf/"), {
       method: "POST",
       body: formData,
       credentials: 'include',
     });
    
     if (!response.ok) {
       throw new Error("Failed to process PDF");
     }
    
     setAutofillStep("Processing with AI...");
     setAutofillProgress(75);
     
     const resultData = await response.json();
     debugLog("Backend response:", resultData);
     debugLog("Response status:", resultData.status);
     debugLog("AI result exists:", !!resultData.ai_result);
     debugLog("Response keys:", Object.keys(resultData));
    
     if (resultData.status === "completed" && resultData.ai_result) {
       setAutofillStep("Complete!");
       setAutofillProgress(100);
       setAutofillResult(resultData);
      
       // Populate form fields with AI results
       const aiData = resultData.ai_result;
       debugLog("AI Result:", aiData);
       debugLog("AI Result keys:", Object.keys(aiData));
      
       // Set the title
       if (aiData.title) {
         debugLog("Setting title:", aiData.title);
         setName(aiData.title);
       } else {
         debugLog("No title found in AI result");
       }
      
       // Set the description
       if (aiData.description) {
         console.log("Setting description:", aiData.description);
         const formattedDescription = formatDescription(aiData.description);
         console.log("Formatted description:", formattedDescription);
         setDescription(formattedDescription);
       } else {
         debugLog("No description found in AI result");
         console.log("Description field value:", aiData.description);
       }
      
      // Set the learning outcomes with proper formatting
      if (aiData.learning_outcomes && Array.isArray(aiData.learning_outcomes)) {
        debugLog("Setting learning outcomes:", aiData.learning_outcomes);
        const formattedOutcomes = formatLearningOutcomes(aiData.learning_outcomes);
        console.log("Formatted learning outcomes:", formattedOutcomes);
        setLearningOutcomes(formattedOutcomes);
      } else {
        debugLog("No learning outcomes found in AI result");
      }
       
       // Create personas from key figures (excluding the student role)
       debugLog("Checking for key_figures in aiData:", aiData.key_figures);
       if (aiData.key_figures && Array.isArray(aiData.key_figures)) {
         debugLog("=== KEY FIGURES DEBUG ===");
         debugLog("Total key figures identified:", aiData.key_figures.length);
         debugLog("All key figures:", aiData.key_figures);
         console.log("Student role:", aiData.student_role);
         
         console.log("=== FILTERING PROCESS ===");
         
         // Only exclude the actual main character (student role), not everyone mentioned in the description
         const studentRole = aiData.student_role?.toLowerCase() || '';
         
         console.log(`[DEBUG] Student role: "${studentRole}"`);
         
         const filteredFigures = aiData.key_figures.filter((figure: any) => {
           const figureName = figure.name?.toLowerCase() || '';
           const figureRole = figure.role?.toLowerCase() || '';
           
           console.log(`[DEBUG] Checking figure: "${figure.name}" (role: "${figure.role}")`);
           
           // Check 1: Skip if this figure matches the student role exactly
           if (studentRole && (figureName.includes(studentRole) || figureRole.includes(studentRole))) {
             console.log(`[DEBUG] ❌ EXCLUDING ${figure.name} - matches student role: "${studentRole}"`);
             return false;
           }
           
           // Check 2: Skip if this figure has a role that suggests they're the main protagonist
           // Only exclude if they're clearly the main character, not just mentioned in the description
           const protagonistRoles = ['protagonist', 'main character', 'lead', 'principal', 'central figure'];
           if (protagonistRoles.some(role => figureRole.includes(role))) {
             console.log(`[DEBUG] ❌ EXCLUDING ${figure.name} - has protagonist role: "${figureRole}"`);
             return false;
           }
           
           console.log(`[DEBUG] ✅ KEEPING ${figure.name}`);
           return true;
         });
         
         debugLog(`After filtering: ${filteredFigures.length} figures remain out of ${aiData.key_figures.length} total`);
         
         const newPersonas = filteredFigures
           .map((figure: any, index: number) => {
             debugLog(`Processing key figure ${index + 1}:`, figure);
             console.log(`[DEBUG] Personality traits for ${figure.name}:`, figure.personality_traits);
             console.log(`[DEBUG] Primary goals for ${figure.name}:`, figure.primary_goals);
             
             // Format goals properly
             let formattedGoals = 'Goals not specified in the case study.';
             if (Array.isArray(figure.primary_goals) && figure.primary_goals.length > 0) {
               formattedGoals = figure.primary_goals.map((goal: string) => `• ${goal}`).join('\n');
             } else if (typeof figure.primary_goals === 'string' && figure.primary_goals.trim()) {
               // If it's a string, try to split by common separators and bullet them
               const goals = figure.primary_goals.split(/[;\n]/).map((goal: string) => goal.trim()).filter((goal: string) => goal.length > 0);
               if (goals.length > 1) {
                 formattedGoals = goals.map((goal: string) => `• ${goal}`).join('\n');
               } else {
                 formattedGoals = `• ${figure.primary_goals}`;
               }
             }
             
             console.log(`[DEBUG] Formatted goals for ${figure.name}:`, formattedGoals);
             
             return {
               id: `persona-${Date.now()}-${index}`,
               name: figure.name || `Person ${index + 1}`,
               position: figure.role || 'Unknown',
               description: formatDescription(figure.background || figure.correlation || 'No background information available.'),
               primaryGoals: formattedGoals,
               traits: {
                analytical: figure.personality_traits?.analytical || 5,
                creative: figure.personality_traits?.creative || 5,
                assertive: figure.personality_traits?.assertive || 5,
                collaborative: figure.personality_traits?.collaborative || 5,
                detail_oriented: figure.personality_traits?.detail_oriented || 5,
                risk_taking: figure.personality_traits?.risk_taking || 5,
                empathetic: figure.personality_traits?.empathetic || 5,
                decisive: figure.personality_traits?.decisive || 5
               },
               defaultTraits: {
                analytical: 5,
                creative: 5,
                assertive: 5,
                collaborative: 5,
                detail_oriented: 5,
                risk_taking: 5,
                empathetic: 5,
                decisive: 5
               }
             };
           });
         
         console.log("=== FINAL PERSONAS ===");
         console.log(`Total personas created: ${newPersonas.length}`);
         newPersonas.forEach((persona: any, index: number) => {
           console.log(`Persona ${index + 1}: ${persona.name} (${persona.position})`);
           console.log(`  Goals: ${persona.primaryGoals}`);
           console.log(`  Personality:`, persona.traits);
         });
         setPersonas(newPersonas);
       } else {
         debugLog("No key_figures found in aiData, creating empty personas array");
         setPersonas([]);
       }
       
       // Process scenes from AI results
       debugLog("Checking for scenes in aiData:", aiData.scenes);
       if (aiData.scenes && Array.isArray(aiData.scenes)) {
         console.log("=== SCENES DEBUG ===");
         debugLog("Total scenes identified:", aiData.scenes.length);
         console.log("All scenes:", aiData.scenes);
         
         const processedScenes = aiData.scenes
           .sort((a: any, b: any) => (a.sequence_order || 0) - (b.sequence_order || 0)) // Sort by sequence order
           .map((scene: any, index: number) => {
             console.log(`[DEBUG] Processing scene ${index + 1}:`, scene);
             return {
               id: `scene-${Date.now()}-${index}`,
               title: scene.title || `Scene ${index + 1}`,
               description: scene.description || '',
               personas_involved: scene.personas_involved || [],
               user_goal: scene.user_goal || '',
               sequence_order: scene.sequence_order || index + 1,
               image_url: scene.image_url || '',
               successMetric: scene.successMetric || '',
               timeout_turns: scene.timeout_turns !== undefined && scene.timeout_turns !== null ? scene.timeout_turns : 15
             };
           });
         
         console.log("=== FINAL SCENES ===");
         console.log(`Total scenes created: ${processedScenes.length}`);
         processedScenes.forEach((scene: any, index: number) => {
           console.log(`Scene ${index + 1}: ${scene.title}`);
           console.log(`  Goal: ${scene.user_goal}`);
           console.log(`  Personas: ${scene.personas_involved?.join(', ') || 'None'}`);
           console.log(`  Image: ${scene.image_url ? 'Generated' : 'None'}`);
         });
         setScenes(processedScenes);
         console.log("Processed scenes:", processedScenes.map((s: any) => ({ title: s.title, personas_involved: s.personas_involved || [] })));
       } else {
         console.log("[DEBUG] No scenes found in aiData, creating empty scenes array");
         setScenes([]);
       }
      
     } else {
       console.log("No AI result found in response:", resultData);
       console.log("Full result data:", resultData);
       throw new Error("No AI result received from backend");
     }
    
   } catch (err: any) {
     console.error("Autofill error details:", err);
     console.error("Error stack:", err.stack);
     setAutofillError(err.message || "Unknown error occurred during autofill");
  } finally {
    setAutofillLoading(false);
    setAutofillStep("");
    setAutofillProgress(0);
  }
};

const handleAutofillWithTeachingNotes = async () => {
  if (!teachingNotesFile && !uploadedFile) return;
  setAutofillLoading(true);
  setAutofillError(null);
  setAutofillResult(null);
  setAutofillStep(teachingNotesFile ? "Processing Teaching Notes as primary context..." : "Processing Business Case Study...");
  setAutofillProgress(25);
 
  try {
    const formData = new FormData();
    
    // Add Teaching Notes as the primary file if available, otherwise use Business Case Study
    if (teachingNotesFile) {
      formData.append("file", teachingNotesFile);
      // Add Business Case Study as secondary context if available
      if (uploadedFile) {
        formData.append("context_files", uploadedFile);
      }
    } else if (uploadedFile) {
      // If no Teaching Notes, use Business Case Study as primary
      formData.append("file", uploadedFile);
    }
    
    // Attach any additional context files
    if (uploadedFiles.length > 0) {
      uploadedFiles.forEach((file) => {
        formData.append("context_files", file);
      });
    }
    
    console.log("[DEBUG] handleAutofillWithTeachingNotes: Primary file (Teaching Notes):", teachingNotesFile?.name || "None");
    console.log("[DEBUG] handleAutofillWithTeachingNotes: Secondary context (Business Case Study):", uploadedFile?.name || "None");
    console.log("[DEBUG] handleAutofillWithTeachingNotes: Additional context files:", uploadedFiles.map(f => f.name));
    
    setAutofillStep("Processing Uploaded Files...");
    setAutofillProgress(50);
    
    const response = await fetch(buildApiUrl("/api/parse-pdf/"), {
      method: "POST",
      body: formData,
      credentials: 'include',
    });
   
    if (!response.ok) {
      throw new Error(teachingNotesFile ? "Failed to process Teaching Notes and context files" : "Failed to process Business Case Study");
    }
   
    setAutofillStep(teachingNotesFile ? "Processing with AI using Teaching Notes as primary context..." : "Processing with AI using Business Case Study...");
    setAutofillProgress(75);
    
    const resultData = await response.json();
    console.log(`Backend response (${teachingNotesFile ? 'Teaching Notes priority' : 'Business Case Study only'}):`, resultData);
    console.log("Response status:", resultData.status);
    console.log("AI result exists:", !!resultData.ai_result);
    debugLog("Response keys:", Object.keys(resultData));
   
    if (resultData.status === "completed" && resultData.ai_result) {
      setAutofillStep("Complete!");
      setAutofillProgress(100);
      setAutofillResult(resultData);
     
      // Populate form fields with AI results (same logic as handleAutofill)
      const aiData = resultData.ai_result;
      console.log(`AI Result (${teachingNotesFile ? 'Teaching Notes priority' : 'Business Case Study only'}):`, aiData);
      
      // Set the title (same logic as handleAutofill)
      if (aiData.title) {
        console.log("Setting title:", aiData.title);
        setName(aiData.title);
      } else {
        console.log("No title found in AI result");
      }
      
      // Set the description with proper formatting
      if (aiData.description) {
        console.log("Setting description:", aiData.description);
        const formattedDescription = formatDescription(aiData.description);
        console.log("Formatted description:", formattedDescription);
        setDescription(formattedDescription);
      } else {
        console.log("No description found in AI result");
      }
      
      // Set the learning outcomes with proper formatting
      if (aiData.learning_outcomes && Array.isArray(aiData.learning_outcomes)) {
        debugLog("Setting learning outcomes:", aiData.learning_outcomes);
        const formattedOutcomes = formatLearningOutcomes(aiData.learning_outcomes);
        console.log("Formatted learning outcomes:", formattedOutcomes);
        setLearningOutcomes(formattedOutcomes);
      } else {
        debugLog("No learning outcomes found in AI result");
      }
      
      // Process personas from key_figures with Teaching Notes context (same logic as main handler)
      debugLog("Checking for key_figures in aiData (Teaching Notes):", aiData.key_figures);
      if (aiData.key_figures && Array.isArray(aiData.key_figures)) {
        debugLog(`=== KEY FIGURES DEBUG (${teachingNotesFile ? 'Teaching Notes Priority' : 'Business Case Study Only'}) ===`);
        debugLog("Total key figures identified:", aiData.key_figures.length);
        debugLog("All key figures:", aiData.key_figures);
        console.log("Student role:", aiData.student_role);
        
        console.log("=== FILTERING PROCESS (Teaching Notes) ===");
        
        // Only exclude the actual main character (student role), not everyone mentioned in the description
        const studentRole = aiData.student_role?.toLowerCase() || '';
        
        console.log(`[DEBUG] Student role: "${studentRole}"`);
        
        const filteredFigures = aiData.key_figures.filter((figure: any) => {
          const figureName = figure.name?.toLowerCase() || '';
          const figureRole = figure.role?.toLowerCase() || '';
          
          console.log(`[DEBUG] Checking figure: "${figure.name}" (role: "${figure.role}")`);
          
          // Check 1: Skip if this figure matches the student role exactly
          if (studentRole && (figureName.includes(studentRole) || figureRole.includes(studentRole))) {
            console.log(`[DEBUG] ❌ EXCLUDING ${figure.name} - matches student role: "${studentRole}"`);
            return false;
          }
          
          // Check 2: Skip if this figure has a role that suggests they're the main protagonist
          // Only exclude if they're clearly the main character, not just mentioned in the description
          const protagonistRoles = ['protagonist', 'main character', 'lead', 'principal', 'central figure'];
          if (protagonistRoles.some(role => figureRole.includes(role))) {
            console.log(`[DEBUG] ❌ EXCLUDING ${figure.name} - has protagonist role: "${figureRole}"`);
            return false;
          }
          
          console.log(`[DEBUG] ✅ KEEPING ${figure.name}`);
          return true;
        });
        
        debugLog(`After filtering: ${filteredFigures.length} figures remain out of ${aiData.key_figures.length} total`);
        
        const newPersonas = filteredFigures
          .map((figure: any, index: number) => {
            debugLog(`Processing key figure ${index + 1}:`, figure);
            console.log(`[DEBUG] Personality traits for ${figure.name}:`, figure.personality_traits);
            console.log(`[DEBUG] Primary goals for ${figure.name}:`, figure.primary_goals);
            
            // Format goals properly
            let formattedGoals = 'Goals not specified in the case study.';
            if (Array.isArray(figure.primary_goals) && figure.primary_goals.length > 0) {
              formattedGoals = figure.primary_goals.map((goal: string) => `• ${goal}`).join('\n');
            } else if (typeof figure.primary_goals === 'string' && figure.primary_goals.trim()) {
              // If it's a string, try to split by common separators and bullet them
              const goals = figure.primary_goals.split(/[;\n]/).map((goal: string) => goal.trim()).filter((goal: string) => goal.length > 0);
              if (goals.length > 1) {
                formattedGoals = goals.map((goal: string) => `• ${goal}`).join('\n');
              } else {
                formattedGoals = `• ${figure.primary_goals}`;
              }
            }
            
            console.log(`[DEBUG] Formatted goals for ${figure.name}:`, formattedGoals);
            
            return {
              id: `persona-${Date.now()}-${index}`,
              name: figure.name || `Person ${index + 1}`,
              position: figure.role || 'Unknown',
              description: formatDescription(figure.background || figure.correlation || 'No background information available.'),
              primaryGoals: formattedGoals,
              traits: {
                analytical: figure.personality_traits?.analytical || 5,
                creative: figure.personality_traits?.creative || 5,
                assertive: figure.personality_traits?.assertive || 5,
                collaborative: figure.personality_traits?.collaborative || 5,
                detail_oriented: figure.personality_traits?.detail_oriented || 5,
                risk_taking: figure.personality_traits?.risk_taking || 5,
                empathetic: figure.personality_traits?.empathetic || 5,
                decisive: figure.personality_traits?.decisive || 5
              },
              defaultTraits: {
                analytical: 5,
                creative: 5,
                assertive: 5,
                collaborative: 5,
                detail_oriented: 5,
                risk_taking: 5,
                empathetic: 5,
                decisive: 5
              }
            };
          });
        
        console.log("=== FINAL PERSONAS (Teaching Notes) ===");
        console.log(`Total personas created: ${newPersonas.length}`);
        newPersonas.forEach((persona: any, index: number) => {
          console.log(`Persona ${index + 1}: ${persona.name} (${persona.position})`);
          console.log(`  Goals: ${persona.primaryGoals}`);
          console.log(`  Personality:`, persona.traits);
        });
        setPersonas(newPersonas);
      } else {
        debugLog("No key_figures found in aiData (Teaching Notes), creating empty personas array");
        setPersonas([]);
      }
      
      // Process scenes with Teaching Notes context
      if (aiData.scenes && Array.isArray(aiData.scenes)) {
        console.log("Scenes identified (Teaching Notes priority):", aiData.scenes);
        setScenes(aiData.scenes);
      }
      
      markAsUnsaved();
    } else {
      throw new Error("AI processing failed or returned incomplete results");
    }
  } catch (err: any) {
    console.error("Error in handleAutofillWithTeachingNotes:", err);
    setAutofillError(err.message || "Unknown error occurred during Teaching Notes autofill");
  } finally {
    setAutofillLoading(false);
    setAutofillStep("");
    setAutofillProgress(0);
  }
};


 // Utility to normalize scenes
 function normalizeScenes(scenes: any[]) {
   // Only use timeout_turns for turn limit, not max_turns
   return scenes.map(scene => ({
     ...scene,
     image_url: scene.image_url, // Always preserve image_url
     timeout_turns:
       scene.timeout_turns !== undefined && scene.timeout_turns !== null
         ? scene.timeout_turns
         : 15,
   }));
 }


 // Helper to extract likely player name from the title
 function extractPlayerName(title: string) {
   if (!title) return "";
   // e.g., "Greg James at Sun Microsystems" => "Greg James"
   const match = title.match(/^([^,\-@]+?)(?:\s+at|\s+in|,|\-|$)/i);
   return match ? match[1].trim() : title.trim();
 }


 // Helper to normalize names for comparison
 function normalizeName(name: string) {
   return name ? name.replace(/[^a-zA-Z ]/g, "").toLowerCase().trim() : "";
 }


 function isLikelySamePerson(playerName: string, personaName: string) {
   const nPlayer = normalizeName(playerName);
   const nPersona = normalizeName(personaName);
   if (!nPlayer || !nPersona) return false;
   if (nPlayer === nPersona) return true;
   // Split into words and check for overlap
   const playerWords = nPlayer.split(" ").filter(Boolean);
   const personaWords = nPersona.split(" ").filter(Boolean);
   const overlap = playerWords.filter(word => personaWords.includes(word));
   return overlap.length >= 2; // At least first and last name match
 }


 // Helper to format description with proper paragraphs
 function formatDescription(text: string): string {
   if (!text) return '';
   
   // First, clean up the text by removing excessive whitespace
   let cleanedText = text.replace(/\s+/g, ' ').trim();
   
   // Split by common paragraph separators
   let paragraphs = cleanedText.split(/\n\s*\n/);
   
   // If no double line breaks, try splitting by single line breaks
   if (paragraphs.length <= 1) {
     paragraphs = cleanedText.split(/\n/);
   }
   
   // If still only one paragraph, try to break it up by sentences
   if (paragraphs.length <= 1) {
     const sentences = cleanedText.match(/[^.!?]+[.!?]+/g) || [];
     if (sentences.length > 2) {
       // Group sentences into paragraphs (2-3 sentences per paragraph)
       const groupedParagraphs = [];
       for (let i = 0; i < sentences.length; i += 2) {
         const paragraph = sentences.slice(i, i + 2).join(' ').trim();
         if (paragraph) groupedParagraphs.push(paragraph);
       }
       paragraphs = groupedParagraphs;
     }
   }
   
   // Clean up each paragraph
   paragraphs = paragraphs
     .map(p => p.trim())
     .filter(p => p.length > 0)
     .map(p => {
       // Remove excessive whitespace within paragraphs
       p = p.replace(/\s+/g, ' ');
       // Ensure proper sentence endings
       if (!p.endsWith('.') && !p.endsWith('!') && !p.endsWith('?')) {
         p += '.';
       }
       return p;
     });
   
   // Join with double line breaks for proper paragraph separation
   return paragraphs.join('\n\n');
 }

 // Helper to format learning outcomes with proper spacing
 function formatLearningOutcomes(outcomes: string[]): string {
   if (!outcomes || !Array.isArray(outcomes)) return '';
   
   return outcomes
     .map((outcome, index) => {
       // Clean up each outcome
       let cleaned = outcome.trim();
       // Remove existing numbering if present (e.g., "1. " or "• ")
       cleaned = cleaned.replace(/^[\d\-\•\*]\s*\.?\s*/, '');
       // Ensure it starts with a capital letter
       if (cleaned && !cleaned.match(/^[A-Z]/)) {
         cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
       }
       // Ensure it ends with proper punctuation
       if (cleaned && !cleaned.endsWith('.') && !cleaned.endsWith('!') && !cleaned.endsWith('?')) {
         cleaned += '.';
       }
       // Add proper numbering
       return `${index + 1}. ${cleaned}`;
     })
     .filter(outcome => outcome.length > 0)
     .join('\n\n'); // Use double line breaks for better spacing
 }


 // Helper to extract single names that might be the main character
 function extractSingleNames(title: string, description: string) {
   const names: string[] = [];
   const text = `${title} ${description}`;
   
   // Look for capitalized single names (likely main characters)
   const singleNameMatches = [...text.matchAll(/\b([A-Z][a-z]{2,})\b/g)];
   for (const match of singleNameMatches) {
     const name = match[1].trim();
     // Filter out common words that aren't names
     const commonWords = ['the', 'and', 'for', 'with', 'from', 'this', 'that', 'they', 'their', 'company', 'network', 'ltd', 'inc', 'corp'];
     if (!commonWords.includes(name.toLowerCase()) && name.length > 2) {
       if (!names.includes(name)) names.push(name);
     }
   }
   
   return names;
 }






 // Update persona traits handler
 const handleTraitsChange = (idx: number, newTraits: any) => {
   console.log(`[DEBUG] SimulationBuilder: handleTraitsChange called for persona ${idx} with traits:`, newTraits);
   
   // Check if we're editing a temporary persona
   if (editingIdx !== null && tempPersonas[editingIdx]?.isTemp) {
     setTempPersonas(tempPersonas => tempPersonas.map((p, i) => i === idx ? { ...p, traits: { ...newTraits } } : p));
     console.log(`[DEBUG] SimulationBuilder: Updated temp persona ${idx} traits`);
   } else {
     setPersonas(personas => personas.map((p, i) => i === idx ? { ...p, traits: { ...newTraits } } : p));
     console.log(`[DEBUG] SimulationBuilder: Updated persona ${idx} traits`);
   }
   markAsUnsaved(); // Mark as unsaved when traits change
 };


 // Save persona edits handler
 const handleSavePersona = (idx: number, updatedPersona: any) => {
   if (updatedPersona.isTemp) {
     // This is a temporary persona being saved for the first time
     const { isTemp, ...personaToSave } = updatedPersona; // Remove isTemp flag
     personaToSave.id = `persona-${Date.now()}-${idx}`; // Generate permanent ID
     
     // Remove from temp personas and add to permanent personas at the top
     setTempPersonas(tempPersonas => tempPersonas.filter((_, i) => i !== idx));
     setPersonas(personas => [personaToSave, ...personas]);
   } else {
     // This is an existing persona being updated
     setPersonas(personas => personas.map((p, i) => i === idx ? { ...updatedPersona } : p));
   }
   setEditingIdx(null);
   markAsUnsaved(); // Mark as unsaved when persona is saved/updated
 };


 // Delete persona handler
 const handleDeletePersona = (idx: number) => {
   // Check if we're editing a temporary persona
   if (editingIdx !== null && tempPersonas[editingIdx]?.isTemp) {
     // Delete from temporary personas
     setTempPersonas(tempPersonas => tempPersonas.filter((_, i) => i !== idx));
   } else {
     // Delete from permanent personas
     setPersonas(personas => personas.filter((_, i) => i !== idx));
   }
   setEditingIdx(null);
   markAsUnsaved(); // Mark as unsaved when persona is deleted
 };

 // Scene management handlers
 const handleSaveScene = (idx: number, updatedScene: any) => {
   setScenes(scenes => scenes.map((s, i) => {
     if (i === idx) {
       // Merge the updated scene, preserving all new fields (like timeout_turns)
       return { ...s, ...updatedScene };
     }
     return s;
   }));
   setEditingSceneIdx(null);
   markAsUnsaved(); // Mark as unsaved when scene is saved/updated
 };

 const handleDeleteScene = (idx: number) => {
   setScenes(scenes => scenes.filter((_, i) => i !== idx));
   setEditingSceneIdx(null);
   markAsUnsaved(); // Mark as unsaved when scene is deleted
};

// Debug logging for personas
console.log("[DEBUG] Temp personas to render:", tempPersonas.map(p => p.name));
console.log("[DEBUG] Permanent personas to render:", personas.map(p => p.name));

return (
   <div className="min-h-screen bg-background text-foreground">
     {/* New Sidebar Component */}
     <RoleBasedSidebar currentPath="/professor/simulation-builder" />
     
     {/* Main content area with left margin for sidebar */}
     <div className="ml-20">
     {/* Top overlay bar */}
     <div className="fixed top-0 left-20 right-0 z-40 bg-background shadow-lg flex items-center justify-between h-14 px-8">
       <span className="text-lg font-semibold">Simulation Builder</span>
       <div className="flex gap-4">
         <button 
           onClick={handleSave}
           disabled={isSaving}
           className={`rounded px-4 py-2 font-medium shadow transition flex items-center gap-2 ${
             isSaved 
               ? "bg-green-100 text-green-800 border border-green-300" 
               : "bg-white text-black hover:bg-gray-200"
           } ${isSaving ? "opacity-50 cursor-not-allowed" : ""}`}
         >
           {isSaving ? (
             "Saving..."
           ) : isSaved ? (
             <>
               <Check className="h-4 w-4" />
               Saved
             </>
           ) : (
             "Save"
           )}
         </button>
         <button 
           onClick={handlePublish}
           disabled={isPublishing}
           className={`rounded px-4 py-2 font-medium shadow transition flex items-center gap-2 ${
             isPublished 
               ? "bg-green-600 text-white" 
               : "bg-black text-white hover:bg-gray-800"
           } ${isPublishing ? "opacity-50 cursor-not-allowed" : ""}`}
         >
           {isPublishing ? (
             "Publishing..."
           ) : isPublished ? (
             <>
               <Check className="h-4 w-4" />
               Published
             </>
           ) : (
             "Publish"
           )}
         </button>
         {autofillResult && (
           <button 
             onClick={handlePlayScenario}
             className="bg-blue-600 text-white rounded px-4 py-2 font-medium shadow hover:bg-blue-700 transition flex items-center gap-2"
           >
             <Activity className="h-4 w-4" />
             Play Scenario
           </button>
         )}
       </div>
     </div>
     {/* Add top padding to prevent content from being hidden under the bar */}
     <div className="h-14" />
     {/* Main content area */}
     <div className="w-full pl-16 pr-16 py-10 flex justify-center">
       <div className="w-full max-w-4xl">
       {/* Header and Upload Row */}
       <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-8 mb-8 items-start">
         {/* Left: Title and Subtitle */}
         <div className="flex flex-col gap-2">
           <h1 className="text-2xl font-bold">Upload your Business Case Study</h1>
           <p className="text-muted-foreground text-sm">We will analyze the contents and autofill the configuration for you.</p>
         </div>
         {/* Right: Drag and Drop File Upload Box */}
         <div
           className={`border-2 border-dashed rounded-lg p-8 text-center transition-all duration-200 flex flex-col items-center justify-center min-h-[120px] cursor-pointer ${
             isDragOver
               ? 'border-blue-500 bg-blue-50 scale-105'
               : uploadedFile
               ? 'border-green-500 bg-green-50'
               : 'border-gray-300 bg-card hover:border-gray-400'
           }`}
           onDragOver={handleDragOver}
           onDragLeave={handleDragLeave}
           onDrop={handleDrop}
           onClick={() => fileInputRef.current?.click()}
         >
           {uploadedFile ? (
             <span className="flex flex-col items-center">
               {/* Red file icon */}
               <svg className="h-10 w-10 mx-auto mb-2 text-red-500" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                 <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                 <polyline points="14,2 14,8 20,8" />
                 <line x1="16" y1="13" x2="8" y2="13" />
                 <line x1="16" y1="17" x2="8" y2="17" />
                 <polyline points="10,9 9,9 8,9" />
               </svg>
               <span className="text-sm font-semibold text-green-700">File attached</span>
               <span className="text-xs text-green-600 mt-1">{uploadedFile.name}</span>
             </span>
           ) : (
             <>
               {/* Generic file icon - three overlapping documents */}
               <svg className="h-10 w-10 mx-auto mb-2 text-gray-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                 <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                 <polyline points="14,2 14,8 20,8" />
                 <line x1="16" y1="13" x2="8" y2="13" />
                 <line x1="16" y1="17" x2="8" y2="17" />
                 <polyline points="10,9 9,9 8,9" />
               </svg>
               
               <span className="font-medium text-gray-600">
                 <span className="font-bold text-black">Click here</span> to upload your file or drag and drop
               </span>
             </>
           )}
          
           <input
             id="file-upload"
             type="file"
             className="hidden"
             onChange={handleFileChange}
             ref={fileInputRef}
           />
         </div>
         <div className="flex gap-2 justify-right">


         </div>
        
       </div>


       {/* Teaching Notes Upload Section */}
       <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-8 mb-8 items-start">
         {/* Left: Title and Subtitle */}
         <div className="flex flex-col gap-2">
           <h1 className="text-2xl font-bold">Upload your Teaching Notes</h1>
           <p className="text-muted-foreground text-sm">We will use this for defining better learning outcomes and concise grading metrics.</p>
         </div>
         {/* Right: Drag and Drop File Upload Box */}
         <div
           className={`border-2 border-dashed rounded-lg p-8 text-center transition-all duration-200 flex flex-col items-center justify-center min-h-[120px] cursor-pointer ${
             teachingNotesFile
               ? 'border-green-500 bg-green-50'
               : 'border-gray-300 bg-card hover:border-gray-400'
           }`}
           onDragOver={handleTeachingNotesDragOver}
           onDragLeave={handleTeachingNotesDragLeave}
           onDrop={handleTeachingNotesDrop}
           onClick={() => teachingNotesInputRef.current?.click()}
         >
           {teachingNotesFile ? (
             <span className="flex flex-col items-center">
               {/* Red file icon */}
               <svg className="h-10 w-10 mx-auto mb-2 text-red-500" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                 <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                 <polyline points="14,2 14,8 20,8" />
                 <line x1="16" y1="13" x2="8" y2="13" />
                 <line x1="16" y1="17" x2="8" y2="17" />
                 <polyline points="10,9 9,9 8,9" />
               </svg>
               <span className="text-sm font-semibold text-green-700">File attached</span>
               <span className="text-xs text-green-600 mt-1">{teachingNotesFile.name}</span>
             </span>
           ) : (
             <>
               {/* Generic file icon - three overlapping documents */}
               <svg className="h-10 w-10 mx-auto mb-2 text-gray-400" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                 <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                 <polyline points="14,2 14,8 20,8" />
                 <line x1="16" y1="13" x2="8" y2="13" />
                 <line x1="16" y1="17" x2="8" y2="17" />
                 <polyline points="10,9 9,9 8,9" />
               </svg>
               
               <span className="font-medium text-gray-600">
                 <span className="font-bold text-black">Click here</span> to upload your file or drag and drop
               </span>
             </>
           )}
           
           <input
             id="teaching-notes-upload"
             type="file"
             className="hidden"
             onChange={handleTeachingNotesFileChange}
             ref={teachingNotesInputRef}
           />
           
         </div>
         
         <div className="flex gap-2 justify-right">


         </div>
         {/* Buttons directly below the upload box, perfectly aligned */}
         {(uploadedFile || teachingNotesFile) && (
           <div className="flex ml-25 gap-2 justify-right">
             {/* Choose a different file */}
             <button
               type="button"
               onClick={() => {
                 // Clear both files
                 setUploadedFile(null);
                 setTeachingNotesFile(null);
                 if (fileInputRef.current) fileInputRef.current.value = "";
                 if (teachingNotesInputRef.current) teachingNotesInputRef.current.value = "";
               }}
               className="bg-white text-black rounded px-4 py-2 font-medium shadow hover:bg-gray-200 transition border border-gray-300 h-10"
             >
               Choose a different file
             </button>
             {/* Use and autofill */}
             <button
               className="bg-black text-white rounded px-4 py-2 font-medium shadow hover:bg-gray-800 transition border border-black h-10 w-60whitespace-nowrap"
               onClick={() => {
                 // Use the new progress tracking for Business Case Study
                 if (uploadedFile) {
                   handleAutofillWithProgress();
                 } else if (teachingNotesFile) {
                   handleAutofillWithTeachingNotes();
                 } else {
                   console.log("No files uploaded for autofill");
                 }
               }}
               disabled={isParsingWithProgress || autofillLoading}
             >
               <Sparkles className="mr-2 h-4 w-5 text-white inline" />
               Use and autofill
             </button>
           </div>
         )}
       </div>


      {/* Show simulation builder progress */}
      <SimulationBuilderProgress
        name={name}
        description={description}
        studentRole={studentRole}
        personas={personas}
        scenes={scenes}
        learningOutcomes={learningOutcomes}
        isProcessing={isParsingWithProgress}
        isAIEnhancementComplete={!!(aiEnhancementComplete || (!isParsingWithProgress && sessionId && !parsingError))}
        completionStatus={completionStatus || undefined}
        hasAutofillResult={!!autofillResult}
        nameCompleted={dbCompletionFields.nameCompleted}
        descriptionCompleted={dbCompletionFields.descriptionCompleted}
        studentRoleCompleted={dbCompletionFields.studentRoleCompleted}
        personasCompleted={dbCompletionFields.personasCompleted}
        scenesCompleted={dbCompletionFields.scenesCompleted}
        imagesCompleted={dbCompletionFields.imagesCompleted}
        learningOutcomesCompleted={dbCompletionFields.learningOutcomesCompleted}
        aiEnhancementCompleted={dbCompletionFields.aiEnhancementCompleted}
        className="mt-4"
      />

      {/* Hidden PDF progress tracker for field updates */}
      {(isParsingWithProgress || sessionId) && (
        <div style={{ display: 'none' }}>
          <PDFProgressTrackerHTTP
            sessionId={sessionId || ''}
            onComplete={(result) => {
              console.log('PDF parsing completed:', result);
            }}
            onError={(error) => {
              console.error('PDF parsing error:', error);
              setAutofillError(error);
            }}
            onFieldUpdate={(fieldName, fieldValue) => {
              console.log('Field update received:', fieldName, fieldValue);
              handleFieldUpdate(fieldName, fieldValue);
            }}
          />
        </div>
      )}
         
         {/* Show legacy loading progress for Teaching Notes */}
         {autofillLoading && !isParsingWithProgress && (
           <div className="mt-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
             <div className="flex items-center justify-between mb-2">
               <span className="text-sm font-medium text-blue-800">{autofillStep}</span>
               <span className="text-xs text-blue-600">{Math.round(autofillProgress)}%</span>
             </div>
             <Progress value={autofillProgress} className="w-full h-2" />
           </div>
         )}
         
         {/* Show error */}
         {autofillError && (
           <div className="mt-4 p-4 bg-red-50 rounded-lg border border-red-200">
             <div className="flex items-center">
               <span className="text-red-600 font-medium">Error:</span>
               <span className="text-red-600 ml-2">{autofillError}</span>
             </div>
           </div>
         )}
        
         {/* Show success message */}
         {autofillResult && autofillStep === "Complete!" && (
           <div className="mt-4 p-4 bg-green-50 rounded-lg border border-green-200">
             <div className="flex items-center">
               <span className="text-green-600 font-medium">✓ Success!</span>
               <span className="text-green-600 ml-2">PDF content has been mapped to your form fields.</span>
             </div>
           </div>
         )}


       {/* Accordions */}
       <div className="w-full max-w-4xl">
         <Accordion type="multiple" className="space-y-6" defaultValue={['info', 'personas', 'timeline']}>
           {/* Information Accordion */}
           <AccordionItem value="info">
             <AccordionTrigger className="flex items-center gap-2 text-lg font-semibold justify-start text-left">
               <Info className="h-5 w-5" />
               Information
               <span className="ml-2 text-muted-foreground text-sm font-normal">The overall description of the simulation. This is the foundation and sense of direction.</span>
             </AccordionTrigger>
             <AccordionContent className="overflow-visible" style={{ overflow: 'visible' }}>
               <div className="space-y-5 pt-4 w-full mx-auto overflow-visible">
                 <div className="overflow-visible focus-within:overflow-visible">
                   <Label htmlFor="name">Name</Label>
                   <Input id="name" value={name} onChange={e => {
                  setName(e.target.value);
                  markAsUnsaved();
                }} className="mt-1 w-full box-border p-2" />
                 </div>
                 <div className="overflow-visible focus-within:overflow-visible rounded-none">
                   <Label htmlFor="description">Description/Background</Label>
                   <Textarea
                     id="description"
                     value={description}
                     onChange={e => {
                       setDescription(e.target.value);
                       markAsUnsaved();
                     }}
                     className="mt-1 w-full overflow-visible rounded-none z-10 p-2 min-h-[200px] resize-y whitespace-pre-wrap"
                     style={{ minHeight: '200px', maxHeight: '400px' }}
                   />
                 </div>
                 <div className="overflow-visible focus-within:overflow-visible">
                   <Label htmlFor="studentRole">Student Role</Label>
                   <Input 
                     id="studentRole" 
                     value={studentRole} 
                     onChange={e => {
                       setStudentRole(e.target.value);
                       markAsUnsaved();
                     }} 
                     placeholder="e.g., John Smith (CEO of Company Name), Business Analyst, Strategic Advisor"
                     className="mt-1 w-full box-border p-2" 
                   />
                   <p className="text-sm text-muted-foreground mt-1">
                     The role the student will assume in this simulation. This could be a specific character from the case study or a business position.
                   </p>
                 </div>
                 <div className="overflow-visible focus-within:overflow-visible">
                   <Label htmlFor="learning-outcomes">Learning Outcomes</Label>
                   <Textarea
                     id="learning-outcomes"
                     value={learningOutcomes}
                     onChange={e => {
                       setLearningOutcomes(e.target.value);
                       markAsUnsaved();
                     }}
                     className="mt-1 w-full box-border p-2 min-h-[200px] resize-y whitespace-pre-wrap"
                     style={{ minHeight: '200px', maxHeight: '400px' }}
                   />
                 </div>
                           <div>
                   <Label className="block mb-1">Files</Label>
                   <span className="block text-muted-foreground text-xs mb-2">Use this to give more context to the simulation</span>
                   <Button variant="outline" onClick={handleUploadFilesClick}>Upload Files</Button>
                   <input
                     type="file"
                     multiple
                     className="hidden"
                     ref={filesInputRef}
                     onChange={handleFilesChange}
                   />
                   {uploadedFiles.length > 0 && (
                     <ul className="mt-2 text-xs text-muted-foreground">
                       {uploadedFiles.map((file, idx) => (
                         <li key={idx} className="flex items-center gap-2">
                           {file.name}
                           <button
                             type="button"
                             className="ml-1 text-red-500 hover:text-red-700"
                             onClick={() => handleRemoveFile(idx)}
                             aria-label={`Remove ${file.name}`}
                           >
                             <X className="w-3 h-3" />
                           </button>
                         </li>
                       ))}
                     </ul>
                   )}
                 </div>
               </div>
             </AccordionContent>
           </AccordionItem>


           {/* Personas Accordion */}
           <AccordionItem value="personas">
             <AccordionTrigger className="flex items-center gap-2 text-lg font-semibold justify-start text-left">
               <Users className="h-5 w-5" />
               Personas
               <span className="ml-2 text-muted-foreground text-sm font-normal">The characters the user will interact during the simulation with their own personality and goals.</span>
             </AccordionTrigger>
             <AccordionContent>
               <div className="flex flex-col items-center py-6">
                 <Button onClick={handleAddPersona} variant="outline" className="w-60">Add new persona</Button>
                 {/* Render persona cards here, excluding the player character */}
                 {(tempPersonas.length > 0 || personas.length > 0) && (
                   <div className="w-full flex flex-col items-center mt-6">
                     {/* Render temporary personas first (at the top) */}
                     {tempPersonas.map((persona: any, idx: number) => (
                       <div key={`temp-${idx}`} className="relative w-full">
                         <div onClick={() => setEditingIdx(idx)} style={{ cursor: 'pointer' }}>
                           <PersonaCard
                             persona={{ ...persona, traits: persona.traits }}
                             defaultTraits={persona.defaultTraits}
                             onTraitsChange={newTraits => handleTraitsChange(idx, newTraits)}
                             onSave={updatedPersona => handleSavePersona(idx, updatedPersona)}
                             onDelete={() => handleDeletePersona(idx)}
                             editMode={false}
                           />
                         </div>
                       </div>
                     ))}
                     {/* Render permanent personas */}
                     {personas.map((persona: any, idx: number) => (
                       <div key={`perm-${idx}`} className="relative w-full">
                         <div onClick={() => setEditingIdx(idx)} style={{ cursor: 'pointer' }}>
                           <PersonaCard
                             persona={{ ...persona, traits: persona.traits }}
                             defaultTraits={persona.defaultTraits}
                             onTraitsChange={newTraits => handleTraitsChange(idx, newTraits)}
                             onSave={updatedPersona => handleSavePersona(idx, updatedPersona)}
                             onDelete={() => handleDeletePersona(idx)}
                             editMode={false}
                           />
                         </div>
                       </div>
                     ))}
                   </div>
                 )}
               </div>
             </AccordionContent>
           </AccordionItem>


           {/* Timeline Accordion */}
           <AccordionItem value="timeline">
             <AccordionTrigger className="flex items-center gap-2 text-lg font-semibold justify-start text-left">
               <Activity className="h-5 w-5" />
               Timeline
               <span className="ml-2 text-muted-foreground text-sm font-normal">These are the sequence of events the user needs to solve for during the simulation.</span>
             </AccordionTrigger>
             <AccordionContent>
               <div className="py-4">
                 <p className="text-muted-foreground text-sm mb-6">Think of each segment as a self-contained mini-level in your simulation. Arrange them from top to bottom, this will be the sequence each scene will take place in.</p>
                 <div className="flex flex-col items-center">
                   <Button onClick={handleAddScene} variant="outline" className="w-60">Add new Scene</Button>
                   
                   {/* Render scene cards */}
                   {scenes.length > 0 && (
                     <div className="w-full flex flex-col items-center mt-6">
                       {(() => {
                         // Create a sorted array with original indices preserved
                         const sortedScenesWithIndices = scenes
                           .map((scene, originalIdx) => ({ scene, originalIdx }))
                           .sort((a, b) => a.scene.sequence_order - b.scene.sequence_order);
                         
                         return sortedScenesWithIndices.map(({ scene, originalIdx }, sortedIdx) => {
                           // Use a combination of id and index as key to ensure uniqueness
                           const uniqueKey = scene.id ? `scene-${scene.id}` : `scene-temp-${sortedIdx}`;
                          return (
                            <div key={uniqueKey} className="relative w-full">
                              <div onClick={() => setEditingSceneIdx(originalIdx)} style={{ cursor: 'pointer' }}>
                                <SceneCard
                                   scene={scene}
                                   onSave={updatedScene => handleSaveScene(originalIdx, updatedScene)}
                                   onDelete={() => handleDeleteScene(originalIdx)}
                                   editMode={false}
                                   allPersonas={personas}
                                   studentRole={autofillResult?.student_role || ""}
                                 />
                               </div>
                             </div>
                           );
                         });
                       })()}
                     </div>
                   )}
                 </div>
               </div>
             </AccordionContent>
           </AccordionItem>
         </Accordion>
       </div>
     </div>
     {/* Modal for editing persona */}
     {editingIdx !== null && (
       <PersonaModal isOpen={true} onClose={() => setEditingIdx(null)}>
         <PersonaCard
           persona={{ 
             ...(editingIdx < tempPersonas.length ? tempPersonas[editingIdx] : personas[editingIdx - tempPersonas.length]), 
             traits: (editingIdx < tempPersonas.length ? tempPersonas[editingIdx] : personas[editingIdx - tempPersonas.length]).traits 
           }}
           defaultTraits={(editingIdx < tempPersonas.length ? tempPersonas[editingIdx] : personas[editingIdx - tempPersonas.length]).defaultTraits}
           onTraitsChange={newTraits => handleTraitsChange(editingIdx, newTraits)}
           onSave={updatedPersona => handleSavePersona(editingIdx, updatedPersona)}
           onDelete={() => handleDeletePersona(editingIdx)}
           editMode={true}
         />
       </PersonaModal>
     )}
     
     {/* Modal for editing scene */}
    {editingSceneIdx !== null && (
       <SceneModal isOpen={true} onClose={() => setEditingSceneIdx(null)}>
         <SceneCard
           scene={scenes[editingSceneIdx]}
           onSave={updatedScene => handleSaveScene(editingSceneIdx, updatedScene)}
           onDelete={() => handleDeleteScene(editingSceneIdx)}
           editMode={true}
           allPersonas={[...personas, ...tempPersonas]}
           studentRole={autofillResult?.student_role || ""}
         />
       </SceneModal>
     )}
       </div>
     </div>
   </div>
 )
}


