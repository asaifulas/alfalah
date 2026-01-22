# Falah Crawler

A comprehensive Python crawler that extracts content from web pages and PDFs, processes them into searchable chunks, generates embeddings, and uploads them to Vertex AI Vector Search for RAG (Retrieval-Augmented Generation) applications.

## What It Does

The crawler provides a complete pipeline for building a knowledge base:

1. **Source Extraction**: Reads sources from `resources/sources.json` and extracts content from:
   - Web pages (HTML content)
   - PDF files (local or remote)
   - PDFs linked from web pages
   - Paginated tables and lists

2. **Text Processing**: 
   - Extracts text from PDFs page by page
   - Chunks text into smaller pieces (default: 1000 chars) with overlap (default: 200 chars)
   - Preserves metadata (page numbers, URLs, source types)

3. **Embedding Generation**:
   - Converts text chunks to 768-dimensional vectors using Vertex AI's `text-embedding-005` model
   - Processes in batches for efficiency

4. **Vector Upload**:
   - Uploads vectors to Vertex AI Matching Engine Index
   - Supports both streaming (real-time) and batch (via GCS) update methods
   - Makes content searchable via semantic similarity

5. **Query Interface**:
   - Query the vector search index with natural language questions
   - Returns relevant chunks with metadata
   - Generates natural answers using Gemini

6. **Screenshot Generation**:
   - Takes screenshots of specific PDF pages
   - Useful for displaying source documents in the UI

---

## Setup

### 1. Install Requirements

```bash
cd crawler
pip install -r requirements.txt
```

**Required packages**:
- `beautifulsoup4`, `requests`, `lxml` - Web scraping
- `selenium`, `playwright` - JavaScript rendering
- `PyMuPDF` - PDF processing
- `langchain-google-vertexai`, `langchain-google-genai` - Vertex AI integration
- `google-cloud-aiplatform`, `google-cloud-storage` - Google Cloud services
- `vertexai` - Gemini model for natural answer generation
- `python-dotenv` - Environment variable management

### 2. Create `.env` File

Create a `.env` file in the `crawler` directory:

```bash
cp .env.example .env  # If you have an example file
# Or create manually:
touch .env
```

Add the following configuration:

```bash
# Vertex AI Configuration
VERTEX_PROJECT_ID=your-project-id
VERTEX_LOCATION=us-central1
VERTEX_INDEX_ID=your-index-id
VERTEX_INDEX_ENDPOINT=your-endpoint-id

# Google Cloud Credentials
# Path to your service account JSON file (see Step 3)
GOOGLE_APPLICATION_CREDENTIALS=cred.json

# GCS Bucket (required for batch updates if streaming not supported)
GCS_BUCKET_NAME=your-bucket-name

# Optional: Crawler Settings
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
MAX_PAGES_PER_PDF=1000
REQUEST_DELAY=1.0
```

### 3. Setup Vertex AI

Follow the complete setup guide in **[VERTEX_AI_SETUP.md](VERTEX_AI_SETUP.md)** to:

1. Enable Vertex AI API in your Google Cloud project
2. Create a Vector Search Index (768 dimensions, Tree-AH algorithm recommended)
3. Create an Index Endpoint and deploy the index
4. Get your `VERTEX_INDEX_ID` and `VERTEX_INDEX_ENDPOINT` IDs

**Quick reference**:
- **Dimensions**: `768` (required for text-embedding-005)
- **Algorithm**: `Tree-AH` (recommended)
- **Approximate Neighbors**: `50` (good starting point)
- **Distance Measure**: `DOT_PRODUCT` (recommended)

### 4. Download Google Application Credentials

1. **Create a Service Account**:
   - Go to [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
   - Click "Create Service Account"
   - Name it (e.g., `crawler-service-account`)
   - Grant roles: `Vertex AI User` (`roles/aiplatform.user`), `Storage Object Admin` (if using GCS)

2. **Create and Download Key**:
   - Click on the service account
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key" > "JSON"
   - Download the JSON file

3. **Save Credentials**:
   - Place the JSON file in the `crawler` directory (e.g., `cred.json`)
   - Update `GOOGLE_APPLICATION_CREDENTIALS` in `.env` to point to the file:
     ```bash
     GOOGLE_APPLICATION_CREDENTIALS=cred.json
     ```
   - Or use absolute path: `GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json`

4. **Security Note**: 
   - Never commit credentials to git (they're in `.gitignore`)
   - Keep credentials secure and rotate them regularly

For detailed authentication setup, see **[AUTHENTICATION_SETUP.md](AUTHENTICATION_SETUP.md)**.

---

## File and Folder Structure

```
crawler/
├── config.py                 # Configuration file (loads from .env)
├── crawler.py                # Main crawler script (complete pipeline)
├── query_vertex.py           # Query Vertex AI vector search
├── screenshot_page.py        # Generate PDF page screenshots
├── utils.py                  # Utility functions (text extraction, chunking)
├── requirements.txt          # Python dependencies
├── GOOGLE_CREDENTIALS.json   # GOOGLE_APPLICATION_CREDENTIALS.json
├── .env                      # Environment variables (create this, not in git)
├── .gitignore                # Git ignore rules
│
├── resources/                # Source files and configuration
│   ├── sources.json         # Main sources configuration
│   ├── sources_test.json    # Test sources (optional)
│   └── data/                # Local PDF files
│       ├── file1.pdf
│       ├── file2.pdf
│       └── ...
│
└── output/                   # Generated files (created automatically)
    ├── chunks.json          # Extracted text chunks
    ├── chunks_test.json     # Test chunks (when using --test)
    ├── vectors.json         # Generated embeddings (if using generate_embeddings.py)
    ├── pdf_urls.json        # Extracted PDF URLs (if using --url-only)
    ├── crawler.log          # Execution log
    ├── screenshots/          # PDF page screenshots
    │   └── *.png
    ├── my_pdfs/             # Downloaded PDFs (if any)
    │   └── *.pdf
    └── my_screenshots/      # Alternative screenshot location
        └── *.png
```

### Key Files

- **`resources/sources.json`**: Define your sources (PDFs, web pages) to crawl
- **`output/chunks.json`**: All extracted text chunks with metadata
- **`output/crawler.log`**: Detailed execution log
- **`.env`**: Your configuration (create this file, not in git)

---

## Commands

### `crawler.py` - Main Crawler Script

Complete pipeline: Extract → Chunk → Generate Embeddings → Upload to Vertex AI

#### Basic Usage

```bash
# Production mode (full pipeline)
python3 crawler.py
```

This will:
1. Read sources from `resources/sources.json`
2. Extract text and create chunks
3. Save chunks to `output/chunks.json`
4. Generate embeddings from chunks
5. Upload vectors to Vertex AI Vector Search

#### Flags

```bash
# Test mode (skip embedding generation and upload)
python3 crawler.py --test

# Test mode with custom sources file
python3 crawler.py --test --test-sources resources/sources_test.json

# URL extraction only (extract PDF URLs without processing)
python3 crawler.py --url-only
```

**Options**:
- `--test`: Run in test mode (extract and chunk only, skip embeddings and upload)
- `--test-sources PATH`: Use a custom sources file instead of `resources/sources.json`
- `--url-only`: Only extract PDF URLs from sources and save to `output/pdf_urls.json`

**Output**:
- Production mode: `output/chunks.json` + vectors uploaded to Vertex AI
- Test mode: `output/chunks_test.json` (no upload)
- URL-only mode: `output/pdf_urls.json`

---

### `query_vertex.py` - Query Vector Search

Query the Vertex AI vector search index with natural language questions.

#### Basic Usage

```bash
# Query with default top_k=3
python3 query_vertex.py "What is a charge card?"

# Query with custom top_k
python3 query_vertex.py "What is a charge card?" 5
```

#### Arguments

1. **Question** (required): The natural language question to search for
2. **top_k** (optional): Number of results to return (default: 3)

#### Output

Returns JSON with:
- `answer`: Natural answer generated by Gemini (if available)
- `sources`: Array of relevant chunks with:
  - `text`: Chunk text content
  - `metadata`: Source metadata (url, page, source_type, etc.)
  - `score`: Similarity score
  - `datapoint_id`: Unique identifier

**Example**:
```json
{
  "answer": "A charge card is a payment card that...",
  "sources": [
    {
      "text": "Charge Card and Charge Card-i...",
      "metadata": {
        "url": "https://...",
        "page": 1,
        "source_type": "local_pdf"
      },
      "score": 0.85,
      "datapoint_id": "doc_0_1_12345"
    }
  ]
}
```

---

### `screenshot_page.py` - Generate PDF Screenshots

Take screenshots of specific pages from PDF files.

#### Basic Usage

```bash
# Screenshot page 5 of default PDF
python3 screenshot_page.py

# Screenshot specific PDF and page
python3 screenshot_page.py --pdf resources/data/file.pdf --page 10
```

#### Flags

```bash
# Specify PDF file
python3 screenshot_page.py --pdf path/to/file.pdf

# Specify page number (1-indexed)
python3 screenshot_page.py --page 5

# Specify output directory
python3 screenshot_page.py --output-dir output/my_screenshots

# Choose method (pymupdf or browser)
python3 screenshot_page.py --method pymupdf
python3 screenshot_page.py --method browser

# PyMuPDF options (when using --method pymupdf)
python3 screenshot_page.py --zoom 2.0 --dpi 150

# Browser options (when using --method browser)
python3 screenshot_page.py --no-headless  # Show browser window
```

**Options**:
- `--pdf PATH`: Path to PDF file (default: `output/my_pdfs/charge_card_and_charge_card-i_PD.pdf`)
- `--page N`: Page number to screenshot (default: 5, 1-indexed)
- `--output-dir PATH`: Directory to save screenshot (default: `output/screenshots`)
- `--method METHOD`: Method to use - `pymupdf` (fast, default) or `browser` (Playwright)
- `--zoom FLOAT`: Zoom factor for PyMuPDF (default: 2.0, higher = better quality)
- `--dpi INT`: DPI for PyMuPDF rendering (default: 150)
- `--no-headless`: Show browser window (only for browser method)

**Output**:
- Saves screenshot to `output/screenshots/{pdf_name}_page_{page}_{timestamp}.png`
- Automatically cleans up screenshots older than 5 minutes

**Methods**:
- **pymupdf** (default): Fast, direct PDF rendering, no browser needed
- **browser**: Uses Playwright/Chromium, better for complex PDFs with JavaScript

---

## Source Configuration

Define your sources in `resources/sources.json`:

```json
{
  "sources": [
    {
      "type": "local_pdf",
      "url": "resources/data/file.pdf",
      "description": "Local PDF file"
    },
    {
      "type": "pdf",
      "url": "https://example.com/document.pdf",
      "description": "Remote PDF"
    },
    {
      "type": "page",
      "url": "https://example.com/page",
      "description": "Web page",
      "selectors": {
        "content": ".main-content",
        "pdf_links": "a[href$='.pdf']"
      }
    },
    {
      "type": "pdf_in_page",
      "url": "https://example.com/documents",
      "description": "Extract PDFs from page",
      "pdf_selector": "a[href$='.pdf']",
      "pagination": {
        "enabled": true,
        "next_button_selector": ".pagination .next",
        "max_pages": 100
      }
    }
  ]
}
```

### Source Types

- **`local_pdf`**: Local PDF file in `resources/data/`
- **`pdf`**: Direct PDF URL
- **`page`**: Web page content
- **`pdf_in_page`**: Extract and process PDFs linked from a page

For detailed source configuration, see the examples in `resources/sources.json`.

---

## Configuration

Edit `.env` file or set environment variables:

### Required
- `VERTEX_PROJECT_ID`: Your Google Cloud project ID
- `VERTEX_LOCATION`: Region (e.g., `us-central1`)
- `VERTEX_INDEX_ID`: Your Vector Search Index ID
- `VERTEX_INDEX_ENDPOINT`: Your Index Endpoint ID
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account JSON

### Optional
- `CHUNK_SIZE`: Text chunk size in characters (default: 1000)
- `CHUNK_OVERLAP`: Overlap between chunks (default: 200)
- `MAX_PAGES_PER_PDF`: Maximum pages to process (default: 1000)
- `REQUEST_DELAY`: Delay between requests in seconds (default: 1.0)
- `GCS_BUCKET_NAME`: GCS bucket for batch updates (required if streaming not supported)

---

## Troubleshooting

See **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** for common issues and solutions.

Common issues:
- DNS resolution errors → Already handled with `GRPC_DNS_RESOLVER=native`
- Authentication errors → Check `GOOGLE_APPLICATION_CREDENTIALS` path
- Quota exceeded → Script automatically waits and retries
- Token limit errors → Script automatically reduces batch size

---

## Workflow Documentation

For detailed workflow information, see:
- **[WORKFLOW_SUMMARY.md](WORKFLOW_SUMMARY.md)** - Complete workflow from source to vector search
- **[VERTEX_AI_SETUP.md](VERTEX_AI_SETUP.md)** - Vertex AI setup guide
- **[AUTHENTICATION_SETUP.md](AUTHENTICATION_SETUP.md)** - Authentication setup guide

---

## Quick Start Example

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create .env file with your configuration
# (See Setup section above)

# 3. Add sources to resources/sources.json
# (See Source Configuration section)

# 4. Run the crawler
python3 crawler.py

# 5. Query the index
python3 query_vertex.py "What is a charge card?"

# 6. Generate a screenshot
python3 screenshot_page.py --pdf resources/data/file.pdf --page 5
```

---

## License

[Your License Here]
