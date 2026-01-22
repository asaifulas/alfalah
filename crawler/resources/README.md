# Local Data Files

Place your local data files in data folder to be processed by the crawler.

## Supported File Types

- **PDF files** (`.pdf`) - Processed using PyMuPDF
- **Text files** (`.txt`, `.md`, `.text`) - Processed as plain text

## Usage in sources.json

Add entries to `sources.json` with type `local_pdf` or `local_file`:

```json
{
      "type": "local_pdf",
      "file_path": "charge_card_and_charge_card-i_PD.pdf",
      "source_url": "https://www.bnm.gov.my/documents/20124/938039/charge_card_and_charge_card-i_PD.pdf",
      "description": "Local PDF file from resources/data folder"
    }
```

or

```json
{
      "type": "pdf_in_page",
      "url": "https://www.bnm.gov.my/banking-islamic-banking",
      "description": "Extract PDF links from page and crawl their content",
      "pdf_selector": "a[href$='.pdf']",
      "use_javascript": true,
      "javascript": {
        "wait_time": 5.0,
        "wait_for_selector": "table, .dataTable, [class*='table'], [id*='table']"
      },
      "pagination": {
        "enabled": true,
        "next_button_selector": ".pagination .next, .pager .next, a[aria-label='Next'], button[aria-label='Next'], .paginate_button.next, a.paginate_button.next",
        "next_link_selector": ".pagination a:contains('Next'), .pager a:contains('Next'), a.paginate_button:contains('Next')",
        "page_number_selector": ".pagination .page, .pager .page, .paginate_button",
        "max_pages": 100,
        "wait_time": 2.0,
        "datatables": true
      }
    }
```

or

```json
{
      "type": "pdf_in_page",
      "url": "https://www.bnm.gov.my/banking-islamic-banking",
      "description": "Extract PDF links from page and crawl their content",
      "pdf_selector": "a[href$='.pdf']",
      "use_javascript": true,
      "javascript": {
        "wait_time": 5.0,
        "wait_for_selector": "table, .dataTable, [class*='table'], [id*='table']"
      },
      "pagination": {
        "enabled": false,
      }
    }
```

The `file_path` should be relative to this `data` folder, or you can use an absolute path.

## Examples

- `file_path: "example.pdf"` → looks for `resources/data/example.pdf`
- `file_path: "/absolute/path/to/file.pdf"` → uses absolute path
