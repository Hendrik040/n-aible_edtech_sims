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
  // Use database boolean fields if all sections are complete, otherwise use real-time calculation
  const allDbFieldsComplete = nameCompleted && descriptionCompleted && studentRoleCompleted && personasCompleted && 
                              scenesCompleted && imagesCompleted && learningOutcomesCompleted && 
                              aiEnhancementCompleted;
  
  
  const sections = allDbFieldsComplete ? [
    { name: "Name", completed: nameCompleted },
    { name: "Description", completed: descriptionCompleted },
    { name: "Student Role", completed: studentRoleCompleted },
    { name: "Personas", completed: personasCompleted },
    { name: "Scenes", completed: scenesCompleted },
    { name: "Images", completed: imagesCompleted },
    { name: "Learning Outcomes", completed: learningOutcomesCompleted },
    { name: "AI Enhancement", completed: aiEnhancementCompleted },
  ] : [
    { name: "Name", completed: !!name?.trim() || hasAutofillResult },
    { name: "Description", completed: !!description?.trim() || hasAutofillResult },
    { name: "Student Role", completed: !!studentRole?.trim() || hasAutofillResult },
    { name: "Personas", completed: personas?.length > 0 || hasAutofillResult },
    { name: "Scenes", completed: scenes?.length > 0 || hasAutofillResult },
    { name: "Images", completed: scenes?.some(scene => scene.image_url) || hasAutofillResult },
    { name: "Learning Outcomes", completed: learningOutcomes?.length > 0 || (hasAutofillResult && !isProcessing) },
    { name: "AI Enhancement", completed: !!isAIEnhancementComplete || (hasAutofillResult && (learningOutcomes?.length > 0)) },
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
  
  // Debug logging for AI Enhancement
  console.log('SimulationBuilderProgress - AI Enhancement debug:', {
    isAIEnhancementComplete,
    hasAutofillResult,
    isProcessing,
    aiEnhancementCompletedFromProp: aiEnhancementCompleted,
    calculatedCompletion: isAIEnhancementComplete || hasAutofillResult,
    allDbFieldsComplete
  });

  const completedSections = sections.filter(section => section.completed).length;
  const totalSections = sections.length;
  const completionPercentage = Math.round((completedSections / totalSections) * 100);

  const getStatusIcon = (completed: boolean, allComplete: boolean) => {
    // Show loading wheel only during processing, not just when incomplete
    if (isProcessing && !allComplete) {
      return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
    }
    
    // Show checkmarks when everything is complete
    if (allComplete) {
      return completed ? 
        <CheckCircle2 className="h-4 w-4 text-green-500" /> : 
        <Circle className="h-4 w-4 text-gray-400" />;
    }
    
    // Default state: empty circles when not processing and not complete
    return <Circle className="h-4 w-4 text-gray-400" />;
  };

  return (
    <Card className={`w-full ${className}`}>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          {isProcessing ? (
            <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
          ) : completionPercentage === 100 ? (
            <CheckCircle2 className="h-5 w-5 text-green-500" />
          ) : (
            <Minus className="h-5 w-5 text-gray-400" />
          )}
          <span>Simulation Builder Progress</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
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
                {getStatusIcon(section.completed, completionPercentage === 100)}
                <span className={`text-sm ${section.completed && completionPercentage === 100 ? 'text-green-700' : 'text-gray-500'}`}>
                  {section.name}
                </span>
              </div>
            ))}
          </div>
        </div>

        {completionPercentage === 100 && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-md">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <span className="text-sm font-medium text-green-700">
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
