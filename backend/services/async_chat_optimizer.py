"""
Async Chat Optimization Service
Handles AI API calls asynchronously with proper rate limiting and caching
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import openai
from functools import wraps

from database.connection import settings
from common.utilities.debug_logging import debug_log

# Performance monitoring
logger = logging.getLogger(__name__)

# Thread pool for AI operations
AI_EXECUTOR = ThreadPoolExecutor(max_workers=4)

# Global semaphores for rate limiting
_openai_semaphore = asyncio.Semaphore(3)  # Max 3 concurrent OpenAI calls

class AsyncChatOptimizer:
    """Optimized async chat processing with AI"""
    
    def __init__(self):
        self._response_cache = {}
        self._cache_ttl = 1800  # 30 minutes cache for similar requests
        self._client = None
    
    def _get_openai_client(self):
        """Get or create OpenAI client"""
        if not self._client:
            api_key = settings.openai_api_key
            if not api_key or not api_key.strip():
                raise ValueError("OpenAI API key not configured")
            self._client = openai.OpenAI(api_key=api_key)
        return self._client
    
    def _create_cache_key(self, prompt: str, model: str, max_tokens: int) -> str:
        """Create cache key for request"""
        import hashlib
        content = f"{prompt[:200]}_{model}_{max_tokens}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def _openai_chat_with_retry(
        self,
        messages: List[Dict[str, str]],
        model: str = "gpt-4o",
        max_tokens: int = 1000,
        temperature: float = 0.7,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """OpenAI chat completion with retry logic and rate limiting"""
        
        async with _openai_semaphore:  # Rate limiting
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    
                    # Run OpenAI call in thread pool to avoid blocking
                    def _make_openai_call():
                        client = self._get_openai_client()
                        return client.chat.completions.create(
                            model=model,
                            messages=messages,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                    
                    response = await asyncio.get_event_loop().run_in_executor(
                        AI_EXECUTOR, _make_openai_call
                    )
                    
                    api_time = time.time() - start_time
                    debug_log(f"[AI_OPTIMIZED] OpenAI call completed in {api_time:.3f}s (attempt {attempt + 1})")
                    
                    return {
                        "content": response.choices[0].message.content,
                        "usage": response.usage.model_dump() if response.usage else {},
                        "api_time": api_time,
                        "attempt": attempt + 1
                    }
                    
                except openai.RateLimitError as e:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff
                    debug_log(f"[AI_RETRY] Rate limited, waiting {wait_time}s (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                    else:
                        raise
                        
                except openai.APITimeoutError as e:
                    wait_time = (2 ** attempt)
                    debug_log(f"[AI_RETRY] Timeout, waiting {wait_time}s (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                    else:
                        raise
                        
                except Exception as e:
                    debug_log(f"[AI_ERROR] OpenAI call failed: {e} (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        raise
    
    async def generate_persona_response_async(
        self,
        user_message: str,
        persona_data: Dict[str, Any],
        scene_context: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        response_style: str = "conversational"
    ) -> Dict[str, Any]:
        """Generate AI persona response asynchronously"""
        
        start_time = time.time()
        
        try:
            # Create optimized prompt
            prompt = self._create_persona_prompt(
                user_message, persona_data, scene_context, conversation_history, response_style
            )
            
            # Check cache first
            cache_key = self._create_cache_key(prompt, "gpt-4o", 800)
            if cache_key in self._response_cache:
                cached_data = self._response_cache[cache_key]
                if time.time() - cached_data["timestamp"] < self._cache_ttl:
                    debug_log(f"[CACHE_HIT] Using cached persona response")
                    return cached_data["response"]
            
            # Prepare messages for OpenAI
            messages = [
                {"role": "system", "content": "You are an AI persona in a business simulation. Respond in character based on the provided context."},
                {"role": "user", "content": prompt}
            ]
            
            # Make async OpenAI call
            result = await self._openai_chat_with_retry(
                messages=messages,
                model="gpt-4o",
                max_tokens=800,
                temperature=0.7
            )
            
            # Process response
            response_data = {
                "content": result["content"],
                "persona_name": persona_data.get("name", "Unknown"),
                "response_time": time.time() - start_time,
                "api_time": result["api_time"],
                "usage": result["usage"],
                "cached": False
            }
            
            # Cache the response
            self._response_cache[cache_key] = {
                "response": response_data,
                "timestamp": time.time()
            }
            
            debug_log(f"[AI_OPTIMIZED] Persona response generated in {response_data['response_time']:.3f}s")
            return response_data
            
        except Exception as e:
            debug_log(f"[AI_ERROR] Failed to generate persona response: {e}")
            # Return fallback response
            return {
                "content": f"I apologize, but I'm having trouble responding right now. As {persona_data.get('name', 'a team member')}, I suggest we continue our discussion shortly.",
                "persona_name": persona_data.get("name", "Unknown"),
                "response_time": time.time() - start_time,
                "error": str(e),
                "cached": False
            }
    
    def _create_persona_prompt(
        self,
        user_message: str,
        persona_data: Dict[str, Any],
        scene_context: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        response_style: str
    ) -> str:
        """Create optimized prompt for persona response"""
        
        # Streamlined prompt for better performance
        history_text = ""
        if conversation_history:
            recent_history = conversation_history[-5:]  # Only last 5 messages
            history_text = "\n".join([
                f"{msg.get('role', 'User')}: {msg.get('content', '')[:200]}"  # Truncate long messages
                for msg in recent_history
            ])
        
        prompt = f"""
PERSONA: {persona_data.get('name', 'Team Member')}
ROLE: {persona_data.get('role', 'Colleague')}
SCENE: {scene_context.get('title', 'Business Meeting')}
GOAL: {scene_context.get('user_goal', 'Collaborate effectively')}

BACKGROUND: {persona_data.get('background', '')[:300]}

RECENT CONVERSATION:
{history_text}

USER MESSAGE: {user_message}

Respond as {persona_data.get('name', 'this persona')} in character. Keep response focused and under 150 words.
"""
        return prompt
    
    async def validate_goal_achievement_async(
        self,
        conversation_history: str,
        scene_goal: str,
        success_metric: str,
        current_attempts: int
    ) -> Dict[str, Any]:
        """Async goal validation with OpenAI function calling"""
        
        start_time = time.time()
        
        try:
            # Create function definition for goal validation
            function_def = {
                "name": "validate_scene_goal",
                "description": "Validate if the user has achieved the scene goal",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "goal_achieved": {"type": "boolean"},
                        "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "reasoning": {"type": "string"},
                        "next_action": {"type": "string", "enum": ["continue", "progress", "hint"]}
                    },
                    "required": ["goal_achieved", "confidence_score", "reasoning", "next_action"]
                }
            }
            
            # Create optimized validation prompt
            prompt = f"""
Analyze this conversation to determine if the user achieved the scene goal.

SCENE GOAL: {scene_goal}
SUCCESS METRIC: {success_metric}
ATTEMPT: {current_attempts}

CONVERSATION:
{conversation_history[-1000:]}  # Last 1000 chars only

Use the validate_scene_goal function to provide your assessment.
"""
            
            messages = [
                {"role": "system", "content": "You are a goal validation system for business simulations."},
                {"role": "user", "content": prompt}
            ]
            
            # Make async function call
            def _make_function_call():
                client = self._get_openai_client()
                return client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    functions=[function_def],
                    function_call={"name": "validate_scene_goal"},
                    max_tokens=300,
                    temperature=0.1
                )
            
            async with _openai_semaphore:
                response = await asyncio.get_event_loop().run_in_executor(
                    AI_EXECUTOR, _make_function_call
                )
            
            # Parse function call result
            function_call = response.choices[0].message.function_call
            if function_call and function_call.name == "validate_scene_goal":
                result = json.loads(function_call.arguments)
                result["validation_time"] = time.time() - start_time
                debug_log(f"[AI_OPTIMIZED] Goal validation completed in {result['validation_time']:.3f}s")
                return result
            else:
                # Fallback response
                return {
                    "goal_achieved": False,
                    "confidence_score": 0.5,
                    "reasoning": "Unable to parse validation result",
                    "next_action": "continue",
                    "validation_time": time.time() - start_time
                }
                
        except Exception as e:
            debug_log(f"[AI_ERROR] Goal validation failed: {e}")
            return {
                "goal_achieved": False,
                "confidence_score": 0.0,
                "reasoning": "Validation system error",
                "next_action": "continue",
                "error": str(e),
                "validation_time": time.time() - start_time
            }
    
    def clear_cache(self):
        """Clear the response cache"""
        self._response_cache.clear()
        debug_log("[CACHE] Response cache cleared")

# Global instance
async_chat_optimizer = AsyncChatOptimizer()
