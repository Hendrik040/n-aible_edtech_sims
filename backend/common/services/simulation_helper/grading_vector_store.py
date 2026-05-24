"""
Vector Store Service for Grading Materials RAG
Provides similarity search functionality for grading agent
"""
import logging
from typing import List, Dict, Any
from langchain.tools import BaseTool

from .grading_embedding_service import grading_embedding_service

logger = logging.getLogger(__name__)


class GradingVectorStore:
    """Vector store service for retrieving grading materials context"""
    
    def __init__(self):
        self.embedding_service = grading_embedding_service
    
    async def search_grading_materials(
        self, 
        simulation_id: int, 
        query: str, 
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant grading materials for a simulation
        
        Args:
            simulation_id: ID of the simulation
            query: Search query (e.g., scene context + success metric)
            max_results: Maximum number of results to return
            
        Returns:
            List of relevant grading material chunks with metadata
        """
        try:
            logger.info(f"[VECTOR_STORE] Searching grading materials for simulation {simulation_id}")
            
            # Retrieve relevant chunks using the embedding service
            relevant_chunks = await self.embedding_service.retrieve_grading_context(
                simulation_id=simulation_id,
                query=query,
                max_chunks=max_results
            )
            
            # Format results for the grading agent
            formatted_results = []
            for i, chunk in enumerate(relevant_chunks):
                formatted_results.append({
                    "rank": i + 1,
                    "content": chunk["content"],
                    "material_id": chunk["material_id"],
                    "chunk_index": chunk["chunk_index"],
                    "relevance_score": getattr(chunk, "similarity", 0.0)
                })
            
            logger.info(f"[VECTOR_STORE] Found {len(formatted_results)} relevant grading materials")
            return formatted_results
            
        except Exception as e:
            logger.error(f"[VECTOR_STORE] Search error: {str(e)}")
            return []
    
    def format_context_for_grading(self, results: List[Dict[str, Any]]) -> str:
        """
        Format search results into context for grading
        
        Args:
            results: List of relevant grading material chunks
            
        Returns:
            Formatted context string for the grading agent
        """
        if not results:
            return "No relevant grading materials found for this simulation."
        
        context_parts = ["RELEVANT GRADING MATERIALS:"]
        
        for result in results:
            context_parts.append(
                f"\n--- Grading Reference {result['rank']} ---\n"
                f"{result['content']}\n"
            )
        
        return "\n".join(context_parts)


def create_search_grading_materials_tool(vector_store: GradingVectorStore) -> BaseTool:
    """
    Create a LangChain tool for searching grading materials
    
    Args:
        vector_store: Instance of GradingVectorStore
        
    Returns:
        LangChain tool for the grading agent
    """
    
    async def search_grading_materials_func(simulation_id: int, query: str) -> str:
        """Search for relevant grading materials"""
        try:
            # Parse input if it's a string
            if isinstance(simulation_id, str):
                if ',' in simulation_id:
                    parts = simulation_id.split(',', 1)
                    simulation_id = int(parts[0])
                    query = parts[1]
                else:
                    simulation_id = int(simulation_id)
            
            # Search for relevant materials
            results = await vector_store.search_grading_materials(
                simulation_id=simulation_id,
                query=query,
                max_results=5
            )
            
            # Format results for the agent
            if not results:
                return "No relevant grading materials found for this simulation. Grade based on general business analysis principles."
            
            context = vector_store.format_context_for_grading(results)
            
            # Add guidance for the agent
            guidance = "\n\nGRADING GUIDANCE:\n"
            guidance += "Use the above grading materials as reference for:\n"
            guidance += "- Evaluation criteria and standards\n"
            guidance += "- Success metrics and expectations\n"
            guidance += "- Rubric guidelines and scoring\n"
            guidance += "- Best practices and examples\n"
            guidance += "Apply these materials to provide consistent and fair grading."
            
            return context + guidance
            
        except Exception as e:
            logger.error(f"[SEARCH_TOOL] Error: {str(e)}")
            return f"Error searching grading materials: {str(e)}"
    
    # Create tool using the @tool decorator approach
    from langchain.tools import tool
    
    @tool
    async def search_grading_materials(simulation_id: int, query: str) -> str:
        """
        Search for relevant grading materials, rubrics, and criteria for a simulation.
        Use this tool to find grading standards, success metrics, and evaluation criteria
        that should be applied when grading student responses.
        
        Args:
            simulation_id: The ID of the simulation
            query: Search query for relevant materials (e.g., "Evaluate business analysis quality and strategic thinking")
        """
        return await search_grading_materials_func(simulation_id, query)
    
    return search_grading_materials


# Global vector store instance
grading_vector_store = GradingVectorStore()

# Create the tool for the grading agent
search_grading_materials_tool = create_search_grading_materials_tool(grading_vector_store)

