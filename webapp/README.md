# Webapp - RAG Chat Interface (POC)

**Note: This is a Proof of Concept (POC)** - A simple, single-file PHP solution for demonstrating the RAG (Retrieval-Augmented Generation) chat interface. You can put both backend and frontend code here for development and testing.

## What It Does

A ChatGPT-like interface that:
- Queries Vertex AI Vector Search using natural language questions
- Generates natural answers using Gemini AI
- Displays relevant source chunks with metadata
- Automatically generates screenshots from PDF sources
- Shows source links and page numbers

## Features

- ✅ Single PHP file (`index.php`) - no framework needed
- ✅ Plain JavaScript (no external dependencies)
- ✅ Queries Vertex AI via Python script from crawler
- ✅ Generates natural answers using Gemini
- ✅ Generates screenshots automatically from PDF results
- ✅ Displays: Natural answer, source chunks, screenshot images, and source links
- ✅ Responsive design (mobile-friendly)

## Requirements

- PHP 7.4+ with `shell_exec()` enabled
- Python 3 with required packages (from `../crawler/requirements.txt`)
- Web server (Apache/Nginx) or PHP built-in server

## Setup

### 1. Make sure Python scripts are executable:
```bash
chmod +x ../crawler/query_vertex.py
chmod +x ../crawler/screenshot_page.py
```

### 2. Configure Vertex AI
The webapp uses the same configuration as the crawler. Make sure `../crawler/.env` has:
- `VERTEX_PROJECT_ID`
- `VERTEX_LOCATION`
- `VERTEX_INDEX_ID`
- `VERTEX_INDEX_ENDPOINT`
- `GOOGLE_APPLICATION_CREDENTIALS`

### 3. Start the PHP Server

#### Option A: PHP Built-in Server (Recommended for POC/Development)

```bash
cd webapp
php -S localhost:8000
```

Then open in your browser: **http://localhost:8000**

**To run on a different port:**
```bash
php -S localhost:8020
```

**To allow access from other devices on your network:**
```bash
php -S 0.0.0.0:8000
```

#### Option B: Apache/Nginx (Production)

**Apache:**
- Point your Apache document root to the `webapp` directory
- Make sure `.htaccess` is enabled (mod_rewrite)
- Ensure PHP is enabled

**Nginx:**
- Configure Nginx to serve the `webapp` directory
- Set up PHP-FPM
- Example configuration:
  ```nginx
  server {
      listen 80;
      server_name localhost;
      root /path/to/webapp;
      index index.php;
      
      location ~ \.php$ {
          fastcgi_pass unix:/var/run/php/php-fpm.sock;
          fastcgi_index index.php;
          include fastcgi_params;
      }
  }
  ```

## File Structure

```
webapp/
├── index.php              # Main file (backend API + frontend UI)
├── .htaccess              # Apache configuration (optional)
└── README.md              # This file
```

**Note**: This is a POC structure. For production, you may want to:
- Separate backend (API) and frontend (HTML/JS/CSS)
- Use a proper framework (Laravel, Symfony, etc.)
- Implement proper authentication and security
- Add database for session management
- Implement proper error handling and logging

## Backend and Frontend

**Current Structure (POC)**:
- **Backend**: PHP code in `index.php` (handles API requests, calls Python scripts)
- **Frontend**: HTML/CSS/JavaScript embedded in `index.php` (single-page application)

**You can organize it differently**:
- Put backend API endpoints in separate PHP files (e.g., `api/chat.php`)
- Put frontend in separate files (e.g., `public/index.html`, `public/css/style.css`, `public/js/app.js`)
- Use a framework like Laravel, Symfony, or CodeIgniter
- Use a frontend framework like React, Vue, or Angular

**Example structure for separated backend/frontend**:
```
webapp/
├── api/                   # Backend API
│   ├── chat.php          # Chat endpoint
│   └── screenshot.php    # Screenshot endpoint
├── public/                # Frontend
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
└── config.php            # Shared configuration
```

## How It Works

1. **User Input**: User types a question in the chat interface
2. **Backend Processing** (PHP):
   - Receives POST request with question
   - Calls `../crawler/query_vertex.py` to query Vertex AI
   - Gets natural answer and source chunks
   - For each result with PDF and page number, calls `../crawler/screenshot_page.py`
   - Returns JSON response
3. **Frontend Display** (JavaScript):
   - Receives JSON response
   - Displays natural answer prominently
   - Shows source chunks as supporting details
   - Displays screenshot images
   - Shows source links with page numbers

## API Endpoints

### POST `/` (or `index.php`)
**Action**: `chat`

**Request**:
```json
{
  "action": "chat",
  "question": "What is a charge card?"
}
```

**Response**:
```json
{
  "question": "What is a charge card?",
  "answer": "A charge card is a payment card...",
  "results": [
    {
      "text": "Charge Card and Charge Card-i...",
      "source_name": "charge_card.pdf",
      "source_url": "https://...",
      "pdf_url": "resources/data/charge_card.pdf",
      "page": 1,
      "score": 0.85,
      "screenshot": "?screenshot=charge_card_page_1_20250122.png"
    }
  ]
}
```

### GET `?screenshot=filename.png`
Serves screenshot images from `../crawler/output/screenshots/`

## Troubleshooting

**"Permission denied" when calling Python scripts:**
- Make sure scripts are executable: `chmod +x ../crawler/query_vertex.py ../crawler/screenshot_page.py`
- Check PHP `shell_exec()` is enabled in `php.ini`
- Verify PHP user has permission to execute Python scripts

**Screenshots not generating:**
- Check that PDF paths in metadata are correct
- Verify `../crawler/screenshot_page.py` works when run manually
- Check `../crawler/output/screenshots/` directory is writable
- Verify PDF files exist at the specified paths

**Vertex AI query fails:**
- Verify `../crawler/.env` file has correct credentials
- Test with: `python3 ../crawler/query_vertex.py "test question"`
- Check PHP error logs for detailed error messages

**PHP server not starting:**
- Make sure PHP is installed: `php -v`
- Check if port is already in use: `lsof -i :8000`
- Try a different port: `php -S localhost:8020`

**"Natural answer not showing":**
- Check browser console for JavaScript errors
- Verify Gemini API is working (check Python script logs)
- Check PHP error logs for API call errors

For more troubleshooting, see **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.

## Development Notes

**This is a POC**, so:
- ✅ Quick to set up and test
- ✅ Single file for easy deployment
- ✅ No complex dependencies
- ⚠️ Not optimized for production
- ⚠️ No authentication/authorization
- ⚠️ Limited error handling
- ⚠️ No database for session management

**For production**, consider:
- Separating backend and frontend
- Adding authentication (OAuth, JWT, etc.)
- Implementing rate limiting
- Adding proper logging and monitoring
- Using a web framework
- Implementing caching
- Adding database for user sessions and history

## Quick Start

```bash
# 1. Navigate to webapp directory
cd webapp

# 2. Start PHP server
php -S localhost:8000

# 3. Open in browser
# http://localhost:8000

# 4. Type a question and get answers!
```

## License

[Your License Here]
