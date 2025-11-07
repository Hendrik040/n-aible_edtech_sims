"use client"

import React, { useState, useEffect, useRef } from 'react';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CheckCircle2, XCircle, Loader2, Upload, Sparkles, Server } from 'lucide-react';
import { buildApiUrl } from '@/lib/api';

interface ProgressData {
  overall_progress: number;
  current_stage: string;
  stage_progress: number;
  message: string;
  details?: any;
  timestamp: number;
  completed?: boolean;
  error?: string;
}

interface PDFProgressTrackerProps {
  sessionId: string;
  onComplete?: (result: any) => void;
  onError?: (error: string) => void;
  onFieldUpdate?: (fieldName: string, fieldValue: any) => void;
  onScenarioId?: (scenarioId: number) => void;
  className?: string;
}

const stageIcons: { [key: string]: React.ElementType } = {
  upload: Upload,
  processing: Sparkles,
};

const stageTitles: { [key: string]: string } = {
  upload: "File Upload",
  processing: "Document Processing",
};

export default function PDFProgressTracker({ 
  sessionId, 
  onComplete, 
  onError, 
  onFieldUpdate,
  onScenarioId,
  className = "" 
}: PDFProgressTrackerProps) {
  const [progressData, setProgressData] = useState<ProgressData | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastFieldUpdatesRef = useRef<Set<string>>(new Set());
  const consecutive404sRef = useRef<number>(0);
  const maxConsecutive404s = 10; // Stop after 10 consecutive 404s (10 seconds)
  const pollingStartTimeRef = useRef<number>(0);
  const maxPollingDuration = 5 * 60 * 1000; // Stop after 5 minutes

  const pollProgress = async () => {
    if (!sessionId) return;

    // Check if we've been polling too long
    const now = Date.now();
    if (pollingStartTimeRef.current > 0 && (now - pollingStartTimeRef.current) > maxPollingDuration) {
      const errorMsg = 'Session timeout: Progress polling exceeded maximum duration';
      setPollingError(errorMsg);
      onError?.(errorMsg);
      stopPolling();
      return;
    }

    // Development-only logging
    const isDev = process.env.NODE_ENV === 'development'

    try {
      const response = await fetch(buildApiUrl(`/pdf-progress/${sessionId}`));
      
      if (!response.ok) {
        if (response.status === 404) {
          // Increment 404 counter
          consecutive404sRef.current += 1;
          
          // If too many consecutive 404s, assume session is gone and stop polling
          if (consecutive404sRef.current >= maxConsecutive404s) {
            const errorMsg = 'Session not found: Progress tracking session does not exist or has expired';
            if (isDev) {
              console.warn(`⚠️ ${errorMsg} after ${consecutive404sRef.current} attempts`)
            }
            setPollingError(errorMsg);
            onError?.(errorMsg);
            stopPolling();
            return;
          }
          
          // Session not found yet, keep polling (expected during initialization)
          if (isDev && consecutive404sRef.current === 1) {
            console.log('⏳ Waiting for session to be created...')
          }
          return;
        }
        if (isDev) {
          console.error(`❌ Progress polling failed:`, response.status)
        }
        throw new Error(`Failed to fetch progress (HTTP ${response.status})`);
      }

      // Reset 404 counter on successful response
      consecutive404sRef.current = 0;

      const data = await response.json();
      
      if (isDev && data.current_stage) {
        console.log(`📊 Progress: ${data.overall_progress}% - ${data.current_stage}`)
      }
      
      setProgressData(data);
      setPollingError(null);

      // Extract and pass scenario_id if present
      if (data.scenario_id && onScenarioId) {
        onScenarioId(data.scenario_id);
      }

      // Check for field updates
      if (data.field_updates) {
        for (const [fieldName, fieldValue] of Object.entries(data.field_updates)) {
          const updateKey = `${fieldName}-${JSON.stringify(fieldValue)}`;
          if (!lastFieldUpdatesRef.current.has(updateKey)) {
            if (isDev) {
              console.log(`📝 Field update: ${fieldName}`)
            }
            onFieldUpdate?.(fieldName, fieldValue);
            lastFieldUpdatesRef.current.add(updateKey);
          }
        }
      }

      // Check for completion
      if (data.completed) {
        if (isDev) {
          console.log('✅ Processing completed')
        }
        onComplete?.(data.result);
        stopPolling();
      }

      // Check for error
      if (data.error) {
        if (isDev) {
          console.error('❌ Processing error:', data.error)
        }
        onError?.(data.error);
        stopPolling();
      }

    } catch (error) {
      if (isDev) {
        console.error('❌ Progress polling error:', error)
      }
      setPollingError(error instanceof Error ? error.message : 'Unknown error');
    }
  };

  const startPolling = () => {
    if (pollingIntervalRef.current) return;
    
    setIsPolling(true);
    setPollingError(null);
    consecutive404sRef.current = 0;
    pollingStartTimeRef.current = Date.now();
    
    // Poll immediately
    pollProgress();
    
    // Then poll every 1 second
    pollingIntervalRef.current = setInterval(pollProgress, 1000);
  };

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setIsPolling(false);
    consecutive404sRef.current = 0;
    pollingStartTimeRef.current = 0;
  };

  useEffect(() => {
    if (sessionId) {
      startPolling();
    }

    return () => {
      stopPolling();
    };
  }, [sessionId]);

  if (!sessionId) {
    return null;
  }

  const overallProgress = progressData?.overall_progress || 0;
  const overallMessage = progressData?.message || "Starting PDF processing...";
  const error = progressData?.error || pollingError;
  
  // Show progress bar during PDF processing
  const showProgressBar = true;

  const getStatusIcon = (status: string) => {
    if (status === 'completed') return <CheckCircle2 className="h-5 w-5 text-green-600" />;
    if (status === 'error') return <XCircle className="h-5 w-5 text-red-600" />;
    return <Loader2 className="h-5 w-5 animate-spin text-blue-600" />;
  };

  const getStatusBg = (status: string) => {
    if (status === 'completed') return 'bg-gradient-to-br from-green-100 to-green-50';
    if (status === 'error') return 'bg-gradient-to-br from-red-100 to-red-50';
    return 'bg-gradient-to-br from-blue-100 to-blue-50';
  };

  return (
    <Card className={`w-full card-elevated bg-white/90 backdrop-blur-sm border border-gray-200/60 rounded-xl shadow-md ${className} animate-fade-scale`}>
      <CardHeader className="pb-3 border-b border-gray-200/60">
        <CardTitle className="flex items-center gap-3 text-lg font-bold tracking-tight">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-sm ${getStatusBg(progressData?.completed ? 'completed' : progressData?.error ? 'error' : 'in_progress')}`}>
            {getStatusIcon(progressData?.completed ? 'completed' : progressData?.error ? 'error' : 'in_progress')}
          </div>
          <span className="text-gray-900">PDF Parsing Progress</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-4">
        {pollingError && (
          <div className="flex items-center gap-2 text-red-600 mb-4 p-3 bg-red-50/80 backdrop-blur-sm rounded-xl border border-red-200/60 animate-fade-scale">
            <XCircle className="h-4 w-4 flex-shrink-0" />
            <span className="text-sm font-medium">Error: {pollingError}</span>
          </div>
        )}
        
        {showProgressBar ? (
          <div className="mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-gray-900">{overallMessage}</span>
              <span className="text-sm font-bold text-gray-700">{overallProgress}%</span>
            </div>
            <Progress value={overallProgress} className="w-full h-2.5" />
          </div>
        ) : (
          <div className="mb-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-100 to-blue-50 rounded-lg flex items-center justify-center shadow-sm">
                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
              </div>
              <span className="text-sm font-semibold text-gray-900">{overallMessage}</span>
            </div>
          </div>
        )}

        {/* Removed individual stage progress bar - only show overall progress */}

        {isPolling && (
          <div className="mt-4 text-xs text-gray-600 flex items-center gap-2 pt-3 border-t border-gray-200/60">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span className="font-medium">Polling for updates...</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
