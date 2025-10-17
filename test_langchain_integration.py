#!/usr/bin/env python3
"""
Test script to verify LangChain integration is working
"""

import sys
import os
sys.path.append('/Users/amybihag/n-aible_edtech_sims/n-aible_edtech_sims/backend')

def test_langchain_imports():
    """Test if LangChain components can be imported"""
    try:
        from api.chat_orchestrator import ChatOrchestrator, LANGCHAIN_AVAILABLE
        print(f"✅ ChatOrchestrator imported successfully")
        print(f"✅ LangChain available: {LANGCHAIN_AVAILABLE}")
        
        if LANGCHAIN_AVAILABLE:
            from agents.persona_agent import PersonaAgent
            print(f"✅ PersonaAgent imported successfully")
            
            # Test basic initialization
            test_data = {
                'title': 'Test Scenario',
                'scenes': [{'id': 1, 'title': 'Test Scene'}],
                'personas': [{'id': 'test_persona', 'identity': {'name': 'Test Persona', 'role': 'Test Role'}}]
            }
            
            orchestrator = ChatOrchestrator(test_data, enable_langchain=True)
            print(f"✅ ChatOrchestrator initialized with LangChain: {orchestrator.langchain_enabled}")
            print(f"✅ Persona agents dict type: {type(orchestrator.persona_agents)}")
            
            return True
        else:
            print("❌ LangChain not available - running in compatibility mode")
            return False
            
    except Exception as e:
        print(f"❌ Error importing LangChain components: {e}")
        return False

def test_langchain_manager():
    """Test if LangChainManager can be initialized"""
    try:
        from langchain_config import langchain_manager
        print(f"✅ LangChainManager imported successfully")
        
        # Test basic properties
        llm = langchain_manager.llm
        embeddings = langchain_manager.embeddings
        vectorstore = langchain_manager.vectorstore
        
        print(f"✅ LLM: {type(llm)}")
        print(f"✅ Embeddings: {type(embeddings)}")
        print(f"✅ Vectorstore: {type(vectorstore) if vectorstore else 'None (fallback)'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error with LangChainManager: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing LangChain Integration...")
    print("=" * 50)
    
    success1 = test_langchain_imports()
    print()
    success2 = test_langchain_manager()
    
    print("=" * 50)
    if success1 and success2:
        print("✅ LangChain integration is working correctly!")
    else:
        print("❌ LangChain integration has issues")
