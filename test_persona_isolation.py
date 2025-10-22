#!/usr/bin/env python3
"""
Test script to verify persona isolation is working correctly.
This script tests that Hussein and FMCG personas respond correctly to their specific triggers.
"""

import sys
import os
import asyncio
from datetime import datetime

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from database.connection import get_db
from database.models import ScenarioPersona, Scenario
from agents.persona_agent import PersonaAgent

async def test_persona_isolation():
    """Test that personas are properly isolated"""
    print("🧪 Testing Persona Isolation")
    print("=" * 50)
    
    try:
        # Get database session
        db = next(get_db())
        
        # Find Hussein and FMCG personas
        hussein_persona = db.query(ScenarioPersona).filter(
            ScenarioPersona.name.ilike('%hussein%')
        ).first()
        
        fmcg_persona = db.query(ScenarioPersona).filter(
            ScenarioPersona.name.ilike('%fmcg%')
        ).first()
        
        if not hussein_persona:
            print("❌ Hussein persona not found")
            return False
            
        if not fmcg_persona:
            print("❌ FMCG persona not found")
            return False
        
        print(f"✅ Found Hussein persona: {hussein_persona.name} (ID: {hussein_persona.id})")
        print(f"✅ Found FMCG persona: {fmcg_persona.name} (ID: {fmcg_persona.id})")
        
        # Test 1: Create isolated persona agents
        print("\n🔧 Creating isolated persona agents...")
        
        hussein_session_id = f"test_hussein_{datetime.now().timestamp()}"
        fmcg_session_id = f"test_fmcg_{datetime.now().timestamp()}"
        
        hussein_agent = PersonaAgent(hussein_persona, hussein_session_id, user_progress_id=999)
        fmcg_agent = PersonaAgent(fmcg_persona, fmcg_session_id, user_progress_id=999)
        
        print(f"✅ Hussein agent created with session: {hussein_agent.persona_session_id}")
        print(f"✅ FMCG agent created with session: {fmcg_agent.persona_session_id}")
        
        # Test 2: Verify session isolation
        print("\n🔍 Verifying session isolation...")
        
        if hussein_agent.persona_session_id == fmcg_agent.persona_session_id:
            print("❌ Session IDs are not isolated!")
            return False
        
        print("✅ Session IDs are properly isolated")
        
        # Test 3: Test custom system prompts
        print("\n🎯 Testing custom system prompts...")
        
        # Check if Hussein has custom system prompt
        if hussein_persona.system_prompt:
            print(f"✅ Hussein has custom system prompt: {hussein_persona.system_prompt[:100]}...")
        else:
            print("⚠️  Hussein does not have custom system prompt")
        
        # Check if FMCG has custom system prompt
        if fmcg_persona.system_prompt:
            print(f"✅ FMCG has custom system prompt: {fmcg_persona.system_prompt[:100]}...")
        else:
            print("⚠️  FMCG does not have custom system prompt")
        
        # Test 4: Test persona-specific responses
        print("\n💬 Testing persona-specific responses...")
        
        # Test Hussein with "goat" trigger
        print("Testing Hussein with 'goat' trigger...")
        hussein_response = await hussein_agent.chat(
            message="goat",
            scene_context={"scenario": {"title": "Test Scenario"}},
            user_progress_id=999,
            scene_id=1
        )
        print(f"Hussein response: {hussein_response}")
        
        # Test FMCG with "cheese" trigger
        print("Testing FMCG with 'cheese' trigger...")
        fmcg_response = await fmcg_agent.chat(
            message="cheese",
            scene_context={"scenario": {"title": "Test Scenario"}},
            user_progress_id=999,
            scene_id=1
        )
        print(f"FMCG response: {fmcg_response}")
        
        # Test 5: Verify responses are different
        print("\n🔍 Verifying responses are persona-specific...")
        
        if "Testing for Hussein" in hussein_response:
            print("✅ Hussein correctly responded to 'goat' trigger")
        else:
            print("❌ Hussein did not respond correctly to 'goat' trigger")
        
        if "Testing for FMCG" in fmcg_response:
            print("✅ FMCG correctly responded to 'cheese' trigger")
        else:
            print("❌ FMCG did not respond correctly to 'cheese' trigger")
        
        # Test 6: Test cross-contamination
        print("\n🛡️  Testing for cross-contamination...")
        
        # Test Hussein with "cheese" (should not trigger FMCG response)
        hussein_cheese_response = await hussein_agent.chat(
            message="cheese",
            scene_context={"scenario": {"title": "Test Scenario"}},
            user_progress_id=999,
            scene_id=1
        )
        print(f"Hussein response to 'cheese': {hussein_cheese_response}")
        
        if "Testing for FMCG" in hussein_cheese_response:
            print("❌ Cross-contamination detected! Hussein responded with FMCG trigger")
            return False
        else:
            print("✅ No cross-contamination detected")
        
        # Test FMCG with "goat" (should not trigger Hussein response)
        fmcg_goat_response = await fmcg_agent.chat(
            message="goat",
            scene_context={"scenario": {"title": "Test Scenario"}},
            user_progress_id=999,
            scene_id=1
        )
        print(f"FMCG response to 'goat': {fmcg_goat_response}")
        
        if "Testing for Hussein" in fmcg_goat_response:
            print("❌ Cross-contamination detected! FMCG responded with Hussein trigger")
            return False
        else:
            print("✅ No cross-contamination detected")
        
        print("\n🎉 All tests passed! Persona isolation is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    result = asyncio.run(test_persona_isolation())
    if result:
        print("\n✅ Persona isolation test PASSED")
        sys.exit(0)
    else:
        print("\n❌ Persona isolation test FAILED")
        sys.exit(1)
