# Crawler Workflow Summary

## Overview

This document explains the complete integrated workflow from reading sources to uploading vectors to Vertex AI Vector Search. The `crawler.py` script now handles the entire pipeline in one execution.

---

## 🎯 Complete Integrated Workflow

```
Sources → Extract Text → Chunk Text → Save chunks.json → Generate Embeddings → Upload Vectors to Vertex AI
```

### Step-by-Step Process:

1. **Source Input** (`resources/sources.json`)
   - Define sources: PDFs, web pages, or local files
   - Example: `local_pdf` pointing to a PDF in `resources/data/`
   - Supports: `local_pdf`, `pdf`, `page`, `pdf_in_page` source types

2. **Text Extraction** (`crawler.py` + `utils.py`)
   - **For PDFs**: Uses PyMuPDF to extract text page by page
   - **For Web Pages**: Uses BeautifulSoup/Selenium/Playwright to extract content
   - **For Local Files**: Reads text directly
   - Output: Raw text with page numbers and metadata

3. **Text Chunking** (`utils.py`)
   - Splits long text into smaller chunks (default: 1000 chars, configurable via `CHUNK_SIZE`)
   - Adds overlap between chunks (default: 200 chars, configurable via `CHUNK_OVERLAP`) for context
   - Each chunk includes: `text`, `page`, `url`, `source_type`, `source_url`, `local_source`, `description`
   - Output: List of chunk dictionaries

4. **Save Chunks to JSON** (`crawler.py` - Step 1)
   - Saves all chunks to `output/chunks.json`
   - Format: Array of chunk objects
   - Each chunk has: `text`, `page`, `url`, `source_type`, `source_url`, `local_source`, `description`
   - This file serves as a backup and can be used for reprocessing

5. **Generate Embeddings** (`crawler.py` - Step 2)
   - Reads chunks from memory (or can load from `chunks.json`)
   - Uses Vertex AI Embeddings API (`text-embedding-005` model)
   - Converts each text chunk to a 768-dimensional vector
   - Processes in batches (default: 100 chunks per batch)
   - Creates vector records with: `id`, `embedding`, `embedding_metadata`
   - Output: List of vector records (not saved to disk, kept in memory)

6. **Upload Vectors to Vertex AI** (`crawler.py` - Step 3)
   - Connects to Vertex AI Matching Engine Index Endpoint
   - Supports two upload methods:
     - **Streaming Updates**: Direct upload via `upsert_datapoints()` (faster, real-time)
     - **Batch Updates**: Upload via GCS bucket (for indexes without streaming enabled)
   - Uploads vectors in batches (default: 100 vectors per batch)
   - Handles errors, retries, and quota limits
   - Updates the Vector Search index with all vectors

---

## 📁 What Each Component Does

### 1. `crawler.py` - Main Integrated Crawler Script

**Purpose**: Complete pipeline from source extraction to vector upload

**What it does**:
- ✅ **Step 1: Source Processing**
  - Reads `resources/sources.json` to get list of sources
  - For each source:
    - Processes based on type (`local_pdf`, `pdf`, `page`, `pdf_in_page`, etc.)
    - Extracts text content (PDFs, web pages, local files)
    - Chunks the text (splits into smaller pieces with overlap)
    - Adds metadata (page number, URL, source type, etc.)
  - Saves all chunks to `output/chunks.json`

- ✅ **Step 2: Embedding Generation**
  - Loads chunks from memory
  - Initializes Vertex AI Embeddings model (`text-embedding-005`)
  - Generates embeddings for each chunk in batches
  - Creates vector records with unique IDs and metadata
  - Returns list of vector records

- ✅ **Step 3: Vector Upload**
  - Connects to Vertex AI Matching Engine Index Endpoint
  - Determines if index supports streaming or batch updates
  - Uploads vectors in batches:
    - **Streaming**: Direct upload via `upsert_datapoints()` API
    - **Batch**: Upload to GCS bucket, then trigger index update
  - Handles errors, retries, and provides progress logging

**Output**: 
- `output/chunks.json` - JSON file with all text chunks (Step 1)
- Vectors uploaded directly to Vertex AI Vector Search (Step 3)

**Example chunk structure**:
```json
{
  "page": 1,
  "text": "Issued on: 19 December 2025...",
  "url": "https://www.bnm.gov.my/...",
  "source_type": "local_pdf",
  "source_url": "https://www.bnm.gov.my/...",
  "local_source": "charge_card_and_charge_card-i_PD.pdf",
  "description": "Local PDF file from resources/data folder"
}
```

---

### 2. `generate_embeddings.py` - Standalone Embedding Generator (Optional)

**Purpose**: Generate embeddings from existing `chunks.json` file

**What it does**:
- ✅ Reads `chunks.json` file
- ✅ Generates embeddings using Vertex AI (`text-embedding-005`)
- ✅ Saves vectors to `output/vectors.json`
- ✅ Useful for reprocessing chunks without re-extracting

**When to use**: When you want to regenerate embeddings from existing chunks without re-running the full crawler

---

### 3. `upload_vectors_direct.py` - Standalone Vector Uploader (Optional)

**Purpose**: Upload pre-generated vectors to Vertex AI

**What it does**:
- ✅ Reads `vectors.json` file (from `generate_embeddings.py`)
- ✅ Uploads vectors directly to Vertex AI Matching Engine
- ✅ Supports both streaming and batch update methods
- ✅ Uses Vertex AI API directly (no LangChain/TensorFlow dependencies)

**When to use**: When you want to upload vectors separately, or when using the two-step process (generate embeddings first, then upload)

---

## 🔄 Complete Integrated Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. SOURCE: resources/sources.json                               │
│    - Defines sources: PDFs, web pages, local files              │
│    - Example: {"type": "local_pdf", "url": "file.pdf", ...}    │
└────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. EXTRACTION: crawler.py processes each source                │
│    - PDFs: PyMuPDF extracts text page by page                  │
│    - Web Pages: BeautifulSoup/Selenium/Playwright              │
│    - Local Files: Direct file reading                          │
│    Output: Raw text with page numbers and metadata              │
└────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. CHUNKING: utils.py splits text into chunks                   │
│    - Chunk size: 1000 chars (configurable)                      │
│    - Overlap: 200 chars (configurable)                          │
│    - Chunk 1: chars 0-1000 of page 1                           │
│    - Chunk 2: chars 800-1800 (200 char overlap)                │
│    - Each chunk includes: text, page, url, source_type, etc.   │
└────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. SAVE CHUNKS: crawler.py - Step 1                            │
│    Saves to output/chunks.json:                                 │
│    [                                                             │
│      {                                                           │
│        "page": 1,                                               │
│        "text": "Charge Card and Charge Card-i...",              │
│        "url": "https://...",                                    │
│        "source_type": "local_pdf",                              │
│        "local_source": "file.pdf",                              │
│        ...                                                       │
│      },                                                          │
│      ...                                                         │
│    ]                                                             │
└────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. GENERATE EMBEDDINGS: crawler.py - Step 2                    │
│    - Initialize Vertex AI Embeddings (text-embedding-005)       │
│    - Process chunks in batches (100 per batch)                  │
│    - Convert each chunk text → 768-dim vector                   │
│    - Create vector records:                                     │
│      {                                                           │
│        "id": "doc_0_1_12345",                                  │
│        "embedding": [0.123, -0.456, ..., 0.789],               │
│        "embedding_metadata": {text, url, page, ...}            │
│      }                                                           │
└────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. UPLOAD VECTORS: crawler.py - Step 3                         │
│    - Connect to Vertex AI Matching Engine Index Endpoint        │
│    - Check if streaming updates are supported                   │
│    - Upload method A (Streaming):                                │
│      → Direct upload via upsert_datapoints() API                │
│      → Real-time updates, faster                                │
│    - Upload method B (Batch):                                   │
│      → Upload JSONL to GCS bucket                               │
│      → Trigger index.update_embeddings() operation              │
│      → Long-running async operation                             │
└────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. VERTEX AI VECTOR SEARCH INDEX                                │
│    - Vectors stored in Matching Engine Index                    │
│    - Index is now searchable via query_vertex.py                │
│    - Supports semantic similarity search                        │
│    - Returns top-k most similar chunks                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Concepts

### What are "Chunks"?

Chunks are smaller pieces of text split from the original document. Why?
- **Token limits**: Embedding models have token limits (~2048 tokens)
- **Better search**: Smaller chunks = more precise search results
- **Context**: Overlap between chunks preserves context

**Example**:
```
Original text (5000 chars):
"Charge Card and Charge Card-i. Issued on: 19 December 2025..."

Chunk 1 (chars 0-1000):
"Charge Card and Charge Card-i. Issued on: 19 December 2025..."

Chunk 2 (chars 800-1800):  ← 200 char overlap
"19 December 2025... [continues]"
```

### What are "Embeddings"?

Embeddings are numerical representations of text:
- Text: `"Charge Card and Charge Card-i"`
- Embedding: `[0.123, -0.456, 0.789, ..., 0.234]` (768 numbers)
- Similar texts have similar embeddings
- Used for semantic search (finding similar content)

### What is "Vector Search"?

Vector Search finds documents by comparing embeddings:
1. User query: `"What is a charge card?"`
2. Generate embedding for query
3. Find chunks with similar embeddings
4. Return most similar chunks

---

## 📊 File Formats

### `chunks.json` Format:
```json
[
  {
    "page": 1,
    "text": "Full text content of the chunk...",
    "url": "https://...",
    "source_type": "local_pdf",
    "source_url": "https://...",
    "local_source": "file.pdf",
    "description": "Description"
  },
  ...
]
```

### Vector Record Format (what gets uploaded):
```json
{
  "id": "doc_0_1_12345",
  "embedding": [0.123, -0.456, ..., 0.789],  // 768-dimensional vector
  "embedding_metadata": {
    "text": "Full text content of the chunk...",
    "url": "https://...",
    "page": 1,
    "source_type": "local_pdf",
    "source_url": "https://...",
    "description": "Optional description"
  }
}
```

### Vertex AI Datapoint Format (for upload):
```json
{
  "datapoint_id": "doc_0_1_12345",
  "feature_vector": [0.123, -0.456, ..., 0.789],  // 768 numbers
  "restricts": [
    {
      "namespace": "url",
      "allow_list": ["https://..."]
    },
    {
      "namespace": "page",
      "allow_list": ["1"]
    },
    ...
  ]
}
```

---

## 🚀 Typical Usage

### Option 1: Complete Integrated Workflow (Recommended)

Run the complete pipeline in one command:
```bash
cd crawler
python3 crawler.py
```

**What happens**:
1. ✅ Reads sources from `resources/sources.json`
2. ✅ Extracts text and creates chunks
3. ✅ Saves chunks to `output/chunks.json`
4. ✅ Generates embeddings from chunks
5. ✅ Uploads vectors to Vertex AI Vector Search

**Result**: Complete pipeline executed, vectors are searchable in Vertex AI

### Option 2: Test Mode (Skip Upload)

Test the extraction and chunking without uploading:
```bash
python3 crawler.py --test
```

**Result**: Creates `output/chunks_test.json` but skips embedding generation and upload

### Option 3: Two-Step Process (Advanced)

If you want to separate embedding generation from upload:

**Step 1: Extract and chunk**
```bash
python3 crawler.py --test
```

**Step 2: Generate embeddings**
```bash
python3 generate_embeddings.py output/chunks.json
```

**Step 3: Upload vectors**
```bash
python3 upload_vectors_direct.py output/vectors.json
```

### Option 4: URL Extraction Only

Extract PDF URLs from web pages without processing:
```bash
python3 crawler.py --url-only
```

**Result**: Creates `output/pdf_urls.json` with list of PDF URLs

---

## 🔧 Technical Details

### Embedding Generation Process

1. **Model**: `text-embedding-005` (Vertex AI)
   - Dimensions: 768
   - Max tokens per document: ~2048 tokens
   - Batch limit: 20,000 tokens total per batch

2. **Batch Processing**:
   - Default batch size: 100 chunks
   - Processes chunks in batches to avoid token limits
   - Each batch generates embeddings via `embed_documents()` API

3. **Vector Record Creation**:
   - Unique ID format: `doc_{chunk_idx}_{page}_{hash}`
   - Stores original text in `embedding_metadata` for retrieval
   - Preserves all chunk metadata (url, page, source_type, etc.)

### Vector Upload Process

1. **Streaming Updates** (Preferred):
   - Method: `index.upsert_datapoints(datapoints=[])`
   - Real-time updates to index
   - Faster, immediate availability
   - Requires index with streaming enabled

2. **Batch Updates** (Fallback):
   - Method: Upload JSONL to GCS, then `index.update_embeddings()`
   - Format: JSONL file with datapoints
   - Location: `gs://{bucket}/vector-updates/{timestamp}/datapoints.json`
   - Long-running operation (10-30+ minutes)
   - Used when streaming is not supported

3. **Error Handling**:
   - Automatic retry on quota errors (429)
   - Batch size reduction on token limit errors
   - Continues with next batch on failures
   - Detailed logging for troubleshooting

### Configuration Requirements

**Required Environment Variables** (in `crawler/.env`):
```bash
VERTEX_PROJECT_ID=your-project-id
VERTEX_LOCATION=us-central1
VERTEX_INDEX_ID=your-index-id
VERTEX_INDEX_ENDPOINT=your-endpoint-id
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
GCS_BUCKET_NAME=your-bucket-name  # Required for batch updates
```

**Optional Configuration**:
```bash
CHUNK_SIZE=1000          # Characters per chunk
CHUNK_OVERLAP=200        # Overlap between chunks
MAX_PAGES_PER_PDF=1000   # Limit pages per PDF
```

## ⚠️ Common Issues

1. **"DNS resolution failed" error**
   - **Cause**: Network connectivity or DNS issues
   - **Solution**: Set `GRPC_DNS_RESOLVER=native` (already set in code)

2. **"StreamUpdate is not enabled" error**
   - **Cause**: Index doesn't support streaming updates
   - **Solution**: Script automatically falls back to batch updates via GCS

3. **"Quota exceeded" error**
   - **Cause**: Too many concurrent index update operations
   - **Solution**: Script waits 60-120 seconds between batches automatically

4. **"Token limit" error**
   - **Cause**: Text chunks are too large
   - **Solution**: Script automatically reduces batch size and retries

5. **"GCS_BUCKET_NAME is required" error**
   - **Cause**: Batch updates require GCS bucket
   - **Solution**: Set `GCS_BUCKET_NAME` in `.env` file

---

## 📝 Summary

### `crawler.py` - Integrated Pipeline (Recommended)

**Complete workflow in one script**:
- ✅ Extracts text from PDFs/web pages
- ✅ Chunks text into smaller pieces
- ✅ Saves to `chunks.json`
- ✅ Generates embeddings (text → 768-dim vectors)
- ✅ Uploads vectors to Vertex AI Vector Search
- ✅ Handles streaming and batch upload methods
- ✅ Provides detailed logging and progress tracking

**Configuration**:
- Set `VERTEX_PROJECT_ID`, `VERTEX_INDEX_ID`, `VERTEX_INDEX_ENDPOINT` in `.env`
- Set `GCS_BUCKET_NAME` for batch updates (if streaming not supported)
- Use `--test` flag to skip upload and only generate chunks

### Standalone Scripts (Optional)

**`generate_embeddings.py`**:
- ✅ Reads `chunks.json`
- ✅ Generates embeddings (text → vectors)
- ✅ Saves to `vectors.json`
- ❌ Does NOT extract text or chunk
- ❌ Does NOT upload to Vertex AI

**`upload_vectors_direct.py`**:
- ✅ Reads `vectors.json`
- ✅ Uploads vectors to Vertex AI
- ✅ Supports streaming and batch methods
- ❌ Does NOT extract text, chunk, or generate embeddings

### Complete Flow (Integrated)

**Single Command**:
```bash
python3 crawler.py
```

**Executes**:
1. Sources → Text extraction (crawler.py)
2. Text → Chunks (crawler.py)
3. Chunks → JSON file (crawler.py - Step 1)
4. Chunks → Embeddings (crawler.py - Step 2)
5. Embeddings → Vertex AI (crawler.py - Step 3)

**All in one execution!** 🚀
