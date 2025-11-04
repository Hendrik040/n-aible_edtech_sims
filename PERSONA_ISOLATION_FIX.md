# Persona Isolation Fix

## Problem
The custom system prompts from individual personas were leaking into each other, causing cross-contamination where:
- Hussein's custom system prompt was affecting FMCG's responses
- FMCG's custom system prompt was affecting Hussein's responses
- Conversation history was being shared between personas
- System prompts were not properly isolated

## Root Causes
1. **Shared Memory**: All persona agents were using the same memory system
2. **Context Leakage**: Conversation history tools were not properly filtering by persona
3. **System Prompt Priority**: Custom system prompts were not being properly isolated from orchestrator prompts
4. **Session Sharing**: Persona agents were using the same session IDs

## Solutions Implemented

### 1. Persona-Specific Session IDs
```python
# Create persona-specific session ID to ensure complete isolation
self.persona_session_id = f"{session_id}_persona_{persona.id}"

# Create isolated memory for this specific persona
self.memory = langchain_manager.create_conversation_memory(
    self.persona_session_id, 
    memory_type="buffer_window"
)
```

### 2. Strict Conversation History Filtering
```python
# Search for conversation context - STRICT filtering by persona and user
search_filter = {
    "persona_id": str(self.persona.id), 
    "context_type": "conversation"
}

# Add user_progress_id filter if we have it
if hasattr(self, 'user_progress_id') and self.user_progress_id:
    search_filter["user_progress_id"] = str(self.user_progress_id)

# Add scene_id filter for additional isolation
if hasattr(self, 'current_scene_id') and self.current_scene_id:
    search_filter["scene_id"] = str(self.current_scene_id)

# Add session_id filter for complete isolation
if hasattr(self, 'persona_session_id') and self.persona_session_id:
    search_filter["session_id"] = str(self.persona_session_id)
```

### 3. Custom System Prompt Isolation
```python
# If custom system prompt is provided, use it directly and completely isolate it
if self.persona.system_prompt:
    print(f"[DEBUG] Using CUSTOM system prompt for {self.persona.name} - ISOLATED MODE")
    # Use the custom system prompt exactly as provided - no modifications
    # This ensures complete isolation from orchestrator prompts
    return self.persona.system_prompt
```

### 4. Isolated Memory Storage
```python
# Store user message with STRICT persona isolation metadata
self.vectorstore.add_texts(
    [f"User: {message}"],
    metadatas=[{
        "persona_id": str(self.persona.id),
        "context_type": "conversation",
        "message_type": "user",
        "user_progress_id": str(user_progress_id),
        "scene_id": str(scene_id),
        "timestamp": str(datetime.now()),
        "session_id": self.persona_session_id  # Add session isolation
    }]
)
```

### 5. Strict Memory Cleanup
```python
# Delete conversation documents using direct SQL with STRICT metadata filtering
delete_filter = {
    "persona_id": str(self.persona.id),
    "context_type": "conversation",
    "user_progress_id": str(user_progress_id),
    "session_id": str(self.persona_session_id)  # Add session isolation
}

# Build the delete statement with JSONB metadata filtering including session isolation
stmt = delete(self.vectorstore.EmbeddingStore).where(
    and_(
        self.vectorstore.EmbeddingStore.cmetadata['persona_id'].astext == str(self.persona.id),
        self.vectorstore.EmbeddingStore.cmetadata['context_type'].astext == 'conversation',
        self.vectorstore.EmbeddingStore.cmetadata['user_progress_id'].astext == str(user_progress_id),
        self.vectorstore.EmbeddingStore.cmetadata['session_id'].astext == str(self.persona_session_id)
    )
)
```

## Key Changes Made

### File: `backend/agents/persona_agent.py`

1. **PersonaAgent.__init__()**: Added persona-specific session ID generation
2. **get_conversation_history()**: Added strict filtering by session_id
3. **_get_system_prompt()**: Complete isolation of custom system prompts
4. **chat()**: Added current_scene_id tracking for isolation
5. **clear_conversation_history()**: Added session_id filtering for cleanup

## Testing

A test script `test_persona_isolation.py` has been created to verify:
- Session isolation between personas
- Custom system prompt isolation
- Persona-specific response triggers
- Cross-contamination prevention

## Expected Results

After these fixes:
- ✅ Hussein will only respond to "goat" with "Testing for Hussein"
- ✅ FMCG will only respond to "cheese" with "Testing for FMCG"
- ✅ No cross-contamination between personas
- ✅ Each persona maintains its own conversation history
- ✅ Custom system prompts are completely isolated
- ✅ Memory and context are properly separated

## Files Modified
- `backend/agents/persona_agent.py` - Main persona isolation fixes
- `test_persona_isolation.py` - Test script for verification
- `PERSONA_ISOLATION_FIX.md` - This documentation
