import React, { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { debugLog } from "@/lib/debug";

interface Persona {
  name: string;
  position: string;
  description: string;
  primaryGoals?: string;
  traits: Record<string, number>;
  defaultTraits?: Record<string, number>;
  imageUrl?: string;
  systemPrompt?: string;
}

const traitLabels = [
  { key: "analytical", label: "Analytical" },
  { key: "creative", label: "Creative" },
  { key: "assertive", label: "Assertive" },
  { key: "collaborative", label: "Collaborative" },
  { key: "detail_oriented", label: "Detail Oriented" },
  { key: "risk_taking", label: "Risk Taking" },
  { key: "empathetic", label: "Empathetic" },
  { key: "decisive", label: "Decisive" },
];

interface PersonaCardProps {
  persona: Persona;
  defaultTraits?: any;
  onTraitsChange?: (traits: any) => void;
  onSave?: (persona: Persona) => void;
  onDelete?: () => void;
  editMode?: boolean;
}

export default function PersonaCard({ 
  persona, 
  defaultTraits, 
  onTraitsChange, 
  onSave, 
  onDelete, 
  editMode = false 
}: PersonaCardProps) {
  // Ensure all traits are present with default values
  const defaultTraitValues = {
    analytical: 5, creative: 5, assertive: 5, collaborative: 5,
    detail_oriented: 5, risk_taking: 5, empathetic: 5, decisive: 5,
  };
  const fullTraits = { ...defaultTraitValues, ...persona.traits };
  
  const [traits, setTraits] = useState<Record<string, number>>(fullTraits);
  const [editFields, setEditFields] = useState<{
    name: string;
    position: string;
    description: string;
    primaryGoals?: string;
    traits: Record<string, number>;
    systemPrompt?: string;
    imageUrl?: string;
  }>({
    name: persona.name,
    position: persona.position,
    description: persona.description,
    primaryGoals: persona.primaryGoals,
    traits: fullTraits,
    systemPrompt: persona.systemPrompt,
    imageUrl: persona.imageUrl
  });

  const [advancedMode, setAdvancedMode] = useState(!!persona.systemPrompt);

  // Sync local traits state with props when persona.traits or defaultTraits change
  useEffect(() => {
    // Ensure all traits are present with default values
    const defaultTraitValues = {
      analytical: 5, creative: 5, assertive: 5, collaborative: 5,
      detail_oriented: 5, risk_taking: 5, empathetic: 5, decisive: 5,
    };
    const fullTraits = { ...defaultTraitValues, ...persona.traits };
    debugLog(`PersonaCard: Syncing traits for ${persona.name}:`, {
      original: persona.traits,
      full: fullTraits,
      defaultTraitsProvided: !!defaultTraits
    });
    setTraits(fullTraits);
    setEditFields(fields => ({ ...fields, traits: fullTraits }));
  }, [persona.traits, defaultTraits, persona.name]);

  // Keep display sliders in sync with parent
  useEffect(() => {
    if (!editMode) {
      const defaultTraits = {
        analytical: 5, creative: 5, assertive: 5, collaborative: 5,
        detail_oriented: 5, risk_taking: 5, empathetic: 5, decisive: 5,
      };
      const fullTraits = { ...defaultTraits, ...persona.traits };
      setTraits(fullTraits);
    }
  }, [persona.traits, editMode]);

  const handleSliderChange = (key: string, value: number[]) => {
    debugLog(`PersonaCard: Slider changed for ${persona.name} - ${key}: ${value[0]}`);
    
    if (editMode) {
      setEditFields(fields => ({
        ...fields,
        traits: {
          ...fields.traits,
          [key]: value[0],
        },
      }));
    } else {
      const newTraits = { ...traits, [key]: value[0] };
      setTraits(newTraits);
      // Also update editFields to keep them in sync
      setEditFields(fields => ({
        ...fields,
        traits: {
          ...fields.traits,
          [key]: value[0],
        },
      }));
      debugLog(`PersonaCard: Calling onTraitsChange with:`, newTraits);
      if (onTraitsChange) onTraitsChange(newTraits);
    }
  };

  const handleReset = () => {
    const resetTraits = defaultTraits || {
      analytical: 5,
      creative: 5,
      assertive: 5,
      collaborative: 5,
      detail_oriented: 5,
      risk_taking: 5,
      empathetic: 5,
      decisive: 5,
    };
    
    if (editMode) {
      setEditFields(fields => ({
        ...fields,
        traits: { ...resetTraits },
      }));
    } else {
      setTraits({ ...resetTraits });
      if (onTraitsChange) onTraitsChange({ ...resetTraits });
    }
  };

  const handleEditFieldChange = (field: string, value: string) => {
    setEditFields(fields => ({ ...fields, [field]: value }));
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const imageUrl = event.target?.result as string;
        setEditFields(fields => ({ ...fields, imageUrl }));
      };
      reader.readAsDataURL(file);
    }
  };

  const handleImageDelete = () => {
    setEditFields(fields => ({ ...fields, imageUrl: undefined }));
  };

  const handleSave = () => {
    debugLog(`[DEBUG] PersonaCard: Saving persona ${editFields.name} with systemPrompt:`, {
      hasSystemPrompt: !!editFields.systemPrompt,
      systemPromptLength: editFields.systemPrompt?.length || 0,
      advancedMode: advancedMode,
      systemPromptPreview: editFields.systemPrompt?.substring(0, 100) + '...' || 'No system prompt'
    });
    
    if (onSave) {
      onSave({
        ...persona,
        name: editFields.name,
        position: editFields.position,
        description: editFields.description,
        primaryGoals: editFields.primaryGoals,
        traits: { ...editFields.traits },
        systemPrompt: advancedMode && editFields.systemPrompt?.trim() ? editFields.systemPrompt : undefined,
        imageUrl: editFields.imageUrl,
      });
    }
    // setEditMode(false); // This is now handled by the parent
  };

  const generateSystemPrompt = () => {
    const personality_traits = editFields.traits;
    const primary_goals = editFields.primaryGoals ? editFields.primaryGoals.split(/\r?\n/).filter(g => g.trim()) : [];
    
    // Format goals properly - remove existing bullet points and add clean ones
    const formatted_goals = primary_goals.map(goal => {
      // Remove existing bullet points (•, *, -) and trim whitespace
      const cleanGoal = goal.replace(/^[•\-\*]\s*/, '').trim();
      return `• ${cleanGoal}`;
    });
    
    const systemPrompt = `You are ${editFields.name}, a ${editFields.position} in this business simulation.

PERSONA BACKGROUND:
${editFields.description}

PERSONALITY TRAITS:
${JSON.stringify(personality_traits, null, 2)}

PRIMARY GOALS:
${formatted_goals.join('\n')}

INSTRUCTIONS:
- Stay in character as ${editFields.name} at all times
- Respond based on your role, background, and personality traits
- Help guide the user toward scene objectives through realistic business interaction
- Don't directly give away answers, but provide realistic business insights
- Keep responses concise and professional (2-4 sentences typically)
- If the user seems stuck, provide subtle hints through natural conversation

Remember: You are ${editFields.name}, not an AI assistant. Respond as this character would in a real business situation.`;

    setEditFields(fields => ({ ...fields, systemPrompt }));
  };

  const handleDelete = () => {
    if (onDelete) onDelete();
  };

  // Display mode
  if (!editMode) {
    return (
      <Card
        className="flex flex-row items-stretch w-full max-w-4xl min-h-[140px] p-4 mb-3 card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md cursor-pointer hover:shadow-lg transition-all duration-300 animate-fade-scale"
        tabIndex={0}
        aria-label={`Edit persona: ${persona.name}`}
      >
        {/* Left: Avatar and Info */}
        <div className="flex flex-col items-center justify-center w-32 mr-4">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-gray-100 to-gray-50 overflow-hidden flex items-center justify-center mb-1 shadow-sm border border-gray-200/60">
            {persona.imageUrl ? (
              <img src={persona.imageUrl} alt={persona.name} className="object-cover w-full h-full" />
            ) : (
              <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <circle cx="12" cy="8" r="4" />
                <path d="M6 20c0-2.2 3-4 6-4s6 1.8 6 4" />
              </svg>
            )}
          </div>
        </div>
        {/* Middle: Name, Position, Description, Goals */}
        <div className="flex-1 flex flex-col justify-center pr-6">
          <div className="text-xl font-bold leading-tight mb-0.5">{persona.name}</div>
          <div className="text-base text-gray-500 mb-2">
            {persona.position || <span className="italic text-gray-400">Click to add role/title</span>}
          </div>
          <div className="text-sm text-gray-800 mb-1">
            {persona.description || <span className="italic text-gray-400">Click to add background/bio</span>}
          </div>
          {persona.primaryGoals && (
            <div className="text-xs text-slate-800 mt-1">
              <span className="font-semibold">Primary Goals:</span>{" "}
              {(() => {
                // Render as bulleted list if lines start with -, *, or •
                const lines = persona.primaryGoals.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
                const isBulleted = lines.every(l => /^(-|\*|•)\s+/.test(l));
                if (isBulleted) {
                  return (
                    <ul className="list-disc ml-5">
                      {lines.map((l, i) => (
                        <li key={i}>{l.replace(/^(-|\*|•)\s+/, "")}</li>
                      ))}
                    </ul>
                  );
                } else {
                  return persona.primaryGoals;
                }
              })()}
            </div>
          )}
        </div>
        {/* Right: Traits (read-only) */}
        <div className="flex flex-col justify-center min-w-[220px]">
          {traitLabels.map(({ key, label }) => {
            const traitValue = traits[key as keyof typeof traits] ?? 5;
            debugLog(`PersonaCard Display: Showing trait ${key} for ${persona.name}: ${traitValue}`);
            return (
              <div key={key} className="flex items-center mb-1.5">
                <span className="w-32 text-right pr-2 text-sm font-medium text-gray-800">{label}</span>
                <div className="flex-1 flex items-center">
                  <Slider
                    min={0}
                    max={10}
                    step={1}
                    value={[traitValue]}
                    disabled
                    className="w-32 mx-1"
                  />
                  <span className="w-5 text-xs text-gray-500 text-center">{traitValue}</span>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    );
  }

  // Edit mode (no Card wrapper)
  return (
    <div className="w-full max-w-none mx-auto bg-white/90 backdrop-blur-sm rounded-xl border border-gray-200/60 shadow-lg rounded-t-xl animate-fade-scale flex flex-col h-full overflow-hidden">
      {/* Header Section */}
      <div className="flex items-center space-x-4 p-6 border-b border-gray-200/60 bg-gray-50/30 rounded-t-xl">
        <div className="w-28 h-28 rounded-lg bg-gradient-to-br from-gray-100 to-gray-50 border border-gray-200/60 overflow-hidden flex items-center justify-center relative group cursor-pointer shadow-sm">
          {editFields.imageUrl ? (
            <img src={editFields.imageUrl} alt={editFields.name} className="object-cover w-full h-full" />
          ) : (
            <svg className="w-16 h-16 text-gray-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <circle cx="12" cy="8" r="4" />
              <path d="M6 20c0-2.2 3-4 6-4s6 1.8 6 4" />
            </svg>
          )}
          
          {/* X button for deleting image */}
          {editFields.imageUrl && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleImageDelete();
              }}
              className="absolute top-1 right-1 w-6 h-6 bg-black bg-opacity-60 text-white rounded-full flex items-center justify-center hover:bg-opacity-80 transition-all duration-200 z-10"
              title="Delete image"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
          
          <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-20 flex items-center justify-center transition-all duration-200">
            <svg className="w-7 h-7 text-white opacity-0 group-hover:opacity-100 transition-opacity duration-200" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <input
            type="file"
            accept="image/*"
            onChange={(e) => handleImageUpload(e)}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          />
        </div>
        <div className="flex-1 grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <Input
              id="persona-name"
              className="w-full text-base font-medium bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.name}
              onChange={e => handleEditFieldChange("name", e.target.value)}
              placeholder="Persona name"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Role/Title</label>
            <Input
              id="persona-role"
              className="w-full text-base bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.position}
              onChange={e => handleEditFieldChange("position", e.target.value)}
              placeholder="Job title or role"
            />
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-3 gap-6 p-6 overflow-y-auto flex-1">
        {/* Left Column - Basic Info */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Background</label>
            <Textarea
              id="persona-bio"
              className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[160px] text-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.description}
              onChange={e => handleEditFieldChange("description", e.target.value)}
              placeholder="Professional background and experience..."
              rows={8}
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Primary Goals</label>
            <Textarea
              id="persona-goals"
              className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[140px] text-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.primaryGoals}
              onChange={e => handleEditFieldChange("primaryGoals", e.target.value)}
              placeholder="What does this persona want to achieve?"
              rows={7}
            />
          </div>
        </div>

        {/* Middle Column - Personality Traits */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <label className="block text-sm font-medium text-gray-700">Personality Traits</label>
            <Button
              size="sm"
              variant="outline"
              className="text-xs"
              onClick={handleReset}
            >
              Reset All
            </Button>
          </div>
          <div className="space-y-3">
            {traitLabels.map(({ key, label }) => {
              const sliderValue = editMode ? (editFields.traits[key] ?? 5) : (traits[key] ?? 5);
              const displayValue = editMode ? editFields.traits[key] : traits[key];
              
              return (
                <div key={key} className="space-y-1">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-medium text-gray-700">{label}</span>
                    <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                      {displayValue}
                    </span>
                  </div>
                  <Slider
                    min={0}
                    max={10}
                    step={1}
                    value={[sliderValue]}
                    onValueChange={value => handleSliderChange(key, value)}
                    className="w-full"
                  />
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column - Advanced Mode */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Switch
                id="advanced-mode"
                checked={advancedMode}
                onCheckedChange={(checked: boolean) => {
                  setAdvancedMode(checked);
                  if (!checked) {
                    // Clear local system prompt when turning Advanced Mode off
                    setEditFields(fields => ({ ...fields, systemPrompt: "" }));
                  }
                }}
              />
              <Label htmlFor="advanced-mode" className="text-sm font-medium text-gray-700">
                Advanced Mode
              </Label>
            </div>
            {advancedMode && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={generateSystemPrompt}
                className="text-xs"
              >
                Generate
              </Button>
            )}
          </div>
          
          {advancedMode && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">System Prompt</label>
              <Textarea
                id="system-prompt"
                className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[280px] text-xs border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md font-mono"
                value={editFields.systemPrompt || ''}
                onChange={e => handleEditFieldChange("systemPrompt", e.target.value)}
                placeholder="Custom system prompt for this persona..."
                rows={14}
              />
              <p className="text-xs text-gray-500 mt-2">
                Override default behavior with custom AI instructions
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Footer with Action Buttons */}
      <div className="flex justify-between items-center p-6 border-t border-gray-200/60 bg-gray-50/50 rounded-b-xl">
        <div className="text-sm text-gray-600 font-medium">
          {advancedMode ? "Advanced mode enabled" : "Using default persona behavior"}
        </div>
        <div className="flex space-x-3">
          <Button 
            variant="outline"
            size="sm" 
            onClick={handleDelete}
            className="text-red-600 border-red-200/80 hover:bg-red-50/80 bg-white/80 backdrop-blur-sm transition-all"
          >
            Delete Persona
          </Button>
          <Button 
            size="sm" 
            onClick={handleSave}
            className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
          >
            Save Changes
          </Button>
        </div>
      </div>
    </div>
  );
} 