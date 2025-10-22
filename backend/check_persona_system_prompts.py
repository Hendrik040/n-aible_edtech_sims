#!/usr/bin/env python3
"""
Script to check the actual system prompts stored in the database
"""
import sys
import os

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.connection import get_db
from database.models import ScenarioPersona

def check_persona_system_prompts():
    """Check what system prompts are actually stored in the database"""
    print("🔍 Checking persona system prompts in database...")
    print("=" * 60)
    
    db = next(get_db())
    
    try:
        # Get all personas with system prompts
        personas = db.query(ScenarioPersona).filter(
            ScenarioPersona.system_prompt.isnot(None),
            ScenarioPersona.deleted_at.is_(None)
        ).all()
        
        print(f"Found {len(personas)} personas with system prompts:")
        print()
        
        for persona in personas:
            print(f"📋 Persona: {persona.name} (ID: {persona.id})")
            print(f"   Role: {persona.role}")
            print(f"   System Prompt Length: {len(persona.system_prompt) if persona.system_prompt else 0}")
            
            if persona.system_prompt:
                # Check for trigger words
                system_prompt = persona.system_prompt.lower()
                
                print(f"   🔍 Trigger Analysis:")
                if "goat" in system_prompt:
                    print(f"      ✅ Contains 'goat' trigger")
                if "cheese" in system_prompt:
                    print(f"      ✅ Contains 'cheese' trigger")
                if "lebrnnnn boobobobo" in system_prompt:
                    print(f"      ✅ Contains 'LEBRONNNN BOOBOBOBO' response")
                if "googoogagaga" in system_prompt:
                    print(f"      ✅ Contains 'GOOGOOGAGAGA' response")
                
                # Show first 200 characters of system prompt
                print(f"   📝 System Prompt Preview:")
                print(f"      {persona.system_prompt[:200]}...")
                
                # Check for corruption
                if persona.name == "Hussein Bakari":
                    if "cheese" in system_prompt:
                        print(f"      ❌ CORRUPTION: Hussein has 'cheese' trigger (should only have 'goat')")
                    if "googoogagaga" in system_prompt:
                        print(f"      ❌ CORRUPTION: Hussein has 'GOOGOOGAGAGA' response (should only have 'LEBRONNNN BOOBOBOBO')")
                
                if persona.name == "FMCG Manufacturers":
                    if "goat" in system_prompt:
                        print(f"      ❌ CORRUPTION: FMCG has 'goat' trigger (should only have 'cheese')")
                    if "lebrnnnn boobobobo" in system_prompt:
                        print(f"      ❌ CORRUPTION: FMCG has 'LEBRONNNN BOOBOBOBO' response (should only have 'GOOGOOGAGAGA')")
                
            print("-" * 40)
        
        # Check for specific personas by ID
        print("\n🎯 Checking specific personas by ID:")
        print("=" * 40)
        
        # Check Hussein (ID 27)
        hussein = db.query(ScenarioPersona).filter(ScenarioPersona.id == 27).first()
        if hussein:
            print(f"👤 Hussein Bakari (ID: 27):")
            print(f"   System Prompt: {hussein.system_prompt[:100] if hussein.system_prompt else 'None'}...")
            if hussein.system_prompt:
                if "goat" in hussein.system_prompt.lower():
                    print(f"   ✅ Has 'goat' trigger")
                if "cheese" in hussein.system_prompt.lower():
                    print(f"   ❌ CORRUPTION: Has 'cheese' trigger (should not have this)")
        else:
            print("❌ Hussein Bakari (ID: 27) not found")
        
        # Check FMCG (ID 28)
        fmcg = db.query(ScenarioPersona).filter(ScenarioPersona.id == 28).first()
        if fmcg:
            print(f"👤 FMCG Manufacturers (ID: 28):")
            print(f"   System Prompt: {fmcg.system_prompt[:100] if fmcg.system_prompt else 'None'}...")
            if fmcg.system_prompt:
                if "cheese" in fmcg.system_prompt.lower():
                    print(f"   ✅ Has 'cheese' trigger")
                if "goat" in fmcg.system_prompt.lower():
                    print(f"   ❌ CORRUPTION: Has 'goat' trigger (should not have this)")
        else:
            print("❌ FMCG Manufacturers (ID: 28) not found")
            
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_persona_system_prompts()
