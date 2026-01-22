#!/usr/bin/env python3
"""
Helper script to query Vertex AI using direct API (no LangChain needed!)
This matches the approach used in upload_vectors_direct.py
"""
import sys
import json
import os
import warnings
from pathlib import Path

# Suppress warnings that interfere with JSON output
# Redirect warnings to stderr so they don't corrupt JSON output
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

# Fix DNS resolution issue on local machines (Mac/Linux)
# Use native DNS resolver instead of c-ares to avoid gRPC DNS failures
# This is especially important for local development outside Google Cloud Shell
os.environ['GRPC_DNS_RESOLVER'] = 'native'

# Import config from crawler directory (webapp config was removed)
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    VERTEX_PROJECT_ID,
    VERTEX_LOCATION,
    VERTEX_INDEX_ID,
    VERTEX_INDEX_ENDPOINT,
    GOOGLE_APPLICATION_CREDENTIALS
)

# IMPORTANT: Set credentials BEFORE importing Google Cloud modules
# Google Cloud libraries read GOOGLE_APPLICATION_CREDENTIALS at import time
if GOOGLE_APPLICATION_CREDENTIALS:
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_APPLICATION_CREDENTIALS

def generate_natural_answer(question: str, context_chunks: list) -> str:
    """
    Generate a natural answer using LLM based on retrieved context chunks
    
    Args:
        question: The user's question
        context_chunks: List of retrieved text chunks with metadata
    
    Returns:
        Natural answer string
    """
    if not context_chunks:
        return "I couldn't find relevant information to answer your question."
    
    # Combine context chunks into a single context string
    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        text = chunk.get("text", "").strip()
        if text:
            context_parts.append(f"[Source {i}]\n{text}")
    
    if not context_parts:
        return "I couldn't find relevant information to answer your question."
    
    context = "\n\n".join(context_parts)
    
    # Create a prompt for natural answer generation
    prompt = f"""You are a helpful assistant that answers questions based on the provided context documents.

Your task is to provide a clear, natural, and comprehensive answer to the user's question using ONLY the information from the context provided below. 

Guidelines:
- Write in a natural, conversational tone
- Synthesize information from multiple sources when relevant
- If the context doesn't contain enough information, say so
- Don't quote the source text verbatim - paraphrase and explain naturally
- Use proper grammar and complete sentences
- Be concise but thorough

User's Question: {question}

Context Documents:
{context}

Please provide a natural, well-written answer to the question based on the context above:"""
    
    try:
        # Try to use Gemini model (recommended)
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel, GenerationConfig
            from vertexai.generative_models import HarmCategory, HarmBlockThreshold
            
            vertexai.init(project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION)
            model = GenerativeModel("gemini-1.5-flash")
            
            # Configure generation to allow longer responses
            generation_config = GenerationConfig(
                max_output_tokens=8192,  # Increased from default to allow complete answers
                temperature=0.2,
                top_p=0.8,
                top_k=40
            )
            
            # Generate with safety settings that allow longer responses
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            response = model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # Get the full text - handle both single and multi-part responses
            if hasattr(response, 'text'):
                answer = response.text.strip()
            elif hasattr(response, 'candidates') and response.candidates:
                # Handle multi-part responses
                answer_parts = []
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'text'):
                                answer_parts.append(part.text)
                answer = ' '.join(answer_parts).strip()
            else:
                answer = str(response).strip()
            
            # Ensure we have a complete answer
            if not answer:
                answer = "I couldn't generate an answer based on the available information."
            
            # Log the full answer for debugging
            import logging
            import sys
            logging.basicConfig(level=logging.INFO)
            logger = logging.getLogger(__name__)
            
            # Log to both file and stderr
            logger.info(f"=== FULL NATURAL ANSWER (Length: {len(answer)} chars) ===")
            logger.info(answer)
            logger.info("=== END OF NATURAL ANSWER ===")
            
            # Also print to stderr for immediate visibility
            print(f"\n=== FULL NATURAL ANSWER (Length: {len(answer)} chars) ===", file=sys.stderr)
            print(answer, file=sys.stderr)
            print("=== END OF NATURAL ANSWER ===\n", file=sys.stderr)
            
            return answer
            
        except ImportError:
            # Fallback to PaLM/Chat model
            try:
                from vertexai.language_models import TextGenerationModel
                
                model = TextGenerationModel.from_pretrained("text-bison@001")
                response = model.predict(
                    prompt,
                    temperature=0.2,
                    max_output_tokens=1024,
                    top_p=0.8,
                    top_k=40
                )
                
                answer = response.text.strip()
                return answer if answer else "I couldn't generate an answer based on the available information."
                
            except ImportError:
                # Last resort: return first chunk's text (not ideal but works)
                return context_chunks[0].get("text", "No answer available.")
                
    except Exception as e:
        # If LLM generation fails, return a synthesized version of the chunks
        # This is a fallback - better than nothing
        combined_text = " ".join([chunk.get("text", "") for chunk in context_chunks[:3] if chunk.get("text")])
        if combined_text:
            # Simple cleanup
            combined_text = " ".join(combined_text.split())
            return combined_text[:500] + "..." if len(combined_text) > 500 else combined_text
        return "I couldn't generate an answer based on the available information."


def query_vertex(question: str, top_k: int = 3, generate_answer: bool = True):
    """Query Vertex AI using direct API (no LangChain)"""
    try:
        from google.cloud import aiplatform
        from google.cloud.aiplatform.matching_engine import MatchingEngineIndexEndpoint
        
        # Try different import paths for TextEmbeddingModel
        use_langchain_embeddings = False
        TextEmbeddingModel = None
        VertexAIEmbeddings = None
        
        try:
            from vertexai.language_models import TextEmbeddingModel
        except ImportError:
            try:
                from vertexai.preview.language_models import TextEmbeddingModel
            except ImportError:
                # Fallback to LangChain if direct API not available
                from langchain_google_vertexai import VertexAIEmbeddings
                use_langchain_embeddings = True
        
        # Initialize Vertex AI
        aiplatform.init(
            project=VERTEX_PROJECT_ID,
            location=VERTEX_LOCATION
        )
        
        # Generate embedding for the question
        if use_langchain_embeddings:
            # Fallback to LangChain
            embeddings_model = VertexAIEmbeddings(
                model_name="text-embedding-005",
                project=VERTEX_PROJECT_ID,
                location=VERTEX_LOCATION
            )
            query_embedding = embeddings_model.embed_query(question)
        else:
            # Use direct Vertex AI API
            model = TextEmbeddingModel.from_pretrained("text-embedding-005")
            embeddings = model.get_embeddings([question])
            query_embedding = embeddings[0].values
        
        # Connect to the index endpoint
        endpoint_name = f"projects/{VERTEX_PROJECT_ID}/locations/{VERTEX_LOCATION}/indexEndpoints/{VERTEX_INDEX_ENDPOINT}"
        endpoint = MatchingEngineIndexEndpoint(index_endpoint_name=endpoint_name)
        
        # Get the deployed index ID (usually "deployed_index_0" or from endpoint)
        deployed_index_id = None
        try:
            # Try to get deployed index from endpoint
            endpoint_resource = endpoint._gca_resource
            if hasattr(endpoint_resource, 'deployed_indexes') and endpoint_resource.deployed_indexes:
                deployed_index_id = endpoint_resource.deployed_indexes[0].id
            else:
                # Default to common deployed index ID
                deployed_index_id = "deployed_index_0"
        except:
            deployed_index_id = "deployed_index_0"
        
        # Query the index
        # queries must be a list of lists (list of query vectors)
        neighbors = endpoint.find_neighbors(
            deployed_index_id=deployed_index_id,
            queries=[query_embedding],  # List of query vectors
            num_neighbors=top_k
        )
        
        # Format results
        formatted_results = []
        if neighbors and len(neighbors) > 0:
            neighbor_list = neighbors[0]  # First query result (list of MatchNeighbor objects)
            for neighbor in neighbor_list:
                # MatchNeighbor has: id, distance, restricts
                datapoint_id = neighbor.id
                distance = neighbor.distance
                
                # Get metadata from restricts (if available)
                metadata = {}
                if hasattr(neighbor, 'restricts') and neighbor.restricts:
                    for restrict in neighbor.restricts:
                        namespace = restrict.namespace
                        # Get allow_list values
                        if hasattr(restrict, 'allow_list') and restrict.allow_list:
                            metadata[namespace] = restrict.allow_list[0] if restrict.allow_list else None
                
                # Note: The actual text content is stored in the index but not returned by find_neighbors
                # We need to look it up from the original chunks.json or vectors.json
                result = {
                    "text": f"Datapoint ID: {datapoint_id}",  # Will be enriched below
                    "metadata": metadata,
                    "score": float(distance),
                    "datapoint_id": datapoint_id
                }
                formatted_results.append(result)
        
        # Try to enrich results with actual text from chunks.json
        formatted_results = enrich_with_text(formatted_results)
        
        # Generate natural answer if requested
        if generate_answer and formatted_results:
            try:
                natural_answer = generate_natural_answer(question, formatted_results)
                # Add the natural answer as the first result with a special flag
                return {
                    "answer": natural_answer,
                    "sources": formatted_results
                }
            except Exception as e:
                # If answer generation fails, still return the chunks
                # Log error but don't fail completely
                import sys
                print(f"Warning: Could not generate natural answer: {e}", file=sys.stderr)
                return formatted_results
        
        return formatted_results
        
    except ImportError as e:
        return {"error": f"Import error: {str(e)}. Install: pip install google-cloud-aiplatform vertexai"}
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return {"error": f"Query failed: {str(e)}\nDetails: {error_details}"}


def enrich_with_text(results):
    """Enrich results with actual text from chunks.json or vectors.json"""
    if not results:
        return results
    
    # Try to find chunks.json or vectors.json
    # In GCS: chunks.json in base path, vectors.json in output/ folder
    # Try multiple possible locations
    script_dir = Path(__file__).parent
    base_dir = Path.cwd()
    
    # Possible locations for chunks.json (in base path)
    chunks_locations = [
        base_dir / "chunks.json",  # Current directory (GCS structure)
        script_dir / "chunks.json",  # Same directory as script
        script_dir.parent / "crawler" / "output" / "chunks.json",  # Local dev
        Path("/home/asaifulas/chunks.json"),  # GCS home directory
    ]
    
    # Possible locations for vectors.json (in output/ folder)
    vectors_locations = [
        base_dir / "output" / "vectors.json",  # Current directory/output (GCS structure)
        script_dir / "output" / "vectors.json",  # Script directory/output
        base_dir / "vectors.json",  # Also check base path
        script_dir.parent / "crawler" / "output" / "vectors.json",  # Local dev
        Path("/home/asaifulas/output/vectors.json"),  # GCS home/output
    ]
    
    chunks_file = None
    vectors_file = None
    
    # Find chunks.json
    for path in chunks_locations:
        if path.exists():
            chunks_file = path
            break
    
    # Find vectors.json
    for path in vectors_locations:
        if path.exists():
            vectors_file = path
            break
    
    # Load chunks or vectors to map datapoint_id to text
    text_map = {}
    metadata_map = {}
    
    # Try vectors.json first (has exact datapoint IDs)
    # ID format: doc_{chunk_idx}_{page}_{hash}
    if vectors_file and vectors_file.exists():
        try:
            with open(vectors_file, 'r', encoding='utf-8') as f:
                vectors = json.load(f)
                for vec in vectors:
                    vec_id = vec.get("id", "")
                    embedding_metadata = vec.get("embedding_metadata", {})
                    text = embedding_metadata.get("text", "")
                    if vec_id:
                        if text:
                            text_map[vec_id] = text
                        # Store full metadata
                        metadata_map[vec_id] = embedding_metadata
        except Exception:
            pass  # Silently fail - vectors.json might not exist
    
    # Try chunks.json as fallback
    # Parse ID format: doc_{chunk_idx}_{page}_{hash}
    if not text_map and chunks_file and chunks_file.exists():
        try:
            with open(chunks_file, 'r', encoding='utf-8') as f:
                chunks = json.load(f)
                
                # Parse datapoint IDs and match with chunks
                for result in results:
                    datapoint_id = result.get("datapoint_id", "")
                    if datapoint_id in text_map:
                        continue  # Already found in vectors.json
                    
                    # Parse ID: doc_{chunk_idx}_{page}_{hash}
                    # Example: doc_3_4_49864 -> chunk_idx=3, page=4
                    try:
                        parts = datapoint_id.split("_")
                        if len(parts) >= 3 and parts[0] == "doc":
                            chunk_idx = int(parts[1])
                            page = int(parts[2])
                            
                            # Match by chunk index
                            if 0 <= chunk_idx < len(chunks):
                                chunk = chunks[chunk_idx]
                                # Verify page matches (optional check)
                                if chunk.get("page", 0) == page:
                                    text = chunk.get("text", "")
                                    if text:
                                        text_map[datapoint_id] = text
                                        metadata_map[datapoint_id] = chunk
                    except (ValueError, IndexError):
                        # ID format doesn't match, skip
                        pass
        except Exception:
            pass  # Silently fail - chunks.json might not exist
    
    # Enrich results with text and metadata
    for result in results:
        datapoint_id = result.get("datapoint_id", "")
        
        # Get text from map
        if datapoint_id in text_map:
            result["text"] = text_map[datapoint_id]
        
        # Merge metadata
        if datapoint_id in metadata_map:
            existing_metadata = result.get("metadata", {})
            # Update with metadata from vectors/chunks
            for key, value in metadata_map[datapoint_id].items():
                if key not in existing_metadata or not existing_metadata[key]:
                    existing_metadata[key] = value
            result["metadata"] = existing_metadata
        
        # If still no text, try metadata
        if result["text"].startswith("Datapoint ID:") and "text" in result.get("metadata", {}):
            result["text"] = result["metadata"]["text"]
    
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Question required"}), file=sys.stdout)
        sys.exit(1)
    
    question = sys.argv[1]
    top_k = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    
    try:
        results = query_vertex(question, top_k)
        # Only output JSON to stdout (for PHP to parse)
        # Any errors should already be in the results dict
        print(json.dumps(results, indent=2), file=sys.stdout)
    except Exception as e:
        # If something goes wrong, output error as JSON
        error_result = {
            "error": f"Unexpected error: {str(e)}"
        }
        print(json.dumps(error_result, indent=2), file=sys.stdout)
        sys.exit(1)
