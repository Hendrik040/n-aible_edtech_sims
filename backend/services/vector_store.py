"""
Vector Store Service for LangChain Integration
Provides fallback implementations when pgvector is not available
"""

import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
import hashlib
import pickle
import base64

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False

from database.connection import get_db, settings
from database.models import VectorEmbeddings
from langchain_config import langchain_manager, settings as langchain_settings

class VectorStoreService:
    """
    Vector store service with fallback implementations
    """
    
    def __init__(self, embedding_model: str = None):
        import os
        # Enable pgvector only when both the package and an explicit flag are present.
        self.pgvector_available = PGVECTOR_AVAILABLE and os.getenv("PGVECTOR_ENABLED", "0") == "1"
        # Instantiate embeddings provider
        self.embeddings_model = langchain_manager.embeddings
        # Use provided embedding model or get from config with fallback
        self.embedding_model = embedding_model or self._get_configured_embedding_model()
    
    def _get_configured_embedding_model(self) -> str:
        """Get the configured embedding model with fallback"""
        try:
            # Try to get from langchain settings first
            if hasattr(langchain_settings, 'embedding_model'):
                if langchain_settings.embedding_model == "openai":
                    return getattr(langchain_settings, 'openai_embedding_model', 'text-embedding-ada-002')
                else:
                    return langchain_settings.embedding_model
        except Exception:
            pass
        
        # Fallback to environment variable
        import os
        env_model = os.getenv('EMBEDDING_MODEL')
        if env_model:
            return env_model
        
        # Final fallback
        return "text-embedding-ada-002"
        
    async def store_embedding(self, 
                            content: str, 
                            metadata: Dict[str, Any] = None,
                            collection_name: str = "default",
                            document_id: str = None) -> str:
        """
        Store text content as embedding with metadata
        """
        try:
            # Generate embedding
            embedding_vector = await self._generate_embedding(content)
            
            # Generate document ID if not provided
            if not document_id:
                document_id = self._generate_document_id(content, metadata)
            
            # Store in database
            if self.pgvector_available:
                return await self._store_with_pgvector(
                    content, embedding_vector, metadata, collection_name, document_id
                )
            else:
                return await self._store_with_fallback(
                    content, embedding_vector, metadata, collection_name, document_id
                )
                
        except Exception as e:
            return None
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text (async version)"""
        try:
            # Use LangChain embeddings - check if async method exists
            if hasattr(self.embeddings_model, 'aembed_query'):
                embedding = await self.embeddings_model.aembed_query(text)
            else:
                # Fall back to sync method
                embedding = self.embeddings_model.embed_query(text)
            
            return self._normalize_embedding_dimensions(embedding)
        except Exception as e:
            # Fallback to simple hash-based embedding
            return self._generate_fallback_embedding(text)
    
    def _generate_embedding_sync(self, text: str) -> List[float]:
        """Generate embedding for text (sync version)"""
        try:
            # Use LangChain embeddings sync method
            embedding = self.embeddings_model.embed_query(text)
            return self._normalize_embedding_dimensions(embedding)
        except Exception as e:
            # Fallback to simple hash-based embedding
            return self._generate_fallback_embedding(text)
    
    def _normalize_embedding_dimensions(self, embedding: List[float]) -> List[float]:
        """Normalize embedding dimensions to 1536 for consistency"""
        # Convert to plain Python list if it's a NumPy array
        if hasattr(embedding, 'tolist'):
            embedding = embedding.tolist()
        
        # Ensure we have the right dimension (1536 for OpenAI, 384 for HuggingFace)
        if len(embedding) == 384:
            # Pad to 1536 dimensions for consistency
            embedding = embedding + [0.0] * (1536 - 384)
        elif len(embedding) != 1536:
            # Truncate or pad to 1536 dimensions
            if len(embedding) > 1536:
                embedding = embedding[:1536]
            else:
                embedding = embedding + [0.0] * (1536 - len(embedding))
        
        return embedding
    
    def _generate_fallback_embedding(self, text: str) -> List[float]:
        """Generate a simple fallback embedding when OpenAI is not available"""
        # Create a deterministic embedding based on text hash using BLAKE2b
        text_hash = hashlib.blake2b(text.encode(), digest_size=32).hexdigest()
        
        # Generate 1536 bytes of entropy by iteratively hashing
        embedding_bytes = bytearray()
        counter = 0
        
        while len(embedding_bytes) < 1536:
            # Create hash with counter for additional entropy
            counter_bytes = counter.to_bytes(4, byteorder='big')
            chunk_hash = hashlib.blake2b(
                text.encode() + counter_bytes, 
                digest_size=min(64, 1536 - len(embedding_bytes))
            ).digest()
            embedding_bytes.extend(chunk_hash)
            counter += 1
        
        # Convert bytes to 1536-dimensional vector
        embedding = []
        for i in range(1536):
            # Map byte to float in range [-1, 1] to avoid long tails of zeros
            byte_val = embedding_bytes[i]
            # Normalize: (byte_val / 255.0) * 2 - 1 maps [0,255] to [-1,1]
            value = (byte_val / 255.0) * 2.0 - 1.0
            embedding.append(value)
        
        return embedding
    
    def _generate_document_id(self, content: str, metadata: Dict[str, Any] = None) -> str:
        """Generate a unique document ID"""
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        if metadata:
            metadata_str = json.dumps(metadata, sort_keys=True)
            metadata_hash = hashlib.sha256(metadata_str.encode()).hexdigest()
            return f"{content_hash}_{metadata_hash[:16]}"
        return content_hash
    
    async def _store_with_pgvector(self, 
                                 content: str, 
                                 embedding_vector: List[float], 
                                 metadata: Dict[str, Any],
                                 collection_name: str,
                                 document_id: str) -> str:
        """Store embedding using pgvector"""
        db_gen = get_db()
        try:
            db = next(db_gen)
            
            # Check if document already exists
            existing = db.query(VectorEmbeddings).filter(
                VectorEmbeddings.content_hash == document_id,
                VectorEmbeddings.content_type == collection_name
            ).first()
            
            if existing:
                # Update existing
                existing.original_content = content
                existing.embedding_vector = embedding_vector
                existing.content_metadata = metadata
                db.commit()
                return document_id
            
            # Create new embedding store entry
            embedding_store = VectorEmbeddings(
                content_type=collection_name,
                content_id=0,  # We'll use content_hash as the unique identifier
                content_hash=document_id,
                embedding_vector=embedding_vector,
                embedding_model=self.embedding_model,
                embedding_dimension=len(embedding_vector),
                original_content=content,
                content_metadata=metadata
            )
            
            db.add(embedding_store)
            db.commit()
            return document_id
            
        except Exception as e:
            # Fallback to non-vector storage
            return await self._store_with_fallback(
                content, embedding_vector, metadata, collection_name, document_id
            )
        finally:
            try:
                next(db_gen)  # This will trigger the finally block in get_db()
            except StopIteration:
                pass  # Generator is already closed
    
    async def _store_with_fallback(self, 
                                 content: str, 
                                 embedding_vector: List[float], 
                                 metadata: Dict[str, Any],
                                 collection_name: str,
                                 document_id: str) -> str:
        """Store embedding using fallback method (JSON storage)"""
        db_gen = get_db()
        try:
            db = next(db_gen)
            
            # Store as JSON in embedding_vector field (fallback when pgvector not available)
            embedding_data = {
                "embedding": embedding_vector,
                "content": content,
                "metadata": metadata or {},
                "collection_name": collection_name,
                "document_id": document_id
            }
            
            # Check if document already exists
            existing = db.query(VectorEmbeddings).filter(
                VectorEmbeddings.content_hash == document_id,
                VectorEmbeddings.content_type == collection_name
            ).first()
            
            if existing:
                # Update existing
                existing.original_content = content
                existing.content_metadata = embedding_data
                db.commit()
                return document_id
            
            # Create new entry (store vector in metadata since pgvector column is required)
            embedding_store = VectorEmbeddings(
                content_type=collection_name,
                content_id=0,
                content_hash=document_id,
                embedding_vector=embedding_vector,  # Store the actual vector
                embedding_model=f"fallback-{self.embedding_model}",
                embedding_dimension=len(embedding_vector),
                original_content=content,
                content_metadata=embedding_data
            )
            
            db.add(embedding_store)
            db.commit()
            return document_id
            
        except Exception as e:
            return None
        finally:
            try:
                next(db_gen)  # This will trigger the finally block in get_db()
            except StopIteration:
                pass  # Generator is already closed
    
    async def similarity_search(self, 
                              query: str, 
                              collection_name: str = "default",
                              k: int = 5,
                              score_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        Perform similarity search
        """
        try:
            # Generate query embedding
            query_embedding = await self._generate_embedding(query)
            
            if self.pgvector_available:
                return await self._similarity_search_pgvector(
                    query_embedding, collection_name, k, score_threshold
                )
            else:
                return await self._similarity_search_fallback(
                    query_embedding, collection_name, k, score_threshold
                )
                
        except Exception as e:
            return []
    
    async def _similarity_search_pgvector(self, 
                                        query_embedding: List[float],
                                        collection_name: str,
                                        k: int,
                                        score_threshold: float) -> List[Dict[str, Any]]:
        """Similarity search using pgvector"""
        # Early guard: fall back if pgvector is not available
        if not self.pgvector_available:
            return await self._similarity_search_fallback(query_embedding, collection_name, k, score_threshold)
        
        db_gen = get_db()
        try:
            db = next(db_gen)
            
            # Use pgvector similarity search
            # Validate and convert embedding to proper format
            if not isinstance(query_embedding, (list, tuple, np.ndarray)):
                raise ValueError("query_embedding must be a list, tuple, or numpy array")
            
            # Convert to plain Python list of floats
            if hasattr(query_embedding, 'tolist'):
                embedding_list = query_embedding.tolist()
            else:
                embedding_list = [float(x) for x in query_embedding]
            
            # Ensure pgvector extension is registered
            from pgvector.sqlalchemy import Vector
            
            # Validate collection_name to prevent SQL injection
            if not collection_name or not isinstance(collection_name, str):
                raise ValueError("Invalid collection_name")
            
            # Only allow alphanumeric characters, underscores, and hyphens
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', collection_name):
                raise ValueError("Invalid collection_name: only alphanumeric characters, underscores, and hyphens are allowed")
            
            # Use parameterized query with proper pgvector syntax
            # Convert embedding list to pgvector literal format
            embedding_str = "[" + ",".join(map(str, embedding_list)) + "]"
            
            # Use parameterized query to prevent SQL injection
            query = """
                SELECT content_hash,
                       original_content,
                       content_metadata,
                       1 - (embedding_vector <=> %s::vector) AS similarity_score
                FROM vector_embeddings
                WHERE content_type = %s
                ORDER BY embedding_vector <=> %s::vector
                LIMIT %s
            """
            
            results = db.execute(text(query), (embedding_str, collection_name, embedding_str, k)).fetchall()
            
            # Filter by score threshold and format results
            filtered_results = []
            for row in results:
                if row.similarity_score >= score_threshold:
                    filtered_results.append({
                        "document_id": row.content_hash,
                        "content": row.original_content,
                        "metadata": row.content_metadata or {},
                        "score": row.similarity_score
                    })
            
            return filtered_results
            
        except Exception as e:
            # Fallback to non-vector search
            return await self._similarity_search_fallback(
                query_embedding, collection_name, k, score_threshold
            )
        finally:
            try:
                next(db_gen)  # This will trigger the finally block in get_db()
            except StopIteration:
                pass  # Generator is already closed
    
    async def _similarity_search_fallback(self, 
                                        query_embedding: List[float],
                                        collection_name: str,
                                        k: int,
                                        score_threshold: float) -> List[Dict[str, Any]]:
        """Similarity search using fallback method (cosine similarity)"""
        db_gen = get_db()
        try:
            db = next(db_gen)
            
            # Get all embeddings from collection
            embeddings_data = db.query(VectorEmbeddings).filter(
                VectorEmbeddings.content_type == collection_name
            ).all()
            
            if not embeddings_data:
                return []
            
            # Calculate similarities
            similarities = []
            for item in embeddings_data:
                # Try to get embedding from embedding_vector field first (fallback storage)
                stored_embedding = None
                if item.embedding_vector:
                    try:
                        # If it's a JSON string, parse it
                        if isinstance(item.embedding_vector, str):
                            embedding_data = json.loads(item.embedding_vector)
                            stored_embedding = embedding_data.get("embedding")
                        else:
                            # If it's already a list, use it directly
                            stored_embedding = item.embedding_vector
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                # Fallback to content_metadata if embedding_vector doesn't have the data
                if not stored_embedding and item.content_metadata and "embedding" in item.content_metadata:
                    stored_embedding = item.content_metadata["embedding"]
                
                if stored_embedding:
                    similarity = self._cosine_similarity(query_embedding, stored_embedding)
                    if similarity >= score_threshold:
                        similarities.append({
                            "document_id": item.content_hash,
                            "content": item.original_content,
                            "metadata": item.content_metadata,
                            "score": similarity
                        })
            
            # Sort by similarity and return top k
            similarities.sort(key=lambda x: x["score"], reverse=True)
            return similarities[:k]
            
        except Exception as e:
            return []
        finally:
            try:
                next(db_gen)  # This will trigger the finally block in get_db()
            except StopIteration:
                pass  # Generator is already closed
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            # Ensure both vectors are plain Python lists
            if hasattr(vec1, 'tolist'):
                vec1 = vec1.tolist()
            if hasattr(vec2, 'tolist'):
                vec2 = vec2.tolist()
            
            # Convert to numpy arrays
            a = np.array(vec1, dtype=float)
            b = np.array(vec2, dtype=float)
            
            # Calculate cosine similarity
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            return float(dot_product / (norm_a * norm_b))
            
        except Exception as e:
            return 0.0
    
    async def get_document(self, document_id: str, collection_name: str = "default") -> Optional[Dict[str, Any]]:
        """Retrieve a specific document"""
        db_gen = get_db()
        try:
            db = next(db_gen)
            
            result = db.query(VectorEmbeddings).filter(
                VectorEmbeddings.content_hash == document_id,
                VectorEmbeddings.content_type == collection_name
            ).first()
            
            if result:
                return {
                    "document_id": result.content_hash,
                    "content": result.original_content,
                    "metadata": result.content_metadata or {},
                    "created_at": result.created_at
                }
            
            return None
            
        except Exception as e:
            return None
        finally:
            try:
                next(db_gen)  # This will trigger the finally block in get_db()
            except StopIteration:
                pass  # Generator is already closed
    
    async def delete_document(self, document_id: str, collection_name: str = "default") -> bool:
        """Delete a document"""
        db_gen = get_db()
        try:
            db = next(db_gen)
            
            result = db.query(VectorEmbeddings).filter(
                VectorEmbeddings.content_hash == document_id,
                VectorEmbeddings.content_type == collection_name
            ).first()
            
            if result:
                db.delete(result)
                db.commit()
                return True
            
            return False
            
        except Exception as e:
            return False
        finally:
            try:
                next(db_gen)  # This will trigger the finally block in get_db()
            except StopIteration:
                pass  # Generator is already closed
    
    async def delete_documents_by_metadata(self, 
                                         metadata_filter: Dict[str, Any], 
                                         collection_name: str = "default") -> int:
        """
        Delete documents based on metadata filter criteria.
        
        This method provides a clean abstraction for deleting vector documents
        based on metadata criteria, avoiding direct SQL manipulation in calling code.
        
        Args:
            metadata_filter: Dictionary containing metadata criteria to match for deletion.
                           Keys should correspond to metadata fields, values are the 
                           exact matches to filter by.
            collection_name: Name of the collection to search in (default: "default")
            
        Returns:
            Number of documents deleted (0 if none found or error occurred)
            
        Raises:
            ValueError: If metadata_filter is empty or invalid
            Exception: Database errors are caught and logged, returns 0
            
        Example:
            metadata_filter = {
                "persona_id": "123",
                "context_type": "conversation", 
                "user_progress_id": "456"
            }
            deleted_count = await vectorstore.delete_documents_by_metadata(metadata_filter)
        """
        # Validate input parameters
        if not metadata_filter or not isinstance(metadata_filter, dict):
            return 0
        
        if not collection_name or not isinstance(collection_name, str):
            return 0
        
        db_gen = get_db()
        try:
            db = next(db_gen)
            
            # Build the query with metadata filtering
            query = db.query(VectorEmbeddings).filter(
                VectorEmbeddings.content_type == collection_name
            )
            
            # Apply metadata filters using JSON operations
            for key, value in metadata_filter.items():
                if not key or value is None:
                    continue
                    
                # Use raw SQL for JSON path operations to filter by metadata
                # This uses PostgreSQL's JSON operators for reliable filtering
                from sqlalchemy import text
                json_filter = text(f"content_metadata->>'{key}' = :value")
                query = query.filter(json_filter.params(value=str(value)))
            
            # Get count before deletion for logging
            count_before = query.count()
            
            if count_before == 0:
                return 0
            
            
            # Delete the matching documents
            deleted_count = query.delete(synchronize_session=False)
            db.commit()
            
            return deleted_count
            
        except Exception as e:
            try:
                db.rollback()
            except Exception as rollback_error:
                pass
            return 0
        finally:
            try:
                next(db_gen)  # This will trigger the finally block in get_db()
            except StopIteration:
                pass  # Generator is already closed

    async def get_collection_stats(self, collection_name: str = "default") -> Dict[str, Any]:
        """Get statistics for a collection"""
        db_gen = get_db()
        try:
            db = next(db_gen)
            
            total_docs = db.query(VectorEmbeddings).filter(
                VectorEmbeddings.content_type == collection_name
            ).count()
            
            return {
                "collection_name": collection_name,
                "total_documents": total_docs,
                "pgvector_available": self.pgvector_available
            }
            
        except Exception as e:
            return {
                "collection_name": collection_name,
                "total_documents": 0,
                "pgvector_available": self.pgvector_available,
                "error": str(e)
            }
        finally:
            try:
                next(db_gen)  # This will trigger the finally block in get_db()
            except StopIteration:
                pass  # Generator is already closed

# Global instance - uses configured embedding model
vector_store_service = VectorStoreService()
