import React, { useState, useEffect, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { getImageUrl } from "@/lib/image-utils";
import { Users, MoreVertical, Edit2, Trash2, Target, Clock } from "lucide-react";

interface Scene {
  id: string;
  title: string;
  description: string;
  personas_involved: string[];
  user_goal: string;
  sequence_order: number;
  image_url?: string;
  // For future extensibility
  successMetric?: string;
  timeout_turns?: number;
}

interface SceneCardProps {
  scene: Scene;
  onSave?: (scene: Scene) => void;
  onDelete?: () => void;
  editMode?: boolean;
  allPersonas?: any[]; // List of available personas for selection
  studentRole?: string; // Add this prop for filtering
}

export default function SceneCard({ 
  scene, 
  onSave, 
  onDelete, 
  editMode = false,
  allPersonas = [],
  studentRole
}: SceneCardProps) {
  const [editFields, setEditFields] = useState({
    title: scene.title,
    description: scene.description,
    personas_involved: scene.personas_involved,
    user_goal: scene.user_goal,
    sequence_order: scene.sequence_order,
    image_url: scene.image_url || "",
    timeout_turns: scene.timeout_turns !== undefined && scene.timeout_turns !== null ? String(scene.timeout_turns) : "15", // Default to 15
    successMetric: scene.successMetric || ""
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(scene.image_url || null);

  useEffect(() => {
    const normStudentRole = normalizeName(studentRole || "");
    console.log("useEffect - scene.personas_involved:", scene.personas_involved);
    console.log("useEffect - allPersonas:", allPersonas.map(p => p.name));
    console.log("useEffect - scene.image_url:", scene.image_url);
    setEditFields({
      title: scene.title,
      description: scene.description,
      personas_involved: scene.personas_involved || [], // Ensure it's an array
      user_goal: scene.user_goal,
      sequence_order: scene.sequence_order,
      image_url: scene.image_url || "",
      timeout_turns: scene.timeout_turns !== undefined && scene.timeout_turns !== null ? String(scene.timeout_turns) : "15", // Default to 15
      successMetric: scene.successMetric || ""
    });
    setImagePreviewUrl(scene.image_url || null);
  }, [scene, studentRole, allPersonas]);

  const handleFieldChange = (field: string, value: any) => {
    setEditFields(fields => ({ ...fields, [field]: value }));
  };

  const handleImageClick = () => {
    if (fileInputRef.current) fileInputRef.current.click();
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && (file.type.startsWith("image/png") || file.type.startsWith("image/jpeg"))) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreviewUrl(reader.result as string);
        setEditFields(fields => ({ ...fields, image_url: reader.result as string }));
      };
      reader.readAsDataURL(file);
    }
  };

  const handleRemoveImage = () => {
    setImagePreviewUrl(null);
    setEditFields(fields => ({ ...fields, image_url: "" }));
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handlePersonaToggle = (persona: string) => {
    setEditFields(fields => {
      const exists = fields.personas_involved.includes(persona);
      return {
        ...fields,
        personas_involved: exists
          ? fields.personas_involved.filter(p => p !== persona)
          : [...fields.personas_involved, persona]
      };
    });
  };

  const handleSave = () => {
    // Debug log to check editFields before saving
    console.log("editFields before save:", editFields);
    if (onSave) {
      onSave({
        ...scene,
        title: editFields.title,
        description: editFields.description,
        personas_involved: editFields.personas_involved,
        user_goal: editFields.user_goal,
        sequence_order: editFields.sequence_order,
        image_url: editFields.image_url,
        timeout_turns: editFields.timeout_turns ? parseInt(editFields.timeout_turns) || 15 : 15, // Ensure timeout_turns is included
        successMetric: editFields.successMetric || ""
      });
    }
  };

  const handleDelete = () => {
    if (onDelete) onDelete();
  };

  // Helper to normalize names for comparison
  function normalizeName(name: string) {
    if (!name) return "";
    
    // Remove common title prefixes (Mr., Mrs., Ms., Dr., Prof., etc.)
    let normalized = name.trim();
    normalized = normalized.replace(/^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Professor)\s+/i, "");
    
    // Remove all non-alphabetic characters (apostrophes, dots, hyphens, etc.)
    normalized = normalized.replace(/[^a-zA-Z]/g, "").toLowerCase();
    
    return normalized;
  }
  const normStudentRole = normalizeName(studentRole || "");

  // Filter out main character from personas_involved for display and edit
  // Show ALL personas_involved except the main character
  let filteredPersonasInvolved = (editFields.personas_involved || []).filter(
    name => normalizeName(name) !== normStudentRole
  );

  // For chips: show all personas_involved except the main character
  const chipsPersonasInvolved = filteredPersonasInvolved;

  // Debugging logs
  console.log("=== SCENE CARD DEBUG ===");
  console.log("Scene title:", scene.title);
  console.log("editFields.personas_involved:", editFields.personas_involved);
  console.log("studentRole:", studentRole);
  console.log("normStudentRole:", normStudentRole);
  console.log("allPersonas:", allPersonas.map(p => p.name));
  console.log("Normalized allPersonas:", allPersonas.map(p => normalizeName(p.name)));
  console.log("filteredPersonasInvolved:", filteredPersonasInvolved);

  // Helper to get persona image from allPersonas
  const getPersonaImage = (personaName: string): string | undefined => {
    if (!allPersonas || allPersonas.length === 0) return undefined;
    const persona = allPersonas.find(p => normalizeName(p.name) === normalizeName(personaName));
    if (persona) {
      const imageUrl = (persona as any).imageUrl || (persona as any).image_url;
      if (imageUrl && typeof imageUrl === 'string' && imageUrl.trim().length > 0) {
        return getImageUrl(imageUrl);
      }
    }
    return undefined;
  };

  // Display mode (TimelineCard style)
  if (!editMode) {
    // Show ALL personas_involved except the main character
    // Don't filter by allPersonas - show what the AI generated
    let filteredPersonasInvolvedDisplay = (scene.personas_involved || []).filter(
      name => normalizeName(name) !== normStudentRole
    );
    
    return (
      <Card
        className={`relative flex flex-row items-stretch w-full max-w-4xl min-h-[200px] p-0 mb-4 bg-white rounded-xl shadow-md cursor-pointer hover:shadow-lg transition-all duration-300 overflow-hidden`}
        tabIndex={0}
        aria-label={`Edit scene: ${scene.title}`}
      >
        {/* Three-dot menu in top right */}
        <div className="absolute top-4 right-4 z-10">
          <MoreVertical className="w-5 h-5 text-gray-400 hover:text-gray-600" />
        </div>

        {/* White numbered badge in top-left */}
        <div className="absolute top-4 left-4 z-10 w-10 h-10 rounded-full bg-white flex items-center justify-center shadow-md">
          <span className="text-lg font-semibold text-gray-900">{scene.sequence_order}</span>
        </div>

        {/* Left: Scene Image (~40% of card) */}
        <div className="relative w-[40%] min-w-[200px] overflow-hidden">
          {scene.image_url ? (
            <img
              src={getImageUrl(scene.image_url)}
              alt="Scene"
              className="object-cover w-full h-full"
              onError={(e) => {
                console.log("Image failed to load:", scene.image_url);
                e.currentTarget.style.display = 'none';
              }}
            />
          ) : (
            <div className="w-full h-full bg-gradient-to-br from-gray-100 to-gray-200 flex items-center justify-center">
              <svg className="w-20 h-20 text-gray-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
          )}
        </div>

        {/* Right: Content (~60% of card) */}
        <div className="flex-1 flex flex-col justify-between p-6 bg-white">
          <div>
            <div className="text-xl font-bold leading-tight mb-3 text-gray-900">{scene.title}</div>
            
            {/* Description with target icon */}
            <div className="flex items-start gap-2 mb-4">
              <Target className="w-4 h-4 text-green-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-gray-700 leading-relaxed">{scene.description}</div>
            </div>
            
            {/* Personas involved as pills */}
            {filteredPersonasInvolvedDisplay.length > 0 && (
              <div className="flex items-center gap-2 mb-4 flex-wrap">
                <Users className="w-4 h-4 text-blue-500 flex-shrink-0" />
                <div className="flex items-center gap-2 flex-wrap">
                  {filteredPersonasInvolvedDisplay.map((personaName, idx) => (
                    <span 
                      key={idx} 
                      className="inline-flex items-center px-3 py-1 rounded-full bg-blue-100 text-blue-800 text-xs font-medium"
                    >
                      {personaName}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Duration */}
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <Clock className="w-4 h-4" />
              <span>{scene.timeout_turns || 15} turns</span>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3 mt-6 pt-4 border-t border-gray-200">
            <Button
              variant="outline"
              size="sm"
              className="h-8 px-3 text-blue-600 border-blue-200 hover:bg-blue-50"
              onClick={(e) => {
                e.stopPropagation();
                // Edit action is handled by parent's onClick on the Card
              }}
            >
              <Edit2 className="w-3 h-3 mr-1" />
              Edit
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8 px-3 text-red-600 border-red-200 hover:bg-red-50"
              onClick={(e) => {
                e.stopPropagation();
                if (onDelete) onDelete();
              }}
            >
              <Trash2 className="w-3 h-3 mr-1" />
              Delete
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  // In edit mode, use chipsPersonasInvolved for the chips and filter the dropdown as before
  // For chips: show all personas_involved except the main character
  // const chipsPersonasInvolved = filteredPersonasInvolved; // This line is removed

  // Debugging logs
  console.log("=== SCENE CARD EDIT MODE DEBUG ===");
  console.log("Scene title:", scene.title);
  console.log("editFields.personas_involved:", editFields.personas_involved);
  console.log("studentRole:", studentRole);
  console.log("normStudentRole:", normStudentRole);
  console.log("allPersonas:", allPersonas.map(p => p.name));
  console.log("Normalized allPersonas:", allPersonas.map(p => normalizeName(p.name)));
  console.log("filteredPersonasInvolved:", filteredPersonasInvolved);

  // Edit mode (TimelineCard style)
  return (
    <div className="w-full flex flex-col h-full animate-fade-scale relative">
      {/* Header - outside white container to fully cover rounded corners, extends to cover border and any gaps */}
      <div className="text-white p-5 rounded-t-xl flex-shrink-0 shadow-lg relative z-20 overflow-hidden"
           style={{
             marginLeft: '-4px',
             marginRight: '-4px',
             marginTop: '-2px',
             width: 'calc(100% + 8px)',
             borderRadius: '0.75rem 0.75rem 0 0',
             background: 'linear-gradient(to bottom right, rgb(17, 24, 39), rgb(31, 41, 55), rgb(17, 24, 39))',
             border: 'none',
             outline: 'none'
           }}>
        {/* Additional layer to ensure complete coverage */}
        <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-t-xl -z-10"
             style={{
               top: '-2px',
               left: '-2px',
               right: '-2px',
               bottom: '0',
               width: 'calc(100% + 4px)',
               height: 'calc(100% + 2px)'
             }}></div>
        <div className="flex items-center space-x-3 relative z-10">
          <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center">
            <svg className="w-5 h-5 text-black" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12,6 12,12 16,14" />
            </svg>
          </div>
          <div>
            <h2 className="text-xl font-bold tracking-tight">Scenario Scene</h2>
            <p className="text-sm text-gray-300 mt-1">Edit the details for this scene in your simulation.</p>
          </div>
        </div>
      </div>
      {/* White content container - no top rounded corners, positioned to align with header */}
      <div className="flex-1 bg-white/90 backdrop-blur-sm rounded-b-xl shadow-xl border-x border-b border-gray-200/60 flex flex-col overflow-hidden"
           style={{
             marginTop: '0',
             borderTop: 'none'
           }}>
        {/* Content */}
        <div className="flex-1 p-6 overflow-y-auto bg-white rounded-b-xl">
        <div className="grid grid-cols-3 gap-6">
          {/* Main Content Area */}
          <div className="col-span-3 flex flex-col space-y-4">
            <div className="flex items-center space-x-4">
              {/* Big icon to the left of both fields */}
              <div className="flex-shrink-0 flex items-center justify-center">
                <div
                  className="w-32 h-32 flex items-center justify-center rounded-lg border border-gray-200/60 bg-gradient-to-br from-gray-100 to-gray-50 relative cursor-pointer group shadow-sm hover:shadow-md transition-all"
                  onClick={handleImageClick}
                  title="Click to upload image"
                >
                  {imagePreviewUrl ? (
                    <>
                      <img
                        src={getImageUrl(imagePreviewUrl)}
                        alt="Scene"
                        className="object-cover w-full h-full rounded-lg"
                      />
                      <button
                        type="button"
                        className="absolute top-1 right-1 bg-white bg-opacity-80 rounded-full p-1 text-gray-700 hover:text-red-600 shadow"
                        onClick={e => { e.stopPropagation(); handleRemoveImage(); }}
                        title="Remove image"
                      >
                        &times;
                      </button>
                    </>
                  ) : (
                    <>
                      <svg className="w-20 h-20 text-gray-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="10" />
                        <polyline points="12,6 12,12 16,14" />
                      </svg>
                      <span className="absolute bottom-1 left-1 text-xs text-gray-500 bg-white bg-opacity-80 rounded px-1 py-0.5 hidden group-hover:block">Upload</span>
                    </>
                  )}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg"
                    className="hidden"
                    onChange={handleImageChange}
                  />
                </div>
              </div>
              <div className="flex-1">
                <span className="block text-gray-700 font-semibold text-sm">Scene Title</span>
                <Input
                  id="scene-title"
                  className="mt-1 block w-full rounded-xl bg-white/80 backdrop-blur-sm border-gray-200/80 text-sm font-medium focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                  value={editFields.title}
                  onChange={e => handleFieldChange("title", e.target.value)}
                  placeholder="Scene Title"
                />
                <span className="block text-gray-700 font-semibold mt-2 text-sm">Goal</span>
                <Input
                  id="scene-goal"
                  className="mt-1 block w-full rounded-xl bg-white/80 backdrop-blur-sm border-gray-200/80 text-sm focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                  value={editFields.user_goal}
                  onChange={e => handleFieldChange("user_goal", e.target.value)}
                  placeholder="Core challenge for this scene."
                />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-6">
              <div className="col-span-2">
                <span className="block text-lg font-bold text-gray-800 mb-2">Scene Description</span>
                <Textarea
                  id="scene-description"
                  className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[200px] text-sm border border-gray-200/80 rounded-xl text-gray-700 focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                  value={editFields.description}
                  onChange={e => handleFieldChange("description", e.target.value)}
                  placeholder="Description of what happens in this scene."
                  rows={10}
                />
                {/* Personas involved pills/chips UI */}
                <div className="mt-4">
                  <span className="block text-xs font-semibold text-purple-800 mb-1">Persona Involved in this Scene:</span>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {chipsPersonasInvolved.map((persona, idx) => (
                      <span key={idx} className="inline-flex items-center px-3 py-1 rounded-full bg-purple-100 text-purple-800 text-xs font-medium shadow-sm">
                        {persona}
                        <button
                          type="button"
                          className="ml-2 text-purple-600 hover:text-purple-900 focus:outline-none"
                          onClick={() => handlePersonaToggle(persona)}
                          aria-label={`Remove ${persona}`}
                        >
                          &times;
                        </button>
                      </span>
                    ))}
                  </div>
                  {/* Dropdown to add more personas, excluding student role */}
                  <div className="relative mt-1 w-full">
                    <select
                      className="appearance-none w-full rounded-lg border border-purple-300 bg-white text-xs text-gray-800 px-3 py-2 pr-8 shadow-sm focus:outline-none focus:ring-2 focus:ring-purple-400 focus:border-purple-400 transition-all cursor-pointer"
                      value=""
                      onChange={e => {
                        const val = e.target.value;
                        if (val) handlePersonaToggle(val);
                      }}
                    >
                      <option value="" disabled className="text-gray-400">+ Add persona...</option>
                      {allPersonas
                        .filter(p => normalizeName(p.name) !== normStudentRole && !editFields.personas_involved.includes(p.name))
                        .map((persona, idx) => (
                          <option key={idx} value={persona.name} className="hover:bg-purple-100">{persona.name}</option>
                        ))}
                    </select>
                    {/* Custom caret icon */}
                    <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-purple-400">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path d="M6 9l6 6 6-6" />
                      </svg>
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex flex-col space-y-4">
                <div>
                  <span className="block text-lg font-bold text-gray-800 mb-2">Scene Order</span>
                  <Input
                    id="scene-sequence-order"
                    type="number"
                    className="mt-1 block w-full rounded-xl bg-white/80 backdrop-blur-sm border-gray-200/80 text-sm focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                    value={editFields.sequence_order}
                    onChange={e => handleFieldChange("sequence_order", parseInt(e.target.value) || 1)}
                    placeholder="Scene order in the simulation."
                    min="1"
                  />
                </div>
                <div>
                  <span className="block text-gray-700 font-semibold text-sm">Timeout Turns</span>
                  <Input
                    id="scene-timeout-turns"
                    type="number"
                    className="mt-1 block w-full rounded-xl bg-white/80 backdrop-blur-sm border-gray-200/80 text-sm focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                    value={editFields.timeout_turns}
                    onChange={e => handleFieldChange("timeout_turns", e.target.value)}
                    placeholder="Turns before the scenario ends."
                    min="1"
                  />
                </div>
                <div>
                  <span className="block text-lg font-bold text-gray-800 mb-2">Success Metric</span>
                  <Textarea
                    id="scene-success-metric"
                    className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[150px] text-sm border border-gray-200/80 rounded-xl text-gray-700 focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
                    value={editFields.successMetric}
                    onChange={e => handleFieldChange("successMetric", e.target.value)}
                    placeholder="How to measure success in this scene."
                    rows={4}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
        </div>
        {/* Action Buttons - Fixed at bottom */}
        <div className="flex justify-end space-x-4 p-5 border-t border-gray-200/60 bg-gray-50/50 rounded-b-xl flex-shrink-0">
          <Button 
            id="scene-delete-button"
            variant="outline"
            className="px-4 py-2 text-red-600 border-red-200/80 hover:bg-red-50/80 bg-white/80 backdrop-blur-sm transition-all"
            onClick={handleDelete}
          >
            Delete
          </Button>
          <Button 
            id="scene-save-button"
            className="px-4 py-2 btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
            onClick={handleSave}
          >
            Save
          </Button>
        </div>
      </div>
    </div>
  );
} 