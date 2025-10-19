#!/usr/bin/env python3
"""
Test script for RAG grading functionality
This script tests the grading agent's ability to use RAG materials for evaluation
"""

import asyncio
import sys
import os
from pathlib import Path

# Set environment variables for testing
os.environ["ENVIRONMENT"] = "development"
os.environ["DATABASE_URL"] = "sqlite:///./backend/ai_agent_platform.db"
os.environ["OPENAI_API_KEY"] = "your-openai-api-key-here"  # Replace with actual key
os.environ["SECRET_KEY"] = "test-secret-key-for-development-only"
os.environ["REDIS_URL"] = "redis://localhost:6379"

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from database.connection import get_db
from database.models import Scenario, ScenarioScene, GradingMaterial, GradingMaterialChunk, User
from agents.grading_agent import grading_agent
from services.grading_embedding_service import grading_embedding_service
from sqlalchemy.orm import Session

async def test_rag_grading():
    """Test the RAG grading functionality"""
    
    print("🚀 Starting RAG Grading Test...")
    
    # Get database session
    db = next(get_db())
    
    try:
        # 1. Create a test scenario
        print("\n📝 Creating test scenario...")
        test_scenario = Scenario(
            title="Business Analysis Techniques Test",
            description="Test scenario for evaluating business analysis skills",
            challenge="Analyze a declining retail business using appropriate frameworks",
            industry="Retail",
            learning_objectives=["Apply SWOT analysis", "Use Porter's Five Forces", "Develop strategic recommendations"],
            created_by=1,  # Assuming user ID 1 exists
            status="active"
        )
        
        db.add(test_scenario)
        db.commit()
        db.refresh(test_scenario)
        print(f"✅ Created scenario with ID: {test_scenario.id}")
        
        # 2. Create a test scene
        print("\n🎬 Creating test scene...")
        test_scene = ScenarioScene(
            scenario_id=test_scenario.id,
            title="Strategic Analysis of Retail Decline",
            description="You are a business consultant hired to analyze why a major retail chain is losing market share. The company has seen declining sales for three consecutive quarters and faces increased competition from online retailers.",
            user_goal="Provide a comprehensive strategic analysis using business frameworks to identify root causes and recommend solutions.",
            success_metric="Demonstrate clear understanding of business analysis frameworks and provide actionable strategic recommendations",
            scene_order=1,
            max_attempts=3
        )
        
        db.add(test_scene)
        db.commit()
        db.refresh(test_scene)
        print(f"✅ Created scene with ID: {test_scene.id}")
        
        # 3. Create grading material
        print("\n📚 Creating grading material...")
        grading_doc_path = Path(__file__).parent / "business_analysis_techniques.md"
        
        with open(grading_doc_path, 'r') as f:
            content = f.read()
        
        grading_material = GradingMaterial(
            simulation_id=test_scenario.id,
            filename="business_analysis_techniques.md",
            file_type=".md",
            file_size=len(content.encode('utf-8')),
            original_content=content,
            processing_status="pending",
            uploaded_by=1
        )
        
        db.add(grading_material)
        db.commit()
        db.refresh(grading_material)
        print(f"✅ Created grading material with ID: {grading_material.id}")
        
        # 4. Process the grading material (create embeddings)
        print("\n🔄 Processing grading material for RAG...")
        await grading_embedding_service.process_grading_material_async(
            material_id=grading_material.id,
            content=content,
            filename="business_analysis_techniques.md"
        )
        print("✅ Grading material processed and indexed")
        
        # 5. Create good sample response
        print("\n✅ Creating good sample response...")
        good_response = {
            "content": """Based on the retail chain's declining performance, I'll conduct a comprehensive strategic analysis using multiple business frameworks.

**SWOT Analysis:**
Strengths: Established brand recognition, physical store presence, existing customer base
Weaknesses: High operating costs, limited digital presence, outdated inventory management
Opportunities: E-commerce expansion, omnichannel integration, customer experience enhancement
Threats: Online competition, changing consumer preferences, economic uncertainty

**Porter's Five Forces:**
- Threat of New Entrants: Low due to high capital requirements and established players
- Supplier Power: Moderate due to multiple supplier options
- Buyer Power: High due to price sensitivity and online alternatives
- Threat of Substitutes: High from online retailers and direct-to-consumer brands
- Industry Rivalry: Intense competition on price and convenience

**Root Cause Analysis:**
Using the 5 Whys methodology:
1. Why are sales declining? Because customers are shopping elsewhere
2. Why are customers shopping elsewhere? Because competitors offer better value
3. Why do competitors offer better value? Because they have lower costs and better convenience
4. Why do we have higher costs? Because of inefficient operations and high overhead
5. Why are operations inefficient? Because of outdated systems and processes

**Strategic Recommendations:**
1. Implement omnichannel strategy integrating online and offline experiences
2. Optimize supply chain and inventory management systems
3. Enhance customer experience through personalization and service quality
4. Develop competitive pricing strategies while maintaining margins
5. Invest in digital transformation and e-commerce capabilities

This analysis demonstrates strategic thinking by identifying root causes and providing actionable solutions that address both immediate challenges and long-term competitiveness."""
        }
        
        # 6. Create bad sample response
        print("\n❌ Creating bad sample response...")
        bad_response = {
            "content": """The retail store is not doing well because people don't shop there anymore. The prices are too high and the products are not good. The employees are not helpful and the store looks old. 

I think they should just close the store and open an online shop instead. Everyone shops online now anyway. They could save money on rent and hire fewer people. 

Maybe they should also change their logo and get new colors. Red and blue are boring colors. They should use bright colors like neon green or hot pink to attract younger customers.

Also, they should have a sale every week to get more customers. People love sales and discounts. If everything is 50% off, people will definitely come back.

That's my analysis of the business problem."""
        }
        
        # 7. Test grading with good response
        print("\n🎯 Testing grading with GOOD response...")
        good_grade_result = await grading_agent.grade_scene(
            scene=test_scene,
            user_responses=[good_response],
            user_progress_id=1
        )
        
        print(f"Good Response Score: {good_grade_result.get('score', 'N/A')}")
        print(f"Good Response Feedback: {good_grade_result.get('feedback', 'N/A')[:200]}...")
        
        # 8. Test grading with bad response
        print("\n🎯 Testing grading with BAD response...")
        bad_grade_result = await grading_agent.grade_scene(
            scene=test_scene,
            user_responses=[bad_response],
            user_progress_id=2
        )
        
        print(f"Bad Response Score: {bad_grade_result.get('score', 'N/A')}")
        print(f"Bad Response Feedback: {bad_grade_result.get('feedback', 'N/A')[:200]}...")
        
        # 9. Test RAG search directly
        print("\n🔍 Testing RAG search functionality...")
        search_results = await grading_agent.tools[0].arun(
            f"{test_scenario.id}, Evaluate business analysis quality and strategic thinking"
        )
        print(f"RAG Search Results: {search_results[:300]}...")
        
        print("\n✅ RAG Grading Test Complete!")
        print(f"Good Response Score: {good_grade_result.get('score', 'N/A')}")
        print(f"Bad Response Score: {bad_grade_result.get('score', 'N/A')}")
        
        return {
            "good_grade": good_grade_result,
            "bad_grade": bad_grade_result,
            "rag_search": search_results
        }
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        db.close()

if __name__ == "__main__":
    # Run the test
    result = asyncio.run(test_rag_grading())
    
    if result:
        print("\n🎉 Test completed successfully!")
        print("\nSummary:")
        print(f"Good response score: {result['good_grade'].get('score', 'N/A')}")
        print(f"Bad response score: {result['bad_grade'].get('score', 'N/A')}")
    else:
        print("\n💥 Test failed!")
