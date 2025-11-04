"use client"

import React from 'react';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CheckCircle2, Circle, Loader2, Minus } from 'lucide-react';

interface SimulationBuilderProgressProps {
  name: string;
  description: string;
  studentRole?: string;
  personas: any[];
  scenes: any[];
  learningOutcomes: string;
  isProcessing?: boolean; // Add processing state
  isAIEnhancementComplete?: boolean; // Add AI enhancement completion state
  completionStatus?: { [key: string]: boolean }; // Optional completion status from database
  hasAutofillResult?: boolean; // Add flag to indicate if autofill was used
  // Database boolean fields
  nameCompleted?: boolean;
  descriptionCompleted?: boolean;
  studentRoleCompleted?: boolean;
  personasCompleted?: boolean;
  scenesCompleted?: boolean;
  imagesCompleted?: boolean;
  learningOutcomesCompleted?: boolean;
  aiEnhancementCompleted?: boolean;
  className?: string;
}

const SimulationBuilderProgress: React.FC<SimulationBuilderProgressProps> = ({
  name,
  description,
  studentRole = "",
  personas,
  scenes,
  learningOutcomes,
  isProcessing = false,
  isAIEnhancementComplete = false,
  completionStatus,
  hasAutofillResult = false,
  nameCompleted,
  descriptionCompleted,
  studentRoleCompleted,
  personasCompleted,
  scenesCompleted,
  imagesCompleted,
  learningOutcomesCompleted,
  aiEnhancementCompleted,
  className = ""
}) => {
  // Use database boolean fields if available, otherwise use real-time calculation
  // Database fields take precedence when they exist
  const sections = [
    { 
      name: "Name", 
      completed: nameCompleted !== undefined ? nameCompleted : !!name?.trim(),
      hasDbValue: nameCompleted !== undefined
    },
    { 
      name: "Description", 
      completed: descriptionCompleted !== undefined ? descriptionCompleted : !!description?.trim(),
      hasDbValue: descriptionCompleted !== undefined
    },
    { 
      name: "Student Role", 
      completed: studentRoleCompleted !== undefined ? studentRoleCompleted : !!studentRole?.trim(),
      hasDbValue: studentRoleCompleted !== undefined
    },
    { 
      name: "Personas", 
      completed: personasCompleted !== undefined ? personasCompleted : personas?.length > 0,
      hasDbValue: personasCompleted !== undefined
    },
    { 
      name: "Scenes", 
      completed: scenesCompleted !== undefined ? scenesCompleted : scenes?.length > 0,
      hasDbValue: scenesCompleted !== undefined
    },
    { 
      name: "Images", 
      completed: imagesCompleted !== undefined ? imagesCompleted : scenes?.some(scene => scene.image_url),
      hasDbValue: imagesCompleted !== undefined
    },
    { 
      name: "Learning Outcomes", 
      completed: learningOutcomesCompleted !== undefined ? learningOutcomesCompleted : learningOutcomes?.length > 0,
      hasDbValue: learningOutcomesCompleted !== undefined
    },
  ];

  // Debug logging for images
  const imagesCompletedLocal = scenes?.some(scene => scene.image_url) || false;
  const scenesWithImages = scenes?.filter(scene => scene.image_url) || [];
  console.log('SimulationBuilderProgress - Images debug:', {
    totalScenes: scenes?.length || 0,
    scenesWithImages: scenesWithImages.length,
    imagesCompletedLocal,
    imagesCompletedFromProp: imagesCompleted,
    sceneImageUrls: scenes?.map(scene => ({ title: scene.title, image_url: scene.image_url })) || []
  });

  const completedSections = sections.filter(section => section.completed).length;
  const totalSections = sections.length;
  const completionPercentage = Math.round((completedSections / totalSections) * 100);

  const getStatusIcon = (completed: boolean, hasDbValue: boolean, isProcessing: boolean) => {
    // Show loading wheel during processing for incomplete sections
    if (isProcessing && !completed) {
      return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
    }
    
    // Show checkmarks for completed sections, empty circles for incomplete
    return completed ? 
      <CheckCircle2 className="h-4 w-4 text-green-500" /> : 
      <Circle className="h-4 w-4 text-gray-400" />;
  };

  return (
    <Card className={`w-full card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${className}`}>
      <CardHeader className="pb-3 border-b border-gray-200/60">
        <CardTitle className="text-lg font-bold flex items-center gap-2 tracking-tight">
          <div className={`w-8 h-8 rounded-xl flex items-center justify-center shadow-sm ${
            isProcessing 
              ? 'bg-gradient-to-br from-blue-100 to-blue-50' 
              : completionPercentage === 100 
              ? 'bg-gradient-to-br from-green-100 to-green-50'
              : 'bg-gradient-to-br from-gray-100 to-gray-50'
          }`}>
            {isProcessing ? (
              <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
            ) : completionPercentage === 100 ? (
              <CheckCircle2 className="h-4 w-4 text-green-600" />
            ) : (
              <Minus className="h-4 w-4 text-gray-500" />
            )}
          </div>
          <span className="text-gray-900">Simulation Builder Progress</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        {/* Overall Progress */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-sm font-medium">
              {isProcessing ? "Processing PDF..." : `Form Completion: ${completedSections}/${totalSections} sections completed`}
            </span>
            <span className="text-sm text-muted-foreground">
              {isProcessing ? "..." : `${completionPercentage}%`}
            </span>
          </div>
          <Progress 
            value={isProcessing ? 0 : completionPercentage} 
            className="h-2"
          />
        </div>

        {/* Section Breakdown */}
        <div className="space-y-2">
          <h4 className="text-sm font-medium text-gray-700">Sections:</h4>
          <div className="space-y-1">
            {sections.map((section, index) => (
              <div key={index} className="flex items-center gap-2">
                {getStatusIcon(section.completed, section.hasDbValue, isProcessing)}
                <span className={`text-sm ${section.completed ? 'text-green-700' : 'text-gray-500'}`}>
                  {section.name}
                </span>
              </div>
            ))}
          </div>
        </div>

        {completionPercentage === 100 && (
          <div className="mt-4 p-4 bg-gradient-to-br from-green-50 to-green-100/50 border border-green-200/60 rounded-xl shadow-sm animate-fade-scale">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-green-600" />
              <span className="text-sm font-semibold text-green-800">
                All sections completed! Your simulation is ready.
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default SimulationBuilderProgress;
