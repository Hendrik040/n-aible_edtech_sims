"use client"

import React, { useState, useRef, useEffect, useCallback } from "react"
import { createPortal } from "react-dom"
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
import { Upload, Info, Users, Activity, Sparkles, X, Check, Target, Settings, ArrowLeft, ChevronDown, Plus, RefreshCw, Trash2 } from "lucide-react"
import Link from "next/link"
import PersonaCard from "@/components/PersonaCard";
import SceneCard from "@/components/SceneCard";
import RoleBasedSidebar from "@/components/RoleBasedSidebar";
import SimulationBuilderProgress from "@/components/SimulationBuilderProgress"
import PDFProgressTrackerHTTP from "@/components/PDFProgressTrackerHTTP"
import { usePDFParsingWithProgress } from "@/hooks/usePDFParsingWithProgress"
import { apiClient, buildApiUrl } from "@/lib/api"

// Type definition for rubric configuration
interface RubricConfig {
  title: string;
  performanceLevels: Array<{ name: string; points: number }>;
  criteria: Array<{
    description: string;
    descriptions: Record<string, string>;
  }>;
}

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

 const modalContent = (
   <div 
     className="fixed inset-0 z-[9999] flex items-center justify-center bg-gray-900 bg-opacity-60"
     style={{ 
       position: 'fixed',
       left: 0, 
       right: 0, 
       top: 0, 
       bottom: 0,
       zIndex: 9999
     }}
   >
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

 // Use portal to render modal at document body level
 if (typeof window !== 'undefined') {
   return createPortal(modalContent, document.body);
 }
 
 return null;
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

 const modalContent = (
   <div 
     className="fixed inset-0 z-[9999] flex items-center justify-center bg-black bg-opacity-50 p-4"
     style={{ 
       position: 'fixed',
       left: 0, 
       right: 0, 
       top: 0, 
       bottom: 0,
       zIndex: 9999
     }}
   >
     <div className="bg-white rounded-xl shadow-2xl w-full max-w-6xl h-[95vh] flex flex-col relative overflow-hidden">
       <button
         className="absolute top-1 right-1 text-gray-400 text-2xl font-bold hover:text-gray-600 z-10 w-10 h-10 flex items-center justify-center"
         onClick={onClose}
         aria-label="Close edit window"
       >
         &times;
       </button>
       <div className="flex-1 overflow-y-auto flex flex-col">
         {children}
       </div>
     </div>
   </div>
 );

 // Use portal to render modal at document body level
 if (typeof window !== 'undefined') {
   return createPortal(modalContent, document.body);
 }
 
 return null;
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

 const modalContent = (
   <div 
     className="fixed inset-0 z-[9999] flex items-center justify-center bg-gray-900 bg-opacity-60"
     style={{ 
       position: 'fixed',
       left: 0, 
       right: 0, 
       top: 0, 
       bottom: 0,
       zIndex: 9999
     }}
   >
     <div className="bg-white rounded-lg shadow-lg w-[1000px] h-[95vh] flex flex-col relative p-0 resize-none overflow-hidden">
       <button
         className="absolute top-4 right-4 text-gray-400 text-2xl font-bold hover:text-gray-600 z-10"
         onClick={onClose}
         aria-label="Close edit window"
       >
         &times;
       </button>
       <div className="flex-1 overflow-y-auto flex flex-col">
         {children}
       </div>
     </div>
   </div>
 );

 // Use portal to render modal at document body level
 if (typeof window !== 'undefined') {
   return createPortal(modalContent, document.body);
 }
 
 return null;
}


export default function SimulationBuilder() {
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
const [existingGradingMaterials, setExistingGradingMaterials] = useState<any[]>([]); // Already uploaded materials
const [uploadingFiles, setUploadingFiles] = useState<Set<string>>(new Set()); // Track files currently being uploaded
const [processingMaterials, setProcessingMaterials] = useState<Set<number>>(new Set()); // Track materials being processed
 const filesInputRef = useRef<HTMLInputElement>(null);
 const hasLoadedDraft = useRef(false); // Track if draft has been loaded
 const isRestoringFromStorage = useRef(false); // Track if we're restoring from localStorage
 const [personas, setPersonas] = useState<any[]>([]);

// Debug logging for personas state changes
useEffect(() => {
  console.log("[DEBUG] Personas state changed:", personas.length, "personas");
  console.log("[DEBUG] Personas names:", personas.map(p => p.name));
}, [personas]);
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
  const [isPlayingSimulation, setIsPlayingSimulation] = useState(false);
  const [savedSimulationId, setSavedSimulationId] = useState<number | null>(null);
  const [completionStatus, setCompletionStatus] = useState<{ [key: string]: boolean } | null>(null);
  const [aiEnhancementComplete, setAiEnhancementComplete] = useState(false);
  const [isSimulationDraft, setIsSimulationDraft] = useState(true); // Track if simulation is draft or published
  
  // Database boolean fields for completion tracking
  const [dbCompletionFields, setDbCompletionFields] = useState({
    nameCompleted: false,
    descriptionCompleted: false,
    studentRoleCompleted: false,
    personasCompleted: false,
    scenesCompleted: false,
    imagesCompleted: false,
    learningOutcomesCompleted: false,
    aiEnhancementCompleted: false,
  });

  // Rubric Configuration state
  const [gradingPrompt, setGradingPrompt] = useState("");
  const [rubricConfig, setRubricConfig] = useState<RubricConfig>({
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
          "Outstanding": "Presents an extremely thorough and insightful analysis of all major issues in the case. Conclusions are well justified by factual and computational support.",
          "Excellent": "Presents a strong analysis of most of the major issues in the case but has some limitations and lacks full depth in some areas. Some conclusions may lack support.",
          "Good": "Presents a good analysis of most of the major issues in the case but lacks depth in some areas. Some conclusions may lack support.",
          "Fair": "Presents an adequate yet limited analysis of most of the major issues in the case but lacks depth in several areas. Conclusions may lack support.",
          "Poor": "The level of analysis lacks adequate depth and/or factual and computational support for analysis is omitted."
        }
      },
      {
        description: "Quality and feasibility of recommendations",
        descriptions: {
          "Outstanding": "Recommendations are detailed and insightful and together compose a thorough plan to address major challenges.",
          "Excellent": "Recommendations are excellent to address major issues and are linked to the analysis. Almost all anticipated consequences and alternatives are included.",
          "Good": "Recommendations are strong to address major issues and are somewhat but not fully linked to the analysis. Some anticipated consequences and alternatives are included.",
          "Fair": "Recommendations are appropriate to address major issues and are linked to the analysis. Some anticipated consequences and alternatives are included.",
          "Poor": "Recommendations are mostly appropriate to address issues and are at least partially linked to the analysis. Anticipated consequences and alternatives are lacking."
        }
      }
    ]
  });

  // Load grading materials when simulation is saved
  useEffect(() => {
    if (savedSimulationId) {
      loadGradingMaterials(savedSimulationId);
    }
  }, [savedSimulationId]);

  // Load grading materials when component mounts if we have a saved simulation
  useEffect(() => {
    if (savedSimulationId) {
      loadGradingMaterials(savedSimulationId);
    }
  }, []); // Empty dependency array means this runs once on mount

  // Check processing status periodically
  useEffect(() => {
    if (savedSimulationId && processingMaterials.size > 0) {
      const interval = setInterval(() => {
        checkProcessingStatus(savedSimulationId);
      }, 3000); // Check every 3 seconds

      return () => clearInterval(interval);
    }
  }, [savedSimulationId, processingMaterials.size]);

  // Tab state
  const [activeTab, setActiveTab] = useState<'configuration' | 'grading'>('configuration');

 // Authentication logic - must be after all hooks
 useEffect(() => {
   if (!authLoading && !user) {
     router.push("/")
   }
 }, [user, authLoading, router])

// Load draft data if editing
useEffect(() => {
  const loadDraftData = async () => {
    // Prevent loading draft multiple times
    if (hasLoadedDraft.current) {
      return;
    }
    
    try {
      // Check if we're editing a draft by looking at URL parameters
      const urlParams = new URLSearchParams(window.location.search)
      const editId = urlParams.get('edit')
      
     if (editId) {
       debugLog("Loading draft data for editing ID:", editId)
       hasLoadedDraft.current = true; // Mark as loaded
        
        // Fetch draft data directly from the database
        const draftData = await apiClient.getDraftScenario(parseInt(editId))
        debugLog("Fetched draft data:", draftData)
         
         if (draftData && draftData.id) {
           // Load the draft data into the form
           setName(draftData.title || "")
           setDescription(draftData.description || "")
           setStudentRole(draftData.student_role || "")
           
           // Load completion status if available
           if (draftData.completion_status) {
             setCompletionStatus(draftData.completion_status)
             debugLog("Loaded completion status:", draftData.completion_status)
           }
           
           // Load database boolean completion fields
          const completionFields = {
            nameCompleted: draftData.name_completed || false,
            descriptionCompleted: draftData.description_completed || false,
            studentRoleCompleted: draftData.student_role_completed || false,
            personasCompleted: draftData.personas_completed || false,
            scenesCompleted: draftData.scenes_completed || false,
            imagesCompleted: draftData.images_completed || false,
            learningOutcomesCompleted: draftData.learning_outcomes_completed || false,
            aiEnhancementCompleted: draftData.ai_enhancement_completed || false
          };
          
          setDbCompletionFields(completionFields);
          
          // Load grading prompt if available
          if (draftData.grading_prompt !== undefined) {
            setGradingPrompt(draftData.grading_prompt || "");
            debugLog("Loaded grading prompt:", draftData.grading_prompt);
          }
          
          // Load rubric configuration if available
          if (draftData.rubric_title !== undefined || draftData.rubric_criteria !== undefined || draftData.rubric_performance_levels !== undefined) {
            setRubricConfig(prev => ({
              ...prev,
              title: draftData.rubric_title || prev.title,
              performanceLevels: draftData.rubric_performance_levels || prev.performanceLevels,
              criteria: draftData.rubric_criteria || prev.criteria
            }));
            debugLog("Loaded rubric configuration:", {
              title: draftData.rubric_title,
              performanceLevels: draftData.rubric_performance_levels,
              criteria: draftData.rubric_criteria
            });
          }
           
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
             const transformedScenes = draftData.scenes.map((scene: any) => {
               const transformed = {
                 ...scene,
                 // CRITICAL: Preserve the numeric ID from database
                 id: scene.id,
                 sequence_order: scene.scene_order, // Map scene_order to sequence_order for compatibility
                 successMetric: scene.success_metric, // Map success_metric to successMetric for compatibility
                 // Ensure personas_involved is an array of names
                 personas_involved: scene.personas_involved || []
               };
               debugLog(`[LOAD] Loaded scene: ${transformed.title} with ID: ${transformed.id} (type: ${typeof transformed.id})`);
               return transformed;
             })
             console.log("DEBUG: Transformed scenes:", transformedScenes);
             const sceneIds = transformedScenes.map((s: any) => ({ id: s.id, title: s.title }));
             debugLog(`[LOAD] Loaded ${transformedScenes.length} scenes with IDs:`, sceneIds);
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
             
             // Combine scene personas and global personas, removing duplicates
             const allPersonas = [...allScenePersonas];
             
             // Add global personas that are not already in scene personas
             if (draftData.personas && draftData.personas.length > 0) {
               const scenePersonaNames = new Set(allScenePersonas.map(p => p.name));
               const globalPersonas = draftData.personas.filter((persona: any) => !scenePersonaNames.has(persona.name));
               allPersonas.push(...globalPersonas);
             }
             
             if (allPersonas.length > 0) {
               debugLog("Using combined personas (scene + global):", JSON.stringify(allPersonas, null, 2))
               debugLog(`Found ${allScenePersonas.length} scene personas and ${draftData.personas?.length || 0} global personas, total: ${allPersonas.length}`)
               
               // Debug: Check what fields are available in the persona objects
               if (allPersonas.length > 0) {
                 debugLog("First persona fields:", Object.keys(allPersonas[0]))
                 debugLog("First persona system_prompt:", allPersonas[0].system_prompt)
                 debugLog("First persona image_url:", allPersonas[0].image_url)
               }
               
               // Transform personas to match PersonaCard expected structure
               const transformedPersonas = allPersonas.map((persona: any) => ({
                 name: persona.name,
                 position: persona.role,
                 description: persona.background,
                 primaryGoals: Array.isArray(persona.primary_goals) ? persona.primary_goals.join(", ") : persona.primary_goals || "",
                 traits: persona.personality_traits || {},
                 imageUrl: persona.image_url,
                 systemPrompt: persona.system_prompt
               }))
               debugLog("Transformed combined personas:", JSON.stringify(transformedPersonas, null, 2))
               setPersonas(transformedPersonas)
               debugLog("setPersonas called with", transformedPersonas.length, "personas")
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
                 imageUrl: persona.image_url,
                 systemPrompt: persona.system_prompt
               }))
               setPersonas(transformedPersonas)
             }
           }
           
           // Set the saved simulation ID for updating
           setSavedSimulationId(draftData.id)
           setIsSaved(true) // Mark as already saved
           
           // Load draft status to determine if simulation can be played
           setIsSimulationDraft(draftData.is_draft === true)
           
           debugLog("Draft data loaded successfully")
         } else {
           throw new Error("Invalid draft data received")
         }
       } else if (!editId) {
         debugLog("No draft ID found - checking localStorage for unsaved work")
         // Check localStorage for unsaved work (not saved drafts)
         // Only restore if it's unsaved work (no savedSimulationId), not saved draft data
         try {
           const saved = localStorage.getItem(STORAGE_KEY);
           if (saved) {
             const formData = JSON.parse(saved);
             // Only restore if this is unsaved work (no savedSimulationId), not a saved draft
             // This prevents saved draft data from appearing when creating new simulations
             if (formData && !formData.savedSimulationId) {
               debugLog("Found unsaved work in localStorage, restoring...");
               // Restore unsaved work
               if (formData.name) setName(formData.name);
               if (formData.description) setDescription(formData.description);
               if (formData.studentRole) setStudentRole(formData.studentRole);
               if (formData.learningOutcomes) setLearningOutcomes(formData.learningOutcomes);
               if (formData.personas && Array.isArray(formData.personas) && formData.personas.length > 0) {
                 setPersonas(formData.personas);
               }
               if (formData.scenes && Array.isArray(formData.scenes) && formData.scenes.length > 0) {
                 setScenes(formData.scenes);
               }
               if (formData.gradingPrompt !== undefined) setGradingPrompt(formData.gradingPrompt);
               if (formData.rubricConfig) setRubricConfig(formData.rubricConfig);
               if (formData.autofillResult) setAutofillResult(formData.autofillResult);
               if (formData.isSaved !== undefined) setIsSaved(formData.isSaved);
               debugLog("Restored unsaved work from localStorage");
             } else if (formData && formData.savedSimulationId) {
               // This is saved draft data, clear it to prevent leakage
               debugLog("Found saved draft data in localStorage, clearing to prevent data leakage");
               localStorage.removeItem(STORAGE_KEY);
               // Start with clean form
               setName("")
               setDescription("")
               setStudentRole("")
               setLearningOutcomes("")
               setPersonas([])
               setScenes([])
               setSavedSimulationId(null)
               setIsSaved(false)
               setAutofillResult(null)
               setGradingPrompt("")
               setRubricConfig({
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
                       "Outstanding": "Presents an extremely thorough and insightful analysis of all major issues in the case. Conclusions are well justified by factual and computational support.",
                       "Excellent": "Presents a strong analysis of most of the major issues in the case but has some limitations and lacks full depth in some areas. Some conclusions may lack support.",
                       "Good": "Presents a good analysis of most of the major issues in the case but lacks depth in some areas. Some conclusions may lack support.",
                       "Fair": "Presents an adequate yet limited analysis of most of the major issues in the case but lacks depth in several areas. Conclusions may lack support.",
                       "Poor": "The level of analysis lacks adequate depth and/or factual and computational support for analysis is omitted."
                     }
                   },
                   {
                     description: "Quality and feasibility of recommendations",
                     descriptions: {
                       "Outstanding": "Recommendations are detailed and insightful and together compose a thorough plan to address major challenges.",
                       "Excellent": "Recommendations are excellent to address major issues and are linked to the analysis. Almost all anticipated consequences and alternatives are included.",
                       "Good": "Recommendations are strong to address major issues and are somewhat but not fully linked to the analysis. Some anticipated consequences and alternatives are included.",
                       "Fair": "Recommendations are appropriate to address major issues and are linked to the analysis. Some anticipated consequences and alternatives are included.",
                       "Poor": "Recommendations are mostly appropriate to address issues and are at least partially linked to the analysis. Anticipated consequences and alternatives are lacking."
                     }
                   }
                 ]
               })
             } else {
               // No data or invalid data, start fresh
               setName("")
               setDescription("")
               setStudentRole("")
               setLearningOutcomes("")
               setPersonas([])
               setScenes([])
               setSavedSimulationId(null)
               setIsSaved(false)
             }
           } else {
             // No localStorage data, start with clean form
             setName("")
             setDescription("")
             setStudentRole("")
             setLearningOutcomes("")
             setPersonas([])
             setScenes([])
             setSavedSimulationId(null)
             setIsSaved(false)
           }
         } catch (error) {
           console.error("Failed to check/restore localStorage:", error);
           // On error, start with clean form
           setName("")
           setDescription("")
           setStudentRole("")
           setLearningOutcomes("")
           setPersonas([])
           setScenes([])
           setSavedSimulationId(null)
           setIsSaved(false)
         }
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

// Utility to normalize scenes (moved here for use in autoSaveToDatabase)
const normalizeScenesForAutoSave = (scenes: any[]) => {
  return scenes.map(scene => {
    const normalized = {
      ...scene,
      image_url: scene.image_url,
      timeout_turns:
        scene.timeout_turns !== undefined && scene.timeout_turns !== null
          ? scene.timeout_turns
          : 15,
    };
    // Ensure scene ID is preserved if it exists (critical for matching existing scenes)
    if (scene.id !== undefined) {
      normalized.id = scene.id;
    }
    // Map sequence_order to scene_order for backend compatibility
    if (scene.sequence_order !== undefined) {
      normalized.sequence_order = scene.sequence_order;
    }
    return normalized;
  });
};

// Auto-save function for database (draft mode only)
const autoSaveToDatabase = useCallback(async () => {
  // Only auto-save to database if:
  // - We have a saved simulation ID (draft mode)
  // - Not currently saving manually
  // - Not restoring from storage
  // - Not publishing
  // - Not parsing PDF (to avoid incomplete saves and race conditions)
  if (!savedSimulationId || isSaving || isRestoringFromStorage.current || isPublishing || isParsingWithProgress) {
    return;
  }
  
  // Check if we have any data to save
  const hasData = name || description || studentRole || learningOutcomes || 
                  (personas && personas.length > 0) || 
                  (scenes && scenes.length > 0);
  
  if (!hasData && !autofillResult) {
    return;
  }
  
  try {
    // Normalize scenes and ensure IDs are preserved
    const normalizedScenes = normalizeScenesForAutoSave(scenes);
    debugLog(`[AUTO-SAVE] Sending ${normalizedScenes.length} scenes with IDs:`, normalizedScenes.map(s => ({ id: s.id, title: s.title })));
    
    // Build payload (same as handleSave but without alerts)
    const payload = {
      title: name || (autofillResult?.title || ""),
      description: description || (autofillResult?.description || ""),
      learning_outcomes: learningOutcomes || (autofillResult?.learning_outcomes || ""),
      student_role: studentRole || (autofillResult?.student_role || ""),
      key_figures: autofillResult?.key_figures || [],
      scenes: normalizedScenes,
      personas: personas.map(persona => {
        const mappedPersona = {
          ...persona,
          role: persona.position,
          background: persona.description,
          primary_goals: persona.primaryGoals,
          personality_traits: persona.traits,
        };
        if (persona.systemPrompt && persona.systemPrompt.trim()) {
          mappedPersona.systemPrompt = persona.systemPrompt;
        }
        if (persona.imageUrl) {
          mappedPersona.imageUrl = persona.imageUrl;
        }
        return mappedPersona;
      }),
      rubric_title: rubricConfig.title,
      rubric_criteria: rubricConfig.criteria,
      rubric_performance_levels: rubricConfig.performanceLevels,
      grading_prompt: gradingPrompt,
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
    
    const endpoint = `/api/publishing/simulations/save?simulation_id=${savedSimulationId}`;
    const response = await apiClient.apiRequest(endpoint, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    
    if (response.ok) {
      const result = await response.json();
      // Update savedSimulationId if it changed
      const newId = result.simulation_id || result.scenario_id; // Support both field names
      if (newId && newId !== savedSimulationId) {
        setSavedSimulationId(newId);
      }
      debugLog("Auto-saved draft to database");
      // Silently update isSaved status without showing notification
      setIsSaved(true);
    } else {
      // Silently fail - don't show alerts for auto-save failures
      debugLog("Auto-save to database failed (silent):", response.status);
    }
  } catch (error) {
    // Silently fail - don't show alerts for auto-save failures
    debugLog("Auto-save to database error (silent):", error);
  }
}, [savedSimulationId, isSaving, isPublishing, name, description, studentRole, learningOutcomes, personas, scenes, gradingPrompt, rubricConfig, autofillResult, aiEnhancementComplete, isParsingWithProgress, parsingError]);

// Auto-save to localStorage and database whenever form data changes
useEffect(() => {
  // Don't auto-save if:
  // - User is not authenticated
  // - Auth is still loading
  // - We're currently restoring from storage (to avoid saving during restore)
  // - PDF parsing is in progress (to avoid incomplete saves and race conditions)
  if (!user || authLoading || isRestoringFromStorage.current || isParsingWithProgress) {
    return;
  }
  
  // Debounce the save to avoid too frequent writes
  const timeoutId = setTimeout(() => {
    // Double-check the flag before saving
    if (!isRestoringFromStorage.current && !isParsingWithProgress) {
      // Always save to localStorage
      saveToLocalStorage();
      
      // Also auto-save to database if we're in draft mode (have savedSimulationId)
      // Only save if we have meaningful data (not just empty arrays)
      const hasData = (personas && personas.length > 0) || 
                     (scenes && scenes.length > 0) || 
                     name?.trim() || 
                     description?.trim() || 
                     studentRole?.trim();
      
      if (savedSimulationId && !isSaving && !isPublishing && hasData) {
        autoSaveToDatabase();
      }
    }
  }, 300); // Save 300ms after last change
  
  return () => clearTimeout(timeoutId);
}, [name, description, studentRole, learningOutcomes, personas, scenes, gradingPrompt, rubricConfig, autofillResult, savedSimulationId, isSaved, user, authLoading, isSaving, isPublishing, isParsingWithProgress, autoSaveToDatabase])

// Final save on unmount (when user navigates away)
useEffect(() => {
  return () => {
    // Save one final time when component unmounts if there's any form data
    const hasData = formDataRef.current.name || 
                   formDataRef.current.description || 
                   formDataRef.current.studentRole || 
                   formDataRef.current.learningOutcomes ||
                   (formDataRef.current.personas && formDataRef.current.personas.length > 0) ||
                   (formDataRef.current.scenes && formDataRef.current.scenes.length > 0);
    
    if (!isRestoringFromStorage.current && user && hasData) {
      try {
        const formData = {
          ...formDataRef.current,
          timestamp: Date.now()
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(formData));
        debugLog("Final save to localStorage on unmount");
      } catch (error) {
        console.error("Failed to save to localStorage on unmount:", error);
      }
    }
  };
}, [user])
 
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

// Load existing grading materials for a simulation
const loadGradingMaterials = async (simulationId: number): Promise<void> => {
  try {
    const response = await apiClient.apiRequest(
      `/professor/simulations/${simulationId}/grading-materials`,
      { method: 'GET' }
    );
    
    if (response.ok) {
      const result = await response.json();
      const materials = result.materials || [];
      debugLog(`Loaded ${materials.length} existing grading materials`);
      setExistingGradingMaterials(materials);
      
      // Update processing materials set
      const stillProcessing = new Set<number>();
      materials.forEach((material: any) => {
        if (material.processing_status === 'pending' || material.processing_status === 'processing') {
          stillProcessing.add(material.id);
        }
      });
      setProcessingMaterials(stillProcessing);
    }
  } catch (error) {
    debugLog("Error loading grading materials:", error);
  }
};

// Delete grading material
const deleteGradingMaterial = async (materialId: number): Promise<void> => {
  try {
    debugLog(`Deleting grading material ${materialId}`);
    
    const response = await apiClient.apiRequest(
      `/professor/grading-materials/${materialId}`,
      { method: 'DELETE' }
    );
    
    if (response.ok) {
      debugLog(`Successfully deleted grading material ${materialId}`);
      // Reload the materials list
      if (savedSimulationId) {
        await loadGradingMaterials(savedSimulationId);
      }
    } else {
      console.error(`Failed to delete material ${materialId}:`, await response.text());
    }
  } catch (error) {
    console.error(`Error deleting material ${materialId}:`, error);
  }
};

// Upload a single file immediately when selected
const uploadFileImmediately = async (file: File, simulationId: number): Promise<void> => {
  const fileKey = `${file.name}-${file.size}`;
  
  try {
    // Add to uploading set
    setUploadingFiles(prev => new Set(prev).add(fileKey));
    
    debugLog(`Uploading file immediately: ${file.name}`);
    
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await apiClient.apiRequest(
      `/professor/simulations/${simulationId}/grading-materials`,
      {
        method: 'POST',
        body: formData,
      }
    );
    
    if (response.ok) {
      const result = await response.json();
      debugLog(`Successfully uploaded grading material: ${file.name} (ID: ${result.material.id})`);
      
      // Add to processing set if not completed
      if (result.material.processing_status !== 'completed') {
        setProcessingMaterials(prev => new Set(prev).add(result.material.id));
      }
      
      // Reload materials to show the new one
      await loadGradingMaterials(simulationId);
    } else {
      console.error(`Failed to upload ${file.name}:`, await response.text());
    }
  } catch (error) {
    console.error(`Error uploading ${file.name}:`, error);
  } finally {
    // Remove from uploading set
    setUploadingFiles(prev => {
      const newSet = new Set(prev);
      newSet.delete(fileKey);
      return newSet;
    });
  }
};

// Check and update processing status of materials
const checkProcessingStatus = async (simulationId: number): Promise<void> => {
  try {
    const response = await apiClient.apiRequest(
      `/professor/simulations/${simulationId}/grading-materials`,
      { method: 'GET' }
    );
    
    if (response.ok) {
      const result = await response.json();
      const materials = result.materials || [];
      
      // Update processing materials set
      const stillProcessing = new Set<number>();
      materials.forEach((material: any) => {
        if (material.processing_status === 'pending' || material.processing_status === 'processing') {
          stillProcessing.add(material.id);
        }
      });
      
      setProcessingMaterials(stillProcessing);
      
      // Update existing materials
      setExistingGradingMaterials(materials);
    }
  } catch (error) {
    debugLog("Error checking processing status:", error);
  }
};

// Upload grading materials to backend
const uploadGradingMaterials = async (simulationId: number): Promise<void> => {
  if (uploadedFiles.length === 0) {
    debugLog("No grading materials to upload");
    return;
  }

  debugLog(`Uploading ${uploadedFiles.length} grading materials for simulation ${simulationId}`);
  
  for (const file of uploadedFiles) {
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const response = await apiClient.apiRequest(
        `/professor/simulations/${simulationId}/grading-materials`,
        {
          method: 'POST',
          body: formData,
        }
      );
      
      if (response.ok) {
        const result = await response.json();
        debugLog(`Successfully uploaded grading material: ${file.name} (ID: ${result.material.id})`);
      } else {
        console.error(`Failed to upload ${file.name}:`, await response.text());
      }
    } catch (error) {
      console.error(`Error uploading ${file.name}:`, error);
    }
  }
};

// Save and Publish handlers
const handleSave = async (): Promise<number | null> => {
   // Prevent duplicate save requests
   if (isSaving) {
     debugLog("Save already in progress, ignoring duplicate request")
     return null;
   }
   
   // Prevent saving during PDF parsing to avoid incomplete data
   if (isParsingWithProgress) {
     alert("Please wait for PDF processing to complete before saving. The simulation will be automatically saved once processing is finished.");
     return null;
   }
   
   // Allow saving if we have form data OR autofillResult
   if (!autofillResult && !name && !description && !learningOutcomes && personas.length === 0 && scenes.length === 0) {
     alert("No simulation data to save. Please upload and process a PDF first or create a simulation manually.");
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
    personas: personas.map(persona => {
      const mappedPersona = {
        ...persona,
        role: persona.position,        // Map position → role
        background: persona.description, // Map description → background
        primary_goals: persona.primaryGoals, // Map primaryGoals → primary_goals
        personality_traits: persona.traits,  // Map traits → personality_traits
      };
      
      // Only include systemPrompt if it has a value
      if (persona.systemPrompt && persona.systemPrompt.trim()) {
        mappedPersona.systemPrompt = persona.systemPrompt;
      }
      
      // Only include imageUrl if it has a value
      if (persona.imageUrl) {
        mappedPersona.imageUrl = persona.imageUrl;
      }
      
      return mappedPersona;
    }),
    // Add PDF metadata if available (needed for PDF storage)
    pdf_metadata: autofillResult?.data?.pdf_metadata || autofillResult?.pdf_metadata,
    // Add rubric configuration
    rubric_title: rubricConfig.title,
    rubric_criteria: rubricConfig.criteria,
    rubric_performance_levels: rubricConfig.performanceLevels,
    // Add grading prompt
    grading_prompt: gradingPrompt,
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
  
  // CRITICAL: Log scenes with their IDs to verify they're being sent
  const normalizedScenesForSave = normalizeScenes(scenes);
  debugLog(`[SAVE] Sending ${normalizedScenesForSave.length} scenes with IDs:`, normalizedScenesForSave.map(s => ({ 
    id: s.id, 
    title: s.title, 
    sequence_order: s.sequence_order,
    hasId: s.id !== undefined 
  })));
  
  // Debug log personas with system prompts
  debugLog("Personas being sent to backend:", personas.map(p => ({
    name: p.name,
    hasSystemPrompt: !!p.systemPrompt,
    systemPromptLength: p.systemPrompt?.length || 0,
    systemPromptPreview: p.systemPrompt?.substring(0, 100) + '...' || 'No system prompt',
    hasImageUrl: !!p.imageUrl,
    imageUrlPreview: p.imageUrl?.substring(0, 50) + '...' || 'No image URL'
  })));
  
  // Debug: Log persona names being sent
  debugLog("Persona names being sent to backend:", personas.map(p => p.name));
  
  // Debug: Log the actual persona objects being sent
  debugLog("Full persona objects being sent:", personas.map(p => ({
    name: p.name,
    systemPrompt: p.systemPrompt,
    imageUrl: p.imageUrl,
    allFields: Object.keys(p)
  })));
  
  // Debug: Check if any personas have systemPrompt or imageUrl
  debugLog(`Personas with systemPrompt: ${personas.filter(p => p.systemPrompt && p.systemPrompt.trim()).length}/${personas.length}`);
  debugLog(`Personas with imageUrl: ${personas.filter(p => p.imageUrl).length}/${personas.length}`);
  
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
     
     // Build endpoint with simulation_id if updating an existing simulation
    const endpoint = savedSimulationId 
      ? `/api/publishing/simulations/save?simulation_id=${savedSimulationId}`
      : "/api/publishing/simulations/save";
     
     debugLog("Save endpoint:", endpoint)
     debugLog("savedSimulationId:", savedSimulationId)
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
       const newScenarioId = result.simulation_id; // Support both field names for compatibility
       setSavedSimulationId(newScenarioId); // Store the simulation ID
       debugLog("Simulation saved:", result);
       
       // CRITICAL: Reload scenes from database to get real numeric IDs instead of temporary IDs
       // This ensures future saves can match scenes by ID correctly
       if (newScenarioId && scenes.length > 0) {
         try {
           debugLog("[SAVE] Reloading scenes from database to get real IDs...");
           const draftData = await apiClient.getDraftScenario(newScenarioId);
           if (draftData && draftData.scenes && draftData.scenes.length > 0) {
             const reloadedScenes = draftData.scenes.map((scene: any) => ({
               ...scene,
               sequence_order: scene.scene_order,
               successMetric: scene.success_metric,
               personas_involved: scene.personas_involved || []
             }));
             debugLog(`[SAVE] Reloaded ${reloadedScenes.length} scenes with real IDs:`, reloadedScenes.map((s: any) => ({ id: s.id, title: s.title })));
             setScenes(reloadedScenes);
           }
         } catch (reloadError) {
           debugLog("[SAVE] Failed to reload scenes after save (non-critical):", reloadError);
           // Don't fail the save if reload fails
         }
       }
       
       // Upload grading materials if any are pending
       if (uploadedFiles.length > 0) {
         debugLog("Uploading grading materials after scenario save...");
         await uploadGradingMaterials(newScenarioId);
         // Clear uploaded files after successful upload
         setUploadedFiles([]);
         // Reload existing grading materials to show the newly uploaded ones
         await loadGradingMaterials(newScenarioId);
       }
       
       // Reset save status after 3 seconds to show it's temporary
       setTimeout(() => {
         setIsSaved(false);
       }, 3000);
       
       return newScenarioId;
     } else {
       const errorText = await response.text();
       console.error("Failed to save simulation:", response.status, errorText);
       
       // Provide more user-friendly error messages
       let userMessage = "Failed to save scenario.";
       try {
         const errorData = JSON.parse(errorText);
         if (errorData.detail) {
           userMessage = errorData.detail;
         } else if (errorData.message) {
           userMessage = errorData.message;
         }
       } catch {
         // If error text is not JSON, use it as-is if it's short enough
         if (errorText && errorText.length < 200) {
           userMessage = errorText;
         }
       }
       
       // Check if it's a parsing-related error
       if (isParsingWithProgress || userMessage.toLowerCase().includes('parsing') || userMessage.toLowerCase().includes('processing')) {
         alert("Cannot save while PDF is being processed. Please wait for processing to complete.");
       } else {
         alert(`${userMessage} (Error ${response.status})`);
       }
       return null;
     }
   } catch (error) {
     console.error("Error saving simulation:", error);
     const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
     
     // Check if it's a parsing-related error
     if (isParsingWithProgress || errorMessage.toLowerCase().includes('parsing') || errorMessage.toLowerCase().includes('processing')) {
       alert("Cannot save while PDF is being processed. Please wait for processing to complete.");
     } else {
       alert(`Error saving scenario: ${errorMessage}`);
     }
     return null;
   } finally {
     setIsSaving(false);
   }
 };

 // Check if there's any data to clear
 const hasDataToClear = () => {
   return !!(
     name ||
     description ||
     studentRole ||
     learningOutcomes ||
     (personas && personas.length > 0) ||
     (scenes && scenes.length > 0) ||
     gradingPrompt ||
     autofillResult ||
     uploadedFile ||
     (uploadedFiles && uploadedFiles.length > 0) ||
     teachingNotesFile ||
     (tempPersonas && tempPersonas.length > 0)
   );
 };

 // Handle Clear - reset form and clear localStorage
 const handleClear = () => {
   // Check if there's anything to clear
   if (!hasDataToClear()) {
     return; // Nothing to clear, do nothing
   }
   
   // Confirm with user before clearing
   if (!confirm("Are you sure you want to clear all form data? This action cannot be undone.")) {
     return;
   }
   
   try {
     // Clear localStorage
     localStorage.removeItem(STORAGE_KEY);
     debugLog("Cleared localStorage");
     
     // Reset all form fields
     setName("")
     setDescription("")
     setStudentRole("")
     setLearningOutcomes("")
     setPersonas([])
     setScenes([])
     setSavedSimulationId(null)
     setIsSaved(false)
     setIsPublished(false)
     setAutofillResult(null)
     setGradingPrompt("")
     setRubricConfig({
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
             "Outstanding": "Presents an extremely thorough and insightful analysis of all major issues in the case. Conclusions are well justified by factual and computational support.",
             "Excellent": "Presents a strong analysis of most of the major issues in the case but has some limitations and lacks full depth in some areas. Some conclusions may lack support.",
             "Good": "Presents a good analysis of most of the major issues in the case but lacks depth in some areas. Some conclusions may lack support.",
             "Fair": "Presents an adequate yet limited analysis of most of the major issues in the case but lacks depth in several areas. Conclusions may lack support.",
             "Poor": "The level of analysis lacks adequate depth and/or factual and computational support for analysis is omitted."
           }
         },
         {
           description: "Quality and feasibility of recommendations",
           descriptions: {
             "Outstanding": "Recommendations are detailed and insightful and together compose a thorough plan to address major challenges.",
             "Excellent": "Recommendations are excellent to address major issues and are linked to the analysis. Almost all anticipated consequences and alternatives are included.",
             "Good": "Recommendations are strong to address major issues and are somewhat but not fully linked to the analysis. Some anticipated consequences and alternatives are included.",
             "Fair": "Recommendations are appropriate to address major issues and are linked to the analysis. Some anticipated consequences and alternatives are included.",
             "Poor": "Recommendations are mostly appropriate to address issues and are at least partially linked to the analysis. Anticipated consequences and alternatives are lacking."
           }
         }
       ]
     })
     setUploadedFile(null)
     setUploadedFiles([])
     setTeachingNotesFile(null)
     setTempPersonas([])
     setEditingIdx(null)
     setEditingSceneIdx(null)
     
     debugLog("Form cleared successfully");
   } catch (error) {
     console.error("Failed to clear form:", error);
     alert("Failed to clear form. Please try again.");
   }
 };

const handlePublish = async () => {
  // Prevent publishing during PDF parsing
  if (isParsingWithProgress) {
    alert("Please wait for PDF processing to complete before publishing.");
    return;
  }
  
  // Check if we have simulation data (either from autofill or from draft editing)
  if (!autofillResult && !name && !description && !learningOutcomes && personas.length === 0 && scenes.length === 0) {
    alert("No simulation data to publish. Please create a simulation first.");
    return;
  }

  console.log("[PUBLISH] 🚀 Starting publish flow");
  console.log("[PUBLISH] Current state - isSaved:", isSaved, "savedSimulationId:", savedSimulationId);
  
  setIsPublishing(true);
  try {
    // Always save first to ensure all latest changes are persisted
    console.log("[PUBLISH] 💾 Saving simulation first...");
    const simulationId = await handleSave();
    console.log("[PUBLISH] 💾 Save completed, simulationId:", simulationId);
    
    if (!simulationId) {
      console.error("[PUBLISH] ❌ Failed to save simulation");
      alert("Failed to save simulation. Cannot publish.");
      return;
    }
    
    // Actually publish the simulation
    const publishData = {
      category: autofillResult?.industry || "Business",
      difficulty_level: "Intermediate",
      tags: ["case-study", "management", "teamwork"],
      estimated_duration: 60
    };
    
    console.log("[PUBLISH] 📤 Sending publish request for simulation:", simulationId);
     console.log("[PUBLISH] Publish data:", publishData);
     
     const response = await apiClient.apiRequest(`/api/publishing/simulations/publish/${simulationId}`, {
       method: "POST",
       body: JSON.stringify(publishData),
     });

     console.log("[PUBLISH] 📥 Publish response status:", response.status, response.ok);

     if (response.ok) {
       const result = await response.json();
       console.log("[PUBLISH] ✅ Successfully published:", result);
       setIsPublished(true);
       setIsSimulationDraft(false); // Mark simulation as published
       debugLog("Simulation published:", result);
       
       // Reset publish status after 3 seconds
       setTimeout(() => {
         setIsPublished(false);
       }, 3000);
     } else {
       const errorText = await response.text();
       console.error("[PUBLISH] ❌ Failed to publish scenario. Status:", response.status);
       console.error("[PUBLISH] ❌ Error response:", errorText);
       alert(`Failed to publish scenario. Status: ${response.status}. Check console for details.`);
     }
   } catch (error) {
     console.error("[PUBLISH] ❌ Exception during publish:", error);
     console.error("[PUBLISH] Error stack:", error instanceof Error ? error.stack : "No stack trace");
     alert(`Error publishing simulation: ${error instanceof Error ? error.message : String(error)}`);
   } finally {
     setIsPublishing(false);
     console.log("[PUBLISH] 🏁 Publish flow completed");
   }
 };

 // Reset save status when content changes
 const markAsUnsaved = () => {
   setIsSaved(false);
   setIsPublished(false);
 };

 // Auto-save to localStorage
 const STORAGE_KEY = 'simulationBuilderDraft';
 
 // Use refs to store latest values for save function
 const formDataRef = useRef({
   name,
   description,
   studentRole,
   learningOutcomes,
   personas,
   scenes,
   gradingPrompt,
   rubricConfig,
   autofillResult,
   savedSimulationId,
   isSaved
 });
 
 // Update ref whenever state changes
 useEffect(() => {
   formDataRef.current = {
     name,
     description,
     studentRole,
     learningOutcomes,
     personas,
     scenes,
     gradingPrompt,
     rubricConfig,
     autofillResult,
     savedSimulationId,
     isSaved
   };
 }, [name, description, studentRole, learningOutcomes, personas, scenes, gradingPrompt, rubricConfig, autofillResult, savedSimulationId, isSaved]);
 
 const saveToLocalStorage = () => {
   try {
     const formData = {
       ...formDataRef.current,
       timestamp: Date.now()
     };
     localStorage.setItem(STORAGE_KEY, JSON.stringify(formData));
     debugLog("Auto-saved to localStorage");
   } catch (error) {
     console.error("Failed to save to localStorage:", error);
   }
 };

 // Restore from localStorage (only used for very recent unsaved work, not for new simulations)
 // This function is kept for potential future use but is not called during normal flow
 // to prevent data leakage between new simulations and previous drafts
 const restoreFromLocalStorage = () => {
   try {
     isRestoringFromStorage.current = true; // Set flag to prevent auto-save during restoration
     const saved = localStorage.getItem(STORAGE_KEY);
     if (saved) {
       const formData = JSON.parse(saved);
       debugLog("Restoring from localStorage:", formData);
       
       // Only restore if we're not editing an existing draft (no editId in URL)
       const urlParams = new URLSearchParams(window.location.search);
       const editId = urlParams.get('edit');
       
       // Only restore if data is very recent (within 10 minutes) to prevent data leakage
       // This assumes the user is continuing work they just left
       const dataAge = formData.timestamp ? Date.now() - formData.timestamp : Infinity;
       const MAX_AGE_MS = 10 * 60 * 1000; // 10 minutes
       
       if (!editId && formData && dataAge < MAX_AGE_MS) {
         // Restore form fields only if data is recent
         if (formData.name) setName(formData.name);
         if (formData.description) setDescription(formData.description);
         if (formData.studentRole) setStudentRole(formData.studentRole);
         if (formData.learningOutcomes) setLearningOutcomes(formData.learningOutcomes);
         if (formData.personas && Array.isArray(formData.personas) && formData.personas.length > 0) {
           setPersonas(formData.personas);
         }
         if (formData.scenes && Array.isArray(formData.scenes) && formData.scenes.length > 0) {
           setScenes(formData.scenes);
         }
         if (formData.gradingPrompt !== undefined) setGradingPrompt(formData.gradingPrompt);
         if (formData.rubricConfig) setRubricConfig(formData.rubricConfig);
         if (formData.autofillResult) setAutofillResult(formData.autofillResult);
         if (formData.savedSimulationId) setSavedSimulationId(formData.savedSimulationId);
         if (formData.isSaved !== undefined) setIsSaved(formData.isSaved);
         
         debugLog("Restored form state from localStorage (recent data)");
       } else if (!editId && dataAge >= MAX_AGE_MS) {
         // Data is too old, clear it to prevent data leakage
         debugLog("localStorage data is too old, clearing to prevent data leakage");
         localStorage.removeItem(STORAGE_KEY);
       }
     }
     // Reset flag after a short delay to allow state updates to complete
     setTimeout(() => {
       isRestoringFromStorage.current = false;
     }, 100);
   } catch (error) {
     console.error("Failed to restore from localStorage:", error);
     isRestoringFromStorage.current = false;
   }
 };

// Handle Play Simulation - save first if needed, then navigate to chatbox
const handlePlaySimulation = async () => {
  let simulationId = savedSimulationId;
  
  // Only allow play if simulation is already saved
  if (!simulationId) {
    alert("Please save the simulation before playing.");
    return;
  }

  setIsPlayingSimulation(true);

  // Store simulation ID for chatbox
  const chatboxData = {
    simulation_id: simulationId,
    title: autofillResult?.title || name || "Untitled Simulation"
  };
  
  localStorage.setItem("chatboxSimulation", JSON.stringify(chatboxData));
   
  // Navigate to chatbox
  window.open("/professor/test-simulations", "_blank");
  
  // Reset loading state after navigation
  setTimeout(() => {
    setIsPlayingSimulation(false);
  }, 1000);
 };

 // Transform our simulation data to chatbox format
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
    systemPrompt: "", // Add systemPrompt field
    imageUrl: undefined, // Add imageUrl field
    isTemp: true // Mark as temporary
  };
  
  // Don't add to tempPersonas immediately - just open modal with new persona
  // The persona will only be added when user clicks "Save Changes"
  setEditingIdx(-1); // Use -1 to indicate we're creating a new persona
  setTempPersonas([newPersona]); // Store the new persona temporarily for editing
}
const handleAddScene = () => {
  // Don't add to scenes immediately - just open modal with new scene
  // The scene will only be added when user clicks "Save Changes"
  setEditingSceneIdx(-1); // Use -1 to indicate we're creating a new scene
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
      // Update database completion field
      setDbCompletionFields(prev => ({
        ...prev,
        nameCompleted: !!fieldValue?.trim()
      }));
      markAsUnsaved();
      break;
    case 'description':
      const formattedDescription = formatDescription(fieldValue);
      setDescription(formattedDescription);
      // Update database completion field
      setDbCompletionFields(prev => ({
        ...prev,
        descriptionCompleted: !!formattedDescription?.trim()
      }));
      markAsUnsaved();
      break;
    case 'student_role':
      setStudentRole(fieldValue);
      // Update database completion field
      setDbCompletionFields(prev => ({
        ...prev,
        studentRoleCompleted: !!fieldValue?.trim()
      }));
      // Update student role in autofillResult
      setAutofillResult((prev: any) => ({
        ...prev,
        student_role: fieldValue
      }));
      markAsUnsaved();
      break;
    case 'personas':
      // Filter out personas that match the student role
      const currentStudentRole = studentRole.toLowerCase();
      const filteredFigures = fieldValue.filter((figure: any) => {
        const figureName = (figure.name || '').toLowerCase();
        const figureRole = (figure.role || '').toLowerCase();
        
        // Skip if this figure matches the student role exactly
        if (currentStudentRole && (figureName.includes(currentStudentRole) || figureRole.includes(currentStudentRole) || currentStudentRole.includes(figureName) || currentStudentRole.includes(figureRole))) {
          return false;
        }
        
        // Skip if this figure has a role that suggests they're the main protagonist
        const protagonistRoles = ['protagonist', 'main character', 'lead', 'principal', 'central figure'];
        if (protagonistRoles.some(role => figureRole.includes(role))) {
          return false;
        }
        
        // Skip if marked as main character
        if (figure.is_main_character) {
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
          name: figure.name || `Persona ${index + 1}`,
          position: figure.role || 'Unknown Role',  // Use 'position' not 'role'
          description: formatDescription(figure.background || figure.correlation || 'Background not specified in the case study.'),  // Use 'description' not 'background'
          primaryGoals: formattedGoals,  // Use 'primaryGoals' not 'goals'
          traits: {  // Use 'traits' object, not 'personality' string
            analytical: figure.personality_traits?.analytical || 5,
            creative: figure.personality_traits?.creative || 5,
            assertive: figure.personality_traits?.assertive || 5,
            collaborative: figure.personality_traits?.collaborative || 5,
            detail_oriented: figure.personality_traits?.detail_oriented || 5,
            risk_taking: figure.personality_traits?.risk_taking || 5,
            empathetic: figure.personality_traits?.empathetic || 5,
            decisive: figure.personality_traits?.decisive || 5
          },
          defaultTraits: {  // Add defaultTraits for reset functionality
            analytical: 5,
            creative: 5,
            assertive: 5,
            collaborative: 5,
            detail_oriented: 5,
            risk_taking: 5,
            empathetic: 5,
            decisive: 5
          },
          systemPrompt: undefined,  // Initialize as undefined for Advanced Mode
          imageUrl: figure.image_url || ''  // Map image_url from backend to imageUrl for frontend
        };
      });
      
      setPersonas(newPersonas);
      // Update database completion field
      setDbCompletionFields(prev => ({
        ...prev,
        personasCompleted: newPersonas.length > 0
      }));
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
        // Update database completion fields
        setDbCompletionFields(prev => ({
          ...prev,
          scenesCompleted: formattedScenes.length > 0,
          imagesCompleted: formattedScenes.some(scene => scene.imageUrl)
        }));
        markAsUnsaved();
      }
      break;
          case 'learning_outcomes':
            if (Array.isArray(fieldValue)) {
              const formattedOutcomes = formatLearningOutcomes(fieldValue as string[]);
              setLearningOutcomes(formattedOutcomes);
              // Update database completion field
              setDbCompletionFields(prev => ({
                ...prev,
                learningOutcomesCompleted: formattedOutcomes.length > 0
              }));
              markAsUnsaved();
            }
            break;
          case 'ai_enhancement_complete':
            // Mark AI enhancement as complete when backend signals completion
            console.log('AI enhancement completed by backend');
            setAiEnhancementComplete(true);
            // Update database completion field
            setDbCompletionFields(prev => ({
              ...prev,
              aiEnhancementCompleted: true
            }));
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
     
     const response = await fetch(buildApiUrl("/api/pdf-processing/parse-pdf/"), {
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
    
    const response = await fetch(buildApiUrl("/api/pdf-processing/parse-pdf/"), {
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
   return scenes.map(scene => {
     const normalized = {
       ...scene,
       image_url: scene.image_url, // Always preserve image_url
       timeout_turns:
         scene.timeout_turns !== undefined && scene.timeout_turns !== null
           ? scene.timeout_turns
           : 15,
     };
     // CRITICAL: Preserve scene ID if it exists (needed for matching existing scenes in database)
     if (scene.id !== undefined) {
       normalized.id = scene.id;
     }
     // Map sequence_order to scene_order for backend compatibility
     if (scene.sequence_order !== undefined) {
       normalized.sequence_order = scene.sequence_order;
     }
     return normalized;
   });
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
  
  if (idx === -1) {
    // This is a new persona being created
    setTempPersonas(tempPersonas => tempPersonas.map((p, i) => i === 0 ? { ...p, traits: { ...newTraits } } : p));
    console.log(`[DEBUG] SimulationBuilder: Updated new persona traits`);
  } else if (tempPersonas[idx]?.isTemp) {
    // Check if we're editing a temporary persona (use idx to check the correct persona)
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
  console.log(`[DEBUG] SimulationBuilder: handleSavePersona called for persona ${idx}:`, {
    personaName: updatedPersona.name,
    hasSystemPrompt: !!updatedPersona.systemPrompt,
    systemPromptLength: updatedPersona.systemPrompt?.length || 0,
    systemPromptPreview: updatedPersona.systemPrompt?.substring(0, 100) + '...' || 'No system prompt',
    isNewPersona: idx === -1,
    isTempPersona: updatedPersona.isTemp
  });
  
  if (idx === -1) {
    // This is a new persona being created for the first time
    const { isTemp, ...personaToSave } = updatedPersona; // Remove isTemp flag
    personaToSave.id = `persona-${Date.now()}`; // Generate permanent ID
    
    console.log(`[DEBUG] SimulationBuilder: Creating new persona with systemPrompt:`, {
      hasSystemPrompt: !!personaToSave.systemPrompt,
      systemPromptLength: personaToSave.systemPrompt?.length || 0
    });
    
    // Add to permanent personas at the top
    setPersonas(personas => [personaToSave, ...personas]);
    // Clear the temporary persona
    setTempPersonas([]);
  } else if (updatedPersona.isTemp) {
    // This is a temporary persona being saved for the first time
    const { isTemp, ...personaToSave } = updatedPersona; // Remove isTemp flag
    personaToSave.id = `persona-${Date.now()}-${idx}`; // Generate permanent ID
    
    console.log(`[DEBUG] SimulationBuilder: Converting temp persona to permanent with systemPrompt:`, {
      hasSystemPrompt: !!personaToSave.systemPrompt,
      systemPromptLength: personaToSave.systemPrompt?.length || 0
    });
    
    // Remove from temp personas and add to permanent personas at the top
    setTempPersonas(tempPersonas => tempPersonas.filter((_, i) => i !== idx));
    setPersonas(personas => [personaToSave, ...personas]);
  } else {
    // This is an existing persona being updated
    console.log(`[DEBUG] SimulationBuilder: Updating existing persona with systemPrompt:`, {
      hasSystemPrompt: !!updatedPersona.systemPrompt,
      systemPromptLength: updatedPersona.systemPrompt?.length || 0
    });
    
    setPersonas(personas => personas.map((p, i) => i === idx ? { ...updatedPersona } : p));
  }
  setEditingIdx(null);
  markAsUnsaved(); // Mark as unsaved when persona is saved/updated
};


// Delete persona handler
const handleDeletePersona = (idx: number) => {
  let personaToDelete;
  
  // Check if we're deleting a temporary persona (use idx to check the correct persona)
  if (tempPersonas[idx]?.isTemp) {
    personaToDelete = tempPersonas[idx];
    // Delete from temporary personas
    setTempPersonas(tempPersonas => tempPersonas.filter((_, i) => i !== idx));
  } else {
    personaToDelete = personas[idx];
    // Delete from permanent personas
    setPersonas(personas => personas.filter((_, i) => i !== idx));
  }
  
      // Remove persona from all scenes
      if (personaToDelete) {
        console.log(`[DEBUG] Removing persona "${personaToDelete.name}" from all scenes`);
        setScenes(scenes => {
          const updatedScenes = scenes.map(scene => {
            const originalPersonas = scene.personas_involved || [];
            const filteredPersonas = originalPersonas.filter((p: string) => p !== personaToDelete.name);
            console.log(`[DEBUG] Scene "${scene.title}": ${originalPersonas.length} -> ${filteredPersonas.length} personas`);
            return {
              ...scene,
              personas_involved: filteredPersonas
            };
          });
          return updatedScenes;
        });
      }
  
  setEditingIdx(null);
  markAsUnsaved(); // Mark as unsaved when persona is deleted
};

// Scene management handlers
const handleSaveScene = (idx: number, updatedScene: any) => {
  if (idx === -1) {
    // This is a new scene being created
    const newScene = {
      ...updatedScene,
      id: `scene-${Date.now()}`,
      sequence_order: scenes.length + 1
    };
    setScenes(scenes => [...scenes, newScene]);
  } else {
    // This is an existing scene being updated
    setScenes(scenes => scenes.map((s, i) => {
      if (i === idx) {
        // Merge the updated scene, preserving all new fields (like timeout_turns)
        return { ...s, ...updatedScene };
      }
      return s;
    }));
  }
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
console.log("[DEBUG] Total personas count:", personas.length);
console.log("[DEBUG] Personas details:", personas.map(p => ({ name: p.name, position: p.position })));

return (
   <div className="min-h-screen bg-atmospheric relative pattern-dots text-foreground">
     {/* New Sidebar Component */}
     <RoleBasedSidebar currentPath="/professor/simulation-builder" />
     
     {/* Top overlay bar - positioned outside content container */}
     <div className="fixed top-0 z-40 bg-white/90 backdrop-blur-sm shadow-lg border-b border-gray-200/60 flex items-center justify-between h-14 pl-4 pr-8 stagger-1 animate-fade-scale" style={{ left: '5rem', right: '0' }}>
       <div className="flex items-center gap-4">
         <Button variant="ghost" size="sm" onClick={() => router.back()}>
           <ArrowLeft className="h-4 w-4" />
         </Button>
         <span className="text-lg font-semibold">New Simulation</span>
       </div>
       <div className="flex gap-4">
         <Button 
           onClick={handleClear}
           disabled={!hasDataToClear()}
           variant="outline"
           className={`flex items-center gap-2 bg-white/90 backdrop-blur-sm transition-all ${
             hasDataToClear() 
               ? "border-red-200/60 hover:bg-red-50/90 hover:border-red-300/60 text-red-600 hover:text-red-700 cursor-pointer" 
               : "border-gray-200/60 text-gray-400 cursor-not-allowed opacity-50"
           }`}
         >
           <Trash2 className="h-4 w-4" />
           Clear
           {hasDataToClear() && (
             <span className="ml-1 h-2 w-2 rounded-full bg-red-500 animate-pulse" />
           )}
         </Button>
         <Button 
           onClick={handleSave}
           disabled={isSaving || uploadingFiles.size > 0 || processingMaterials.size > 0 || isParsingWithProgress}
           variant="outline"
           className="flex items-center gap-2 bg-white/90 backdrop-blur-sm border-gray-200/60 hover:bg-gray-50/90"
           title={isParsingWithProgress ? "Please wait for PDF processing to complete before saving" : undefined}
         >
           {isSaving ? (
             "Saving..."
           ) : isParsingWithProgress ? (
             "Processing PDF..."
           ) : uploadingFiles.size > 0 ? (
             `Uploading ${uploadingFiles.size} file${uploadingFiles.size > 1 ? 's' : ''}...`
           ) : processingMaterials.size > 0 ? (
             `Processing ${processingMaterials.size} file${processingMaterials.size > 1 ? 's' : ''}...`
           ) : isSaved ? (
             <>
               <Check className="h-4 w-4" />
               Saved
             </>
           ) : (
             "Save Draft"
           )}
         </Button>
         <Button 
           onClick={handlePublish}
           disabled={isPublishing || isParsingWithProgress}
           className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold flex items-center gap-2 disabled:opacity-50"
           title={isParsingWithProgress ? "Please wait for PDF processing to complete before publishing" : undefined}
         >
           {isPublishing ? (
             "Publishing..."
           ) : isParsingWithProgress ? (
             "Processing PDF..."
           ) : isPublished ? (
             <>
               <Check className="h-4 w-4" />
               Published
             </>
           ) : (
             "Publish"
           )}
         </Button>
         {savedSimulationId && (
           <button 
             onClick={handlePlaySimulation}
             disabled={isPlayingSimulation || isSimulationDraft}
             className="btn-gradient-purple text-white border-0 px-4 py-2 rounded-md shadow-md hover:shadow-lg transition-all font-semibold flex items-center gap-2 disabled:opacity-50 whitespace-nowrap"
           >
             {isPlayingSimulation ? (
               <>
                 <RefreshCw className="h-4 w-4 sim-loading-spinner" />
                 Loading...
               </>
             ) : (
               <>
                 <Activity className="h-4 w-4" />
                 Play Simulation
               </>
             )}
           </button>
         )}
       </div>
     </div>
     
     {/* Main content area with left margin for sidebar */}
     <div className="ml-20 animate-page-enter">
     {/* Add top padding to prevent content from being hidden under the bar */}
     <div className="h-14" />
     {/* Main content area */}
     <div className="w-full pl-16 pr-16 py-10 flex justify-center">
       <div className="w-full max-w-4xl">
       {/* Tabbed Interface */}
       <div className="w-full max-w-4xl">
         {/* Tab Navigation */}
         <div className="flex border-b border-gray-200 mb-6">
           <button
             onClick={() => setActiveTab('configuration')}
             className={`flex items-center gap-2 px-6 py-3 font-medium text-sm transition-colors ${
               activeTab === 'configuration'
                 ? 'border-b-2 border-black text-black'
                 : 'text-gray-600 hover:text-gray-900'
             }`}
           >
             <Settings className="h-4 w-4" />
             Configuration
           </button>
           <button
             onClick={() => setActiveTab('grading')}
             className={`flex items-center gap-2 px-6 py-3 font-medium text-sm transition-colors ${
               activeTab === 'grading'
                 ? 'border-b-2 border-black text-black'
                 : 'text-gray-600 hover:text-gray-900'
             }`}
           >
             <Target className="h-4 w-4" />
             Grading
           </button>
         </div>

         {/* Tab Content */}
         {activeTab === 'configuration' && (
           <div className="space-y-6">
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
             </div>

            {/* Show action buttons if files are uploaded */}
            {(uploadedFile || teachingNotesFile) && (
              <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
                <div></div>
                <div className="flex gap-4 justify-end">
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
                    className="bg-white text-black border border-gray-300 rounded px-4 py-2 font-medium shadow hover:bg-gray-50 transition h-10"
                  >
                    Choose a different file
                  </button>
                  {/* Use and autofill */}
                  <button
                    className="bg-black text-white rounded px-4 py-2 font-medium shadow hover:bg-gray-800 transition border border-black h-10 flex items-center gap-2"
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
                    <Sparkles className="h-4 w-4" />
                    Use and autofill
                  </button>
                </div>
              </div>
            )}

             {/* Show simulation builder progress */}
             <SimulationBuilderProgress
               name={name}
               description={description}
               studentRole={studentRole}
               personas={personas}
               scenes={scenes}
               learningOutcomes={learningOutcomes}
               isProcessing={isParsingWithProgress}
               completionStatus={completionStatus || undefined}
               hasAutofillResult={!!autofillResult}
               nameCompleted={dbCompletionFields.nameCompleted}
               descriptionCompleted={dbCompletionFields.descriptionCompleted}
               studentRoleCompleted={dbCompletionFields.studentRoleCompleted}
               personasCompleted={dbCompletionFields.personasCompleted}
               scenesCompleted={dbCompletionFields.scenesCompleted}
               imagesCompleted={dbCompletionFields.imagesCompleted}
               learningOutcomesCompleted={dbCompletionFields.learningOutcomesCompleted}
               className="mt-4"
             />

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

             {/* Hidden PDF progress tracker for field updates */}
             {(isParsingWithProgress || sessionId) && (
               <div style={{ display: 'none' }}>
                 <PDFProgressTrackerHTTP
                   sessionId={sessionId || ''}
                   onComplete={(result) => {
                     console.log('PDF parsing completed:', result);
                     // Reset the loading state when processing is complete
                     resetParsing();
                   }}
                   onError={(error) => {
                     console.error('PDF parsing error:', error);
                     setAutofillError(error);
                     // Reset the loading state on error
                     resetParsing();
                   }}
                   onFieldUpdate={(fieldName, fieldValue) => {
                     console.log('Field update received:', fieldName, fieldValue);
                     handleFieldUpdate(fieldName, fieldValue);
                   }}
                   onSimulationId={(simulationId: number) => {
                     console.log('Simulation ID received from backend:', simulationId);
                     // Set the simulation ID so auto-save uses the correct one
                     if (!savedSimulationId) {
                       setSavedSimulationId(simulationId);
                     }
                   }}
                 />
               </div>
             )}

             {/* Configuration content */}
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
                   <Input 
                     id="name" 
                     value={name} 
                     onChange={e => {
                       setName(e.target.value);
                       markAsUnsaved();
                     }} 
                     disabled={autofillLoading || isParsingWithProgress}
                     className="mt-1 w-full box-border p-2" 
                   />
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
                     disabled={autofillLoading || isParsingWithProgress}
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
                     disabled={autofillLoading || isParsingWithProgress}
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
                     disabled={autofillLoading || isParsingWithProgress}
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
                 <Button 
                   onClick={handleAddPersona} 
                   variant="outline" 
                   className="w-60"
                   disabled={autofillLoading || isParsingWithProgress}
                 >
                   Add new persona
                 </Button>
                 {/* Render persona cards here, excluding the player character */}
                 {(tempPersonas.length > 0 || personas.length > 0) && (
                   <div className="w-full flex flex-col items-center mt-6">
                     {/* Render temporary personas first (at the top) */}
                     {tempPersonas.map((persona: any, idx: number) => (
                       <div key={`temp-${idx}`} className="relative w-full">
                         <div 
                           onClick={() => !(autofillLoading || isParsingWithProgress) && setEditingIdx(idx)} 
                           style={{ 
                             cursor: (autofillLoading || isParsingWithProgress) ? 'not-allowed' : 'pointer',
                             opacity: (autofillLoading || isParsingWithProgress) ? 0.6 : 1,
                             pointerEvents: (autofillLoading || isParsingWithProgress) ? 'none' : 'auto'
                           }}
                         >
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
                         <div 
                           onClick={() => !(autofillLoading || isParsingWithProgress) && setEditingIdx(idx)} 
                           style={{ 
                             cursor: (autofillLoading || isParsingWithProgress) ? 'not-allowed' : 'pointer',
                             opacity: (autofillLoading || isParsingWithProgress) ? 0.6 : 1,
                             pointerEvents: (autofillLoading || isParsingWithProgress) ? 'none' : 'auto'
                           }}
                         >
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
                   <Button 
                     onClick={handleAddScene} 
                     variant="outline" 
                     className="w-60"
                     disabled={autofillLoading || isParsingWithProgress}
                   >
                     Add new Scene
                   </Button>
                   
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
                              <div 
                                onClick={() => !(autofillLoading || isParsingWithProgress) && setEditingSceneIdx(originalIdx)} 
                                style={{ 
                                  cursor: (autofillLoading || isParsingWithProgress) ? 'not-allowed' : 'pointer',
                                  opacity: (autofillLoading || isParsingWithProgress) ? 0.6 : 1,
                                  pointerEvents: (autofillLoading || isParsingWithProgress) ? 'none' : 'auto'
                                }}
                              >
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
         )}

        {activeTab === 'grading' && (
          <div className="space-y-6">
            {/* Grading Materials Section */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-medium">Grading Materials</h3>
                  <p className="text-sm text-muted-foreground">Upload additional documents for grading reference</p>
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
                    const files = Array.from(e.target.files || []);
                    if (files.length > 0 && savedSimulationId) {
                      // Upload files immediately
                      for (const file of files) {
                        await uploadFileImmediately(file, savedSimulationId);
                      }
                      // Clear the input
                      e.target.value = '';
                    } else if (files.length > 0) {
                      // If no saved simulation yet, add to pending files
                      setUploadedFiles(prev => [...prev, ...files]);
                      markAsUnsaved();
                    }
                  }}
                />
              </div>
              
              {/* Existing Grading Materials */}
              {existingGradingMaterials.length > 0 && (
                <div className="space-y-2 mb-4">
                  <h4 className="text-sm font-medium text-green-700">Uploaded Materials:</h4>
                  {existingGradingMaterials.map((material, index) => (
                    <div key={index} className="flex items-center justify-between p-3 border rounded-lg bg-green-50">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 bg-green-100 rounded flex items-center justify-center">
                          <svg className="h-4 w-4 text-green-600" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                            <polyline points="14,2 14,8 20,8" />
                          </svg>
                        </div>
                        <div>
                          <p className="text-sm font-medium">{material.filename}</p>
                          <p className="text-xs text-muted-foreground">
                            {material.file_size ? `${(material.file_size / 1024).toFixed(1)} KB` : 'Unknown size'} • 
                            Status: <span className={
                              material.processing_status === 'completed' ? 'text-green-600' : 
                              material.processing_status === 'processing' ? 'text-blue-600' :
                              material.processing_status === 'pending' ? 'text-yellow-600' :
                              'text-red-600'
                            }>
                              {material.processing_status === 'processing' ? 'Processing...' : material.processing_status}
                            </span>
                            {material.chunk_count ? ` • ${material.chunk_count} chunks` : ''}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {material.processing_status === 'completed' ? (
                          <div className="text-green-600">
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          </div>
                        ) : material.processing_status === 'processing' ? (
                          <div className="text-blue-600 animate-spin">
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                          </div>
                        ) : (
                          <div className="text-yellow-600">
                            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          </div>
                        )}
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
                    </div>
                  ))}
                </div>
              )}

              {/* Pending Upload Files */}
              {uploadedFiles.length > 0 && (
                <div className="space-y-2 mb-4">
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
                          <p className="text-xs text-muted-foreground">
                            {(file.size / 1024).toFixed(0)} KB • Will be uploaded when saved
                          </p>
                        </div>
                      </div>
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        className="text-gray-500 hover:text-red-600"
                        onClick={() => {
                          setUploadedFiles(prev => prev.filter((_, i) => i !== index));
                          markAsUnsaved();
                        }}
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
                  <p className="text-sm text-muted-foreground">No grading materials uploaded yet</p>
                  <p className="text-xs text-muted-foreground mt-1">Upload PDFs, documents, or text files for grading reference</p>
                </div>
              )}
            </div>

            {/* Grading Prompt Section */}
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Target className="h-5 w-5" />
                <h3 className="text-lg font-medium">Grading Prompt</h3>
              </div>
              <p className="text-sm text-muted-foreground">Enter instructions for the grading agent to customize how students are evaluated.</p>
              
              <div className="space-y-2">
                <Label htmlFor="grading-prompt">Grading Instructions</Label>
                <Textarea
                  id="grading-prompt"
                  value={gradingPrompt}
                  onChange={(e) => {
                    setGradingPrompt(e.target.value);
                    markAsUnsaved();
                  }}
                  placeholder="Enter instructions for the grading agent (e.g., 'Grade students based on their understanding of key concepts, application of theories, and quality of analysis...')"
                  className="min-h-[120px] resize-y"
                />
              </div>
            </div>

             {/* Rubric Configuration */}
             <div className="space-y-6">
               <div className="flex items-center gap-2">
                 <Target className="h-5 w-5" />
                 <h3 className="text-lg font-medium">Rubric Configuration</h3>
               </div>
               <p className="text-sm text-muted-foreground">Configure the rubric criteria and performance levels with point values.</p>
               
               {/* Rubric Title */}
               <div className="space-y-2">
                 <Label htmlFor="rubric-title">Rubric Title</Label>
                 <Input
                   id="rubric-title"
                   value={rubricConfig.title}
                   onChange={(e) => {
                     setRubricConfig(prev => ({
                       ...prev,
                       title: e.target.value
                     }));
                     markAsUnsaved();
                   }}
                   placeholder="e.g., Case Study Analysis, Business Strategy Evaluation"
                 />
               </div>
               
               {/* Performance Levels Header */}
               <div className="space-y-4">
                 <div className="flex items-center justify-between">
                   <h4 className="text-lg font-medium">Performance Levels</h4>
                   <Button
                     type="button"
                     variant="outline"
                     size="sm"
                     onClick={() => {
                       const newLevel = {
                         name: `Level ${rubricConfig.performanceLevels.length + 1}`,
                         points: 0
                       };
                       const newLevels = [...rubricConfig.performanceLevels, newLevel];
                       
                       setRubricConfig(prev => ({
                         ...prev,
                         performanceLevels: newLevels
                       }));
                       markAsUnsaved();
                     }}
                     className="flex items-center gap-2"
                   >
                     <Plus className="h-4 w-4" />
                     Add Column
                   </Button>
                 </div>
                 
                 <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
                   {rubricConfig.performanceLevels.map((level, index) => (
                     <div key={index} className="space-y-2 relative">
                             {rubricConfig.performanceLevels.length > 1 && (
                               <button
                                 type="button"
                                 onClick={() => {
                                   const newLevels = rubricConfig.performanceLevels.filter((_, i) => i !== index);
                                   setRubricConfig(prev => ({
                                     ...prev,
                                     performanceLevels: newLevels
                                   }));
                                   markAsUnsaved();
                                 }}
                                 className="absolute -top-2 -right-2 h-6 w-6 p-0 text-gray-500 hover:text-red-500 transition-colors"
                               >
                                 <X className="h-4 w-4" />
                               </button>
                             )}
                       <Label htmlFor={`level-name-${index}`}>Level Name</Label>
                       <Input
                         id={`level-name-${index}`}
                         value={level.name}
                         onChange={(e) => {
                           const newLevels = [...rubricConfig.performanceLevels];
                           newLevels[index].name = e.target.value;
                           setRubricConfig(prev => ({
                             ...prev,
                             performanceLevels: newLevels
                           }));
                           markAsUnsaved();
                         }}
                         placeholder="e.g., Outstanding"
                       />
                       <Label htmlFor={`level-points-${index}`}>Points</Label>
                       <Input
                         id={`level-points-${index}`}
                         type="number"
                         min="0"
                         max="100"
                         value={level.points === 0 ? "" : level.points}
                         onChange={(e) => {
                           const inputValue = e.target.value;
                           const newPoints = inputValue === "" ? 0 : parseInt(inputValue) || 0;
                           const newLevels = [...rubricConfig.performanceLevels];
                           newLevels[index].points = newPoints;
                           
                           setRubricConfig(prev => ({
                             ...prev,
                             performanceLevels: newLevels
                           }));
                           markAsUnsaved();
                         }}
                         className="w-full"
                       />
                     </div>
                   ))}
                 </div>
               </div>

               {/* Rubric Table */}
               <div className="space-y-4">
                 <div className="overflow-x-auto border border-gray-300 rounded-lg">
                   <table className="w-full border-collapse min-w-[1000px]">
                     <thead>
                       <tr className="bg-gray-50">
                         <th className="border-r border-gray-300 p-4 text-left font-medium w-[250px]">CRITERIA</th>
                         {rubricConfig.performanceLevels.map((level, index) => (
                           <th key={index} className="border-r border-gray-300 p-4 text-center font-medium w-[200px] last:border-r-0">
                             {level.name} ({level.points} pts)
                           </th>
                         ))}
                       </tr>
                     </thead>
                     <tbody>
                       {rubricConfig.criteria.map((criterion, criterionIndex) => (
                         <tr key={criterionIndex} className="border-b-2 border-gray-400 last:border-b-0">
                           <td className="border-r border-gray-300 p-4 relative align-top">
                             {rubricConfig.criteria.length > 1 && (
                               <button
                                 type="button"
                                 onClick={() => {
                                   const newCriteria = rubricConfig.criteria.filter((_, i) => i !== criterionIndex);
                                   setRubricConfig(prev => ({
                                     ...prev,
                                     criteria: newCriteria
                                   }));
                                   markAsUnsaved();
                                 }}
                                 className="absolute -top-2 -right-2 h-6 w-6 p-0 text-gray-500 hover:text-red-500 transition-colors"
                               >
                                 <X className="h-4 w-4" />
                               </button>
                             )}
                             <Textarea
                               value={criterion.description}
                               onChange={(e) => {
                                 const newCriteria = [...rubricConfig.criteria];
                                 newCriteria[criterionIndex].description = e.target.value;
                                 setRubricConfig(prev => ({
                                   ...prev,
                                   criteria: newCriteria
                                 }));
                                 markAsUnsaved();
                               }}
                               placeholder="Description of what this criterion evaluates"
                               className="min-h-[120px] text-sm w-full resize border-0 focus:ring-0 focus:outline-none"
                             />
                           </td>
                           {rubricConfig.performanceLevels.map((level, levelIndex) => (
                             <td key={levelIndex} className="border-r border-gray-300 p-4 align-top last:border-r-0">
                               <Textarea
                                 value={(criterion.descriptions as Record<string, string>)[level.name] || ""}
                                 onChange={(e) => {
                                   const newCriteria = [...rubricConfig.criteria];
                                   if (!newCriteria[criterionIndex].descriptions) {
                                     newCriteria[criterionIndex].descriptions = {} as Record<string, string>;
                                   }
                                   (newCriteria[criterionIndex].descriptions as Record<string, string>)[level.name] = e.target.value;
                                   setRubricConfig(prev => ({
                                     ...prev,
                                     criteria: newCriteria
                                   }));
                                   markAsUnsaved();
                                 }}
                                 placeholder={`Description for ${level.name} performance`}
                                 className="min-h-[120px] text-sm w-full resize border-0 focus:ring-0 focus:outline-none"
                               />
                             </td>
                           ))}
                         </tr>
                       ))}
                     </tbody>
                   </table>
                 </div>

                 {/* Add Criteria Row Button */}
                 <div className="flex justify-center">
                   <Button
                     type="button"
                     variant="outline"
                     onClick={() => {
                       const newDescriptions: Record<string, string> = {};
                       rubricConfig.performanceLevels.forEach(level => {
                         newDescriptions[level.name] = "";
                       });
                       
                       const newCriteria = [...rubricConfig.criteria, {
                         description: "",
                         descriptions: newDescriptions
                       }];
                       setRubricConfig(prev => ({
                         ...prev,
                         criteria: newCriteria
                       }));
                       markAsUnsaved();
                     }}
                     className="flex items-center gap-2"
                   >
                     <Plus className="h-4 w-4" />
                     Add Criteria Row
                   </Button>
                 </div>

                 {/* Total Points Display */}
                 <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                   <span className="font-medium">Total Points:</span>
                   <span className={`font-bold ${rubricConfig.performanceLevels.reduce((sum, level) => sum + level.points, 0) === 100 ? 'text-green-600' : 'text-red-600'}`}>
                     {rubricConfig.performanceLevels.reduce((sum, level) => sum + level.points, 0)}
                   </span>
                 </div>
               </div>
             </div>
           </div>
         )}
       </div>
     </div>
    {/* Modal for editing persona */}
    {editingIdx !== null && (
      (() => {
        const personaToEdit = editingIdx === -1 
          ? tempPersonas[0]
          : editingIdx < tempPersonas.length 
            ? tempPersonas[editingIdx]
            : personas[editingIdx - tempPersonas.length];
        
        return (
          <PersonaModal isOpen={true} onClose={() => {
            setEditingIdx(null);
            if (editingIdx === -1) {
              // If we're canceling a new persona creation, clear tempPersonas
              setTempPersonas([]);
            }
          }}>
            <PersonaCard
              persona={personaToEdit}
              defaultTraits={personaToEdit.defaultTraits}
              onTraitsChange={newTraits => handleTraitsChange(editingIdx, newTraits)}
              onSave={updatedPersona => handleSavePersona(editingIdx, updatedPersona)}
              onDelete={() => handleDeletePersona(editingIdx)}
              editMode={true}
            />
          </PersonaModal>
        );
      })()
    )}
     
     {/* Modal for editing scene */}
    {editingSceneIdx !== null && (
       <SceneModal isOpen={true} onClose={() => setEditingSceneIdx(null)}>
         <SceneCard
           scene={editingSceneIdx === -1 ? {
             id: `scene-${Date.now()}`,
             title: "New Scene",
             description: "",
             personas_involved: [],
             user_goal: "",
             sequence_order: scenes.length + 1,
             image_url: "",
             timeout_turns: 15
           } : scenes[editingSceneIdx]}
           onSave={updatedScene => handleSaveScene(editingSceneIdx, updatedScene)}
           onDelete={editingSceneIdx === -1 ? undefined : () => handleDeleteScene(editingSceneIdx)}
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


