"use client";

import React, { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { debugLog } from "@/lib/debug";

// ─── Types ───────────────────────────────────────────────────────────────────

interface Persona {
  name: string;
  /** Maps to backend `role` field */
  position: string;
  /** Maps to backend `background` field */
  description: string;
  /** Current responsibilities and challenges in the case (backend: current_context) */
  currentContext?: string;
  /** Relationship of this persona to the student role (backend: correlation) */
  correlation?: string;
  /** 3–5 concise goals this persona is pursuing */
  primaryGoals?: string;
  /** Big Five personality traits, each scored 1–10 */
  traits: Record<string, number>;
  defaultTraits?: Record<string, number>;
  /** Domain knowledge: specific facts/data from the case (backend: knowledge_areas) */
  knowledgeAreas?: string[];
  /** How this persona communicates (backend: communication_style) */
  communicationStyle?: string;
  imageUrl?: string;
  /** Optional professor-authored system prompt — becomes the IDENTITY block */
  systemPrompt?: string;
}

interface PersonaCardProps {
  persona: Persona;
  defaultTraits?: Record<string, number>;
  onTraitsChange?: (traits: Record<string, number>) => void;
  onSave?: (persona: Persona) => void;
  onDelete?: () => void;
  editMode?: boolean;
}

// ─── Big Five trait configuration ────────────────────────────────────────────
// Replaces the former 8-trait custom schema with the standard Big Five model.

const traitLabels = [
  { key: "openness",          label: "Openness" },
  { key: "conscientiousness", label: "Conscientiousness" },
  { key: "extraversion",      label: "Extraversion" },
  { key: "agreeableness",     label: "Agreeableness" },
  { key: "neuroticism",       label: "Neuroticism" },
];

const defaultTraitValues: Record<string, number> = {
  openness: 5,
  conscientiousness: 5,
  extraversion: 5,
  agreeableness: 5,
  neuroticism: 5,
};

// ─── Component ───────────────────────────────────────────────────────────────

export default function PersonaCard({
  persona,
  defaultTraits,
  onTraitsChange,
  onSave,
  onDelete,
  editMode = false,
}: PersonaCardProps) {
  // Merge incoming traits with defaults so all Big Five keys are always present
  const fullTraits = { ...defaultTraitValues, ...persona.traits };

  const [traits, setTraits] = useState<Record<string, number>>(fullTraits);
  const [editFields, setEditFields] = useState<{
    name: string;
    position: string;
    description: string;
    currentContext?: string;
    correlation?: string;
    primaryGoals?: string;
    traits: Record<string, number>;
    knowledgeAreas?: string;   // textarea: newline-separated list
    communicationStyle?: string;
    systemPrompt?: string;
    imageUrl?: string;
  }>({
    name: persona.name,
    position: persona.position,
    description: persona.description,
    currentContext: persona.currentContext,
    correlation: persona.correlation,
    primaryGoals: persona.primaryGoals,
    traits: fullTraits,
    knowledgeAreas: (persona.knowledgeAreas || []).join("\n"),
    communicationStyle: persona.communicationStyle,
    systemPrompt: persona.systemPrompt,
    imageUrl: persona.imageUrl,
  });

  const [advancedMode, setAdvancedMode] = useState(!!persona.systemPrompt);

  // Sync trait sliders when persona.traits or defaultTraits props change
  useEffect(() => {
    const merged = { ...defaultTraitValues, ...persona.traits };
    debugLog(`PersonaCard: Syncing traits for ${persona.name}:`, { merged });
    setTraits(merged);
    setEditFields(f => ({ ...f, traits: merged }));
  }, [persona.traits, defaultTraits, persona.name]);

  // Keep display sliders in sync with parent when not in edit mode
  useEffect(() => {
    if (!editMode) {
      setTraits({ ...defaultTraitValues, ...persona.traits });
    }
  }, [persona.traits, editMode]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleSliderChange = (key: string, value: number[]) => {
    debugLog(`PersonaCard: Slider ${key} → ${value[0]} for ${persona.name}`);
    if (editMode) {
      setEditFields(f => ({ ...f, traits: { ...f.traits, [key]: value[0] } }));
    } else {
      const updated = { ...traits, [key]: value[0] };
      setTraits(updated);
      setEditFields(f => ({ ...f, traits: updated }));
      if (onTraitsChange) onTraitsChange(updated);
    }
  };

  const handleReset = () => {
    const reset = defaultTraits || defaultTraitValues;
    if (editMode) {
      setEditFields(f => ({ ...f, traits: { ...reset } }));
    } else {
      setTraits({ ...reset });
      if (onTraitsChange) onTraitsChange({ ...reset });
    }
  };

  const handleEditFieldChange = (field: string, value: string) => {
    setEditFields(f => ({ ...f, [field]: value }));
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      setEditFields(f => ({ ...f, imageUrl: ev.target?.result as string }));
    };
    reader.readAsDataURL(file);
  };

  const handleImageDelete = () => {
    setEditFields(f => ({ ...f, imageUrl: undefined }));
  };

  const handleSave = () => {
    debugLog(`[DEBUG] PersonaCard: Saving ${editFields.name}`, {
      hasSystemPrompt: !!editFields.systemPrompt,
      advancedMode,
    });

    if (onSave) {
      onSave({
        ...persona,
        name: editFields.name,
        position: editFields.position,
        description: editFields.description,
        currentContext: editFields.currentContext,
        correlation: editFields.correlation,
        primaryGoals: editFields.primaryGoals,
        traits: { ...editFields.traits },
        // Convert newline-separated textarea back to string array
        knowledgeAreas: editFields.knowledgeAreas
          ? editFields.knowledgeAreas.split(/\r?\n/).map(s => s.replace(/^[•\-\*]\s*/, "").trim()).filter(Boolean)
          : [],
        communicationStyle: editFields.communicationStyle,
        systemPrompt: advancedMode && editFields.systemPrompt?.trim() ? editFields.systemPrompt : undefined,
        imageUrl: editFields.imageUrl,
      });
    }
  };

  /**
   * Generate a lightweight custom identity prompt from the current form fields.
   * Note: Personality traits, scene context, and tone rules are now injected by
   * the backend meta-prompt framework, so we only output character identity here.
   */
  const generateSystemPrompt = () => {
    const goals = editFields.primaryGoals
      ? editFields.primaryGoals.split(/\r?\n/).filter(g => g.trim()).map(g => `• ${g.replace(/^[•\-\*]\s*/, "").trim()}`)
      : [];

    const prompt = `You are ${editFields.name}, ${editFields.position}.

BACKGROUND:
${editFields.description || ""}${editFields.currentContext ? `\n\nCURRENT CONTEXT:\n${editFields.currentContext}` : ""}

PRIMARY GOALS:
${goals.join("\n") || "• Engage authentically with the student"}${editFields.communicationStyle ? `\n\nCOMMUNICATION STYLE:\n${editFields.communicationStyle}` : ""}`;

    setEditFields(f => ({ ...f, systemPrompt: prompt }));
  };

  // ── Display mode ───────────────────────────────────────────────────────────

  if (!editMode) {
    return (
      <Card
        className="flex flex-row items-stretch w-full max-w-4xl min-h-[140px] p-4 mb-3 card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md cursor-pointer hover:shadow-lg transition-all duration-300 animate-fade-scale"
        tabIndex={0}
        aria-label={`Edit persona: ${persona.name}`}
      >
        {/* Avatar */}
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

        {/* Name, position, background, context, goals */}
        <div className="flex-1 flex flex-col justify-center pr-6">
          <div className="text-xl font-bold leading-tight mb-0.5">{persona.name}</div>
          <div className="text-base text-gray-500 mb-0.5">
            {persona.position || <span className="italic text-gray-400">Click to add role/title</span>}
          </div>
          {persona.correlation && (
            <div className="text-xs text-indigo-600 mb-1 italic">{persona.correlation}</div>
          )}
          <div className="text-sm text-gray-800 mb-1">
            {persona.description || <span className="italic text-gray-400">Click to add background</span>}
          </div>
          {persona.currentContext && (
            <div className="text-sm text-gray-600 mb-1">
              <span className="font-semibold text-gray-700">Context: </span>
              {persona.currentContext}
            </div>
          )}
          {persona.primaryGoals && (
            <div className="text-xs text-slate-800 mt-1">
              <span className="font-semibold">Goals: </span>
              {persona.primaryGoals}
            </div>
          )}
          {persona.communicationStyle && (
            <div className="text-xs text-gray-500 mt-0.5 italic">
              <span className="font-semibold not-italic">Style: </span>
              {persona.communicationStyle}
            </div>
          )}
        </div>

        {/* Big Five trait sliders (read-only) */}
        <div className="flex flex-col justify-center min-w-[220px]">
          {traitLabels.map(({ key, label }) => {
            const value = traits[key] ?? 5;
            return (
              <div key={key} className="flex items-center mb-1.5">
                <span className="w-36 text-right pr-2 text-sm font-medium text-gray-800">{label}</span>
                <div className="flex-1 flex items-center">
                  <Slider
                    min={1}
                    max={10}
                    step={1}
                    value={[value]}
                    disabled
                    className="w-28 mx-1"
                  />
                  <span className="w-5 text-xs text-gray-500 text-center">{value}</span>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    );
  }

  // ── Edit mode ──────────────────────────────────────────────────────────────

  return (
    <div className="w-full max-w-none mx-auto bg-white/90 backdrop-blur-sm rounded-xl border border-gray-200/60 shadow-lg animate-fade-scale flex flex-col h-full overflow-hidden">

      {/* Header: avatar + name/role/correlation */}
      <div className="flex items-center space-x-4 p-6 border-b border-gray-200/60 bg-gray-50/30 rounded-t-xl">
        {/* Image upload */}
        <div className="w-28 h-28 rounded-lg bg-gradient-to-br from-gray-100 to-gray-50 border border-gray-200/60 overflow-hidden flex items-center justify-center relative group cursor-pointer shadow-sm">
          {editFields.imageUrl ? (
            <img src={editFields.imageUrl} alt={editFields.name} className="object-cover w-full h-full" />
          ) : (
            <svg className="w-16 h-16 text-gray-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <circle cx="12" cy="8" r="4" />
              <path d="M6 20c0-2.2 3-4 6-4s6 1.8 6 4" />
            </svg>
          )}
          {editFields.imageUrl && (
            <button
              onClick={e => { e.stopPropagation(); handleImageDelete(); }}
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
          <input type="file" accept="image/*" onChange={handleImageUpload}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
        </div>

        {/* Name / Role / Correlation */}
        <div className="flex-1 grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <Input
              className="w-full text-base font-medium bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.name}
              onChange={e => handleEditFieldChange("name", e.target.value)}
              placeholder="Persona name"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Role / Title</label>
            <Input
              className="w-full text-base bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.position}
              onChange={e => handleEditFieldChange("position", e.target.value)}
              placeholder="Job title or role"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Relation to Student</label>
            <Input
              className="w-full text-base bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.correlation || ""}
              onChange={e => handleEditFieldChange("correlation", e.target.value)}
              placeholder="e.g. Direct supervisor, peer, client..."
            />
          </div>
        </div>
      </div>

      {/* Main content — 3 columns */}
      <div className="grid grid-cols-3 gap-6 p-6 overflow-y-auto flex-1">

        {/* Left: Background + Current Context */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Background</label>
            <Textarea
              className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[140px] text-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.description}
              onChange={e => handleEditFieldChange("description", e.target.value)}
              placeholder="Professional history, experience, and organizational context..."
              rows={6}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Current Context</label>
            <Textarea
              className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[120px] text-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.currentContext || ""}
              onChange={e => handleEditFieldChange("currentContext", e.target.value)}
              placeholder="Current responsibilities, challenges, and perspective in this case..."
              rows={5}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Communication Style</label>
            <Input
              className="w-full bg-white/80 backdrop-blur-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md text-sm"
              value={editFields.communicationStyle || ""}
              onChange={e => handleEditFieldChange("communicationStyle", e.target.value)}
              placeholder="e.g. Direct and data-driven, diplomatic but firm..."
            />
          </div>
        </div>

        {/* Middle: Big Five + Knowledge Areas */}
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="block text-sm font-medium text-gray-700">Personality (Big Five)</label>
              <Button size="sm" variant="outline" className="text-xs" onClick={handleReset}>
                Reset
              </Button>
            </div>
            <p className="text-xs text-gray-500 mb-3">1 = lowest · 10 = highest</p>
            <div className="space-y-3">
              {traitLabels.map(({ key, label }) => {
                const value = editFields.traits[key] ?? 5;
                return (
                  <div key={key} className="space-y-1">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-medium text-gray-700">{label}</span>
                      <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">{value}</span>
                    </div>
                    <Slider
                      min={1}
                      max={10}
                      step={1}
                      value={[value]}
                      onValueChange={v => handleSliderChange(key, v)}
                      className="w-full"
                    />
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Knowledge Areas</label>
            <Textarea
              className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[110px] text-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.knowledgeAreas || ""}
              onChange={e => handleEditFieldChange("knowledgeAreas", e.target.value)}
              placeholder={"One fact or data point per line:\nQ3 revenue declined 18% to $4.2M\nUnion contract expires March 2024\n..."}
              rows={5}
            />
            <p className="text-xs text-gray-400 mt-1">One item per line — specific facts, figures, and domain details this persona knows</p>
          </div>
        </div>

        {/* Right: Goals + Advanced Prompt */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Primary Goals</label>
            <Textarea
              className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[140px] text-sm border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md"
              value={editFields.primaryGoals || ""}
              onChange={e => handleEditFieldChange("primaryGoals", e.target.value)}
              placeholder="What is this persona actively trying to achieve in this simulation?"
              rows={6}
            />
          </div>

          {/* Advanced: Custom Identity Prompt */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Switch
                id="advanced-mode"
                checked={advancedMode}
                onCheckedChange={(checked: boolean) => {
                  setAdvancedMode(checked);
                  if (!checked) setEditFields(f => ({ ...f, systemPrompt: "" }));
                }}
              />
              <Label htmlFor="advanced-mode" className="text-sm font-medium text-gray-700">
                Custom Prompt
              </Label>
            </div>
            {advancedMode && (
              <Button type="button" variant="outline" size="sm" className="text-xs" onClick={generateSystemPrompt}>
                Generate
              </Button>
            )}
          </div>

          {advancedMode && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Identity Prompt</label>
              <Textarea
                className="w-full bg-white/80 backdrop-blur-sm resize-none min-h-[200px] text-xs border-gray-200/80 rounded-xl focus:ring-2 focus:ring-slate-500/20 focus:border-slate-400/50 transition-all shadow-sm hover:shadow-md font-mono"
                value={editFields.systemPrompt || ""}
                onChange={e => handleEditFieldChange("systemPrompt", e.target.value)}
                placeholder="Define this persona's voice and expertise. Scene context, behavioral rules, and tone are added automatically by the system."
                rows={10}
              />
              <p className="text-xs text-gray-500 mt-1">
                This text becomes the persona&apos;s identity — scene awareness and tone rules are always applied on top.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex justify-between items-center p-6 border-t border-gray-200/60 bg-gray-50/50 rounded-b-xl">
        <div className="text-sm text-gray-600 font-medium">
          {advancedMode ? "Custom identity prompt enabled" : "Using auto-generated identity"}
        </div>
        <div className="flex space-x-3">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onDelete && onDelete()}
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
