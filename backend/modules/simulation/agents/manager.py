"""
Manager for multiple persona agents.

Used by persona_agent.py
"""

from typing import Dict, TYPE_CHECKING

from common.db.models import SimulationPersona

if TYPE_CHECKING:
    # Import only for type checking to avoid circular import at runtime.
    from .persona_agent import PersonaAgent


class PersonaAgentManager:
    """Manager for multiple persona agents."""

    def __init__(self):
        # Use a plain dict without importing PersonaAgent at runtime to avoid cycles.
        self.agents: Dict[str, "PersonaAgent"] = {}

    def get_or_create_agent(
        self,
        persona: SimulationPersona,
        session_id: str,
    ):
        """Get existing agent or create new one."""
        # Local import avoids circular import during module initialization.
        from .persona_agent import PersonaAgent

        agent_key = f"{persona.id}_{session_id}"

        if agent_key not in self.agents:
            self.agents[agent_key] = PersonaAgent(persona, session_id)

        return self.agents[agent_key]

    def clear_session_agents(self, session_id: str) -> None:
        """Clear all agents for a specific session.
        
        Note: With stateless PersonaAgent, no memory clearing is needed
        since memory is created fresh per request.
        """
        keys_to_remove = [key for key in self.agents.keys() if key.endswith(f"_{session_id}")]
        for key in keys_to_remove:
            # No need to clear memory - PersonaAgent is stateless per request
            if key in self.agents:
                del self.agents[key]

    def get_agent_count(self) -> int:
        """Get total number of active agents."""
        return len(self.agents)


# Global persona agent manager instance
persona_agent_manager = PersonaAgentManager()


__all__ = ["PersonaAgentManager", "persona_agent_manager"]

