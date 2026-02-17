"""
AI extraction service for PDF processing using OpenAI.
Extracted from api/parse_pdf.py
"""
import asyncio
import json
import re
import logging
import openai
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from common.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

OPENAI_API_KEY = getattr(settings, 'openai_api_key', None)

# Performance optimization constants
MAX_CONCURRENT_OPENAI = 2  # Limit concurrent OpenAI requests

# Thread pool for CPU-bound operations
CPU_EXECUTOR = ThreadPoolExecutor(max_workers=4)

# Global semaphore for OpenAI requests
_openai_semaphore = asyncio.Semaphore(MAX_CONCURRENT_OPENAI)


class AIExtractionService:
    """Service for extracting information from PDF content using OpenAI"""
    
    def __init__(self):
        self.api_key = OPENAI_API_KEY
        self.client = openai.OpenAI(api_key=self.api_key) if self.api_key else None

    def _get_message_content(self, response: Any, context: str, fallback: Optional[str] = None) -> str:
        """Safely extract OpenAI message content."""
        try:
            choice = response.choices[0]
            message = choice.message
        except Exception as exc:
            logger.error(f"[AI_ERROR] {context} missing response choices: {exc}")
            raise ValueError(f"{context} failed: missing response choices")

        content = getattr(message, "content", None)
        if not content:
            finish_reason = getattr(choice, "finish_reason", None)
            refusal = getattr(message, "refusal", None)
            logger.error(
                f"[AI_ERROR] {context} returned empty content "
                f"(finish_reason={finish_reason}, refusal={refusal})"
            )
            if fallback is not None:
                logger.warning(f"[AI_ERROR] Using fallback content for {context}")
                return fallback
            raise ValueError(f"{context} failed: OpenAI returned empty content")

        return content

    def _filter_student_role_from_key_figures(self, result: Dict[str, Any], context_label: str = "FILTER") -> Dict[str, Any]:
        """Filter out the student/protagonist role from key_figures."""
        student_role = (result.get("student_role") or "").lower()
        if not student_role or "key_figures" not in result:
            return result

        logger.info(f"[{context_label}] Filtering out student role '{student_role}' from key_figures")
        original_count = len(result["key_figures"])
        filtered_figures = []

        for figure in result["key_figures"]:
            figure_name = (figure.get("name") or "").lower()
            figure_role = (figure.get("role") or "").lower()
            is_student_role = False

            student_role_parts = re.match(r'([^(]+)(?:\s*\(([^)]+)\))?', student_role)
            if student_role_parts:
                student_name = student_role_parts.group(1).strip().lower()
                student_title = (student_role_parts.group(2) or "").strip().lower()

                if student_name and (student_name in figure_name or figure_name in student_name):
                    is_student_role = True
                    logger.info(f"[{context_label}] Filtering out '{figure.get('name')}' - matches student name '{student_name}'")
                elif student_title and (student_title in figure_role or figure_role in student_title):
                    is_student_role = True
                    logger.info(f"[{context_label}] Filtering out '{figure.get('name')}' - role '{figure_role}' matches student title '{student_title}'")

            if student_role in figure_name or figure_name in student_role:
                is_student_role = True
            elif student_role in figure_role or figure_role in student_role:
                is_student_role = True

            # Backward compatibility for occasional legacy outputs.
            if figure.get("is_main_character"):
                is_student_role = True
                logger.info(f"[{context_label}] Filtering out '{figure.get('name')}' - marked as main character")

            if not is_student_role:
                filtered_figures.append(figure)

        result["key_figures"] = filtered_figures
        logger.info(f"[{context_label}] Filtered {original_count} -> {len(filtered_figures)} personas")
        return result
    
    def preprocess_content(self, raw_content: str) -> dict:
        """Pre-process the parsed content to extract clean case study information"""
        logger.info("[PREPROCESSING] Pre-processing case study content")
        
        # If content is a dict with markdown, extract the markdown
        if isinstance(raw_content, dict) and "markdown" in raw_content:
            content = raw_content["markdown"]
        elif isinstance(raw_content, str):
            # Check if it's a JSON string with markdown
            try:
                parsed_json = json.loads(raw_content)
                if isinstance(parsed_json, dict) and "markdown" in parsed_json:
                    content = parsed_json["markdown"]
                else:
                    content = raw_content
            except (json.JSONDecodeError, TypeError):
                content = raw_content
        else:
            content = raw_content
        
        logger.info(f"[PREPROCESSING] Raw content length: {len(content)}")
        
        # Clean up formatting artifacts
        content = content.replace('  ', ' ')  # Remove double spaces
        content = content.replace(' \n', '\n')  # Remove trailing spaces
        content = content.replace('\n ', '\n')  # Remove leading spaces
        
        # Split into lines and process
        lines = content.split('\n')
        cleaned_lines = []
        title = None
        
        # First pass: extract title from markdown headers
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Look for markdown headers (e.g., "# Title")
            if line.startswith('# '):
                title = line.replace('# ', '').strip()
                logger.info(f"[PREPROCESSING] Found title in markdown header: {title}")
                break
        
        # If no title found in headers, look for the first meaningful line
        if not title:
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Skip metadata and formatting artifacts
                if any(skip_pattern in line.upper() for skip_pattern in [
                    'HARVARD BUSINESS SCHOOL', 'REV:', 'PAGE', '©', 'COPYRIGHT', 'ALL RIGHTS RESERVED',
                    'DOCUMENT ID:', 'FILE:', 'CREATED:', 'MODIFIED:', '9-', 'R E V :'
                ]):
                    continue
                    
                # Skip lines that are just numbers, dates, or formatting
                if re.match(r'^[\d\s\-\.]+$', line):  # Just numbers, spaces, dashes, dots
                    continue
                    
                # Skip very short lines or all-uppercase lines
                if len(line) < 5 or line.isupper():
                    continue
                    
                # This looks like a title
                title = line
                logger.info(f"[PREPROCESSING] Found title in content: {title}")
                break
        
        # Fallback title
        if not title:
            title = "Business Case Study"

        # Clean content (only remove obvious metadata)
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Skip only the most obvious metadata lines
            if any(skip_pattern in line.upper() for skip_pattern in [
                'COPYRIGHT ENCODED', 'DOCUMENT ID:', 'FILE:', 'CREATED:', 'MODIFIED:', 
                'AUTHORIZED FOR USE ONLY', 'THIS DOCUMENT IS FOR USE ONLY BY'
            ]):
                continue
                
            # Skip lines that are just formatting artifacts
            if len(line) == 0 or re.match(r'^[\s\-\_\.]+$', line):
                continue
                
            # Keep everything else
            cleaned_lines.append(line)
        
        cleaned_content = '\n'.join(cleaned_lines)
        
        logger.info(f"[PREPROCESSING] Extracted title: {title}")
        logger.info(f"[PREPROCESSING] Cleaned content length: {len(cleaned_content)}")
        
        return {
            "title": title,
            "cleaned_content": cleaned_content
        }
    
    async def extract_personas_fast(self, content: str, title: str) -> dict:
        """Fast persona extraction with minimal AI call for autofill"""
        logger.info("[FAST_AI] Starting fast persona extraction...")
        
        if not self.client:
            error_msg = "OpenAI API key is not configured. Please set OPENAI_API_KEY environment variable."
            logger.error(f"[FAST_AI_ERROR] {error_msg}")
            raise ValueError(error_msg)
        
        prompt = f"""You are a JSON-only generator extracting realistic personas for a business simulation.

CRITICAL CONTENT REQUIREMENTS:
- Use ONLY information explicitly stated in the case study.
- Do NOT invent names, facts, or relationships.
- If a field is unsupported, use a minimal neutral value and avoid adding new facts.

REALISM REQUIREMENT:
- Personas must feel human and role-authentic, not generic templates.
- Goals should reflect real tensions, incentives, constraints, and tradeoffs in the case.
- Communication style and assumptions should be consistent with role seniority and context.

STUDENT ROLE IDENTIFICATION:
- Identify the MAIN CHARACTER/PROTAGONIST who makes key decisions.
- If a clear protagonist exists, set that as "student_role".
- If none is explicit, default to "Business Analyst".

KEY_FIGURES RULE:
- key_figures are NPC personas the student interacts with.
- DO NOT include the student_role character in key_figures.
- Do not output an "is_main_character" field.

PERSONA OUTPUT REQUIREMENTS:
Each persona must include the following:
- PERSONA NAME: full name and title exactly as stated.
- ROLE: their role/title in the organization or case.
- BACKGROUND: summarize professional role, experience, and organizational context.
- CURRENT CONTEXT: current responsibilities, challenges, and perspective related to the case.
- CORRELATION: relationship to the protagonist (student role).
- PERSONALITY TRAITS (OCEAN 1-10):
  - openness, conscientiousness, extraversion, agreeableness, neuroticism
- PRIMARY GOALS: 3-5 concise, decision-driving goals.
- KNOWLEDGE AREAS: concrete details, facts, data, or domain knowledge this persona knows.
- COMMUNICATION STYLE: how they communicate (formal, persuasive, data-driven, pragmatic, etc.).
- DEFAULT ASSUMPTIONS AND BIASES: known attitudes or assumptions they hold in this context.

SCHEMA FIELD DESCRIPTIONS:
- title: exact case study title as stated; if missing, a faithful descriptive title.
- description: 2-4 paragraphs covering business context, challenges, stakeholders, and decision implications.
- student_role: the specific role the student will assume.
- key_figures: list of persona objects, excluding the student_role character.
- key_figures[].name: full name and title as stated in the case.
- key_figures[].role: role/title within the organization or narrative.
- key_figures[].background: professional role, experience, and organizational context.
- key_figures[].current_context: current responsibilities, challenges, and perspective in the case.
- key_figures[].correlation: relationship to the protagonist (student role).
- key_figures[].primary_goals: 3-5 concise decision-driving goals.
- key_figures[].personality_traits: OCEAN scores 1-10.
- key_figures[].knowledge_areas: key details, facts, or domain knowledge they know from the original case study.
- key_figures[].communication_style: how they communicate.
- key_figures[].assumptions_biases: default assumptions or biases in this context.

OUTPUT FORMAT (JSON ONLY):
{{
  "title": "<Exact case study title>",
  "description": "<2-4 paragraphs describing the business context, challenges, stakeholders, and decision implications>",
  "student_role": "<Specific role the student will assume>",
  "key_figures": [
    {{
      "name": "<Full name or descriptive title>",
      "role": "<Role/title>",
      "background": "<Professional role, experience, and organizational context>",
      "current_context": "<Current responsibilities, challenges, and perspective>",
      "correlation": "<Relationship to the protagonist>",
      "primary_goals": ["<Goal 1>", "<Goal 2>", "<Goal 3>", "<Goal 4>", "<Goal 5>"],
      "personality_traits": {{
        "openness": <1-10>,
        "conscientiousness": <1-10>,
        "extraversion": <1-10>,
        "agreeableness": <1-10>,
        "neuroticism": <1-10>
      }},
      "knowledge_areas": ["<Key detail 1>", "<Key detail 2>", "<Key detail 3>"],
      "communication_style": "<Formal, persuasive, data-driven, pragmatic, etc.>",
      "assumptions_biases": ["<Assumption/Bias 1>", "<Assumption/Bias 2>", "<Assumption/Bias 3>"]
    }}
  ]
}}

CONTENT:
{content[:2000]}...
"""
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a JSON generator for business case study analysis. Create detailed descriptions with specific information, numbers, and context. Be thorough and informative."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000,
                    temperature=0.1,
                )
            )
            
            generated_text = self._get_message_content(response, "Fast persona extraction", "{}")
            
            # Extract JSON from response
            match = re.search(r'({[\s\S]*})', generated_text)
            if match:
                json_str = match.group(1)
                result = json.loads(json_str)
                result = self._filter_student_role_from_key_figures(result, "FAST_FILTER")
                logger.info(f"[FAST_AI] Extracted student_role: {result.get('student_role', 'NOT_FOUND')}")
                return result
            else:
                logger.info("[FAST_AI] No JSON found in response")
                raise ValueError("Failed to extract JSON from AI response")
                
        except Exception as e:
            logger.info(f"[FAST_AI_ERROR] {str(e)}")
            raise
    
    async def extract_personas_and_key_figures(
        self, 
        combined_content: str, 
        title: str, 
        session_id: Optional[str] = None
    ) -> dict:
        """Extract personas and key figures using OpenAI with high-quality prompts"""
        logger.info("[AI] Starting persona extraction...")
        
        if not self.client:
            error_msg = "OpenAI API key is not configured. Please set OPENAI_API_KEY environment variable."
            logger.error(f"[AI_ERROR] {error_msg}")
            raise ValueError(error_msg)
        
        # Validate content before processing
        if not combined_content or combined_content.strip() == "":
            logger.info("[AI] ERROR: Content is empty, cannot extract personas")
            raise ValueError("Content is empty, cannot extract personas")
        
        # Log content preview for debugging
        content_preview = combined_content[:500] + "..." if len(combined_content) > 500 else combined_content
        logger.info(f"[AI] Content preview: {content_preview}")
        logger.info(f"[AI] Content length: {len(combined_content)} characters")
        
        prompt = f"""You are a JSON-only generator extracting personas for a business simulation. Your job is to be precise, grounded in the text, and exhaustive about key figures.

CRITICAL CONTENT REQUIREMENT:
- Use ONLY information explicitly stated in the case study.
- Do NOT invent names, facts, or relationships.
- If a field is not supported by the text, provide a minimal neutral value that does not add new facts.

REALISM REQUIREMENT:
- Personas must feel human and role-authentic, not generic templates.
- Goals should reflect real tensions, incentives, constraints, and tradeoffs in the case.
- Communication style and assumptions should be consistent with role seniority and context.

STUDENT ROLE IDENTIFICATION:
- Find the MAIN CHARACTER/PROTAGONIST who is making decisions.
- If a clear protagonist exists, the student should play that character.
- If no protagonist is explicit, default to "Business Analyst".
- The student role MUST NOT appear in key_figures.

KEY_FIGURES IDENTIFICATION:
- Identify ALL named individuals, companies, organizations, and significant unnamed roles in the narrative.
- Include brief mentions if they have a discernible role or influence.
- key_figures represent NPCs that the student will interact with.

EXCLUSION RULE (IMPORTANT):
- Do NOT include the student role character in key_figures.
- Do not output an "is_main_character" field.

PERSONA OUTPUT REQUIREMENTS:
Each persona must include the following:
- PERSONA NAME: full name and title exactly as stated.
- ROLE: their role/title in the organization or case.
- BACKGROUND: summarize professional role, experience, and organizational context.
- CORRELATION: relationship to the protagonist (student role).
- PERSONALITY TRAITS (OCEAN 1-10): openness, conscientiousness, extraversion, agreeableness, neuroticism
- PRIMARY GOALS: 3-5 concise, decision-driving goals.

OUTPUT FORMAT (JSON ONLY):
{{
  "title": "<Exact case study title>",
  "description": "<2-4 paragraphs describing the business context, challenges, stakeholders, and decision implications>",
  "student_role": "<Specific role the student will assume>",
  "key_figures": [
    {{
      "name": "<Full name or descriptive title>",
      "role": "<Role/title>",
      "background": "<2-3 sentence background>",
      "correlation": "<Relationship to the protagonist>",
      "primary_goals": ["<Goal 1>", "<Goal 2>", "<Goal 3>"],
      "personality_traits": {{
        "openness": <1-10>,
        "conscientiousness": <1-10>,
        "extraversion": <1-10>,
        "agreeableness": <1-10>,
        "neuroticism": <1-10>
      }}
    }}
  ]
}}

CASE STUDY CONTENT:
{combined_content}
"""
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a JSON generator for business case study analysis. Focus on creating comprehensive, detailed descriptions that give students complete context."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=12000,
                    temperature=0.2,
                )
            )
            
            generated_text = self._get_message_content(response, "Persona extraction", "{}")
            
            # Extract JSON from response
            match = re.search(r'({[\s\S]*})', generated_text)
            if match:
                json_str = match.group(1)
                result = json.loads(json_str)
                result = self._filter_student_role_from_key_figures(result, "FILTER")
                
                # Validate that key_figures exist
                if "key_figures" not in result or not result["key_figures"]:
                    logger.info("[WARNING] No key_figures found in AI response, adding fallback personas")
                    result["key_figures"] = [
                        {
                            "name": "Business Manager",
                            "role": "Manager",
                            "correlation": "Key stakeholder in the business scenario",
                            "background": "Experienced business professional involved in the case study.",
                            "primary_goals": ["Achieve business objectives", "Make informed decisions", "Drive results"],
                            "personality_traits": {
                                "openness": 5,
                                "conscientiousness": 7,
                                "extraversion": 5,
                                "agreeableness": 6,
                                "neuroticism": 4
                            }
                        }
                    ]
                
                logger.info(f"[SUCCESS] Persona extraction returned {len(result.get('key_figures', []))} personas")
                return result
            else:
                logger.info("[WARNING] No JSON found in persona extraction response")
                raise ValueError("Failed to extract personas: No JSON found in AI response")
                
        except Exception as e:
            logger.info(f"[ERROR] Persona extraction failed: {str(e)}")
            raise
    
    async def generate_scenes(
        self, 
        combined_content: str, 
        title: str, 
        session_id: Optional[str] = None, 
        personas_result: Optional[dict] = None
    ) -> list:
        """Generate scenes using OpenAI with high-quality prompts"""
        logger.info("[AI] Starting scene generation...")
        
        if not self.client:
            error_msg = "OpenAI API key is not configured. Please set OPENAI_API_KEY environment variable."
            logger.error(f"[AI_ERROR] {error_msg}")
            raise ValueError(error_msg)
        
        # Validate content before processing
        if not combined_content or combined_content.strip() == "":
            logger.info("[AI] ERROR: Content is empty, cannot generate scenes")
            raise ValueError("Content is empty, cannot generate scenes")
        
        # Get available personas for scene generation
        available_personas = []
        student_role = ""
        if personas_result and personas_result.get("key_figures"):
            available_personas = [persona.get("name", "") for persona in personas_result["key_figures"] if persona.get("name")]
        if personas_result and personas_result.get("student_role"):
            student_role = personas_result.get("student_role")
        
        logger.info(f"[AI] Available personas for scenes: {available_personas}")
        logger.info(f"[AI] Student role: {student_role}")
        
        prompt = f"""Create exactly 4 interactive scenes for this business case study. Output ONLY a JSON array of scenes.

CASE CONTEXT:
Title: {title}
Content: {combined_content[:2000]}...

STUDENT ROLE: {student_role if student_role else "Business Analyst"}

AVAILABLE PERSONAS (use ONLY these names in personas_involved):
{', '.join(available_personas) if available_personas else "No specific personas identified"}

⚠️ CRITICAL: DO NOT include the student role character in personas_involved arrays ⚠️

Create 4 scenes following this progression:
1. Crisis Assessment/Initial Briefing
2. Investigation/Analysis Phase  
3. Solution Development
4. Implementation/Approval

Each scene MUST have:
- title: Short descriptive name
- description: 2-3 sentences with vivid setting details for image generation
- personas_involved: Array of 2-4 persona names from the AVAILABLE PERSONAS list above
- user_goal: Specific objective the student must achieve
- sequence_order: 1, 2, 3, or 4
- goal: General summary of what to accomplish
- success_metric: Clear, measurable success criteria

Output format - ONLY this JSON array:
[
  {{
    "title": "Scene Title",
    "description": "Detailed setting description...",
    "personas_involved": ["Persona Name 1", "Persona Name 2"],
    "user_goal": "Specific actionable goal",
    "goal": "General summary",
    "success_metric": "Specific criteria",
    "sequence_order": 1
  }},
  ...4 scenes total
]
"""
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You generate JSON arrays of scenes. Output ONLY valid JSON array, no extra text."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=2048,
                    temperature=0.3,
                )
            )
            
            scenes_text = self._get_message_content(response, "Scene generation", "[]").strip()
            logger.info(f"[AI] Scenes AI response: {scenes_text[:200]}...")
            
            # Extract JSON array from response
            json_match = re.search(r'(\[[\s\S]*\])', scenes_text)
            if json_match:
                scenes_json = json_match.group(1)
                scenes = json.loads(scenes_json)
                logger.info(f"[SUCCESS] Generated {len(scenes)} scenes")
                
                # Post-process: Filter out student role from personas_involved
                if student_role:
                    logger.info(f"[FILTER] Post-processing scenes to remove student role: {student_role}")
                    
                    def normalize_name(name):
                        """Normalize name for comparison"""
                        if not name:
                            return ""
                        normalized = name.strip()
                        # Remove title prefixes
                        normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.)\s+', '', normalized, flags=re.IGNORECASE)
                        # Remove non-alphabetic characters
                        normalized = re.sub(r'[^a-zA-Z]', '', normalized).lower()
                        return normalized
                    
                    student_name = student_role.split('(')[0].strip()
                    student_name_normalized = normalize_name(student_name)
                    
                    for scene in scenes:
                        if "personas_involved" in scene and isinstance(scene["personas_involved"], list):
                            original_personas = scene["personas_involved"]
                            filtered_personas = [
                                persona for persona in original_personas 
                                if normalize_name(persona) != student_name_normalized
                            ]
                            scene["personas_involved"] = filtered_personas
                            if len(original_personas) != len(filtered_personas):
                                logger.info(f"[FILTER] Scene '{scene.get('title')}': {len(original_personas)} -> {len(filtered_personas)} personas")
                
                return scenes
            else:
                logger.info("[WARNING] No JSON array found in scenes response")
                raise ValueError("Failed to extract scenes: No JSON array found in AI response")
                
        except Exception as e:
            logger.info(f"[ERROR] Scene generation failed: {str(e)}")
            raise
    
    async def generate_learning_outcomes(
        self, 
        combined_content: str, 
        title: str, 
        session_id: Optional[str] = None
    ) -> list:
        """Generate learning outcomes using OpenAI with high-quality prompts"""
        logger.info("[AI] Starting learning outcomes generation...")
        
        if not self.client:
            error_msg = "OpenAI API key is not configured. Please set OPENAI_API_KEY environment variable."
            logger.error(f"[AI_ERROR] {error_msg}")
            raise ValueError(error_msg)
        
        prompt = f"""Generate exactly 5 learning outcomes for this business case study. Output ONLY a JSON array of learning outcomes.

CASE CONTEXT:
Title: {title}
Content: {combined_content[:1500]}...

Create 5 learning outcomes that are:
- Specific and measurable
- Relevant to business education
- Aligned with the case study content
- Progressive in complexity

Output format - ONLY this JSON array:
[
  "1. <Outcome 1>",
  "2. <Outcome 2>",
  "3. <Outcome 3>",
  "4. <Outcome 4>",
  "5. <Outcome 5>"
]
"""
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You generate JSON arrays of learning outcomes. Output ONLY valid JSON array, no extra text."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                )
            )
            
            outcomes_text = self._get_message_content(response, "Learning outcomes generation", "[]").strip()
            logger.info(f"[AI] Learning outcomes AI response: {outcomes_text[:200]}...")
            
            # Extract JSON array from response
            json_match = re.search(r'(\[[\s\S]*\])', outcomes_text)
            if json_match:
                outcomes_json = json_match.group(1)
                outcomes = json.loads(outcomes_json)
                logger.info(f"[SUCCESS] Generated {len(outcomes)} learning outcomes")
                return outcomes
            else:
                logger.info("[WARNING] No JSON array found in learning outcomes response")
                raise ValueError("Failed to extract learning outcomes: No JSON array found in AI response")
                
        except Exception as e:
            logger.info(f"[ERROR] Learning outcomes generation failed: {str(e)}")
            raise


# Global AI extraction service instance
ai_extraction_service = AIExtractionService()
