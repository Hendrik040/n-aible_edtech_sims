# True OpenAI Streaming Implementation Plan

> **Created:** December 25, 2024  
> **Status:** Planning  
> **Priority:** High  
> **Expected TTFB Improvement:** 2-3 seconds

---

## Problem Statement

Currently, even though the LLM is configured with `streaming=True`, the `AgentExecutor.ainvoke()` method **waits for the full response** before returning. This means:

```python
# Current code (persona_agent.py line 765)
response = await agent_executor.ainvoke(
    {"input": message},
    callbacks=[callback_handler]
)
# ^ This waits for the ENTIRE response before continuing
```

**Result:** TTFB is ~2-4 seconds because we wait for OpenAI to generate the full response.

---

## Solution Overview

Replace `ainvoke()` with `astream()` or `astream_events()` to get tokens as they arrive from OpenAI.

### Two Approaches

| Approach | Complexity | TTFB Improvement | Recommendation |
|----------|------------|------------------|----------------|
| **A) astream_events()** | Medium | ~2-3s | ✅ Recommended |
| **B) Direct ChatOpenAI streaming** | High | ~2-3s | More work, same result |

---

## Approach A: Using AgentExecutor.astream_events()

### How It Works

```python
# Instead of:
response = await agent_executor.ainvoke({"input": message})

# Use:
full_response = ""
async for event in agent_executor.astream_events({"input": message}, version="v2"):
    if event["event"] == "on_chat_model_stream":
        token = event["data"]["chunk"].content
        if token:
            yield token  # Stream to user immediately!
            full_response += token
```

### Event Types from astream_events()

| Event | Description | Use |
|-------|-------------|-----|
| `on_chat_model_start` | LLM call begins | Log start time |
| `on_chat_model_stream` | Token received | **Stream to user** |
| `on_chat_model_end` | LLM call complete | Log end time |
| `on_tool_start` | Tool invoked | Optional logging |
| `on_tool_end` | Tool complete | Optional logging |

---

## Implementation Plan

### Step 1: Create Streaming Chat Method in PersonaAgent

**File:** `backend/modules/simulation/agents/persona_agent.py`

Add a new method `chat_stream()` that yields tokens:

```python
async def chat_stream(
    self,
    message: str,
    scene_context: Dict[str, Any],
    user_progress_id: int,
    scene_id: int,
    attempt_number: int = 1,
    db: Optional[Session] = None
) -> AsyncGenerator[str, None]:
    """Stream chat response token by token.
    
    Yields tokens as they arrive from OpenAI, dramatically reducing TTFB.
    """
    # ... setup code (same as chat() lines 600-695) ...
    
    # Instead of ainvoke, use astream_events
    full_response = ""
    async for event in agent_executor.astream_events(
        {"input": message},
        version="v2"
    ):
        if event["event"] == "on_chat_model_stream":
            chunk = event["data"].get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                token = chunk.content
                full_response += token
                yield token  # Stream to user immediately!
    
    # After streaming complete, save to DB (same as current chat())
    # ... save response logic ...
```

### Step 2: Update ChatHandler to Use Streaming Method

**File:** `backend/modules/simulation/handlers/chat_handler.py`

Modify the persona chat section to use the new streaming method:

```python
# Current code (simplified):
response_text = await persona_agent.chat(message, scene_context, ...)
for char in response_text:
    yield f"data: {json.dumps({'content': char, ...})}\n\n"
    await asyncio.sleep(0.02)

# New code:
async for token in persona_agent.chat_stream(message, scene_context, ...):
    yield f"data: {json.dumps({'content': token, ...})}\n\n"
    # No artificial delay needed - natural streaming pace
```

### Step 3: Handle Response Saving

The tricky part is saving the full response to the database after streaming. Two options:

**Option A: Accumulate during streaming**
```python
full_response = ""
async for token in persona_agent.chat_stream(...):
    full_response += token
    yield f"data: {json.dumps({'content': token})}\n\n"

# After streaming complete
save_to_database(full_response)
```

**Option B: Return final response from generator**
```python
# In chat_stream(), yield tokens, then save internally
async def chat_stream(...):
    full_response = ""
    async for event in agent_executor.astream_events(...):
        if event["event"] == "on_chat_model_stream":
            token = ...
            full_response += token
            yield token
    
    # After streaming, save response
    self._save_response(full_response, user_progress_id, scene_id)
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `persona_agent.py` | Add `chat_stream()` method |
| `chat_handler.py` | Use `chat_stream()` for persona responses |
| `callbacks.py` | May need updates for streaming callbacks |

---

## Detailed Changes

### persona_agent.py

1. Add new import:
```python
from typing import AsyncGenerator
```

2. Add `chat_stream()` method (see Step 1 above)

3. Keep existing `chat()` method as fallback (optional)

### chat_handler.py

1. Replace `persona_agent.chat()` calls with `persona_agent.chat_stream()`

2. Remove artificial `asyncio.sleep()` delays (streaming provides natural pacing)

3. Handle response accumulation for database saving

---

## Expected Timeline

| Task | Estimated Time |
|------|----------------|
| Add `chat_stream()` to persona_agent.py | 30-45 min |
| Update chat_handler.py | 30-45 min |
| Testing & debugging | 1-2 hours |
| **Total** | **2-4 hours** |

---

## Risks and Mitigations

### Risk 1: Tool Calls During Streaming
**Issue:** If the agent uses tools, the stream may pause during tool execution.
**Mitigation:** Handle `on_tool_start`/`on_tool_end` events to show "thinking" indicator.

### Risk 2: Error Handling During Stream
**Issue:** Errors mid-stream need graceful handling.
**Mitigation:** Wrap stream in try/except, yield error message if needed.

### Risk 3: Memory/Callback Compatibility
**Issue:** Current callback handler may not work with streaming.
**Mitigation:** Update callback handler or handle saving differently.

---

## Testing Plan

1. **Local Test:** Start simulation, send message, verify:
   - First token appears within ~500ms (down from ~3-4 seconds)
   - Full response streams naturally
   - Response saved to database correctly

2. **Error Test:** Force an error mid-stream, verify graceful handling

3. **Load Test:** Multiple concurrent streams, verify no interference

---

## Rollback Plan

Keep existing `chat()` method. If streaming has issues, revert chat_handler.py to use `chat()` instead of `chat_stream()`.

---

## Success Metrics

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| TTFB (first token) | ~3-4 seconds | ~500ms | < 1 second |
| Total response time | Same | Same | No regression |
| Error rate | 0% | 0% | No increase |

---

## Next Steps

1. [ ] Review this plan
2. [ ] Implement `chat_stream()` in persona_agent.py
3. [ ] Update chat_handler.py to use streaming
4. [ ] Test locally
5. [ ] Deploy to staging
6. [ ] Monitor and adjust

---

## Code Snippets

### Full chat_stream() Method Template

```python
async def chat_stream(
    self,
    message: str,
    scene_context: Dict[str, Any],
    user_progress_id: int,
    scene_id: int,
    attempt_number: int = 1,
    db: Optional[Session] = None
) -> AsyncGenerator[str, None]:
    """Stream chat response token by token for reduced TTFB.
    
    Yields tokens as they arrive from OpenAI instead of waiting for full response.
    TTFB reduced from ~3-4 seconds to ~500ms.
    
    Args:
        message: User message
        scene_context: Current scene context
        user_progress_id: User progress ID
        scene_id: Current scene ID
        attempt_number: Attempt number (for few-shot examples)
        db: Optional database session
        
    Yields:
        String tokens as they arrive from OpenAI
    """
    try:
        # === SETUP (same as chat() method) ===
        
        # Step 1: Load conversation history
        conversation_logs = self._load_conversation_history_from_db(
            user_progress_id, scene_id, current_message=message, db=db
        )
        
        # Step 2: Create fresh memory
        memory = langchain_manager.create_conversation_memory(
            self.persona_session_id, memory_type="buffer_window"
        )
        
        # Step 3: Load history into memory
        for log in conversation_logs:
            if log.message_type == "user":
                memory.chat_memory.add_user_message(log.message_content)
            elif log.message_type in ("ai_persona", "orchestrator"):
                memory.chat_memory.add_ai_message(log.message_content)
        
        # Step 4: Create prompt
        prompt = self._create_persona_prompt_with_attempt(attempt_number, scene_context)
        
        # Step 5: Create agent
        agent = create_openai_tools_agent(
            llm=self.llm, tools=self.tools, prompt=prompt
        )
        
        # Step 6: Create executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=memory,
            verbose=False,
            handle_parsing_errors=True,
            max_iterations=2
        )
        
        # === STREAMING (new) ===
        
        full_response = ""
        
        async for event in agent_executor.astream_events(
            {"input": message},
            version="v2"
        ):
            event_type = event.get("event", "")
            
            if event_type == "on_chat_model_stream":
                # Extract token from chunk
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    token = chunk.content
                    full_response += token
                    yield token
            
            elif event_type == "on_tool_start":
                # Optional: yield a "thinking" indicator
                # yield "[thinking...]"
                pass
        
        # === POST-STREAMING (save response) ===
        
        if full_response:
            # Save to database using callback handler
            callback_handler = PersonaCallbackHandler(
                persona_id=self.persona.id,
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                session_id=self.persona_session_id,
                db=db,
            )
            callback_handler._log_conversation(full_response, 0.0)
            
            # Store in vectorstore (background)
            # ... existing vectorstore code ...
    
    except Exception as e:
        logger.error(f"Error in chat_stream: {e}", exc_info=True)
        yield f"I apologize, but I encountered an error: {str(e)}"
```

---

## References

- [LangChain astream_events Documentation](https://python.langchain.com/docs/how_to/streaming/#using-stream-events)
- [OpenAI Streaming API](https://platform.openai.com/docs/api-reference/streaming)

