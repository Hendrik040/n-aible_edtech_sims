"""
Prompt Tracer - Lightweight LLM call tracing for observability.

Records every LLM invocation with full prompt context, response,
token usage, and latency. Designed to be non-blocking: if tracing
fails, the LLM response is still returned to the caller.

Usage:
    from modules.simulation.services.prompt_tracer import prompt_tracer

    # In an async context:
    trace_id = await prompt_tracer.record(
        agent_type="persona",
        agent_name="CEO Sarah",
        session_id="abc-123",
        system_prompt=system_prompt_text,
        user_message=user_msg,
        assistant_response=response_text,
        model_name="gpt-4o-mini",
        latency_ms=1523,
        scene_id=42,
        scenario_id=10,
        user_id=7,
        input_tokens=350,
        output_tokens=200,
        total_tokens=550,
        temperature=0.7,
    )
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

from common.db.core import SessionLocal
from common.db.models.simulation.prompt_trace import PromptTrace

logger = logging.getLogger(__name__)


class PromptTracer:
    """Non-blocking prompt trace recorder.

    All public methods are best-effort: exceptions are caught and logged
    so that tracing never disrupts the LLM hot path.
    """

    async def record(
        self,
        *,
        agent_type: str,
        agent_name: str,
        session_id: str,
        system_prompt: str,
        user_message: str,
        assistant_response: str,
        model_name: str,
        latency_ms: int,
        user_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        scene_id: Optional[int] = None,
        prompt_version: str = "v1",
        context_injected: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Optional[uuid.UUID]:
        """Persist a prompt trace row in the background.

        Returns the trace UUID on success, ``None`` on failure.
        The write is offloaded to a thread-pool executor so the
        calling coroutine is never blocked by DB I/O.
        """
        trace_id = uuid.uuid4()
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                self._write_trace,
                trace_id,
                agent_type,
                agent_name,
                session_id,
                system_prompt,
                user_message,
                assistant_response,
                model_name,
                latency_ms,
                user_id,
                scenario_id,
                scene_id,
                prompt_version,
                context_injected,
                input_tokens,
                output_tokens,
                total_tokens,
                temperature,
                metadata_json,
            )
            return trace_id
        except Exception:
            logger.warning(
                "[PROMPT_TRACE] Failed to record trace (non-critical)",
                exc_info=True,
            )
            return None

    def record_background(self, **kwargs: Any) -> None:
        """Fire-and-forget variant: schedules ``record()`` as a task.

        Use when you don't need the trace UUID back.
        """
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self.record(**kwargs))

            def _handle_exc(t: asyncio.Task) -> None:
                try:
                    t.result()
                except Exception:
                    logger.debug("[PROMPT_TRACE] Background trace task failed (non-critical)")

            task.add_done_callback(_handle_exc)
        except RuntimeError:
            # No running event loop — silently skip
            logger.debug("[PROMPT_TRACE] No event loop; skipping background trace")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _write_trace(
        trace_id: uuid.UUID,
        agent_type: str,
        agent_name: str,
        session_id: str,
        system_prompt: str,
        user_message: str,
        assistant_response: str,
        model_name: str,
        latency_ms: int,
        user_id: Optional[int],
        scenario_id: Optional[int],
        scene_id: Optional[int],
        prompt_version: str,
        context_injected: Optional[str],
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        total_tokens: Optional[int],
        temperature: Optional[float],
        metadata_json: Optional[Dict[str, Any]],
    ) -> None:
        """Synchronous DB write executed in a thread-pool executor."""
        db = SessionLocal()
        try:
            trace = PromptTrace(
                id=trace_id,
                agent_type=agent_type,
                agent_name=agent_name,
                session_id=session_id,
                system_prompt=system_prompt,
                user_message=user_message,
                assistant_response=assistant_response,
                model_name=model_name,
                latency_ms=latency_ms,
                user_id=user_id,
                scenario_id=scenario_id,
                scene_id=scene_id,
                prompt_version=prompt_version,
                context_injected=context_injected,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                temperature=temperature,
                metadata_json=metadata_json,
            )
            db.add(trace)
            db.commit()
            logger.debug(
                "[PROMPT_TRACE] Recorded trace %s for %s/%s",
                trace_id,
                agent_type,
                agent_name,
            )
        except Exception:
            db.rollback()
            logger.warning(
                "[PROMPT_TRACE] DB write failed for trace %s (non-critical)",
                trace_id,
                exc_info=True,
            )
        finally:
            db.close()


def _extract_token_usage(llm_response: Any) -> Dict[str, Optional[int]]:
    """Best-effort extraction of token counts from a LangChain LLM response.

    Works with both ``AIMessage`` objects (which may carry
    ``response_metadata.token_usage``) and raw OpenAI-style dicts.
    Returns a dict with keys ``input_tokens``, ``output_tokens``,
    ``total_tokens`` — any of which may be ``None``.
    """
    result: Dict[str, Optional[int]] = {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
    }
    try:
        # LangChain AIMessage path
        metadata = getattr(llm_response, "response_metadata", None) or {}
        usage = metadata.get("token_usage") or metadata.get("usage") or {}
        if not usage:
            # OpenAI raw dict path
            usage = getattr(llm_response, "usage", None) or {}
            if hasattr(usage, "model_dump"):
                usage = usage.model_dump()

        result["input_tokens"] = usage.get("prompt_tokens") or usage.get("input_tokens")
        result["output_tokens"] = usage.get("completion_tokens") or usage.get("output_tokens")
        result["total_tokens"] = usage.get("total_tokens")
    except Exception:
        pass
    return result


# Module-level singleton
prompt_tracer = PromptTracer()
