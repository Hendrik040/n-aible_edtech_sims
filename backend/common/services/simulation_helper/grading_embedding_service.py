"""
Enhanced Embedding Service for Grading Materials RAG
Implements semantic chunking for optimal retrieval of grading criteria, rubrics, and references
"""
import os
import openai
import asyncio
import hashlib
import logging
from typing import List, Dict, Tuple, Optional
from sklearn.metrics.pairwise import cosine_similarity
import re
import json
from datetime import datetime

from common.db.core import SessionLocal
from common.db.models import GradingMaterial, GradingMaterialChunk
from common.config import get_settings

logger = logging.getLogger(__name__)
config = get_settings()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') or config.openai_api_key
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# Chunking configuration optimized for grading materials
CHUNK_SIZE = 800  # Smaller chunks for better precision in grading criteria
CHUNK_OVERLAP = 150  # Overlap to maintain context
MAX_CHUNKS_FOR_RETRIEVAL = 5  # Top 5 chunks for grading context


class GradingEmbeddingService:
    """Service for processing grading materials with semantic chunking and embeddings"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)
        self.embeddings_cache = {}  # Cache embeddings by content hash
    
    async def process_grading_material(
        self, 
        material_id: int, 
        content: str, 
        filename: str
    ) -> Dict[str, any]:
        """
        Process a grading material: chunk content and create embeddings
        Returns processing results with chunk count and status
        """
        logger.info(f"[GRADING_EMBEDDING] Processing material {material_id}: {filename}")
        
        try:
            # Update processing status
            self._update_material_status(material_id, "processing")
            
            # Create semantic chunks optimized for grading materials
            chunks = self._create_semantic_chunks(content)
            logger.info(f"[GRADING_EMBEDDING] Created {len(chunks)} semantic chunks")
            
            # Create embeddings for all chunks
            chunk_data = []
            embedding_tasks = []
            
            for i, chunk in enumerate(chunks):
                chunk_data.append({
                    'chunk_index': i,
                    'content': chunk,
                    'embedding': None  # Will be filled
                })
                
                # Create async task for embedding
                embedding_tasks.append(self._get_embedding_async(chunk, f"material_{material_id}_chunk_{i}"))
            
            # Execute all embedding tasks in parallel
            embeddings = await asyncio.gather(*embedding_tasks)
            
            # Combine chunks with embeddings
            for chunk_dict, embedding in zip(chunk_data, embeddings):
                chunk_dict['embedding'] = embedding
            
            # Store chunks in database
            stored_chunks = await self._store_chunks(material_id, chunk_data)
            
            # Update processing status
            self._update_material_status(
                material_id, 
                "completed", 
                {"chunks_created": len(stored_chunks)}
            )
            
            logger.info(f"[GRADING_EMBEDDING] Successfully processed {len(stored_chunks)} chunks")
            return {
                "status": "success",
                "chunks_created": len(stored_chunks),
                "material_id": material_id
            }
            
        except Exception as e:
            logger.error(f"[GRADING_EMBEDDING] Error processing material {material_id}: {str(e)}")
            self._update_material_status(material_id, "failed", {"error": str(e)})
            return {
                "status": "error",
                "error": str(e),
                "material_id": material_id
            }
    
    async def retrieve_grading_context(
        self, 
        simulation_id: int, 
        query: str, 
        max_chunks: int = MAX_CHUNKS_FOR_RETRIEVAL
    ) -> List[Dict[str, any]]:
        """
        Retrieve relevant grading materials for a simulation
        Returns top chunks sorted by relevance to the query
        """
        logger.info(f"[GRADING_RETRIEVAL] Retrieving context for simulation {simulation_id}")
        
        try:
            # Get all chunks for the simulation
            chunks = self._get_simulation_chunks(simulation_id)
            if not chunks:
                logger.info(f"[GRADING_RETRIEVAL] No chunks found for simulation {simulation_id}")
                return []
            
            # Get query embedding
            query_embedding = await self._get_embedding_async(query, f"query_{hash(query)}")
            
            # Calculate similarities
            chunk_similarities = []
            for chunk in chunks:
                if chunk['embedding_vector'] is not None:
                    similarity = cosine_similarity(
                        [query_embedding], 
                        [chunk['embedding_vector']]
                    )[0][0]
                    chunk_similarities.append({
                        'chunk': chunk,
                        'similarity': similarity
                    })
            
            # Sort by similarity and return top chunks
            chunk_similarities.sort(key=lambda x: x['similarity'], reverse=True)
            top_chunks = [item['chunk'] for item in chunk_similarities[:max_chunks]]
            
            logger.info(f"[GRADING_RETRIEVAL] Retrieved {len(top_chunks)} relevant chunks")
            return top_chunks
            
        except Exception as e:
            logger.error(f"[GRADING_RETRIEVAL] Error retrieving context: {str(e)}")
            return []
    
    def _create_semantic_chunks(self, content: str) -> List[str]:
        """
        Create semantic chunks optimized for grading materials
        Uses multiple strategies for better context preservation
        """
        # Strategy 1: Split by sections/headings (for rubrics and structured documents)
        section_chunks = self._chunk_by_sections(content)
        if len(section_chunks) > 1:
            return section_chunks
        
        # Strategy 2: Split by paragraphs with semantic overlap
        paragraph_chunks = self._chunk_by_paragraphs(content)
        if len(paragraph_chunks) > 1:
            return paragraph_chunks
        
        # Strategy 3: Split by sentences with overlap (fallback)
        return self._chunk_by_sentences(content)
    
    def _chunk_by_sections(self, content: str) -> List[str]:
        """Split content by sections/headings"""
        # Look for common heading patterns
        heading_patterns = [
            r'\n\s*#{1,6}\s+',  # Markdown headers
            r'\n\s*\d+\.\s+',   # Numbered sections
            r'\n\s*[A-Z][A-Z\s]+:\s*\n',  # CAPS headings
            r'\n\s*[A-Z][a-z]+\s+[A-Z][a-z]+:\s*\n',  # Title Case headings
        ]
        
        chunks = []
        current_chunk = ""
        
        lines = content.split('\n')
        for line in lines:
            is_heading = any(re.match(pattern, f'\n{line}\n') for pattern in heading_patterns)
            
            if is_heading and current_chunk.strip():
                chunks.append(current_chunk.strip())
                current_chunk = line + '\n'
            else:
                current_chunk += line + '\n'
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _chunk_by_paragraphs(self, content: str) -> List[str]:
        """Split content by paragraphs with semantic overlap"""
        paragraphs = re.split(r'\n\s*\n', content)
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # Estimate tokens (rough: 1 token ≈ 4 characters)
            estimated_tokens = len(current_chunk + paragraph) // 4
            
            if estimated_tokens > CHUNK_SIZE and current_chunk:
                chunks.append(current_chunk.strip())
                
                # Create overlap from last sentence
                last_sentence = current_chunk.split('.')[-1] if '.' in current_chunk else ""
                current_chunk = last_sentence + ' ' + paragraph if last_sentence else paragraph
            else:
                current_chunk += '\n\n' + paragraph if current_chunk else paragraph
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _chunk_by_sentences(self, content: str) -> List[str]:
        """Split content by sentences with overlap (fallback method)"""
        sentences = re.split(r'[.!?]+', content)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # Estimate tokens
            estimated_tokens = len(current_chunk + sentence) // 4
            
            if estimated_tokens > CHUNK_SIZE and current_chunk:
                chunks.append(current_chunk.strip())
                
                # Create overlap from last few sentences
                overlap_sentences = current_chunk.split('.')[-3:]  # Last 3 sentences
                current_chunk = '. '.join(overlap_sentences) + '. ' + sentence
            else:
                current_chunk += '. ' + sentence if current_chunk else sentence
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    async def _get_embedding_async(self, text: str, cache_key: str) -> List[float]:
        """Get embedding for text with caching"""
        # Create cache key from content hash
        content_hash = hashlib.md5(text.encode()).hexdigest()
        
        if content_hash in self.embeddings_cache:
            return self.embeddings_cache[content_hash]
        
        try:
            # Run embedding in executor to avoid blocking
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=text[:8000]  # Truncate to model limit
                )
            )
            
            embedding = response.data[0].embedding
            self.embeddings_cache[content_hash] = embedding
            return embedding
            
        except Exception as e:
            logger.error(f"[GRADING_EMBEDDING] Failed to get embedding: {str(e)}")
            # Return zero vector as fallback
            return [0.0] * EMBEDDING_DIMENSION
    
    async def _store_chunks(self, material_id: int, chunk_data: List[Dict]) -> List[Dict]:
        """Store chunks in the database"""
        db = SessionLocal()
        stored_chunks = []
        
        try:
            for chunk_dict in chunk_data:
                # Create content hash for deduplication
                content_hash = hashlib.md5(chunk_dict['content'].encode()).hexdigest()
                
                # Check if chunk already exists
                existing_chunk = db.query(GradingMaterialChunk).filter(
                    GradingMaterialChunk.material_id == material_id,
                    GradingMaterialChunk.content_hash == content_hash
                ).first()
                
                if existing_chunk:
                    continue  # Skip duplicate
                
                # Create new chunk
                chunk = GradingMaterialChunk(
                    material_id=material_id,
                    chunk_index=chunk_dict['chunk_index'],
                    content=chunk_dict['content'],
                    embedding_vector=chunk_dict['embedding'],
                    embedding_model=EMBEDDING_MODEL,
                    embedding_dimension=EMBEDDING_DIMENSION,
                    content_hash=content_hash
                )
                
                db.add(chunk)
                stored_chunks.append(chunk_dict)
            
            db.commit()
            return stored_chunks
            
        except Exception as e:
            db.rollback()
            logger.error(f"[GRADING_EMBEDDING] Error storing chunks: {str(e)}")
            raise
        finally:
            db.close()
    
    def _get_simulation_chunks(self, simulation_id: int) -> List[Dict]:
        """Get all chunks for a simulation"""
        db = SessionLocal()
        
        try:
            chunks = db.query(GradingMaterialChunk).join(GradingMaterial).filter(
                GradingMaterial.simulation_id == simulation_id,
                GradingMaterial.processing_status == "completed"
            ).all()
            
            return [
                {
                    'id': chunk.id,
                    'content': chunk.content,
                    'embedding_vector': chunk.embedding_vector,
                    'material_id': chunk.material_id,
                    'chunk_index': chunk.chunk_index
                }
                for chunk in chunks
            ]
            
        except Exception as e:
            logger.error(f"[GRADING_RETRIEVAL] Error getting simulation chunks: {str(e)}")
            return []
        finally:
            db.close()
    
    def _update_material_status(
        self, 
        material_id: int, 
        status: str, 
        log_data: Optional[Dict] = None
    ):
        """Update material processing status"""
        db = SessionLocal()
        
        try:
            material = db.query(GradingMaterial).filter(
                GradingMaterial.id == material_id
            ).first()
            
            if material:
                material.processing_status = status
                if log_data:
                    material.processing_log = log_data
                material.updated_at = datetime.utcnow()
                db.commit()
                
        except Exception as e:
            db.rollback()
            logger.error(f"[GRADING_EMBEDDING] Error updating material status: {str(e)}")
        finally:
            db.close()
    
    def get_combined_context(self, chunks: List[Dict]) -> str:
        """Combine retrieved chunks into context for grading"""
        if not chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(chunks):
            context_parts.append(f"--- Grading Reference {i+1} ---\n{chunk['content']}\n")
        
        return "\n".join(context_parts)


# Global instance
grading_embedding_service = GradingEmbeddingService()

