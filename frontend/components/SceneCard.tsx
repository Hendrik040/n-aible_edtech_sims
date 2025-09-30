import React, { useState, useEffect, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

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
    return name ? name.replace(/[^a-zA-Z]/g, "").toLowerCase().trim() : "";
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

  // Display mode (TimelineCard style)
  if (!editMode) {
    // Show ALL personas_involved except the main character
    // Don't filter by allPersonas - show what the AI generated
    let filteredPersonasInvolvedDisplay = (scene.personas_involved || []).filter(
      name => normalizeName(name) !== normStudentRole
    );
    return (
      <Card
        className={`flex flex-row items-stretch w-full max-w-4xl min-h-[140px] p-3 mb-3 border border-gray-200 shadow-md cursor-pointer transition-all duration-200`}
        tabIndex={0}
        aria-label={`Edit scene: ${scene.title}`}
      >
        {/* Left: Image */}
        <div className="flex flex-col items-center justify-center w-40 mr-4">
          <div className="w-32 h-32 flex items-center justify-center rounded-lg border bg-gray-100 overflow-hidden mb-1">
            {(() => {
              console.log("SceneCard render - scene.image_url:", scene.image_url);
              console.log("SceneCard render - scene:", scene);
              return scene.image_url ? (
                <img
                  src={scene.image_url}
                  alt="Scene"
                  className="object-cover w-full h-full rounded-lg"
                  onError={(e) => {
                    console.log("Image failed to load:", scene.image_url);
                    console.log("Error event:", e);
                  }}
                  onLoad={() => {
                    console.log("Image loaded successfully:", scene.image_url);
                  }}
                />
              ) : (
                <div className="text-center">
                  <svg className="w-20 h-20 text-gray-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12,6 12,12 16,14" />
                  </svg>
                  <div className="text-xs text-gray-500 mt-1">No Image</div>
                </div>
              );
            })()}
          </div>
        </div>
        {/* Middle: Details */}
        <div className="flex-1 flex flex-col justify-center pr-6">
          <div className="text-xl font-bold leading-tight mb-0.5">{scene.title}</div>
          <div className="text-base text-gray-500 mb-2">{scene.user_goal}</div>
          <div className="text-sm text-gray-800 mb-1">{scene.description}</div>
          {scene.successMetric && (
            <div className="text-xs text-blue-800 mt-1">
              <span className="font-semibold">Success Metric:</span> {scene.successMetric}
            </div>
          )}
          {filteredPersonasInvolvedDisplay.length > 0 && (
            <div className="text-xs text-purple-800 mt-1">
              <span className="font-semibold">Personas Involved:</span> {filteredPersonasInvolvedDisplay.join(', ')}
            </div>
          )}
        </div>
        {/* Right: Sequence/Timeout */}
        <div className="flex flex-col justify-center min-w-[120px]">
          <div className="text-center">
            <div className="text-sm font-medium text-gray-800">Scene Order</div>
            <div className="text-lg font-bold text-gray-600">{scene.sequence_order}</div>
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
    <div className="w-full bg-white rounded-lg shadow-lg flex flex-col h-full">
      {/* Black Header */}
      <div className="bg-black text-white p-4 rounded-t-lg flex-shrink-0">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center">
            <svg className="w-5 h-5 text-black" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12,6 12,12 16,14" />
            </svg>
          </div>
          <div>
            <h2 className="text-xl font-bold">Scenario Scene</h2>
            <p className="text-sm text-gray-300">Edit the details for this scene in your simulation.</p>
          </div>
        </div>
      </div>
      {/* Content */}
      <div className="flex-1 p-6 overflow-y-auto">
        <div className="grid grid-cols-3 gap-6">
          {/* Main Content Area */}
          <div className="col-span-3 flex flex-col space-y-4">
            <div className="flex items-center space-x-4">
              {/* Big icon to the left of both fields */}
              <div className="flex-shrink-0 flex items-center justify-center">
                <div
                  className="w-32 h-32 flex items-center justify-center rounded-lg border bg-gray-100 relative cursor-pointer group"
                  onClick={handleImageClick}
                  title="Click to upload image"
                >
                  {imagePreviewUrl ? (
                    <>
                      <img
                        src={imagePreviewUrl}
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
                  className="mt-1 block w-full rounded border-gray-300 text-sm font-medium"
                  value={editFields.title}
                  onChange={e => handleFieldChange("title", e.target.value)}
                  placeholder="Scene Title"
                />
                <span className="block text-gray-700 font-semibold mt-2 text-sm">Goal</span>
                <Input
                  id="scene-goal"
                  className="mt-1 block w-full rounded border-gray-300 text-sm"
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
                  className="w-full bg-gray-50 resize-none min-h-[200px] text-sm border border-gray-200 rounded text-gray-700 focus:ring-2 focus:ring-black focus:border-black"
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
                    className="mt-1 block w-full rounded border-gray-300 text-sm"
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
                    className="mt-1 block w-full rounded border-gray-300 text-sm"
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
                    className="w-full bg-gray-50 resize-none min-h-[150px] text-sm border border-gray-200 rounded text-gray-700 focus:ring-2 focus:ring-black focus:border-black"
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
      <div className="flex justify-end space-x-4 p-4 border-t border-gray-200 bg-gray-50 rounded-b-lg flex-shrink-0">
        <Button 
          id="scene-delete-button"
          variant="outline"
          className="px-4 py-2 text-red-600 border-red-300 hover:bg-red-50"
          onClick={handleDelete}
        >
          Delete
        </Button>
        <Button 
          id="scene-save-button"
          className="px-4 py-2 bg-black text-white hover:bg-gray-800"
          onClick={handleSave}
        >
          Save
        </Button>
      </div>
    </div>
  );
} 