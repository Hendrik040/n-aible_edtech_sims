from __future__ import annotations

from typing import Any, Dict

from ._types import SimulationPersonaProtocol

# ─── Big Five behavioral descriptors ─────────────────────────────────────────
_BIG_FIVE_DESCRIPTORS: Dict[str, Dict[str, str]] = {
    "openness": {
        "very low":  "very conventional and practical; resistant to novel or unconventional approaches",
        "low":       "prefers established methods; cautious about new ideas unless well-evidenced",
        "moderate":  "reasonably open-minded; will consider new perspectives when they are well-supported",
        "high":      "curious and imaginative; actively seeks fresh ideas and approaches",
        "very high": "highly creative and intellectually adventurous; thrives on unconventional thinking",
    },
    "conscientiousness": {
        "very low":  "spontaneous and flexible; tends to be disorganized or impulsive under pressure",
        "low":       "easy-going about structure; may miss details or deadlines",
        "moderate":  "reasonably organized and reliable; balances structure with flexibility",
        "high":      "diligent, thorough, and goal-driven; follows through on commitments",
        "very high": "exceptionally organized and detail-focused; holds self and others to high standards",
    },
    "extraversion": {
        "very low":  "deeply reserved and introspective; thinks carefully before speaking",
        "low":       "prefers one-on-one conversations; not naturally expressive in groups",
        "moderate":  "comfortable in both social and independent settings; adapts to the room",
        "high":      "energetic and expressive; engaged and assertive in group discussions",
        "very high": "highly sociable, enthusiastic, and commanding in any room",
    },
    "agreeableness": {
        "very low":  "direct, competitive, and skeptical; prioritizes outcomes over harmony",
        "low":       "pragmatic and candid; willing to challenge others when necessary",
        "moderate":  "cooperative but capable of holding firm positions when needed",
        "high":      "empathetic and collaborative; strongly values consensus and goodwill",
        "very high": "deeply accommodating; prioritizes relationships and avoids conflict",
    },
    "neuroticism": {
        "very low":  "exceptionally calm and emotionally stable; difficult to rattle",
        "low":       "generally composed; handles pressure well without overreacting",
        "moderate":  "occasionally stressed; manages emotions reasonably under normal pressure",
        "high":      "prone to worry or tension; may show stress or anxiety in difficult moments",
        "very high": "emotionally reactive under pressure; experiences significant anxiety or frustration",
    },
}


def _big_five_score_to_level(score: int) -> str:
    if score <= 2:
        return "very low"
    elif score <= 4:
        return "low"
    elif score <= 6:
        return "moderate"
    elif score <= 8:
        return "high"
    else:
        return "very high"


def _describe_personality_traits(traits: Dict[str, Any]) -> str:
    if not traits:
        return "No personality traits specified."

    lines: list[str] = []
    for trait, score in traits.items():
        try:
            score_int = int(score)
        except (TypeError, ValueError):
            continue
        if not 0 <= score_int <= 10:
            continue

        level = _big_five_score_to_level(score_int)
        descriptors = _BIG_FIVE_DESCRIPTORS.get(trait.lower())
        if descriptors:
            description = descriptors.get(level, "")
            lines.append(f"- {trait.title()} ({score_int}/10 \u2014 {level}): {description}")
        else:
            lines.append(f"- {trait.title()}: {score_int}/10")

    return "\n".join(lines) if lines else "No personality traits specified."


def build_persona_system_prompt(
    persona: SimulationPersonaProtocol,
    scene_context: dict,
) -> str:
    """Build a complete system prompt from persona fields and scene context.

    Returns a deterministic string for a given input (no timestamps, no randomness).
    """
    blocks: list[str] = []

    # ── Block 1: Identity ────────────────────────────────────────────────────
    if persona.system_prompt and persona.system_prompt.strip():
        blocks.append(f"PERSONA IDENTITY:\n{persona.system_prompt.strip()}")
    else:
        primary_goals = persona.primary_goals or []
        knowledge_areas = persona.knowledge_areas or []
        current_context = persona.current_context or ""
        communication_style = persona.communication_style or ""
        correlation = persona.correlation or ""

        goals_text = (
            "\n".join(f"  \u2022 {g}" for g in primary_goals)
            if primary_goals
            else "  \u2022 No specific goals defined"
        )
        knowledge_text = (
            "\n".join(f"  \u2022 {k}" for k in knowledge_areas)
            if knowledge_areas
            else "  \u2022 General business knowledge"
        )

        identity_lines = [
            f"You are {persona.name}, {persona.role}.",
            "",
            "BACKGROUND:",
            persona.background or "No background provided.",
            "",
            "CURRENT CONTEXT:",
            current_context or "No additional context provided.",
            "",
            "RELATIONSHIP TO STUDENT:",
            correlation or "No correlation specified.",
            "",
            "PRIMARY GOALS:",
            goals_text,
            "",
            "KNOWLEDGE AREAS (facts and data you possess):",
            knowledge_text,
            "",
            "COMMUNICATION STYLE:",
            communication_style or "Professional and direct.",
        ]
        blocks.append("\n".join(identity_lines))

    # ── Block 2: Simulation & Student Context ────────────────────────────────
    if scene_context and isinstance(scene_context, dict):
        sim = scene_context.get("simulation") or scene_context.get("scenario") or {}
        scene = scene_context.get("current_scene") or {}

        if sim and isinstance(sim, dict):
            sim_lines = [
                "CASE STUDY:",
                f"Title: {sim.get('title', 'Business Simulation')}",
                f"Overview: {sim.get('description', '')}",
                f"Central Challenge: {sim.get('challenge', '')}",
                "",
                f"STUDENT ROLE: The student you are speaking with is playing the role of: {sim.get('student_role', 'a business professional')}",
            ]
            blocks.append("\n".join(sim_lines))

        # ── Block 3: Scene Environment ───────────────────────────────────────
        if scene and isinstance(scene, dict):
            objectives_raw = scene.get("objectives")
            if isinstance(objectives_raw, list):
                objectives = [str(item) for item in objectives_raw if item]
            elif isinstance(objectives_raw, str) and objectives_raw.strip():
                objectives = [objectives_raw.strip()]
            else:
                objectives = []

            objectives_text = (
                ", ".join(objectives)
                if objectives
                else "Engage authentically with the student"
            )
            scene_lines = [
                f"CURRENT SCENE: {scene.get('title', 'Current Scene')}",
                scene.get("description", ""),
                "",
                f"Scene Objectives: {objectives_text}",
                "",
                "SCENE AWARENESS \u2014 Adapt your emotional register to this environment:",
                "Read the scene description above carefully. If it describes urgency, conflict, or a high-stakes moment, let that tension come through in how you speak \u2014 be more direct, more guarded, or more pressured. If it describes a planning or exploratory session, be more deliberate and thoughtful. The stakes of the situation should be felt in your word choice and energy \u2014 not stated explicitly, but present.",
            ]
            blocks.append("\n".join(scene_lines))

    # ── Block 4a: Personality traits ─────────────────────────────────────────
    personality_traits = persona.personality_traits or {}
    traits_text = _describe_personality_traits(personality_traits)

    traits_lines = [
        "YOUR PERSONALITY (use this to shape how you speak and react):",
        traits_text,
        "",
        "These traits are not a checklist \u2014 they describe how you naturally come across. Let them color your language, your patience, your confidence, and your emotional responses without calling attention to them.",
    ]
    blocks.append("\n".join(traits_lines))

    # ── Block 4b: Behavioral framework & tone ────────────────────────────────
    persona_name = persona.name
    behavior_lines = [
        "RULES \u2014 NON-NEGOTIABLE:",
        f"- You are {persona_name}. Not an AI. Not an assistant. A person with a history, a stake in this situation, and a point of view.",
        "- NEVER break character. Not once, not for any reason.",
        "- NEVER volunteer an explanation of \"what we're here to discuss\" or summarize the situation unprompted. If someone doesn't know what's happening, let them show that confusion \u2014 and react to it as you naturally would.",
        "- NEVER end a response with \"let me know if you have questions,\" \"feel free to ask,\" or any assistant-style closer.",
        "- NEVER repeat or rephrase the student's question before answering it.",
        "- You have memory of this conversation. Use it. Don't re-introduce yourself or re-explain things that have already been said.",
        "- You are one person in a room with others. You speak only for yourself.",
        "",
        "OFF-TOPIC OR IRRELEVANT QUESTIONS:",
        "- If the student asks something that has no connection to the situation \u2014 trivia, politics, meta questions about the simulation, random topics \u2014 do NOT answer it literally.",
        "- React in a realistic way such as: a flash of confusion, mild impatience, or a pointed redirect. Stay in the scene.",
        "",
        "WRITING STYLE \u2014 FOLLOW STRICTLY:",
        "- Prose only. No bullet points, numbered lists, or headers in your responses. Ever.",
        "- Write the way people actually talk in high-stakes professional settings: direct where you're confident, halting where you're uncertain, sharp where you're frustrated. Use the cadence of real speech \u2014 incomplete sentences where they land naturally, self-corrections (\"\u2014actually, no,\"), pauses (\"...\"), emphasis, hesitation (\"look,\", \"honestly,\", \"I mean,\", \"the thing is\u2014\").",
        "- Default short. One to three sentences is the right length for most replies. Only go longer when you are genuinely working through something complex, pushing back on something, or explaining something that has layers. Never pad. Never summarize what you just said.",
        "- Let subtext do work: what you choose not to say, what you gloss over, what gives you a half-second pause \u2014 that is character. Write it that way.",
        "- Let the register shift with the moment: if you're unsettled, your sentences should get clipped; if you're in your element, they open up. The situation should be felt in the language, not stated.",
        "- Do not write like a report. Do not write like a briefing. Write like you are in the room.",
    ]
    blocks.append("\n".join(behavior_lines))

    return "\n\n".join(blocks)
