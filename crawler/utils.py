"""
Utility functions for PDF processing, web crawling, and text chunking
"""
import json
import logging
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
import fitz  # PyMuPDF
from bs4 import BeautifulSoup

# Selenium for JavaScript rendering (optional)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("Selenium not available. Install with: pip install selenium")

# Playwright for better PDF handling (optional)
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MAX_PAGES_PER_PDF,
    REQUEST_TIMEOUT,
    REQUEST_DELAY,
    USER_AGENT,
    OUTPUT_DIR,
    RESOURCES_DIR
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(OUTPUT_DIR / "crawler.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log Playwright availability after logger is initialized
if not PLAYWRIGHT_AVAILABLE:
    logger.warning("Playwright not available. Install with: pip install playwright && playwright install chromium")


def download_pdf_browser(url: str, output_dir: Path = None, referer_url: str = None, use_playwright: bool = True) -> Optional[Path]:
    """
    Download a PDF using browser automation (mimics right-click, save link as)
    
    Args:
        url: URL of the PDF to download
        output_dir: Directory to save the PDF (default: OUTPUT_DIR/pdfs)
        referer_url: Optional referer URL
        use_playwright: If True, use Playwright; otherwise use Selenium
    
    Returns:
        Path to downloaded PDF file or None if download failed
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / "pdfs"
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Extract filename from URL
    filename = url.split("/")[-1]
    if "?" in filename:
        filename = filename.split("?")[0]
    if not filename.endswith(".pdf"):
        filename = f"{filename}.pdf"
    
    filepath = output_dir / filename
    
    try:
        logger.info(f"Downloading PDF using browser automation: {url}")
        
        if use_playwright and PLAYWRIGHT_AVAILABLE:
            return _download_pdf_playwright(url, filepath, referer_url)
        elif not use_playwright and SELENIUM_AVAILABLE:
            return _download_pdf_selenium(url, filepath, referer_url)
        else:
            logger.warning("Browser automation not available, falling back to HTTP download")
            return download_pdf(url, output_dir, referer_url)
    
    except Exception as e:
        logger.error(f"Failed to download PDF using browser: {e}")
        # Fallback to HTTP download
        logger.info("Falling back to HTTP download method")
        return download_pdf(url, output_dir, referer_url)


def _download_pdf_playwright(url: str, filepath: Path, referer_url: str = None) -> Optional[Path]:
    """
    Download PDF using Playwright (mimics right-click, save link as)
    """
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            # Launch browser with download support
            browser = p.chromium.launch(headless=True)
            
            # Set up download path and context
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080},
                accept_downloads=True
            )
            
            # Set referer if provided
            if referer_url:
                context.set_extra_http_headers({"Referer": referer_url})
            
            page = context.new_page()
            
            # Track download
            download_received = False
            
            def handle_download(download):
                nonlocal download_received
                download_received = True
                logger.info(f"Download started, saving to: {filepath}")
                try:
                    download.save_as(filepath)
                    logger.info(f"Download saved successfully")
                except Exception as e:
                    logger.error(f"Error saving download: {e}")
            
            page.on("download", handle_download)
            
            # Method 1: Try to intercept PDF response directly
            pdf_content = None
            
            def handle_response(response):
                nonlocal pdf_content
                content_type = response.headers.get("content-type", "").lower()
                if "application/pdf" in content_type or response.url.endswith(".pdf"):
                    try:
                        pdf_content = response.body()
                        logger.info(f"Intercepted PDF response ({len(pdf_content)} bytes)")
                    except Exception as e:
                        logger.debug(f"Could not read response body: {e}")
            
            page.on("response", handle_response)
            
            # Navigate to PDF URL
            logger.info(f"Navigating to PDF URL: {url}")
            try:
                response = page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
                
                # Check if we got PDF content directly
                if pdf_content and len(pdf_content) > 0:
                    # Verify it's a PDF by checking magic bytes
                    if pdf_content[:4] == b'%PDF':
                        with open(filepath, "wb") as f:
                            f.write(pdf_content)
                        logger.info(f"Downloaded PDF via Playwright (response intercept) to: {filepath} ({len(pdf_content)} bytes)")
                        browser.close()
                        return filepath
                    else:
                        logger.warning("Response content doesn't appear to be a PDF")
                
                # Wait a bit for download to trigger
                time.sleep(2)
                
                # Check if download was triggered
                if download_received:
                    # Wait for download to complete
                    max_wait = 10
                    waited = 0
                    while waited < max_wait:
                        if filepath.exists() and filepath.stat().st_size > 0:
                            logger.info(f"Downloaded PDF via Playwright (download event) to: {filepath} ({filepath.stat().st_size} bytes)")
                            browser.close()
                            return filepath
                        time.sleep(0.5)
                        waited += 0.5
                
                # If no download triggered, try to get content from page
                # Some PDFs are embedded, try to extract
                content = page.content()
                if len(content) < 1000:  # Small content might be an error page
                    logger.warning("Page content is very small, might be an error")
                
            except Exception as e:
                logger.warning(f"Navigation error: {e}")
            
            browser.close()
            
            # Final check if file exists
            if filepath.exists() and filepath.stat().st_size > 0:
                # Verify it's a PDF
                with open(filepath, "rb") as f:
                    first_bytes = f.read(4)
                    if first_bytes == b'%PDF':
                        logger.info(f"Downloaded PDF via Playwright to: {filepath} ({filepath.stat().st_size} bytes)")
                        return filepath
                    else:
                        logger.warning(f"Downloaded file doesn't appear to be a PDF (first bytes: {first_bytes})")
                        filepath.unlink()  # Delete invalid file
                        return None
            else:
                logger.warning("Download may not have completed, file not found or empty")
                return None
    
    except Exception as e:
        logger.error(f"Playwright download failed: {e}")
        return None


def _download_pdf_selenium(url: str, filepath: Path, referer_url: str = None) -> Optional[Path]:
    """
    Download PDF using Selenium (right-click save as behavior)
    """
    if not SELENIUM_AVAILABLE:
        return None
    
    driver = None
    try:
        logger.info(f"Downloading PDF using Selenium: {url}")
        
        # Setup Chrome options with download preferences
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--user-agent={USER_AGENT}")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Set download preferences
        prefs = {
            "download.default_directory": str(filepath.parent.absolute()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(REQUEST_TIMEOUT)
        
        # Set referer if provided
        if referer_url:
            driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Referer": referer_url}})
        
        # Navigate to PDF URL
        logger.info(f"Navigating to PDF URL: {url}")
        driver.get(url)
        
        # Wait for download to complete
        time.sleep(3)
        
        # Check if file was downloaded
        if filepath.exists() and filepath.stat().st_size > 0:
            logger.info(f"Downloaded PDF via Selenium to: {filepath} ({filepath.stat().st_size} bytes)")
            return filepath
        else:
            logger.warning("Download may not have completed, file not found or empty")
            return None
    
    except Exception as e:
        logger.error(f"Selenium download failed: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def download_pdf(url: str, output_dir: Path = None, referer_url: str = None, use_browser: bool = False) -> Optional[Path]:
    """
    Download a PDF from a URL
    
    Args:
        url: URL of the PDF to download
        output_dir: Directory to save the PDF (default: OUTPUT_DIR/pdfs)
        referer_url: Optional referer URL to use in headers (helps with servers that check referer)
        use_browser: If True, use browser automation (mimics right-click, save link as)
    
    Returns:
        Path to downloaded PDF file or None if download failed
    """
    # Use browser automation if requested
    if use_browser:
        return download_pdf_browser(url, output_dir, referer_url)
    
    # Default HTTP download method
    if output_dir is None:
        output_dir = OUTPUT_DIR / "pdfs"
    output_dir.mkdir(exist_ok=True, parents=True)
    
    try:
        logger.info(f"Downloading PDF: {url}")
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        # Add Referer header if available
        if referer_url:
            headers["Referer"] = referer_url
        else:
            # Try to extract referer from PDF URL
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                referer = f"{parsed.scheme}://{parsed.netloc}"
                headers["Referer"] = referer
            except Exception:
                pass
        
        # Create a session to handle cookies and redirects
        session = requests.Session()
        session.headers.update(headers)
        
        response = session.get(url, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True)
        
        # Check response status and content
        status_code = response.status_code
        content_type = response.headers.get("Content-Type", "").lower()
        logger.debug(f"Response status: {status_code}, Content-Type: {content_type}, Content-Length: {response.headers.get('Content-Length', 'unknown')}")
        
        # Handle status 202 (Accepted) - might be a PDF viewer page
        if status_code == 202 or (content_type and 'html' in content_type and status_code == 200):
            logger.warning(f"Received HTML viewer page (status {status_code}) instead of PDF. Server may require browser automation.")
            # Still try to save it, but it's likely HTML
            response.raise_for_status()
        else:
            response.raise_for_status()
        
        # Extract filename from URL or Content-Disposition header
        filename = url.split("/")[-1]
        # Remove query parameters if any
        if "?" in filename:
            filename = filename.split("?")[0]
        if not filename.endswith(".pdf"):
            filename = f"{filename}.pdf"
        
        filepath = output_dir / filename
        
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        logger.info(f"Downloaded PDF to: {filepath} ({filepath.stat().st_size} bytes)")
        return filepath
    
    except Exception as e:
        logger.error(f"Failed to download PDF from {url}: {e}")
        return None
    if output_dir is None:
        output_dir = OUTPUT_DIR / "pdfs"
    output_dir.mkdir(exist_ok=True, parents=True)
    
    try:
        logger.info(f"Downloading PDF: {url}")
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,application/octet-stream,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        # Add Referer header if available
        if referer_url:
            headers["Referer"] = referer_url
        else:
            # Try to extract referer from PDF URL
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                referer = f"{parsed.scheme}://{parsed.netloc}"
                headers["Referer"] = referer
            except Exception:
                pass
        
        # Create a session to handle cookies and redirects
        session = requests.Session()
        session.headers.update(headers)
        
        response = session.get(url, timeout=REQUEST_TIMEOUT, stream=True, allow_redirects=True)
        
        # Check response status and content
        status_code = response.status_code
        content_type = response.headers.get("Content-Type", "").lower()
        logger.debug(f"Response status: {status_code}, Content-Type: {content_type}, Content-Length: {response.headers.get('Content-Length', 'unknown')}")
        
        # Handle status 202 (Accepted) - might be a PDF viewer page
        if status_code == 202 or (content_type and 'html' in content_type and status_code == 200):
            logger.warning(f"Received HTML viewer page (status {status_code}) instead of PDF. Server may require browser automation.")
            # Still try to save it, but it's likely HTML
            response.raise_for_status()
        else:
            response.raise_for_status()
        
        # Extract filename from URL or Content-Disposition header
        filename = url.split("/")[-1]
        # Remove query parameters if any
        if "?" in filename:
            filename = filename.split("?")[0]
        if not filename.endswith(".pdf"):
            filename = f"{filename}.pdf"
        
        filepath = output_dir / filename
        
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        logger.info(f"Downloaded PDF to: {filepath} ({filepath.stat().st_size} bytes)")
        return filepath
    
    except Exception as e:
        logger.error(f"Failed to download PDF from {url}: {e}")
        return None


def extract_pdf_content(pdf_path: Path, original_url: str = None, max_pages: int = None) -> List[Dict[str, any]]:
    """
    Extract text content from PDF with page metadata
    
    Args:
        pdf_path: Path to PDF file
        original_url: Original URL of the PDF (if different from file path)
        max_pages: Maximum number of pages to extract (None = all pages, default uses MAX_PAGES_PER_PDF)
    
    Returns:
        List of dictionaries with 'page', 'text', 'url' keys
    """
    chunks = []
    
    try:
        logger.info(f"Extracting content from PDF: {pdf_path}")
        doc = fitz.open(pdf_path)
        
        # Use original URL if provided, otherwise use file path
        url = original_url if original_url else str(pdf_path)
        
        # Determine max pages to process
        total_pages = len(doc)
        
        if max_pages is None:
            # Process all pages
            pages_to_process = total_pages
            logger.info(f"Processing all {total_pages} pages from PDF")
        else:
            # Use the specified limit or default to MAX_PAGES_PER_PDF
            limit = max_pages if max_pages > 0 else MAX_PAGES_PER_PDF
            pages_to_process = min(total_pages, limit)
            if total_pages > limit:
                logger.info(f"PDF has {total_pages} pages, processing first {pages_to_process} pages (limit: {limit})")
            else:
                logger.info(f"Processing all {total_pages} pages from PDF")
        
        for page_num in range(pages_to_process):
            page = doc[page_num]
            text = page.get_text()
            
            if text.strip():
                chunks.append({
                    "page": page_num + 1,
                    "text": text.strip(),
                    "url": url,
                    "source_type": "pdf"
                })
        
        doc.close()
        logger.info(f"Extracted {len(chunks)} pages from PDF (out of {pages_to_process} processed)")
        return chunks
    
    except Exception as e:
        logger.error(f"Failed to extract content from PDF {pdf_path}: {e}")
        return []


def extract_pdf_from_bytes(pdf_bytes: bytes, url: str) -> List[Dict[str, any]]:
    """
    Extract content from PDF bytes
    
    Args:
        pdf_bytes: PDF file content as bytes
        url: Original URL of the PDF
    
    Returns:
        List of dictionaries with page content
    """
    try:
        # Open PDF from bytes
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        chunks = []
        
        for page_num in range(min(len(doc), MAX_PAGES_PER_PDF)):
            page = doc[page_num]
            text = page.get_text()
            
            if text.strip():
                chunks.append({
                    "page": page_num + 1,
                    "text": text.strip(),
                    "url": url,
                    "source_type": "pdf"
                })
        
        doc.close()
        logger.info(f"Extracted {len(chunks)} pages from PDF at {url}")
        return chunks
    except Exception as e:
        logger.error(f"Failed to extract content from PDF bytes: {e}")
        return []


def extract_pdf_from_url(url: str, skip_download: bool = False, referer_url: str = None) -> List[Dict[str, any]]:
    """
    Extract content from a PDF URL by downloading it first, then reading with PyMuPDF
    
    Args:
        url: URL of the PDF
        skip_download: If False (default), download PDF first then read from saved file
        referer_url: Optional referer URL to use in headers (helps with servers that check referer)
    
    Returns:
        List of dictionaries with page content
    """
    try:
        logger.info(f"Extracting PDF content from URL: {url}")
        
        # Always download PDF first to output folder
        pdf_path = download_pdf(url, output_dir=OUTPUT_DIR / "pdfs", referer_url=referer_url)
        
        if pdf_path is None or not pdf_path.exists():
            logger.error(f"Failed to download PDF from {url}")
            return []
        
        # Verify it's a PDF by checking magic bytes
        with open(pdf_path, "rb") as f:
            first_bytes = f.read(10)
            if not first_bytes.startswith(b'%PDF'):
                logger.warning(f"Downloaded file doesn't start with PDF magic bytes. First bytes: {first_bytes[:20]}")
                if first_bytes.strip().startswith(b'<'):
                    logger.error(f"Downloaded file appears to be HTML, not PDF. This might be an error page or redirect.")
                    pdf_path.unlink()  # Delete the HTML file
                    return []
                # Still try to open it, might work
                logger.info("Attempting to open despite missing PDF magic bytes...")
        
        # Extract content from saved file using PyMuPDF
        return extract_pdf_content(pdf_path, original_url=url)
        
    except Exception as e:
        logger.error(f"Failed to extract PDF content from URL {url}: {e}")
        return []


def extract_pdf_from_viewer_page(url: str, referer_url: str = None) -> List[Dict[str, any]]:
    """
    Extract PDF content from a page that shows a PDF viewer (HTML page with embed/iframe)
    Uses Playwright to extract PDF blob data or render the PDF
    
    Args:
        url: URL of the PDF viewer page
        referer_url: Optional referer URL
    
    Returns:
        List of dictionaries with page content
    """
    # Prefer Playwright for better PDF blob extraction
    if PLAYWRIGHT_AVAILABLE:
        return extract_pdf_from_viewer_page_playwright(url, referer_url)
    elif SELENIUM_AVAILABLE:
        return extract_pdf_from_viewer_page_selenium(url, referer_url)
    else:
        logger.error("Neither Playwright nor Selenium available for PDF viewer extraction")
        return []


def extract_pdf_from_viewer_page_playwright(url: str, referer_url: str = None) -> List[Dict[str, any]]:
    """
    Extract PDF from viewer page using Playwright (better for blob extraction)
    """
    try:
        logger.info(f"Extracting PDF from viewer page using Playwright: {url}")
        
        with sync_playwright() as p:
            # Launch browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            
            # Set up response interception to capture PDF blob
            pdf_bytes = None
            
            def handle_response(response):
                nonlocal pdf_bytes
                content_type = response.headers.get("content-type", "").lower()
                if "application/pdf" in content_type:
                    try:
                        pdf_bytes = response.body()
                        logger.info(f"Captured PDF from network response: {len(pdf_bytes)} bytes")
                    except Exception as e:
                        logger.debug(f"Failed to capture PDF from response: {e}")
            
            page.on("response", handle_response)
            
            # Navigate to the page
            page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
            
            # Wait a bit for PDF to load
            time.sleep(3)
            
            # Method 1: Try to extract PDF blob from embed element using JavaScript
            if not pdf_bytes:
                try:
                    logger.info("Attempting to extract PDF blob from page...")
                    pdf_blob_data = page.evaluate("""
                        async () => {
                            // Try to get PDF from embed element
                            const embed = document.querySelector('embed[type="application/pdf"]');
                            if (embed && embed.src && embed.src !== 'about:blank') {
                                // If src is a blob URL, try to fetch it
                                if (embed.src.startsWith('blob:')) {
                                    const response = await fetch(embed.src);
                                    const blob = await response.blob();
                                    const arrayBuffer = await blob.arrayBuffer();
                                    return Array.from(new Uint8Array(arrayBuffer));
                                }
                                return embed.src; // Return URL if not blob
                            }
                            
                            // Try to find PDF in iframe
                            const iframe = document.querySelector('iframe[src*=".pdf"], iframe[type="application/pdf"]');
                            if (iframe && iframe.src && !iframe.src.startsWith('about:blank')) {
                                return iframe.src;
                            }
                            
                            // Try to find PDF data in script tags or window objects
                            if (window.pdfData || window.pdfBlob) {
                                const data = window.pdfData || window.pdfBlob;
                                if (data instanceof Blob) {
                                    const arrayBuffer = await data.arrayBuffer();
                                    return Array.from(new Uint8Array(arrayBuffer));
                                }
                            }
                            
                            return null;
                        }
                    """)
                    
                    if pdf_blob_data:
                        if isinstance(pdf_blob_data, list):
                            # It's blob data as array
                            pdf_bytes = bytes(pdf_blob_data)
                            logger.info(f"Extracted PDF blob: {len(pdf_bytes)} bytes")
                        elif isinstance(pdf_blob_data, str) and pdf_blob_data.startswith("http"):
                            # It's a URL, fetch it
                            logger.info(f"Found PDF URL: {pdf_blob_data}")
                            return extract_pdf_from_url(pdf_blob_data, referer_url=referer_url or url)
                except Exception as e:
                    logger.debug(f"JavaScript blob extraction failed: {e}")
            
            # Method 2: Try to get PDF from page content or network requests
            if not pdf_bytes:
                # Check if we can get PDF via page.pdf() (if it's actually a PDF page)
                try:
                    pdf_bytes = page.pdf(format="A4")
                    if pdf_bytes and len(pdf_bytes) > 100:  # Basic validation
                        logger.info(f"Generated PDF from page: {len(pdf_bytes)} bytes")
                except Exception as e:
                    logger.debug(f"Page PDF generation failed: {e}")
            
            # Method 3: Try alternative URL patterns
            if not pdf_bytes:
                logger.info("Trying alternative URL patterns...")
                test_urls = [
                    url + "?download=true",
                    url + "?download=1",
                    url + "?force_download=1",
                ]
                
                for test_url in test_urls:
                    try:
                        response = page.goto(test_url, wait_until="networkidle", timeout=10000)
                        if response:
                            content_type = response.headers.get("content-type", "").lower()
                            if "application/pdf" in content_type:
                                pdf_bytes = response.body()
                                if pdf_bytes and len(pdf_bytes) > 0:
                                    logger.info(f"Found PDF at: {test_url}")
                                    break
                    except Exception:
                        continue
            
            browser.close()
            
            if pdf_bytes and len(pdf_bytes) > 0:
                # Verify it's a PDF
                if pdf_bytes.startswith(b'%PDF'):
                    return extract_pdf_from_bytes(pdf_bytes, url)
                else:
                    logger.warning(f"Extracted data doesn't start with PDF magic bytes")
            
            logger.error(f"Could not extract PDF from viewer page: {url}")
            return []
            
    except Exception as e:
        logger.error(f"Failed to extract PDF from viewer page using Playwright {url}: {e}")
        return []


def extract_pdf_from_viewer_page_selenium(url: str, referer_url: str = None) -> List[Dict[str, any]]:
    """
    Extract PDF from viewer page using Selenium (fallback)
    """
    driver = None
    try:
        logger.info(f"Extracting PDF from viewer page using Selenium: {url}")
        
        # Setup Chrome options
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--user-agent={USER_AGENT}")
        chrome_options.add_argument("--window-size=1920,1080")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(REQUEST_TIMEOUT)
        
        # Navigate to the PDF viewer page
        driver.get(url)
        
        # Wait for page to load
        time.sleep(3)
        
        # Try to extract PDF blob using JavaScript
        try:
            logger.info("Attempting to extract PDF blob using JavaScript...")
            pdf_data = driver.execute_script("""
                return new Promise((resolve) => {
                    const embed = document.querySelector('embed[type="application/pdf"]');
                    if (embed && embed.src) {
                        if (embed.src.startsWith('blob:')) {
                            fetch(embed.src)
                                .then(r => r.blob())
                                .then(blob => blob.arrayBuffer())
                                .then(buffer => {
                                    resolve(Array.from(new Uint8Array(buffer)));
                                })
                                .catch(() => resolve(null));
                        } else {
                            resolve(embed.src);
                        }
                    } else {
                        resolve(null);
                    }
                });
            """)
            
            if pdf_data:
                if isinstance(pdf_data, list):
                    # It's blob data
                    pdf_bytes = bytes(pdf_data)
                    if pdf_bytes.startswith(b'%PDF'):
                        logger.info(f"Extracted PDF blob: {len(pdf_bytes)} bytes")
                        return extract_pdf_from_bytes(pdf_bytes, url)
                elif isinstance(pdf_data, str) and pdf_data.startswith("http"):
                    # It's a URL
                    return extract_pdf_from_url(pdf_data, referer_url=referer_url or url)
        except Exception as e:
            logger.debug(f"JavaScript blob extraction failed: {e}")
        
        logger.error(f"Could not extract PDF from viewer page: {url}")
        return []
        
    except Exception as e:
        logger.error(f"Failed to extract PDF from viewer page using Selenium {url}: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def crawl_page_js(url: str, selectors: Dict[str, str] = None, wait_time: float = 5.0, wait_for_selector: str = None, return_soup: bool = False) -> Tuple[str, List[str], Optional[BeautifulSoup]]:
    """
    Crawl a web page using Selenium to handle JavaScript-rendered content
    
    Args:
        url: URL of the page to crawl
        selectors: Dictionary with 'content' and 'pdf_links' CSS selectors
        wait_time: Time to wait for page to load (seconds)
        wait_for_selector: Optional CSS selector to wait for before extracting content
    
    Returns:
        Tuple of (page_content, list_of_pdf_urls)
    """
    if not SELENIUM_AVAILABLE:
        logger.error("Selenium not available. Falling back to regular crawl.")
        return crawl_page(url, selectors)
    
    if selectors is None:
        selectors = {
            "content": "body",
            "pdf_links": "a[href$='.pdf']"
        }
    
    driver = None
    try:
        logger.info(f"Crawling page with JavaScript rendering: {url}")
        
        # Setup Chrome options
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--user-agent={USER_AGENT}")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Create driver
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(REQUEST_TIMEOUT)
        
        # Navigate to page
        driver.get(url)
        
        # Wait for page to load
        if wait_for_selector:
            try:
                logger.info(f"Waiting for selector: {wait_for_selector}")
                WebDriverWait(driver, wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_for_selector))
                )
            except TimeoutException:
                logger.warning(f"Timeout waiting for selector {wait_for_selector}, continuing anyway")
        else:
            # Wait for DataTables or common dynamic content
            time.sleep(wait_time)
            # Try to wait for common table indicators
            try:
                # Wait for table to be visible
                WebDriverWait(driver, wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table, .dataTable, [class*='table'], [id*='table']"))
                )
                # Additional wait for DataTables to initialize
                time.sleep(2)
            except TimeoutException:
                logger.info("No table found or already loaded, proceeding")
        
        # Get page source after JavaScript execution
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")
        
        # Extract main content
        content_elements = soup.select(selectors.get("content", "body"))
        page_content = "\n\n".join([elem.get_text(strip=True) for elem in content_elements])
        
        # Extract PDF links
        pdf_links = []
        pdf_elements = soup.select(selectors.get("pdf_links", "a[href$='.pdf']"))
        for elem in pdf_elements:
            href = elem.get("href", "")
            if href:
                absolute_url = urljoin(url, href)
                if absolute_url not in pdf_links:
                    pdf_links.append(absolute_url)
        
        logger.info(f"Found {len(pdf_links)} PDF links on page (JavaScript-rendered)")
        if return_soup:
            return page_content, pdf_links, soup
        return page_content, pdf_links, None
    
    except WebDriverException as e:
        logger.error(f"WebDriver error while crawling {url}: {e}")
        logger.info("Falling back to regular crawl without JavaScript")
        page_content, pdf_links = crawl_page(url, selectors)
        return page_content, pdf_links, None
    except Exception as e:
        logger.error(f"Failed to crawl page {url} with JavaScript: {e}")
        return "", [], None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def crawl_page(url: str, selectors: Dict[str, str] = None, use_js: bool = False, js_config: Dict = None) -> Tuple[str, List[str]]:
    """
    Crawl a web page and extract content and PDF links
    
    Args:
        url: URL of the page to crawl
        selectors: Dictionary with 'content' and 'pdf_links' CSS selectors
        use_js: If True, use Selenium for JavaScript rendering
        js_config: Configuration for JavaScript rendering (wait_time, wait_for_selector)
    
    Returns:
        Tuple of (page_content, list_of_pdf_urls)
    """
    if use_js:
        js_config = js_config or {}
        page_content, pdf_links, _ = crawl_page_js(
            url, 
            selectors, 
            wait_time=js_config.get("wait_time", 5.0),
            wait_for_selector=js_config.get("wait_for_selector")
        )
        return page_content, pdf_links
    
    if selectors is None:
        selectors = {
            "content": "body",
            "pdf_links": "a[href$='.pdf']"
        }
    
    try:
        logger.info(f"Crawling page: {url}")
        headers = {"User-Agent": USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Extract main content
        content_elements = soup.select(selectors.get("content", "body"))
        page_content = "\n\n".join([elem.get_text(strip=True) for elem in content_elements])
        
        # Extract PDF links
        pdf_links = []
        pdf_elements = soup.select(selectors.get("pdf_links", "a[href$='.pdf']"))
        for elem in pdf_elements:
            href = elem.get("href", "")
            if href:
                absolute_url = urljoin(url, href)
                pdf_links.append(absolute_url)
        
        logger.info(f"Found {len(pdf_links)} PDF links on page")
        return page_content, pdf_links
    
    except Exception as e:
        logger.error(f"Failed to crawl page {url}: {e}")
        return "", []


def crawl_datatables_pdfs(base_url: str, pdf_selector: str, pagination_config: Dict[str, any], js_config: Dict = None) -> List[str]:
    """
    Crawl PDF links from a DataTables paginated table by clicking through pages
    
    Args:
        base_url: Starting URL
        pdf_selector: CSS selector for PDF links
        pagination_config: Dictionary with pagination settings
        js_config: Configuration for JavaScript rendering
    
    Returns:
        List of all PDF URLs found across all pages
    """
    if not SELENIUM_AVAILABLE:
        logger.error("Selenium not available for DataTables crawling")
        return []
    
    all_pdf_links = []
    max_pages = pagination_config.get("max_pages", 100)
    next_button_selector = pagination_config.get("next_button_selector", ".paginate_button.next, a.paginate_button.next")
    js_wait_time = js_config.get("wait_time", 5.0) if js_config else 5.0
    js_wait_selector = js_config.get("wait_for_selector") if js_config else None
    
    driver = None
    try:
        logger.info(f"Crawling DataTables with JavaScript: {base_url}")
        
        # Setup Chrome options
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--user-agent={USER_AGENT}")
        chrome_options.add_argument("--window-size=1920,1080")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(REQUEST_TIMEOUT)
        
        # Navigate to page
        driver.get(base_url)
        
        # Wait for DataTables to load
        if js_wait_selector:
            try:
                logger.info(f"Waiting for selector: {js_wait_selector}")
                WebDriverWait(driver, js_wait_time).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, js_wait_selector))
                )
            except TimeoutException:
                logger.warning(f"Timeout waiting for selector {js_wait_selector}")
        
        # Additional wait for DataTables to initialize
        time.sleep(2)
        
        page_count = 0
        previous_pdf_count = 0
        
        while page_count < max_pages:
            page_count += 1
            logger.info(f"Extracting PDFs from DataTables page {page_count}")
            
            # Wait a bit for table to render
            time.sleep(1)
            
            # Extract PDF links from current page
            try:
                pdf_elements = driver.find_elements(By.CSS_SELECTOR, pdf_selector)
                page_pdf_links = []
                for elem in pdf_elements:
                    href = elem.get_attribute("href")
                    if href:
                        absolute_url = urljoin(base_url, href)
                        if absolute_url not in all_pdf_links:
                            page_pdf_links.append(absolute_url)
                            all_pdf_links.append(absolute_url)
                
                logger.info(f"Found {len(page_pdf_links)} PDF links on page {page_count} (total: {len(all_pdf_links)})")
                
                # Check if we got new PDFs
                if len(all_pdf_links) == previous_pdf_count:
                    logger.info("No new PDFs found on this page, stopping")
                    break
                previous_pdf_count = len(all_pdf_links)
                
            except Exception as e:
                logger.error(f"Error extracting PDFs from page {page_count}: {e}")
            
            # Try to find and click next button
            next_button = None
            selectors_list = [s.strip() for s in next_button_selector.split(",")]
            
            for sel in selectors_list:
                try:
                    next_button = driver.find_element(By.CSS_SELECTOR, sel)
                    if next_button:
                        # Check if button is disabled
                        classes = next_button.get_attribute("class") or ""
                        if "disabled" in classes.lower():
                            logger.info("Next button is disabled, reached last page")
                            break
                        # Check if it's actually clickable
                        if next_button.is_displayed() and next_button.is_enabled():
                            break
                except Exception:
                    continue
            
            if not next_button:
                logger.info("Next button not found, reached end of pagination")
                break
            
            # Check if button is disabled
            try:
                classes = next_button.get_attribute("class") or ""
                if "disabled" in classes.lower():
                    logger.info("Next button is disabled, reached last page")
                    break
                
                # Click the next button
                logger.info("Clicking next button...")
                driver.execute_script("arguments[0].click();", next_button)
                
                # Wait for table to update
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error clicking next button: {e}")
                break
        
        logger.info(f"Completed DataTables pagination: found {len(all_pdf_links)} total PDF links across {page_count} pages")
        return all_pdf_links
    
    except Exception as e:
        logger.error(f"Error during DataTables crawling: {e}")
        return all_pdf_links
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def crawl_paginated_pdfs(base_url: str, pdf_selector: str, pagination_config: Dict[str, any], use_js: bool = False, js_config: Dict = None) -> List[str]:
    """
    Crawl PDF links from a paginated table/list
    
    Args:
        base_url: Starting URL
        pdf_selector: CSS selector for PDF links
        pagination_config: Dictionary with pagination settings
        use_js: If True, use Selenium for JavaScript rendering
        js_config: Configuration for JavaScript rendering
    
    Returns:
        List of all PDF URLs found across all pages
    """
    all_pdf_links = []
    visited_urls = set()
    current_url = base_url
    max_pages = pagination_config.get("max_pages", 100)
    wait_time = pagination_config.get("wait_time", 2.0)
    next_button_selector = pagination_config.get("next_button_selector", "")
    next_link_selector = pagination_config.get("next_link_selector", "")
    is_datatables = pagination_config.get("datatables", False)
    
    page_count = 0
    
    # For DataTables with JavaScript, use Selenium to click through pages
    if use_js and is_datatables and SELENIUM_AVAILABLE:
        return crawl_datatables_pdfs(base_url, pdf_selector, pagination_config, js_config)
    
    try:
        while current_url and page_count < max_pages:
            if current_url in visited_urls:
                logger.warning(f"Already visited {current_url}, stopping pagination")
                break
            
            visited_urls.add(current_url)
            page_count += 1
            
            logger.info(f"Crawling page {page_count}: {current_url}")
            
            # Use JavaScript rendering if enabled
            if use_js:
                selectors = {"pdf_links": pdf_selector}
                js_wait_time = js_config.get("wait_time", 5.0) if js_config else 5.0
                js_wait_selector = js_config.get("wait_for_selector") if js_config else None
                _, page_pdf_links, soup = crawl_page_js(current_url, selectors, wait_time=js_wait_time, wait_for_selector=js_wait_selector, return_soup=True)
            else:
                headers = {"User-Agent": USER_AGENT}
                response = requests.get(current_url, headers=headers, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, "html.parser")
                
                # Extract PDF links from current page
                pdf_elements = soup.select(pdf_selector)
                page_pdf_links = []
                for elem in pdf_elements:
                    href = elem.get("href", "")
                    if href:
                        absolute_url = urljoin(current_url, href)
                        if absolute_url not in all_pdf_links:
                            page_pdf_links.append(absolute_url)
            
            # Add to all_pdf_links
            for pdf_url in page_pdf_links:
                if pdf_url not in all_pdf_links:
                    all_pdf_links.append(pdf_url)
            
            logger.info(f"Found {len(page_pdf_links)} PDF links on page {page_count} (total: {len(all_pdf_links)})")
            
            # Find next page link
            next_url = None
            
            # Try button selector first
            if next_button_selector:
                # Split selectors by comma and try each
                selectors_list = [s.strip() for s in next_button_selector.split(",")]
                next_button = None
                for sel in selectors_list:
                    next_button = soup.select_one(sel)
                    if next_button:
                        break
                
                if next_button:
                    # Check if button is disabled (DataTables uses 'disabled' class)
                    classes = next_button.get("class", [])
                    if (next_button.get("disabled") or 
                        "disabled" in classes or 
                        "paginate_button" in classes and "disabled" in " ".join(classes)):
                        logger.info("Next button is disabled, reached last page")
                        break
                    # Try to get href from button or parent
                    href = next_button.get("href") or (next_button.find_parent("a") and next_button.find_parent("a").get("href"))
                    if href:
                        next_url = urljoin(current_url, href)
            
            # Try link selector
            if not next_url and next_link_selector:
                # Remove :contains() pseudo-selector if present (not supported by BeautifulSoup)
                clean_selector = next_link_selector.split(":contains")[0].strip()
                try:
                    # Try to use the selector directly (without :contains)
                    potential_links = soup.select(clean_selector) if clean_selector else []
                    for link in potential_links:
                        link_text = link.get_text(strip=True).lower()
                        if "next" in link_text or ">" in link_text or "→" in link_text:
                            href = link.get("href", "")
                            if href:
                                next_url = urljoin(current_url, href)
                                break
                except Exception:
                    pass
                
                # Fallback: search all links if selector didn't work
                if not next_url:
                    all_links = soup.select("a")
                    for link in all_links:
                        link_text = link.get_text(strip=True).lower()
                        # Check if link is in pagination area and contains "next"
                        parent_classes = " ".join(link.find_parent().get("class", []) if link.find_parent() else [])
                        if ("pagination" in parent_classes or "pager" in parent_classes) and ("next" in link_text or ">" in link_text):
                            href = link.get("href", "")
                            if href:
                                next_url = urljoin(current_url, href)
                                break
            
            # Fallback: look for common pagination patterns
            if not next_url:
                # Look for links with "next" text
                for link in soup.find_all("a", string=lambda text: text and "next" in text.lower()):
                    href = link.get("href", "")
                    if href:
                        next_url = urljoin(current_url, href)
                        break
                
                # Look for page number links and find the next one
                if not next_url:
                    page_number_selector = pagination_config.get("page_number_selector", "")
                    if page_number_selector:
                        page_links = soup.select(page_number_selector)
                        current_page_num = None
                        for link in page_links:
                            try:
                                page_num = int(link.get_text(strip=True))
                                if current_page_num is None or page_num == current_page_num + 1:
                                    current_page_num = page_num
                                    href = link.get("href", "")
                                    if href:
                                        next_url = urljoin(current_url, href)
                                        break
                            except ValueError:
                                continue
            
            if not next_url:
                logger.info("No next page found, reached end of pagination")
                break
            
            # Avoid infinite loops
            if next_url == current_url:
                logger.warning("Next URL is same as current, stopping pagination")
                break
            
            current_url = next_url
            time.sleep(wait_time)  # Rate limiting between pages
        
        logger.info(f"Completed pagination: found {len(all_pdf_links)} total PDF links across {page_count} pages")
        return all_pdf_links
    
    except Exception as e:
        logger.error(f"Error during paginated crawling: {e}")
        return all_pdf_links


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into chunks with overlap
    
    Args:
        text: Text to chunk
        chunk_size: Maximum size of each chunk
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Try to break at sentence boundary
        if end < len(text):
            # Look for sentence endings
            for punct in [". ", ".\n", "! ", "!\n", "? ", "?\n"]:
                last_punct = text.rfind(punct, start, end)
                if last_punct != -1:
                    end = last_punct + len(punct)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
        if start >= len(text):
            break
    
    return chunks


def process_local_file(file_path: str, description: str = "", source_url: str = None) -> List[Dict[str, any]]:
    """
    Process a local file from the resources/data folder
    
    Args:
        file_path: Path to the file relative to resources/data or absolute path
        description: Optional description of the file
        source_url: Optional source URL to use in chunks instead of local file path
    
    Returns:
        List of chunks with metadata
    """
    chunks = []
    
    # Resolve file path
    if Path(file_path).is_absolute():
        local_file = Path(file_path)
        # Get relative path from resources/data folder
        data_dir = RESOURCES_DIR / "data"
        try:
            local_source = local_file.relative_to(data_dir)
        except ValueError:
            # If file is not under data folder, use filename only
            local_source = Path(local_file.name)
    else:
        # Assume relative to resources/data
        local_file = RESOURCES_DIR / "data" / file_path
        local_source = Path(file_path)  # Already relative to data folder
    
    if not local_file.exists():
        logger.error(f"Local file not found: {local_file}")
        return []
    
    logger.info(f"Processing local file: {local_file}")
    
    # Use source_url if provided, otherwise use local file path
    url_to_use = source_url if source_url else str(local_file)
    
    # Check file extension to determine processing method
    file_ext = local_file.suffix.lower()
    
    if file_ext == ".pdf":
        # Process PDF file - process all pages for local files
        chunks = extract_pdf_content(local_file, original_url=url_to_use, max_pages=None)
        for chunk in chunks:
            chunk["source_type"] = "local_pdf"
            chunk["source_url"] = url_to_use
            chunk["url"] = url_to_use  # Also update url field
            chunk["local_source"] = str(local_source)  # Relative path to resources/data folder
            chunk["description"] = description
    elif file_ext in [".txt", ".md", ".text"]:
        # Process text file
        try:
            with open(local_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Chunk the text content
            text_chunks = chunk_text(content)
            for i, chunk_text in enumerate(text_chunks):
                chunks.append({
                    "page": None,
                    "text": chunk_text,
                    "url": url_to_use,
                    "source_type": "local_text",
                    "source_url": url_to_use,
                    "local_source": str(local_source),  # Relative path to resources/data folder
                    "chunk_index": i,
                    "description": description
                })
        except Exception as e:
            logger.error(f"Failed to read text file {local_file}: {e}")
            return []
    else:
        logger.warning(f"Unsupported file type for local file: {file_ext}. Supported: .pdf, .txt, .md, .text")
        return []
    
    logger.info(f"Extracted {len(chunks)} chunks from local file: {local_file}")
    return chunks


def process_source(source: Dict[str, any]) -> List[Dict[str, any]]:
    """
    Process a source based on its type
    
    Args:
        source: Source dictionary with 'type', 'url', and other metadata
    
    Returns:
        List of chunks with metadata
    """
    source_type = source.get("type", "").lower()
    url = source.get("url", "")
    description = source.get("description", "")
    
    all_chunks = []
    
    logger.info(f"Processing source: {source_type} - {url}")
    
    if source_type == "local_pdf" or source_type == "local_file":
        # Local file from resources/data folder
        file_path = source.get("file_path") or source.get("url", "")
        source_url = source.get("source_url")  # Get source_url from config if provided
        chunks = process_local_file(file_path, description, source_url=source_url)
        all_chunks.extend(chunks)
    
    elif source_type == "pdf":
        # Direct PDF file - download first, then extract from saved file
        chunks = extract_pdf_from_url(url)
        for chunk in chunks:
            chunk["source_url"] = url
            chunk["description"] = description
        all_chunks.extend(chunks)
    
    elif source_type == "pdf_in_page":
        # Extract PDF links from page and crawl them
        pagination = source.get("pagination", {})
        use_js = source.get("use_javascript", False)
        js_config = source.get("javascript", {})
        
        if pagination.get("enabled", False):
            # Handle paginated table/list
            pdf_selector = source.get("pdf_selector", "a[href$='.pdf']")
            pdf_links = crawl_paginated_pdfs(url, pdf_selector, pagination, use_js=use_js, js_config=js_config)
        else:
            # Single page extraction
            selectors = source.get("selectors", {})
            if not selectors.get("pdf_links"):
                selectors["pdf_links"] = source.get("pdf_selector", "a[href$='.pdf']")
            _, pdf_links = crawl_page(url, selectors, use_js=use_js, js_config=js_config)
        
        for pdf_url in pdf_links:
            time.sleep(REQUEST_DELAY)  # Rate limiting
            chunks = extract_pdf_from_url(pdf_url, referer_url=url)
            for chunk in chunks:
                chunk["source_url"] = url
                chunk["pdf_url"] = pdf_url
                chunk["description"] = description
            all_chunks.extend(chunks)
    
    elif source_type == "page":
        # Crawl entire page content
        use_js = source.get("use_javascript", False)
        js_config = source.get("javascript", {})
        page_content, pdf_links = crawl_page(url, source.get("selectors", {}), use_js=use_js, js_config=js_config)
        
        # Chunk the page content
        if page_content:
            text_chunks = chunk_text(page_content)
            for i, chunk_text in enumerate(text_chunks):
                all_chunks.append({
                    "page": None,
                    "text": chunk_text,
                    "url": url,
                    "source_type": "page",
                    "source_url": url,
                    "chunk_index": i,
                    "description": description
                })
        
        # Also crawl PDFs found on the page
        for pdf_url in pdf_links:
            time.sleep(REQUEST_DELAY)  # Rate limiting
            chunks = extract_pdf_from_url(pdf_url, referer_url=url)
            for chunk in chunks:
                chunk["source_url"] = url
                chunk["pdf_url"] = pdf_url
                chunk["description"] = description
            all_chunks.extend(chunks)
    
    else:
        logger.warning(f"Unknown source type: {source_type}")
    
    logger.info(f"Processed {len(all_chunks)} chunks from source: {url}")
    return all_chunks


def save_chunks(chunks: List[Dict[str, any]], output_file: Path = None) -> Path:
    """
    Save chunks to JSON file
    
    Args:
        chunks: List of chunk dictionaries
        output_file: Path to output file (default: OUTPUT_DIR/chunks.json)
    
    Returns:
        Path to saved file
    """
    if output_file is None:
        output_file = OUTPUT_DIR / "chunks.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved {len(chunks)} chunks to {output_file}")
    return output_file
