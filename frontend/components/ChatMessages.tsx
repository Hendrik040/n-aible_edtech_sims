import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Eye } from 'lucide-react';

interface Message {
  id: string;
  sender: string;
  text: string;
  type: 'user' | 'system' | 'ai_persona' | 'orchestrator';
  timestamp: Date;
  showSubmitForGrading?: boolean;
  showViewGrading?: boolean;
  gradingInProgress?: boolean;
  persona_name?: string;
}

interface ChatMessagesProps {
  messages: Message[];
  gradingInProgress: boolean;
  shouldShowSubmitSystemMessage: boolean;
  isTyping: boolean;
  typingPersona: string;
  isInterfaceGreyed: boolean;
  currentTypingPersona: string;
  simulationComplete: boolean;
  inputBlocked: boolean;
  simulationHasBegun: boolean;
  gradingData: any;
  setShowGrading: (show: boolean) => void;
  setGradingInProgress: (progress: boolean) => void;
  fetchGradingData: (showGrading?: boolean, forceRefresh?: boolean) => Promise<void>;
  handleSubmitForGrading: () => void;
  onRequestSubmitForGrading?: () => void;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  TypingIndicator: React.ComponentType<{ personaName: string; isInterfaceGreyed: boolean }>;
}

export function ChatMessages({
  messages,
  gradingInProgress,
  shouldShowSubmitSystemMessage,
  isTyping,
  typingPersona,
  isInterfaceGreyed,
  currentTypingPersona,
  simulationComplete,
  inputBlocked,
  simulationHasBegun,
  gradingData,
  setShowGrading,
  setGradingInProgress,
  fetchGradingData,
  handleSubmitForGrading,
  onRequestSubmitForGrading,
  messagesEndRef,
  TypingIndicator
}: ChatMessagesProps) {
  return (
    <div className="flex-1 relative">
      {/* Black transparent overlay when interface is greyed - covers entire area */}
      {isInterfaceGreyed && (
        <div className="absolute inset-0 bg-black bg-opacity-50 z-40 pointer-events-none"></div>
      )}
      {/* Scrollable messages content */}
      <div className="h-full overflow-y-auto p-6 space-y-4">
        {[...messages,
          ...(gradingInProgress ? [{
            id: 'grading-in-progress',
            sender: 'System',
            text: 'Grading in progress... ',
            type: 'system' as const,
            timestamp: new Date(),
            showSubmitForGrading: false,
            showViewGrading: false,
            gradingInProgress: true
          }] : []),
          ...(shouldShowSubmitSystemMessage ? [{
            id: 'submit-for-grading',
            sender: 'System',
            text: '',
            type: 'system' as const,
            timestamp: new Date(),
            showSubmitForGrading: true,
            showViewGrading: false
          }] : [])].map((message) => {
          // Check if this is the currently streaming message
          const isStreamingMessage = isTyping && message.sender === typingPersona
          const shouldHighlight = isStreamingMessage || (isInterfaceGreyed && message.sender === currentTypingPersona)
          
          return (
          <div
            key={message.id}
            className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'} transition-all duration-300 ${
              shouldHighlight ? 'z-50 relative' : ''
            }`}
          >
            <div className={`max-w-md px-4 py-3 rounded-lg transition-all duration-300 ${
              shouldHighlight 
                ? 'ring-2 ring-green-400 shadow-xl scale-105' 
                : ''
            } ${
              message.type === 'user'
                ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-md'
                : message.type === 'system'
                ? 'bg-gray-50/90 backdrop-blur-sm text-gray-800 border border-gray-200/60 shadow-sm'
                : message.type === 'ai_persona'
                ? 'bg-green-50/90 backdrop-blur-sm text-gray-800 border border-green-200/60 shadow-sm'
                : message.type === 'orchestrator'
                ? 'bg-purple-50/90 backdrop-blur-sm text-gray-800 border border-purple-200/60 shadow-sm'
                : 'bg-white/90 backdrop-blur-sm text-gray-800 border border-gray-200/60 shadow-sm'
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-semibold opacity-75">
                  {message.sender}
                </span>
                {message.type === 'ai_persona' && message.persona_name && (
                  <Badge variant="secondary" className="text-xs bg-green-100 text-green-800">
                    {message.persona_name}
                  </Badge>
                )}
                {message.type === 'orchestrator' && message.persona_name && (
                  <Badge variant="secondary" className="text-xs">
                    AI
                  </Badge>
                )}
              </div>
              <div className="text-sm whitespace-pre-wrap">
                {message.text.split('\n').map((line, index) => {
                  const boldFormatted = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                  return (
                    <div key={index} dangerouslySetInnerHTML={{ __html: boldFormatted }} />
                  )
                })}
                {message.showSubmitForGrading && (
                  <div className="flex flex-col items-center mt-3">
                    <div className="mb-2 text-sm text-gray-700">Ready to submit your response for this scene?</div>
                    <Button
                      variant="default"
                      onClick={onRequestSubmitForGrading ?? handleSubmitForGrading}
                      disabled={inputBlocked || !simulationHasBegun}
                      className="btn-gradient-green text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                    >
                      Submit for Grading
                    </Button>
                  </div>
                )}
                {message.showViewGrading && (
                  <div className="flex flex-col items-center mt-3">
                    <Button
                      variant="default"
                      onClick={async () => {
                        if (gradingData) {
                          setShowGrading(true)
                        } else {
                          setGradingInProgress(true)
                          await fetchGradingData(false, true)
                          setGradingInProgress(false)
                        }
                      }}
                      disabled={gradingInProgress}
                      className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
                    >
                      {gradingInProgress ? 'Loading...' : 'View Grading & Feedback'}
                    </Button>
                  </div>
                )}
                {message.gradingInProgress && (
                  <div className="w-full mt-2 h-2 bg-gray-200/60 rounded-full overflow-hidden">
                    <div className="h-2 bg-gradient-to-r from-green-400 to-green-500 animate-pulse w-3/4 transition-all duration-1000 rounded-full"></div>
                  </div>
                )}
              </div>
            </div>
          </div>
          )
        })}

        {isTyping && (
          <TypingIndicator personaName={typingPersona} isInterfaceGreyed={isInterfaceGreyed} />
        )}

        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
