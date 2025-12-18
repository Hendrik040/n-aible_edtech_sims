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
        
        prompt = f"""You are a JSON generator for business case study analysis. Extract key information quickly.

STUDENT ROLE IDENTIFICATION:
For the "student_role" field, determine what role the student should assume in this simulation. This could be:
- A specific character from the case study (e.g., "The CEO", "The Marketing Manager", "The Founder")
- A business role/position (e.g., "Business Analyst", "Consultant", "Strategic Advisor", "Investment Analyst")
- A stakeholder role (e.g., "Board Member", "Investor", "Customer Representative")
- A decision-maker role (e.g., "Project Manager", "Operations Director", "Financial Controller")

PRIORITY: Look for the MAIN CHARACTER or PROTAGONIST of the case study first. If there's a clear main character who is the central figure making decisions, the student should play that character.

Look for clues in the case study such as:
- The main character's name and title (e.g., "John Smith, CEO of...")
- "You are [character name]" or "You play the role of [character]"
- "As [character name], you must..."
- "Students are asked to step into the shoes of [character]"
- "You are asked to..." or "Students are tasked with..."
- "As a [role], you must..."
- "Your role is to..."
- "You have been hired as..."
- "You are the [position] and must decide..."

If there's a clear main character/protagonist, use their name and title (e.g., "John Smith (CEO of Company Name)").
If no specific character is mentioned, default to "Business Analyst" as it's a common role for case study analysis.

CRITICAL CONTENT REQUIREMENT: You MUST base your analysis ONLY on the actual content provided. Do NOT make up or hallucinate information that is not explicitly stated in the content. If the content appears to be corrupted or contains placeholder text, still attempt to extract any meaningful information that is present.

Return JSON with:
{{
  "title": "<exact title - if not available, create a meaningful business case title>",
  "description": "<A comprehensive, detailed background description (5-7 paragraphs) covering: business context, challenges, stakeholders, financial details, market dynamics, and decision implications. Include specific numbers, dates, and examples. If content is limited, create a realistic business scenario.>",
  "student_role": "<specific role the student will assume>",
  "key_figures": [
    {{
      "name": "<name or title>",
      "role": "<their role>",
      "correlation": "<relationship to narrative>",
      "background": "<2-3 sentence background>",
      "primary_goals": ["<goal1>", "<goal2>", "<goal3>"],
      "personality_traits": {{
        "analytical": <0-10>,
        "creative": <0-10>,
        "assertive": <0-10>,
        "collaborative": <0-10>,
        "detail_oriented": <0-10>
      }}
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
            
            generated_text = response.choices[0].message.content
            
            # Extract JSON from response
            match = re.search(r'({[\s\S]*})', generated_text)
            if match:
                json_str = match.group(1)
                result = json.loads(json_str)
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
        
        prompt = f"""You are a highly structured JSON-only generator trained to analyze business case studies for college business education.

CRITICAL: You must identify ALL named individuals, companies, organizations, and significant unnamed roles mentioned within the case study narrative.

Instructions for key_figures identification:
- Find ALL types of key figures that can be turned into personas
- Include both named and unnamed entities that are part of the business story
- Even if someone/thing is mentioned only once or briefly, include them if they have a discernible role

⚠️ CRITICAL EXCLUSION RULE ⚠️
DO NOT include the student role character in the key_figures array. This means:
- If the student will play "John Smith (CEO)", do NOT create a key_figure for "John Smith"
- The student role character is the PROTAGONIST that the student will control
- Mark "is_main_character": true ONLY for the figure that matches the student_role (this helps us filter them out)
- Remember: key_figures are NPCs (non-player characters) that the student will interact with during the simulation

STUDENT ROLE IDENTIFICATION:
Look for the MAIN CHARACTER or PROTAGONIST of the case study first. If there's a clear main character who is the central figure making decisions, the student should play that character.

If there's a clear main character/protagonist, use their name and title (e.g., "John Smith (CEO of Company Name)").
If no specific character is mentioned, default to "Business Analyst" as it's a common role for case study analysis.

CRITICAL CONTENT REQUIREMENT: You MUST base your analysis ONLY on the actual content provided.

Your task is to analyze the following business case study content and return a JSON object with exactly the following fields:
  "title": "<The exact title of the business case study>",
  "description": "<A comprehensive, detailed background description (2-4 paragraphs) covering the business context, challenges, stakeholders, and decision implications>",
  "student_role": "<The specific role the student will assume>",
  "key_figures": [
    {{
      "name": "<Full name or descriptive title>",
      "role": "<Their role>",
      "correlation": "<Relationship to the narrative>",
      "background": "<2-3 sentence background>",
      "primary_goals": ["<Goal 1>", "<Goal 2>", "<Goal 3>"],
      "personality_traits": {{
        "analytical": <0-10>,
        "creative": <0-10>,
        "assertive": <0-10>,
        "collaborative": <0-10>,
        "detail_oriented": <0-10>
      }},
      "is_main_character": <true if this figure matches the student_role, otherwise false>
    }}
  ]

Output ONLY a valid JSON object. Do not include any extra commentary.

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
            
            generated_text = response.choices[0].message.content
            
            # Extract JSON from response
            match = re.search(r'({[\s\S]*})', generated_text)
            if match:
                json_str = match.group(1)
                result = json.loads(json_str)
                
                # Filter out the student role from key_figures
                student_role = result.get("student_role", "").lower()
                if student_role and "key_figures" in result:
                    logger.info(f"[FILTER] Filtering out student role '{student_role}' from key_figures")
                    original_count = len(result["key_figures"])
                    
                    filtered_figures = []
                    for figure in result["key_figures"]:
                        figure_name = (figure.get("name") or "").lower()
                        figure_role = (figure.get("role") or "").lower()
                        
                        # Check if this figure matches the student role
                        is_student_role = False
                        
                        # Extract name from student_role if it's in format "Name (Title)"
                        student_role_parts = re.match(r'([^(]+)(?:\s*\(([^)]+)\))?', student_role)
                        if student_role_parts:
                            student_name = student_role_parts.group(1).strip().lower()
                            student_title = (student_role_parts.group(2) or "").strip().lower()
                            
                            # Check if figure name matches student name or student title
                            if student_name and (student_name in figure_name or figure_name in student_name):
                                is_student_role = True
                                logger.info(f"[FILTER] Filtering out '{figure.get('name')}' - matches student name '{student_name}'")
                            elif student_title and (student_title in figure_role or figure_role in student_title):
                                is_student_role = True
                                logger.info(f"[FILTER] Filtering out '{figure.get('name')}' - role '{figure_role}' matches student title '{student_title}'")
                        
                        # Check for exact or partial matches with student_role
                        if student_role in figure_name or figure_name in student_role:
                            is_student_role = True
                        elif student_role in figure_role or figure_role in student_role:
                            is_student_role = True
                        
                        # Check is_main_character flag
                        if figure.get("is_main_character"):
                            is_student_role = True
                            logger.info(f"[FILTER] Filtering out '{figure.get('name')}' - marked as main character")
                        
                        if not is_student_role:
                            filtered_figures.append(figure)
                    
                    result["key_figures"] = filtered_figures
                    logger.info(f"[FILTER] Filtered {original_count} -> {len(filtered_figures)} personas")
                
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
                                "analytical": 7,
                                "creative": 5,
                                "assertive": 6,
                                "collaborative": 7,
                                "detail_oriented": 8
                            },
                            "is_main_character": False
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
            
            scenes_text = response.choices[0].message.content.strip()
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
            
            outcomes_text = response.choices[0].message.content.strip()
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
