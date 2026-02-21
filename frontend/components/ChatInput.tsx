import React from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Send, RefreshCw, Users, User, Type, Mic, Eye } from 'lucide-react';

interface ChatInputProps {
  input: string;
  setInput: (input: string) => void;
  showMentionDropdown: boolean;
  setShowMentionDropdown: (show: boolean) => void;
  handleKeyPress: (e: React.KeyboardEvent) => void;
  inputBlocked: boolean;
  isLoading: boolean;
  isTyping: boolean;
  gradingInProgress: boolean;
  simulationComplete: boolean;
  simulationHasBegun: boolean;
  personas: Array<{ id: string; name: string; role: string }>;
  sendMessage: () => void;
  inputMode: 'text' | 'voice';
  setInputMode: (mode: 'text' | 'voice') => void;
}

export function ChatInput({
  input,
  setInput,
  showMentionDropdown,
  setShowMentionDropdown,
  handleKeyPress,
  inputBlocked,
  isLoading,
  isTyping,
  gradingInProgress,
  simulationComplete,
  simulationHasBegun,
  personas,
  sendMessage,
  inputMode,
  setInputMode
}: ChatInputProps) {
  if (simulationComplete) {
    return (
      <div className="border-t border-gray-200 p-4">
        <div className="flex items-center justify-center py-4 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
          <div className="text-center">
            <Eye className="w-8 h-8 text-gray-400 mx-auto mb-2" />
            <p className="text-sm font-medium text-gray-700">Simulation Completed</p>
            <p className="text-xs text-gray-500 mt-1">All interactions are disabled in review mode</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="border-t border-gray-200 p-4">
      <div className="space-y-3">
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Input
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                setShowMentionDropdown(e.target.value.includes('@'));
              }}
              onKeyPress={handleKeyPress}
              placeholder="Type your message or @mention a persona..."
              disabled={inputBlocked || isLoading || isTyping || gradingInProgress}
              className="w-full"
            />
            {showMentionDropdown && (
              <div className="absolute top-full left-0 right-0 bg-white border border-gray-200 rounded-lg shadow-lg z-10 mt-1">
                <div className="p-2">
                  <div className="text-xs font-semibold text-gray-500 mb-2">All Personas</div>
                  <div className="text-xs text-gray-500 mb-2">Mention everyone in this scene</div>
                  {personas.map((persona) => (
                    <div
                      key={persona.id}
                      className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded cursor-pointer"
                      onClick={() => {
                        const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_');
                        setInput(input.replace(/@[^@]*$/, `@${mentionId} `));
                        setShowMentionDropdown(false);
                      }}
                    >
                      <div className="w-6 h-6 bg-gray-200 rounded-full flex items-center justify-center">
                        <User className="w-3 h-3" />
                      </div>
                      <div>
                        <div className="text-sm font-medium">{persona.name}</div>
                        <div className="text-xs text-gray-500">{persona.role}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          <Button
            onClick={sendMessage}
            disabled={inputBlocked || isLoading || isTyping || !input.trim()}
            className="btn-gradient text-white border-0 shadow-md hover:shadow-lg transition-all font-semibold"
          >
            {isLoading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
        
        {/* Quick Action Buttons */}
        <div className="flex gap-2 flex-wrap">
          {!simulationHasBegun && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setInput("begin")}
              disabled={inputBlocked || isLoading || isTyping}
            >
              Begin
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => setInput("help")}
            disabled={inputBlocked || isLoading || isTyping}
          >
            Help
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setInput(input ? `${input.trimEnd()} @all ` : `@all `)}
            disabled={inputBlocked || isLoading || isTyping}
          >
            <Users className="w-4 h-4 mr-1" />
            @all
          </Button>
          {personas.map((persona, index) => (
            <Button
              key={persona.id || index}
              size="sm"
              variant="outline"
              onClick={() => {
                const mentionId = persona.name.toLowerCase().replace(/\s+/g, '_');
                setInput(input ? `${input.trimEnd()} @${mentionId} ` : `@${mentionId} `);
              }}
              disabled={inputBlocked || isLoading || isTyping}
            >
              <User className="w-4 h-4 mr-1" />
              @{persona.name?.split(' ')[0] || 'Persona'}
            </Button>
          ))}
        </div>

        {/* Input Mode Toggle */}
        <div className="flex items-center justify-end gap-2">
          <Button
            size="sm"
            variant={inputMode === 'text' ? 'default' : 'outline'}
            onClick={() => setInputMode('text')}
          >
            <Type className="w-4 h-4 mr-1" />
            Text
          </Button>
          <Button
            size="sm"
            variant={inputMode === 'voice' ? 'default' : 'outline'}
            onClick={() => setInputMode('voice')}
          >
            <Mic className="w-4 h-4 mr-1" />
            Talk
          </Button>
        </div>
      </div>
    </div>
  );
}
