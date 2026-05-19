"""Handle @mention and @all commands for persona interactions."""

from typing import Dict, Any
import asyncio

from modules.simulation.core import ChatOrchestrator
from common.config import get_settings

settings = get_settings()
_is_dev = settings.environment != "production"


async def handle_all_mention(
    orchestrator: ChatOrchestrator,
    message: str,
    current_scene: Dict[str, Any],
    scene_id: int
) -> Dict[str, Any]:
    """
    Handle @all mention - get responses from all personas in scene.
    
    Args:
        orchestrator: ChatOrchestrator instance
        message: User message with @all
        current_scene: Current scene data
        scene_id: Current scene ID
        
    Returns:
        Dictionary with responses list and persona count
    """
    personas_involved = current_scene.get('personas_involved', [])
    scene_personas = []
    
    for persona in orchestrator.simulation.get('personas', []):
        persona_name = persona['identity']['name']
        if persona_name in personas_involved:
            scene_personas.append(persona)
    
    if not scene_personas:
        return {
            'ai_response': "There are no personas available in this scene to respond to your @all message.",
            'persona_name': "ChatOrchestrator",
            'persona_id': None,
            'responses': []
        }
    
    # Execute all persona responses in parallel
    if orchestrator.langchain_enabled:
        try:
            tasks = []
            for persona in scene_personas:
                persona_db_id = persona.get('db_id')
                persona_simulation_id = persona.get('id')
                if persona_db_id and persona_simulation_id:
                    tasks.append(
                        orchestrator.chat_with_persona_langchain(
                            message=message,
                            persona_id=persona_simulation_id,
                            scene_id=scene_id
                        )
                    )
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            all_responses = []
            for i, response in enumerate(responses):
                if isinstance(response, Exception):
                    all_responses.append({
                        'persona_name': scene_personas[i]['identity']['name'],
                        'persona_id': scene_personas[i].get('db_id'),
                        'response': "I'm sorry, I'm having trouble processing that right now."
                    })
                else:
                    all_responses.append({
                        'persona_name': scene_personas[i]['identity']['name'],
                        'persona_id': scene_personas[i].get('db_id'),
                        'response': response
                    })
            
            return {
                'ai_response': "",  # Will be handled separately
                'persona_name': "All Personas",
                'persona_id': None,
                'responses': all_responses,
                'personas_count': len(scene_personas)
            }
        except Exception as e:
            if _is_dev:
                import traceback
                traceback.print_exc()
            return {
                'ai_response': "I'm sorry, I'm having trouble processing the @all message right now. Please try again.",
                'persona_name': "ChatOrchestrator",
                'persona_id': None,
                'responses': []
            }
    else:
        return {
            'ai_response': "I'm sorry, the @all feature requires LangChain integration which is not available right now.",
            'persona_name': "ChatOrchestrator",
            'persona_id': None,
            'responses': []
        }


async def handle_mention(
    orchestrator: ChatOrchestrator,
    message: str,
    persona_id: str,
    scene_id: int
) -> Dict[str, Any]:
    """
    Handle @mention to a specific persona.
    
    Args:
        orchestrator: ChatOrchestrator instance
        message: User message with @mention
        persona_id: Mentioned persona ID (from regex)
        scene_id: Current scene ID
        
    Returns:
        Dictionary with ai_response, persona_name, persona_id
    """
    # Build name mapping for persona lookup
    import re
    name_mapping = {}
    for persona in orchestrator.simulation.get('personas', []):
        # Simulation-level ID/handle (e.g., "nick_elliott")
        persona_id_value = str(persona.get('id', '')).lower()
        if persona_id_value:
            name_mapping[persona_id_value] = persona['id']

        # Human-readable identity name (e.g., "Nick Elliott")
        name = persona['identity']['name'].lower()
        name_mapping[name] = persona['id']
        name_mapping[name.replace("'", "").replace(" ", "_")] = persona['id']
        name_mapping[name.replace("'", "").replace(" ", "")] = persona['id']
        # Sanitized version: remove all special chars (parentheses, dots, etc.)
        sanitized_name = re.sub(r'[^a-z0-9_]', '', name.replace(' ', '_'))
        name_mapping[sanitized_name] = persona['id']
        first_name = name.split()[0]
        name_mapping[first_name] = persona['id']
        name_mapping[first_name.replace("'", "")] = persona['id']
        # Sanitized first name
        sanitized_first = re.sub(r'[^a-z0-9_]', '', first_name)
        name_mapping[sanitized_first] = persona['id']
    
    search_name = persona_id.lower()
    target_persona = None
    
    if search_name in name_mapping:
        persona_id = name_mapping[search_name]
        target_persona = next((p for p in orchestrator.simulation.get('personas', []) if p['id'] == persona_id), None)
    else:
        # Try fuzzy matching
        for name, pid in name_mapping.items():
            if (search_name in name or name in search_name or
                search_name.replace("'", "").replace("_", "") in name.replace("'", "").replace("_", "")):
                persona_id = pid
                target_persona = next((p for p in orchestrator.simulation.get('personas', []) if p['id'] == persona_id), None)
                break
    
    if target_persona:
        if orchestrator.langchain_enabled:
            try:
                ai_response = await orchestrator.chat_with_persona_langchain(
                    message=message,
                    persona_id=persona_id,
                    scene_id=scene_id
                )
                return {
                    'ai_response': ai_response,
                    'persona_name': target_persona['identity']['name'],
                    'persona_id': target_persona.get('db_id')
                }
            except Exception as e:
                import logging
                import traceback
                logger = logging.getLogger(__name__)
                error_msg = str(e)
                logger.error(f"Error in chat_with_persona_langchain for persona {persona_id}: {error_msg}")
                if _is_dev:
                    traceback.print_exc()
                return {
                    'ai_response': f"I'm sorry, I'm having trouble processing that right now. Please try again or ask the orchestrator for help. (Error: {error_msg})",
                    'persona_name': "ChatOrchestrator",
                    'persona_id': None
                }
        else:
            return {
                'ai_response': "I'm sorry, the persona interaction system is not available right now. Please try again later.",
                'persona_name': "ChatOrchestrator",
                'persona_id': None
            }
    else:
        available = [
            f"@{p['id']}" for p in orchestrator.simulation.get('personas', [])
        ]
        return {
            'ai_response': (
                "I don't recognize that persona. "
                f"Available team members: {', '.join(available)}. "
                "Please use @mentions like @nick_elliott to talk to specific team members."
            ),
            'persona_name': "ChatOrchestrator",
            'persona_id': None
        }
