#!/usr/bin/env python3
"""
Script to open a local PDF file, navigate to page 5, and take a screenshot
"""
import argparse
import sys
import time
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF

from config import OUTPUT_DIR
from utils import logger

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not available. Will use PyMuPDF method only.")


def cleanup_old_screenshots(output_dir: Path, max_age_minutes: int = 5):
    """
    Remove screenshot files older than specified minutes from the output directory
    
    Args:
        output_dir: Directory containing screenshots
        max_age_minutes: Maximum age in minutes (default: 5)
    """
    if not output_dir.exists():
        return
    
    current_time = time.time()
    max_age_seconds = max_age_minutes * 60
    deleted_count = 0
    deleted_size = 0
    
    try:
        # Get all PNG files in the directory
        screenshot_files = list(output_dir.glob("*.png"))
        
        for screenshot_file in screenshot_files:
            try:
                # Get file modification time
                file_mtime = screenshot_file.stat().st_mtime
                file_age_seconds = current_time - file_mtime
                
                # Delete if older than max_age_minutes
                if file_age_seconds > max_age_seconds:
                    file_size = screenshot_file.stat().st_size
                    screenshot_file.unlink()
                    deleted_count += 1
                    deleted_size += file_size
                    logger.debug(f"Deleted old screenshot: {screenshot_file.name} (age: {file_age_seconds/60:.1f} minutes)")
            except (OSError, FileNotFoundError) as e:
                logger.warning(f"Could not delete {screenshot_file.name}: {e}")
                continue
        
        if deleted_count > 0:
            size_mb = deleted_size / (1024 * 1024)
            logger.info(f"🧹 Cleaned up {deleted_count} old screenshot(s) ({size_mb:.2f} MB) older than {max_age_minutes} minutes")
        else:
            logger.debug(f"No old screenshots to clean up (checked {len(screenshot_files)} files)")
            
    except Exception as e:
        logger.warning(f"Error during screenshot cleanup: {e}")


def screenshot_pdf_page_pymupdf(
    pdf_path: Path,
    page_number: int = 5,
    output_dir: Path = None,
    zoom: float = 2.0,
    dpi: int = 150
) -> Path:
    """
    Render a specific PDF page as an image using PyMuPDF
    
    Args:
        pdf_path: Path to PDF file
        page_number: Page number to render (1-indexed, default: 5)
        output_dir: Directory to save screenshot (default: OUTPUT_DIR/screenshots)
        zoom: Zoom factor for rendering (higher = better quality, default: 2.0)
        dpi: DPI for rendering (default: 150)
    
    Returns:
        Path to saved screenshot
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR / "screenshots"
    output_dir.mkdir(exist_ok=True, parents=True)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    try:
        logger.info(f"Opening PDF: {pdf_path}")
        doc = fitz.open(pdf_path)
        
        total_pages = len(doc)
        logger.info(f"PDF has {total_pages} pages")
        
        # Validate page number
        if page_number < 1:
            logger.warning(f"Page number {page_number} is less than 1, using page 1")
            page_number = 1
        elif page_number > total_pages:
            logger.warning(f"Page number {page_number} exceeds total pages ({total_pages}), using last page")
            page_number = total_pages
        
        # Get the page (0-indexed)
        page = doc[page_number - 1]
        
        logger.info(f"Rendering page {page_number}...")
        
        # Calculate zoom matrix for desired DPI
        # Default PDF is 72 DPI, so zoom = desired_dpi / 72
        zoom_factor = dpi / 72.0 * zoom
        mat = fitz.Matrix(zoom_factor, zoom_factor)
        
        # Render page to pixmap
        pix = page.get_pixmap(matrix=mat)
        
        # Save screenshot directly from pixmap
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_name = pdf_path.stem
        screenshot_path = output_dir / f"{pdf_name}_page_{page_number}_{timestamp}.png"
        
        logger.info(f"Saving screenshot: {screenshot_path}")
        pix.save(screenshot_path)
        
        logger.info(f"✅ Screenshot saved: {screenshot_path} ({pix.width}x{pix.height} pixels)")
        
        doc.close()
        
        # Clean up old screenshots after saving new one
        cleanup_old_screenshots(output_dir, max_age_minutes=5)
        
        return screenshot_path
    
    except Exception as e:
        logger.error(f"Failed to render PDF page: {e}")
        raise


def screenshot_pdf_page_browser(
    pdf_path: Path,
    page_number: int = 5,
    output_dir: Path = None,
    headless: bool = True
) -> Path:
    """
    Open PDF in browser, navigate to page 5, and take screenshot using Playwright
    
    Args:
        pdf_path: Path to PDF file
        page_number: Page number to navigate to (default: 5)
        output_dir: Directory to save screenshot (default: OUTPUT_DIR/screenshots)
        headless: Run browser in headless mode
    
    Returns:
        Path to saved screenshot
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not available. Install with: pip install playwright")
    
    if output_dir is None:
        output_dir = OUTPUT_DIR / "screenshots"
    output_dir.mkdir(exist_ok=True, parents=True)
    
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    # Convert to absolute path for file:// URL
    pdf_absolute_path = pdf_path.resolve()
    pdf_url = f"file://{pdf_absolute_path}"
    
    try:
        logger.info(f"Opening PDF in browser: {pdf_path}")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            
            # Navigate to PDF file
            logger.info(f"Loading PDF: {pdf_url}")
            page.goto(pdf_url, wait_until="networkidle", timeout=30000)
            
            # Wait for PDF to load
            time.sleep(3)
            
            # Try to navigate to specific page using JavaScript
            # Chrome's PDF viewer has a page input field
            logger.info(f"Attempting to navigate to page {page_number}...")
            
            try:
                # Method 1: Try to find and use the page number input
                page_input_selector = "input[type='text'][aria-label*='page'], input[type='text'][title*='page']"
                page_input = page.query_selector(page_input_selector)
                
                if page_input:
                    logger.info("Found page input field, entering page number")
                    page_input.fill(str(page_number))
                    page_input.press("Enter")
                    time.sleep(2)
                else:
                    # Method 2: Use keyboard shortcuts (Ctrl+G or Ctrl+Alt+G to go to page)
                    logger.info("Trying keyboard shortcut to go to page")
                    page.keyboard.press("Control+KeyG")
                    time.sleep(0.5)
                    page.keyboard.type(str(page_number))
                    page.keyboard.press("Enter")
                    time.sleep(2)
            except Exception as e:
                logger.warning(f"Could not navigate to page {page_number} using browser controls: {e}")
                logger.info("Will take screenshot of current page")
            
            # Take screenshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdf_name = pdf_path.stem
            screenshot_path = output_dir / f"{pdf_name}_page_{page_number}_{timestamp}.png"
            
            logger.info(f"Taking screenshot: {screenshot_path}")
            page.screenshot(path=str(screenshot_path), full_page=True)
            
            logger.info(f"✅ Screenshot saved: {screenshot_path}")
            
            browser.close()
            
            # Clean up old screenshots after saving new one
            cleanup_old_screenshots(output_dir, max_age_minutes=5)
            
            return screenshot_path
    
    except Exception as e:
        logger.error(f"Failed to take screenshot with browser: {e}")
        raise


def screenshot_pdf_page(
    pdf_path: Path,
    page_number: int = 5,
    output_dir: Path = None,
    method: str = "pymupdf",
    **kwargs
) -> Path:
    """
    Take a screenshot of a specific page in a PDF file
    
    Args:
        pdf_path: Path to PDF file
        page_number: Page number to screenshot (default: 5)
        output_dir: Directory to save screenshot
        method: Method to use - "pymupdf" (default) or "browser"
        **kwargs: Additional arguments for the method
    
    Returns:
        Path to saved screenshot
    """
    if method == "pymupdf":
        return screenshot_pdf_page_pymupdf(pdf_path, page_number, output_dir, **kwargs)
    elif method == "browser":
        return screenshot_pdf_page_browser(pdf_path, page_number, output_dir, **kwargs)
    else:
        raise ValueError(f"Unknown method: {method}. Use 'pymupdf' or 'browser'")


def main():
    """
    Main function
    """
    parser = argparse.ArgumentParser(description="Open PDF file, navigate to page 5, and take screenshot")
    parser.add_argument(
        "--pdf",
        type=str,
        default=str(OUTPUT_DIR / "my_pdfs" / "charge_card_and_charge_card-i_PD.pdf"),
        help="Path to PDF file (default: output/my_pdfs/charge_card_and_charge_card-i_PD.pdf)"
    )
    parser.add_argument(
        "--page",
        type=int,
        default=5,
        help="Page number to screenshot (default: 5)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save screenshot (default: output/screenshots)"
    )
    parser.add_argument(
        "--method",
        type=str,
        choices=["pymupdf", "browser"],
        default="pymupdf",
        help="Method to use: 'pymupdf' (fast, direct) or 'browser' (Playwright, default: pymupdf)"
    )
    parser.add_argument(
        "--zoom",
        type=float,
        default=2.0,
        help="Zoom factor for PyMuPDF rendering (default: 2.0, higher = better quality)"
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="DPI for PyMuPDF rendering (default: 150)"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Show browser window (only for browser method)"
    )
    
    args = parser.parse_args()
    
    pdf_path = Path(args.pdf)
    output_dir = Path(args.output_dir) if args.output_dir else None
    
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        sys.exit(1)
    
    try:
        kwargs = {}
        if args.method == "pymupdf":
            kwargs["zoom"] = args.zoom
            kwargs["dpi"] = args.dpi
        elif args.method == "browser":
            kwargs["headless"] = not args.no_headless
        
        screenshot_path = screenshot_pdf_page(
            pdf_path=pdf_path,
            page_number=args.page,
            output_dir=output_dir,
            method=args.method,
            **kwargs
        )
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ Screenshot saved successfully!")
        logger.info(f"   PDF: {pdf_path}")
        logger.info(f"   Page: {args.page}")
        logger.info(f"   Method: {args.method}")
        logger.info(f"   Path: {screenshot_path}")
        logger.info(f"{'='*60}")
        
    except Exception as e:
        logger.error(f"Failed to take screenshot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import time
    main()
