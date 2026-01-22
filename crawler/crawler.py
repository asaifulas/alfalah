#!/usr/bin/env python3
"""
Main crawler script for extracting content from various sources
and uploading to Vertex AI vector store
"""
import argparse
import json
import os
import sys
import time
import datetime
from pathlib import Path
from typing import List, Dict

# IMPORTANT: Set GRPC DNS resolver for local work
os.environ['GRPC_DNS_RESOLVER'] = 'native'

from config import (
    SOURCES_FILE, 
    CHUNKS_FILE, 
    OUTPUT_DIR,
    VERTEX_PROJECT_ID,
    VERTEX_LOCATION,
    VERTEX_INDEX_ID,
    VERTEX_INDEX_ENDPOINT,
    GOOGLE_APPLICATION_CREDENTIALS
)
from utils import (
    process_source, 
    save_chunks, 
    logger,
    crawl_page,
    crawl_paginated_pdfs
)

# IMPORTANT: Set credentials BEFORE importing Google Cloud modules
if GOOGLE_APPLICATION_CREDENTIALS:
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_APPLICATION_CREDENTIALS


def load_sources(sources_file: Path = None) -> List[Dict]:
    """
    Load sources from resources/sources.json
    
    Args:
        sources_file: Optional path to sources file (default: SOURCES_FILE)
    
    Returns:
        List of source dictionaries
    """
    if sources_file is None:
        sources_file = SOURCES_FILE
    
    try:
        with open(sources_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("sources", [])
    except FileNotFoundError:
        logger.error(f"Sources file not found: {sources_file}")
        logger.info("Please create resources/sources.json with your crawl sources")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in sources file: {e}")
        return []


def extract_pdf_urls_from_source(source: Dict[str, any]) -> List[str]:
    """
    Extract PDF URLs from a source without processing the PDFs
    
    Args:
        source: Source dictionary with 'type', 'url', and other metadata
    
    Returns:
        List of PDF URLs
    """
    source_type = source.get("type", "").lower()
    url = source.get("url", "")
    
    pdf_urls = []
    
    logger.info(f"Extracting PDF URLs from source: {source_type} - {url}")
    
    if source_type == "pdf_in_page":
        # Extract PDF links from page
        pagination = source.get("pagination", {})
        use_js = source.get("use_javascript", False)
        js_config = source.get("javascript", {})
        
        if pagination.get("enabled", False):
            # Handle paginated table/list
            pdf_selector = source.get("pdf_selector", "a[href$='.pdf']")
            pdf_urls = crawl_paginated_pdfs(url, pdf_selector, pagination, use_js=use_js, js_config=js_config)
        else:
            # Single page extraction
            selectors = source.get("selectors", {})
            if not selectors.get("pdf_links"):
                selectors["pdf_links"] = source.get("pdf_selector", "a[href$='.pdf']")
            _, pdf_urls = crawl_page(url, selectors, use_js=use_js, js_config=js_config)
    
    elif source_type == "page":
        # Extract PDF links from page
        use_js = source.get("use_javascript", False)
        js_config = source.get("javascript", {})
        _, pdf_urls = crawl_page(url, source.get("selectors", {}), use_js=use_js, js_config=js_config)
    
    elif source_type == "pdf":
        # Direct PDF URL
        pdf_urls = [url]
    
    logger.info(f"Found {len(pdf_urls)} PDF URLs from source: {url}")
    return pdf_urls


def save_pdf_urls(pdf_urls: List[str], output_file: Path = None) -> Path:
    """
    Save PDF URLs to a JSON file
    
    Args:
        pdf_urls: List of PDF URLs
        output_file: Path to output file (default: OUTPUT_DIR/pdf_urls.json)
    
    Returns:
        Path to saved file
    """
    if output_file is None:
        output_file = OUTPUT_DIR / "pdf_urls.json"
    
    # Create a structured format with metadata
    data = {
        "total_urls": len(pdf_urls),
        "urls": pdf_urls
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved {len(pdf_urls)} PDF URLs to {output_file}")
    return output_file


def generate_embeddings(chunks: List[Dict], batch_size: int = 100) -> List[Dict]:
    """
    Generate embeddings from chunks (similar to generate_embeddings.py)
    
    Args:
        chunks: List of chunk dictionaries
        batch_size: Batch size for embedding generation
    
    Returns:
        List of vector records with embeddings
    """
    if not VERTEX_PROJECT_ID:
        logger.warning("VERTEX_PROJECT_ID not set. Skipping embedding generation.")
        return []
    
    try:
        # Try new package first, fallback to old
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            USE_NEW_EMBEDDINGS = True
            logger.info("   ✅ Using langchain-google-genai (new package)")
        except ImportError:
            from langchain_google_vertexai import VertexAIEmbeddings
            USE_NEW_EMBEDDINGS = False
            logger.info("   ⚠️  Using langchain-google-vertexai (deprecated)")
        
        from google.cloud import aiplatform
        import google.auth
    except ImportError as e:
        logger.error(f"Missing required package: {e}")
        logger.error("Install with: pip install langchain-google-genai google-cloud-aiplatform")
        return []
    
    # Set up authentication
    logger.info(f"\n🔧 Setting up authentication...")
    try:
        credentials, project = google.auth.default()
        logger.info(f"   ✅ Authentication successful")
    except Exception as e:
        logger.error(f"   ❌ Authentication failed: {e}")
        return []
    
    # Initialize Vertex AI
    try:
        aiplatform.init(project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION)
        logger.info(f"   ✅ Vertex AI initialized")
    except Exception as e:
        logger.warning(f"   ⚠️  Vertex AI init warning: {e}")
    
    # Initialize embeddings
    logger.info(f"\n🔧 Initializing embeddings model...")
    logger.info(f"   Model: text-embedding-005")
    
    try:
        if USE_NEW_EMBEDDINGS:
            embeddings = GoogleGenerativeAIEmbeddings(
                model="text-embedding-005",
                project=VERTEX_PROJECT_ID,
                location=VERTEX_LOCATION
            )
        else:
            embeddings = VertexAIEmbeddings(
                model_name="text-embedding-005",
                project=VERTEX_PROJECT_ID,
                location=VERTEX_LOCATION
            )
        
        # Test embeddings
        test_embedding = embeddings.embed_query("test")
        logger.info(f"   ✅ Embeddings model initialized ({len(test_embedding)} dimensions)")
    except Exception as e:
        logger.error(f"❌ Error initializing embeddings: {e}")
        return []
    
    # Process chunks and generate embeddings
    logger.info(f"\n📝 Generating embeddings...")
    logger.info(f"   Total chunks: {len(chunks)}")
    logger.info(f"   Batch size: {batch_size}")
    
    vectors = []
    skipped = 0
    total_batches = (len(chunks) + batch_size - 1) // batch_size
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(chunks))
        batch_chunks = chunks[start_idx:end_idx]
        
        logger.info(f"\n📤 Processing batch {batch_num + 1}/{total_batches} ({len(batch_chunks)} chunks)...")
        
        # Prepare texts
        texts = []
        chunk_indices = []
        
        for i, chunk in enumerate(batch_chunks):
            text = chunk.get("text", "").strip()
            if not text:
                skipped += 1
                continue
            
            texts.append(text)
            chunk_indices.append(start_idx + i)
        
        if not texts:
            logger.warning(f"   ⚠️  No valid texts in batch, skipping...")
            continue
        
        # Generate embeddings
        logger.info(f"   🔄 Generating embeddings for {len(texts)} texts...")
        try:
            embedding_vectors = embeddings.embed_documents(texts)
            logger.info(f"   ✅ Generated {len(embedding_vectors)} embeddings")
        except Exception as e:
            logger.error(f"   ❌ Error generating embeddings: {e}")
            continue
        
        # Create vector records
        for i, (chunk_idx, text, embedding) in enumerate(zip(chunk_indices, texts, embedding_vectors)):
            chunk = chunks[chunk_idx]
            
            vector_record = {
                "id": f"doc_{chunk_idx}_{chunk.get('page', 0)}_{abs(hash(text[:50])) % 100000}",
                "embedding": embedding,
                "embedding_metadata": {
                    "text": text,
                    "url": str(chunk.get("url", ""))[:500],
                    "page": int(chunk.get("page", 0)) if chunk.get("page") is not None else 0,
                    "source_type": str(chunk.get("source_type", ""))[:100],
                    "source_url": str(chunk.get("source_url", ""))[:500],
                }
            }
            
            # Add optional fields
            if chunk.get("description"):
                vector_record["embedding_metadata"]["description"] = str(chunk.get("description", ""))[:500]
            if chunk.get("local_source"):
                vector_record["embedding_metadata"]["local_source"] = str(chunk.get("local_source", ""))[:200]
            if chunk.get("pdf_url"):
                vector_record["embedding_metadata"]["pdf_url"] = str(chunk.get("pdf_url", ""))[:500]
            
            vectors.append(vector_record)
        
        logger.info(f"   ✅ Processed {len(vectors)} vectors so far")
    
    if skipped > 0:
        logger.warning(f"   ⚠️  Skipped {skipped} chunks with empty text")
    
    logger.info(f"\n✅ Generated {len(vectors)} embeddings")
    return vectors


def upload_vectors_to_vertex(vectors: List[Dict], batch_size: int = 100) -> bool:
    """
    Upload vectors directly to Vertex AI (similar to upload_vectors_direct.py)
    
    Args:
        vectors: List of vector records with embeddings
        batch_size: Number of vectors per batch
    
    Returns:
        True if upload successful, False otherwise
    """
    if not VERTEX_PROJECT_ID:
        logger.warning("VERTEX_PROJECT_ID not set. Skipping Vertex AI upload.")
        return False
    
    if not VERTEX_INDEX_ID or not VERTEX_INDEX_ENDPOINT:
        logger.warning("VERTEX_INDEX_ID or VERTEX_INDEX_ENDPOINT not set. Cannot upload to Vertex AI.")
        return False
    
    try:
        from google.cloud import aiplatform
        from google.cloud import storage
        from google.cloud.aiplatform import MatchingEngineIndex
        from google.cloud.aiplatform.matching_engine import MatchingEngineIndexEndpoint
    except ImportError as e:
        logger.error(f"Missing required package: {e}")
        logger.error("Install with: pip install google-cloud-aiplatform google-cloud-storage")
        return False
    
    GCS_BUCKET = os.getenv("GCS_BUCKET_NAME", "")
    
    # Initialize Vertex AI
    logger.info(f"\n🔧 Initializing Vertex AI...")
    logger.info(f"   Project: {VERTEX_PROJECT_ID}")
    logger.info(f"   Location: {VERTEX_LOCATION}")
    
    try:
        aiplatform.init(project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION)
    except Exception as e:
        logger.error(f"❌ Error initializing Vertex AI: {e}")
        return False
    
    # Get index and endpoint
    logger.info(f"🔧 Connecting to Vector Search...")
    logger.info(f"   Index ID: {VERTEX_INDEX_ID}")
    logger.info(f"   Endpoint ID: {VERTEX_INDEX_ENDPOINT}")
    
    try:
        index_name = f"projects/{VERTEX_PROJECT_ID}/locations/{VERTEX_LOCATION}/indexes/{VERTEX_INDEX_ID}"
        endpoint_name = f"projects/{VERTEX_PROJECT_ID}/locations/{VERTEX_LOCATION}/indexEndpoints/{VERTEX_INDEX_ENDPOINT}"
        
        index = MatchingEngineIndex(index_name=index_name)
        endpoint = MatchingEngineIndexEndpoint(index_endpoint_name=endpoint_name)
        
        logger.info("✅ Connected to Vector Search successfully")
    except Exception as e:
        logger.error(f"❌ Error connecting to Vector Search: {e}")
        return False
    
    # Check if index supports streaming updates
    logger.info(f"\n🔍 Checking index update method...")
    supports_streaming = False
    try:
        index_resource = index._gca_resource
        if hasattr(index_resource, 'metadata') and index_resource.metadata:
            config = index_resource.metadata.get('config', {})
            if config.get('streamUpdate', False):
                supports_streaming = True
                logger.info(f"   ✅ Index supports streaming updates")
            else:
                logger.info(f"   ℹ️  Index uses batch updates (streaming not enabled)")
        else:
            try:
                index.upsert_datapoints(datapoints=[])
                supports_streaming = True
                logger.info(f"   ✅ Index supports streaming updates")
            except Exception:
                logger.info(f"   ℹ️  Index uses batch updates (streaming not enabled)")
                supports_streaming = False
    except Exception as e:
        logger.warning(f"   ⚠️  Could not determine update method, will try streaming first: {e}")
        supports_streaming = True
    
    # Upload vectors
    logger.info(f"\n🚀 Starting upload...")
    logger.info(f"   Total vectors: {len(vectors)}")
    logger.info(f"   Batch size: {batch_size}")
    logger.info(f"   Update method: {'Streaming' if supports_streaming else 'Batch (via GCS)'}")
    total_batches = (len(vectors) + batch_size - 1) // batch_size
    logger.info(f"   Total batches: {total_batches}")
    logger.info("="*60)
    
    total_uploaded = 0
    
    if supports_streaming:
        # Use streaming updates
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(vectors))
            batch_vectors = vectors[start_idx:end_idx]
            
            logger.info(f"\n📤 Uploading batch {batch_num + 1}/{total_batches} ({len(batch_vectors)} vectors)...")
            
            # Prepare datapoints
            datapoints = []
            for vec in batch_vectors:
                datapoint = {
                    "datapoint_id": vec["id"],
                    "feature_vector": vec["embedding"],
                    "restricts": []
                }
                
                # Add metadata as restricts
                metadata = vec.get("embedding_metadata", {})
                if metadata:
                    restricts = []
                    for key, value in metadata.items():
                        if value:
                            restricts.append({
                                "namespace": key,
                                "allow_list": [str(value)]
                            })
                    datapoint["restricts"] = restricts
                
                datapoints.append(datapoint)
            
            # Upload batch
            try:
                logger.info(f"   ⏳ Submitting batch (this may take 30-60+ seconds)...")
                start_time = time.time()
                
                index.upsert_datapoints(datapoints=datapoints)
                
                elapsed = time.time() - start_time
                total_uploaded += len(datapoints)
                logger.info(f"   ✅ Batch {batch_num + 1} uploaded successfully ({total_uploaded}/{len(vectors)} total)")
                logger.info(f"   ⏱️  Time taken: {elapsed:.1f} seconds")
                
                # Add delay between batches
                if batch_num < total_batches - 1:
                    delay = 60
                    logger.info(f"   ⏸️  Waiting {delay} seconds before next batch...")
                    time.sleep(delay)
                    
            except Exception as e:
                error_str = str(e)
                logger.error(f"   ❌ Batch {batch_num + 1} failed: {e}")
                
                if "StreamUpdate is not enabled" in error_str:
                    logger.info(f"   🔄 Falling back to batch updates via GCS...")
                    supports_streaming = False
                    break
                
                if "429" in error_str or "quota" in error_str.lower():
                    wait_time = 120
                    logger.info(f"   ⏳ Quota limit hit. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    continue
    
    # Use batch updates via GCS (if streaming not supported or failed)
    if not supports_streaming:
        if not GCS_BUCKET:
            logger.error(f"\n❌ Error: Batch updates require GCS_BUCKET_NAME to be set")
            logger.error(f"   Set it in .env file: GCS_BUCKET_NAME='your-bucket-name'")
            return False
        
        logger.info(f"\n📦 Using batch updates via GCS...")
        logger.info(f"   GCS Bucket: {GCS_BUCKET}")
        
        # Prepare JSONL data
        logger.info(f"   📝 Preparing JSONL data...")
        jsonl_lines = []
        for vec in vectors:
            jsonl_obj = {
                "id": vec["id"],
                "embedding": vec["embedding"]
            }
            
            metadata = vec.get("embedding_metadata", {})
            if metadata:
                restricts = []
                for key, value in metadata.items():
                    if value:
                        restricts.append({
                            "namespace": key,
                            "allow": [str(value)]
                        })
                if restricts:
                    jsonl_obj["restricts"] = restricts
            
            jsonl_lines.append(json.dumps(jsonl_obj, ensure_ascii=False))
        
        # Upload to GCS
        logger.info(f"   ☁️  Uploading to GCS...")
        try:
            storage_client = storage.Client(project=VERTEX_PROJECT_ID)
            bucket = storage_client.bucket(GCS_BUCKET)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            gcs_dir = f"vector-updates/{timestamp}"
            gcs_file = f"{gcs_dir}/datapoints.json"
            
            blob = bucket.blob(gcs_file)
            blob.upload_from_string("\n".join(jsonl_lines), content_type="application/json")
            
            gcs_uri = f"gs://{GCS_BUCKET}/{gcs_dir}"
            logger.info(f"   ✅ Uploaded to: {gcs_uri}")
            
            # Trigger batch update
            logger.info(f"   ⏳ Triggering batch update (this may take several minutes)...")
            start_time = time.time()
            operation = index.update_embeddings(
                contents_delta_uri=gcs_uri,
                is_complete_overwrite=False
            )
            
            logger.info(f"   ✅ Batch update operation started")
            logger.info(f"   📋 Operation: {operation.name}")
            total_uploaded = len(vectors)
            
        except Exception as e:
            logger.error(f"   ❌ Batch update failed: {e}")
            return False
    
    # Final summary
    logger.info("\n" + "="*60)
    if total_uploaded == len(vectors):
        logger.info(f"✅ SUCCESS! Uploaded all {total_uploaded} vectors to Vertex AI")
        return True
    elif total_uploaded > 0:
        logger.warning(f"⚠️  PARTIAL: Uploaded {total_uploaded}/{len(vectors)} vectors")
        return True
    else:
        logger.error(f"❌ FAILED: No vectors were uploaded successfully")
        return False


def main(test_mode: bool = False, test_sources_file: Path = None, url_only: bool = False):
    """
    Main crawler function
    
    Args:
        test_mode: If True, skip Vertex AI upload
        test_sources_file: Optional path to test sources file
        url_only: If True, only extract PDF URLs and save them, don't process PDFs
    """
    mode_str = "TEST MODE" if test_mode else "PRODUCTION MODE"
    if url_only:
        mode_str = "URL EXTRACTION MODE"
    logger.info(f"Starting crawler in {mode_str}...")
    
    # Load sources
    sources_file = test_sources_file or SOURCES_FILE
    sources = load_sources(sources_file)
    
    if not sources:
        logger.error("No sources found. Exiting.")
        sys.exit(1)
    
    logger.info(f"Found {len(sources)} sources to process")
    
    if url_only:
        # URL extraction mode - just get PDF URLs
        all_pdf_urls = []
        for i, source in enumerate(sources, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Extracting PDF URLs from source {i}/{len(sources)}")
            logger.info(f"{'='*60}")
            
            try:
                pdf_urls = extract_pdf_urls_from_source(source)
                all_pdf_urls.extend(pdf_urls)
            except Exception as e:
                logger.error(f"Error extracting PDF URLs from source {source.get('url', 'unknown')}: {e}")
                continue
        
        # Save PDF URLs to file
        if all_pdf_urls:
            output_file = OUTPUT_DIR / "pdf_urls.json"
            if test_mode:
                output_file = OUTPUT_DIR / "pdf_urls_test.json"
            
            save_pdf_urls(all_pdf_urls, output_file)
            logger.info(f"\n{'='*60}")
            logger.info(f"Total PDF URLs extracted: {len(all_pdf_urls)}")
            logger.info(f"PDF URLs saved to: {output_file}")
            logger.info(f"{'='*60}")
        else:
            logger.warning("No PDF URLs extracted. Check your sources and try again.")
            sys.exit(1)
    else:
        # Normal mode - process sources and extract content
        all_chunks = []
        for i, source in enumerate(sources, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing source {i}/{len(sources)}")
            logger.info(f"{'='*60}")
            
            try:
                chunks = process_source(source)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(f"Error processing source {source.get('url', 'unknown')}: {e}")
                continue
        
        # Step 1: Save chunks to file
        if all_chunks:
            output_file = CHUNKS_FILE
            if test_mode:
                output_file = Path(CHUNKS_FILE.parent) / "chunks_test.json"
            
            save_chunks(all_chunks, output_file)
            logger.info(f"\n{'='*60}")
            logger.info(f"Step 1: Chunks extracted and saved")
            logger.info(f"Total chunks extracted: {len(all_chunks)}")
            logger.info(f"Chunks saved to: {output_file}")
            logger.info(f"{'='*60}")
            
            # Print summary
            logger.info("\n📊 Summary:")
            logger.info(f"  - Total chunks: {len(all_chunks)}")
            
            # Count by source type
            source_types = {}
            for chunk in all_chunks:
                stype = chunk.get("source_type", "unknown")
                source_types[stype] = source_types.get(stype, 0) + 1
            
            for stype, count in source_types.items():
                logger.info(f"  - {stype}: {count} chunks")
            
            # Generate embeddings and upload to Vertex AI (if configured and not in test mode)
            if not test_mode:
                # Step 2: Generate embeddings from chunks
                logger.info("\n" + "="*60)
                logger.info("Step 2: Generating embeddings from chunks...")
                logger.info("="*60)
                vectors = generate_embeddings(all_chunks, batch_size=100)
                
                if vectors:
                    # Step 3: Upload vectors to Vertex AI
                    logger.info("\n" + "="*60)
                    logger.info("Step 3: Uploading vectors to Vertex AI...")
                    logger.info("="*60)
                    upload_vectors_to_vertex(vectors, batch_size=100)
                else:
                    logger.warning("No vectors generated. Skipping upload.")
            else:
                logger.info("\n✅ Test mode: Skipping embedding generation and Vertex AI upload")
                logger.info(f"   Review output at: {output_file}")
        else:
            logger.warning("No chunks extracted. Check your sources and try again.")
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl sources and extract content")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run in test mode (skip Vertex AI upload)"
    )
    parser.add_argument(
        "--test-sources",
        type=str,
        help="Path to test sources JSON file"
    )
    parser.add_argument(
        "--url-only",
        action="store_true",
        help="Only extract PDF URLs and save them, don't process PDFs"
    )
    
    args = parser.parse_args()
    
    test_sources_path = None
    if args.test_sources:
        test_sources_path = Path(args.test_sources)
        if not test_sources_path.exists():
            logger.error(f"Test sources file not found: {test_sources_path}")
            sys.exit(1)
    
    main(test_mode=args.test, test_sources_file=test_sources_path, url_only=args.url_only)
