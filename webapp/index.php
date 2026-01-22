<?php
/**
 * Simple ChatGPT-like interface for Vertex AI
 * Single PHP file - no framework needed
 */

// Configuration
$CRAWLER_DIR = __DIR__ . '/../crawler';
$OUTPUT_DIR = $CRAWLER_DIR . '/output';
$SCREENSHOT_DIR = $OUTPUT_DIR . '/screenshots';
$PYTHON_SCRIPT = $CRAWLER_DIR . '/query_vertex.py';
$SCREENSHOT_SCRIPT = $CRAWLER_DIR . '/screenshot_page.py';

// Ensure screenshot directory exists
if (!is_dir($SCREENSHOT_DIR)) {
    mkdir($SCREENSHOT_DIR, 0755, true);
}

// Handle API request
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['action'])) {
    header('Content-Type: application/json');
    
    if ($_POST['action'] === 'chat') {
        $question = trim($_POST['question'] ?? '');
        
        if (empty($question)) {
            echo json_encode(['error' => 'Question is required']);
            exit;
        }
        
        // Query Vertex AI via Python script
        $question_escaped = escapeshellarg($question);
        // Redirect stderr to /dev/null to suppress warnings, only capture stdout (JSON)
        $command = "python3 " . escapeshellarg($PYTHON_SCRIPT) . " " . $question_escaped . " 3 2>/dev/null";
        
        $output = shell_exec($command);
        $results = json_decode($output, true);
        
        // Check if JSON decode failed or returned null
        if ($results === null && json_last_error() !== JSON_ERROR_NONE) {
            echo json_encode(['error' => 'Failed to parse query results: ' . json_last_error_msg() . '. Output: ' . substr($output, 0, 200)]);
            exit;
        }
        
        // Check if results is an error response
        if (isset($results['error'])) {
            echo json_encode(['error' => $results['error']]);
            exit;
        }
        
        // Check if we have a natural answer (new format)
        $natural_answer = null;
        $sources = $results;
        
        if (is_array($results) && isset($results['answer']) && isset($results['sources'])) {
            // New format with natural answer
            $natural_answer = $results['answer'];
            $sources = $results['sources'];
            
            // Log the answer received from Python script
            error_log("=== PHP: RECEIVED ANSWER FROM PYTHON (Length: " . strlen($natural_answer) . " chars) ===");
            error_log("First 200 chars: " . substr($natural_answer, 0, 200) . "...");
            error_log("Last 200 chars: ..." . substr($natural_answer, -200));
            error_log("=== END PHP RECEIVED ANSWER ===");
        } elseif (is_array($results)) {
            // Old format - just chunks (array of results)
            $sources = $results;
        } else {
            echo json_encode(['error' => 'Invalid results format. Expected array, got: ' . gettype($results)]);
            exit;
        }
        
        // Process each result and generate screenshots
        $processed_results = [];
        foreach ($sources as $result_index => $result) {
            $metadata = $result['metadata'] ?? [];
            
            // Debug: log metadata structure for first result
            if ($result_index === 0) {
                error_log("First result metadata: " . json_encode($metadata));
            }
            
            // Extract URL, local_source, and page from metadata
            $url = $metadata['url'] ?? $metadata['source_url'] ?? '';
            $local_source = $metadata['local_source'] ?? '';
            $page = $metadata['page'] ?? null;
            
            // Debug: log extracted values
            if ($result_index === 0) {
                error_log("Extracted - url: " . ($url ?: 'empty') . ", local_source: " . ($local_source ?: 'empty') . ", page: " . ($page ?? 'null'));
            }
            
            // Determine PDF path for screenshot
            $pdf_path = null;
            
            // Try local_source first (usually relative path like "resources/data/filename.pdf")
            if ($local_source) {
                // local_source is typically a relative path from crawler directory
                // e.g., "resources/data/charge_card_and_charge_card-i_PD.pdf"
                
                // Try as-is (if it's already absolute)
                if (file_exists($local_source)) {
                    $pdf_path = $local_source;
                } else {
                    // Try relative to crawler directory (most common case)
                    $crawler_pdf_path = $CRAWLER_DIR . '/' . $local_source;
                    if (file_exists($crawler_pdf_path)) {
                        $pdf_path = $crawler_pdf_path;
                    } else {
                        // Try in resources/data with just filename
                        $crawler_pdf_path2 = $CRAWLER_DIR . '/resources/data/' . basename($local_source);
                        if (file_exists($crawler_pdf_path2)) {
                            $pdf_path = $crawler_pdf_path2;
                        } else {
                            // Try resources/data with full path
                            $crawler_pdf_path3 = $CRAWLER_DIR . '/resources/data/' . $local_source;
                            if (file_exists($crawler_pdf_path3)) {
                                $pdf_path = $crawler_pdf_path3;
                            }
                        }
                    }
                }
            }
            
            // Fallback to URL if local_source didn't work
            if (!$pdf_path) {
                if ($url && strpos($url, 'file://') === 0) {
                    $pdf_path = substr($url, 7);
                    if (!file_exists($pdf_path)) {
                        $pdf_path = null;
                    }
                } elseif ($url && file_exists($url)) {
                    $pdf_path = $url;
                }
            }
            
            // Extract source name from URL or metadata
            $source_name = $metadata['description'] ?? '';
            if (empty($source_name)) {
                if ($url) {
                    $source_name = basename(parse_url($url, PHP_URL_PATH));
                    if (empty($source_name) || $source_name === '/') {
                        $source_name = parse_url($url, PHP_URL_HOST) ?? 'Document';
                    }
                } elseif ($local_source) {
                    $source_name = basename($local_source);
                } else {
                    $source_name = 'Document';
                }
            }
            
            // Clean up text: remove excessive newlines and normalize whitespace
            $text = $result['text'] ?? '';
            $text = preg_replace('/\r\n|\r|\n/', ' ', $text);  // Replace line breaks with space
            $text = preg_replace('/\s+/', ' ', $text);          // Replace multiple spaces with single space
            $text = preg_replace('/\s+([.,;:!?])/', '$1', $text); // Remove space before punctuation
            $text = preg_replace('/([.,;:!?])\s+/', '$1 ', $text); // Ensure space after punctuation
            $text = trim($text);                                // Remove leading/trailing whitespace
            
            $processed_result = [
                'text' => $text,
                'source_name' => $source_name,
                'source_url' => $url,
                'local_source' => $local_source,
                'page' => $page,
                'score' => $result['score'] ?? 0
            ];
            
            // Generate screenshot if we have PDF path and page number
            if ($pdf_path && $page !== null && is_numeric($page) && $page > 0) {
                if (file_exists($pdf_path)) {
                    error_log("Generating screenshot for: " . $pdf_path . " page " . $page);
                    $screenshot_path = generate_screenshot($pdf_path, $page, $SCREENSHOT_SCRIPT, $SCREENSHOT_DIR);
                    if ($screenshot_path && file_exists($screenshot_path)) {
                        // Create web-accessible URL for the screenshot
                        $screenshot_filename = basename($screenshot_path);
                        $processed_result['screenshot'] = '?screenshot=' . urlencode($screenshot_filename);
                        $processed_result['screenshot_path'] = $screenshot_path; // Keep full path for reference
                        error_log("Screenshot generated: " . $screenshot_path);
                    } else {
                        error_log("Screenshot generation failed for: " . $pdf_path . " page " . $page);
                    }
                } else {
                    error_log("PDF file not found for screenshot: " . $pdf_path);
                }
            } else {
                // Debug: log why screenshot wasn't generated
                $debug_info = [
                    'pdf_path' => $pdf_path ? 'set' : 'null',
                    'page' => $page,
                    'pdf_exists' => $pdf_path ? (file_exists($pdf_path) ? 'yes' : 'no') : 'N/A'
                ];
                error_log("Screenshot not generated. Debug: " . json_encode($debug_info));
            }
            
            $processed_results[] = $processed_result;
        }
        
        $response = [
            'question' => $question,
            'results' => $processed_results
        ];
        
        // Add natural answer if available
        if ($natural_answer) {
            $response['answer'] = $natural_answer;
            
            // Log what we're sending to frontend
            error_log("=== PHP: SENDING ANSWER TO FRONTEND (Length: " . strlen($natural_answer) . " chars) ===");
            error_log("First 200 chars: " . substr($natural_answer, 0, 200) . "...");
            error_log("Last 200 chars: ..." . substr($natural_answer, -200));
            error_log("=== END PHP SENDING ANSWER ===");
        }
        
        echo json_encode($response);
        exit;
    }
}

// Serve screenshot files
if (isset($_GET['screenshot'])) {
    $filename = basename($_GET['screenshot']);
    $filepath = $SCREENSHOT_DIR . '/' . $filename;
    
    if (file_exists($filepath) && is_file($filepath)) {
        header('Content-Type: image/png');
        readfile($filepath);
        exit;
    } else {
        http_response_code(404);
        exit;
    }
}

/**
 * Generate screenshot using Python script
 */
function generate_screenshot($pdf_path, $page_number, $screenshot_script, $output_dir) {
    // Ensure output directory exists
    if (!is_dir($output_dir)) {
        mkdir($output_dir, 0755, true);
    }
    
    // The script expects to run from crawler directory with relative paths
    // e.g., "python3 screenshot_page.py --pdf resources/data/file.pdf --page 565"
    global $CRAWLER_DIR;
    $crawler_dir_real = realpath($CRAWLER_DIR);
    if (!$crawler_dir_real) {
        error_log("Screenshot: Crawler directory not found: " . $CRAWLER_DIR);
        return null;
    }
    
    // Find PDF file and get relative path from crawler directory
    $pdf_path_abs = null;
    $pdf_relative = null;
    
    // Check if PDF exists as absolute path
    if (file_exists($pdf_path)) {
        $pdf_path_abs = realpath($pdf_path);
    } else {
        // Try relative to crawler directory
        $try_path = $crawler_dir_real . '/' . $pdf_path;
        if (file_exists($try_path)) {
            $pdf_path_abs = realpath($try_path);
        } else {
            // Try in resources/data
            $try_path2 = $crawler_dir_real . '/resources/data/' . basename($pdf_path);
            if (file_exists($try_path2)) {
                $pdf_path_abs = realpath($try_path2);
            }
        }
    }
    
    if (!$pdf_path_abs || !file_exists($pdf_path_abs)) {
        error_log("Screenshot: PDF file not found: " . $pdf_path);
        return null;
    }
    
    // Calculate relative path from crawler directory
    $pdf_relative = str_replace($crawler_dir_real . '/', '', $pdf_path_abs);
    
    // Verify script exists
    $screenshot_script_abs = realpath($screenshot_script);
    if (!$screenshot_script_abs || !file_exists($screenshot_script_abs)) {
        error_log("Screenshot: Script not found: " . $screenshot_script);
        return null;
    }
    $script_name = basename($screenshot_script_abs);
    
    // Build command - run from crawler directory with relative PDF path
    // Format: cd crawler && python3 screenshot_page.py --pdf resources/data/file.pdf --page 565
    $page_escaped = escapeshellarg($page_number);
    $pdf_relative_escaped = escapeshellarg($pdf_relative);
    $output_dir_escaped = escapeshellarg($output_dir);
    
    $command = "cd " . escapeshellarg($crawler_dir_real) . 
               " && python3 " . escapeshellarg($script_name) . 
               " --pdf " . $pdf_relative_escaped . 
               " --page " . $page_escaped . 
               " --output-dir " . $output_dir_escaped . 
               " --method pymupdf 2>&1";
    
    error_log("Running screenshot command: " . $command);
    $output = shell_exec($command);
    error_log("Screenshot command output: " . substr($output, 0, 500));
    
    // Wait a moment for file to be written
    usleep(500000); // 0.5 seconds
    
    // Find the generated screenshot
    $pdf_name = pathinfo($pdf_path_abs, PATHINFO_FILENAME);
    $pattern = $output_dir . '/' . $pdf_name . '_page_' . $page_number . '_*.png';
    error_log("Looking for screenshot pattern: " . $pattern);
    
    $files = glob($pattern);
    error_log("Found " . count($files) . " matching files");
    
    if ($files && count($files) > 0) {
        // Get the most recent one
        usort($files, function($a, $b) {
            return filemtime($b) - filemtime($a);
        });
        $screenshot_file = $files[0];
        
        // Verify the file exists and is readable
        if (file_exists($screenshot_file) && is_readable($screenshot_file)) {
            error_log("✅ Screenshot found: " . $screenshot_file);
            return $screenshot_file;
        } else {
            error_log("Screenshot file not readable: " . $screenshot_file);
        }
    }
    
    // Log error if screenshot generation failed
    error_log("❌ Screenshot generation failed for: " . $pdf_path . " page " . $page_number);
    error_log("Command output: " . substr($output, 0, 500));
    return null;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vertex AI Chat</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #1a1a1a;
            color: #ffffff;
            height: 100vh;
            overflow: hidden;
        }
        
        /* Hide/transparentize scrollbars */
        * {
            scrollbar-width: thin;
            scrollbar-color: rgba(255, 255, 255, 0.1) transparent;
        }
        
        *::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        *::-webkit-scrollbar-track {
            background: transparent;
        }
        
        *::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
        }
        
        *::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }
        
        .main-container {
            display: flex;
            height: 100vh;
            justify-content: center;
        }
        
        .content-area {
            width: 100%;
            max-width: 1200px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            margin: 0 auto;
        }
        
        .header {
            padding: 24px 32px;
            background: #1a1a1a;
            border-bottom: 1px solid #2d2d2d;
            text-align: center;
        }
        
        .header h1 {
            font-size: 32px;
            font-weight: 600;
            color: #ffffff;
        }
        
        .main-content {
            flex: 1;
            overflow-y: auto;
            padding: 40px 32px;
            background: #1a1a1a;
            max-width: 900px;
            margin: 0 auto;
            width: 100%;
        }
        
        /* Tablet styles */
        @media (max-width: 1024px) {
            .main-content {
                padding: 32px 24px;
            }
            
            .header {
                padding: 20px 24px;
            }
            
            .header h1 {
                font-size: 28px;
            }
            
            .input-container {
                padding: 16px 24px;
            }
            
            .content-area {
                max-width: 100%;
            }
        }
        
        /* Mobile styles */
        @media (max-width: 768px) {
            body {
                overflow: auto;
            }
            
            .main-container {
                flex-direction: column;
            }
            
            .content-area {
                width: 100%;
                max-width: 100%;
            }
            
            .header {
                padding: 16px 20px;
                position: sticky;
                top: 0;
                z-index: 100;
            }
            
            .header h1 {
                font-size: 22px;
            }
            
            .main-content {
                padding: 24px 16px;
                max-width: 100%;
            }
            
            .question-section {
                margin-bottom: 24px;
                padding: 16px 20px;
            }
            
            .question-text {
                font-size: 16px;
            }
            
            .section {
                margin-bottom: 24px;
            }
            
            .answer-section {
                padding: 20px;
                margin-bottom: 20px;
            }
            
            .section-title {
                font-size: 14px;
                margin-bottom: 12px;
            }
            
            .sources-container {
                gap: 8px;
            }
            
            .source-card {
                padding: 10px 12px;
                font-size: 12px;
                flex: 1 1 calc(50% - 4px);
                min-width: 0;
            }
            
            .source-card span:first-of-type {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            
            .view-more {
                padding: 10px 12px;
                font-size: 12px;
            }
            
            .research-progress {
                padding: 12px;
                font-size: 14px;
            }
            
            .answer-content {
                font-size: 14px;
                line-height: 1.7;
            }
            
            .answer-content h2 {
                font-size: 18px;
                margin: 20px 0 12px 0;
            }
            
            .answer-content p {
                margin-bottom: 12px;
            }
            
            .answer-footer {
                margin-top: 16px;
                padding-top: 12px;
                gap: 10px;
            }
            
            .answer-screenshot {
                max-width: 200px;
            }
            
            .answer-screenshot-img {
                max-width: 200px;
            }
            
            .answer-source-link {
                font-size: 12px;
                padding: 6px 10px;
            }
            
            .input-container {
                padding: 12px 16px;
                position: sticky;
                bottom: 0;
                background: #1a1a1a;
                border-top: 1px solid #2d2d2d;
                z-index: 100;
            }
            
            .input-wrapper {
                max-width: 100%;
            }
            
            .input-form {
                gap: 8px;
            }
            
            .input-field {
                padding: 12px 16px;
                font-size: 14px;
            }
            
            .send-button {
                padding: 12px 20px;
                font-size: 14px;
            }
            
            .empty-state {
                padding: 40px 20px;
            }
            
            .empty-state-icon {
                font-size: 48px;
                margin-bottom: 16px;
            }
            
            .empty-state p {
                font-size: 14px;
            }
        }
        
        /* Small mobile styles */
        @media (max-width: 480px) {
            .header {
                padding: 12px 16px;
            }
            
            .header h1 {
                font-size: 20px;
            }
            
            .main-content {
                padding: 20px 12px;
            }
            
            .question-section {
                margin-bottom: 20px;
                padding: 12px 14px;
            }
            
            .question-text {
                font-size: 14px;
            }
            
            .section {
                margin-bottom: 20px;
            }
            
            .answer-section {
                padding: 14px;
                margin-bottom: 16px;
            }
            
            .source-card {
                flex: 1 1 100%;
                font-size: 11px;
                padding: 8px 10px;
            }
            
            .answer-content {
                font-size: 13px;
            }
            
            .answer-content h2 {
                font-size: 16px;
            }
            
            .answer-footer {
                margin-top: 20px;
                padding-top: 16px;
                gap: 12px;
            }
            
            .answer-screenshot {
                max-width: 200px;
            }
            
            .answer-screenshot-img {
                max-width: 200px;
            }
            
            .answer-source-link {
                font-size: 13px;
                padding: 6px 12px;
            }
            
            .input-field {
                padding: 10px 14px;
                font-size: 13px;
            }
            
            .send-button {
                padding: 10px 16px;
                font-size: 13px;
            }
            
            .citation {
                font-size: 0.85em;
            }
        }
        
        /* Touch-friendly improvements for mobile */
        @media (max-width: 768px) {
            .source-card,
            .view-more,
            .research-progress {
                min-height: 44px; /* iOS touch target size */
            }
            
            .send-button {
                min-width: 80px;
            }
        }
        
        .question-section {
            margin-bottom: 32px;
            padding: 20px 24px;
            background: #2d2d2d;
            border-radius: 12px;
            border-left: 4px solid #007bff;
        }
        
        .question-text {
            font-size: 18px;
            font-weight: 500;
            color: #ffffff;
            line-height: 1.6;
        }
        
        .section {
            margin-bottom: 32px;
            width: 100%;
        }
        
        .answer-section {
            background: #1f1f1f;
            padding: 24px;
            border-radius: 12px;
            border: 1px solid #2d2d2d;
            margin-bottom: 24px;
        }
        
        .answer-section:last-child {
            margin-bottom: 0;
        }
        
        .section-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 16px;
            color: #ffffff;
        }
        
        .section-icon {
            width: 18px;
            height: 18px;
            opacity: 0.8;
        }
        
        .sources-container {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 16px;
        }
        
        .source-card {
            background: #2d2d2d;
            border-radius: 8px;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            color: #ffffff;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .source-card:hover {
            background: #3a3a3a;
        }
        
        .source-icon {
            width: 16px;
            height: 16px;
            border-radius: 3px;
            background: #4a4a4a;
        }
        
        .source-number {
            color: #888;
            font-size: 12px;
        }
        
        .view-more {
            background: #2d2d2d;
            border-radius: 8px;
            padding: 12px 16px;
            color: #ffffff;
            font-size: 14px;
            cursor: pointer;
            border: none;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .research-progress {
            background: #2d2d2d;
            border-radius: 8px;
            padding: 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .research-progress:hover {
            background: #3a3a3a;
        }
        
        .research-progress-content {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .answer-content {
            line-height: 1.8;
            font-size: 15px;
            color: #ffffff;
        }
        
        /* Natural answer scrollbar styling */
        .answer-section .answer-content {
            scrollbar-width: thin;
            scrollbar-color: #cbd5e0 #f7fafc;
        }
        
        .answer-section .answer-content::-webkit-scrollbar {
            width: 8px;
        }
        
        .answer-section .answer-content::-webkit-scrollbar-track {
            background: #f7fafc;
            border-radius: 4px;
        }
        
        .answer-section .answer-content::-webkit-scrollbar-thumb {
            background: #cbd5e0;
            border-radius: 4px;
        }
        
        .answer-section .answer-content::-webkit-scrollbar-thumb:hover {
            background: #a0aec0;
        }
        
        .answer-content p {
            margin-bottom: 16px;
        }
        
        .answer-content h2 {
            font-size: 20px;
            font-weight: 600;
            margin: 24px 0 16px 0;
            color: #ffffff;
        }
        
        .citation {
            color: #888;
            font-size: 0.9em;
            margin-left: 2px;
        }
        
        .answer-footer {
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px solid #2d2d2d;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        
        .answer-screenshot {
            width: 100%;
            max-width: 250px;
            margin: 0 auto;
        }
        
        .screenshot-link {
            display: block;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        
        .screenshot-link:hover {
            opacity: 0.9;
        }
        
        .answer-screenshot-img {
            width: 100%;
            height: auto;
            max-width: 250px;
            border-radius: 8px;
            border: 1px solid #2d2d2d;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            display: block;
        }
        
        .answer-link {
            display: flex;
            justify-content: center;
            align-items: center;
        }
        
        .answer-source-link {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            color: #007bff;
            text-decoration: none;
            font-size: 14px;
            padding: 8px 16px;
            border: 1px solid #007bff;
            border-radius: 6px;
            transition: all 0.2s;
        }
        
        .answer-source-link:hover {
            background: #007bff;
            color: #ffffff;
        }
        
        .link-icon {
            width: 16px;
            height: 16px;
        }
        
        .sidebar {
            display: none !important;
            width: 320px;
            background: #1a1a1a;
            border-left: 1px solid #2d2d2d;
            padding: 24px;
            overflow-y: auto;
            position: fixed;
            right: 0;
            top: 0;
            height: 100vh;
        }
        
        .sidebar-image {
            width: 100%;
            border-radius: 8px;
            margin-bottom: 16px;
            background: #2d2d2d;
            aspect-ratio: 1;
            object-fit: cover;
        }
        
        .sidebar-thumbnails {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
            flex-wrap: wrap;
        }
        
            .sidebar-thumbnail {
                width: 60px;
                height: 60px;
                border-radius: 6px;
                object-fit: cover;
                background: #2d2d2d;
                cursor: pointer;
                transition: opacity 0.2s;
            }
            
            .sidebar-thumbnail:hover {
                opacity: 0.8;
            }
        
        /* Hide sidebar on smaller screens */
        @media (max-width: 1400px) {
            .sidebar {
                display: none;
            }
        }
        
        /* Show sidebar as modal on mobile when there are screenshots */
        @media (max-width: 768px) {
            .sidebar {
                display: none;
                position: fixed;
                width: 100%;
                height: 100%;
                z-index: 1000;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                border-left: none;
                padding: 20px;
            }
            
            .sidebar.active {
                display: block;
            }
            
            .sidebar-close {
                position: absolute;
                top: 16px;
                right: 16px;
                background: #2d2d2d;
                border: none;
                color: #fff;
                width: 36px;
                height: 36px;
                border-radius: 50%;
                cursor: pointer;
                font-size: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 1001;
                transition: background 0.2s;
            }
            
            .sidebar-close:hover {
                background: #3a3a3a;
            }
            
            .sidebar-image {
                margin-top: 40px;
            }
        }
        
        
        .input-container {
            padding: 20px 32px;
            background: #1a1a1a;
            border-top: 1px solid #2d2d2d;
            display: flex;
            justify-content: center;
        }
        
        .input-wrapper {
            width: 100%;
            max-width: 900px;
        }
        
        .input-form {
            display: flex;
            gap: 12px;
            width: 100%;
        }
        
        .input-field {
            flex: 1;
            padding: 14px 20px;
            background: #2d2d2d;
            border: 1px solid #3a3a3a;
            border-radius: 24px;
            font-size: 15px;
            color: #ffffff;
            outline: none;
        }
        
        .input-field::placeholder {
            color: #888;
        }
        
        .input-field:focus {
            border-color: #555;
            background: #333;
        }
        
        .send-button {
            padding: 14px 28px;
            background: #007bff;
            color: white;
            border: none;
            border-radius: 24px;
            font-size: 15px;
            cursor: pointer;
            font-weight: 500;
            transition: background 0.2s;
        }
        
        .send-button:hover {
            background: #0056b3;
        }
        
        .send-button:disabled {
            background: #444;
            cursor: not-allowed;
        }
        
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #2d2d2d;
            border-top: 3px solid #007bff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .error {
            color: #ff6b6b;
            background: #3a1f1f;
            padding: 12px 16px;
            border-radius: 8px;
            margin-top: 16px;
            word-wrap: break-word;
        }
        
        @media (max-width: 768px) {
            .error {
                padding: 10px 12px;
                font-size: 13px;
            }
        }
        
        .chevron {
            width: 16px;
            height: 16px;
            opacity: 0.6;
        }
        
        .empty-state {
            text-align: center;
            padding: 80px 20px;
            color: #888;
            max-width: 600px;
            margin: 0 auto;
        }
        
        .empty-state-icon {
            font-size: 64px;
            margin-bottom: 24px;
        }
        
        .empty-state p {
            font-size: 16px;
            line-height: 1.6;
            margin-bottom: 12px;
        }
    </style>
</head>
<body>
    <div class="main-container">
        <div class="content-area">
            <div class="header">
                <h1 id="pageTitle">Al-Falah Syariah Chatbox</h1>
            </div>
            
            <div class="main-content" id="mainContent">
                <div class="empty-state">
                    <div class="empty-state-icon">💬</div>
                    <p>Ask me anything about the Sharia Standards in the knowledge base.</p>
                    <p>I am a chatbot that can answer questions about the Sharia Standards in the knowledge base.</p>
                </div>
            </div>
            
            <div class="input-container">
                <div class="input-wrapper">
                    <form class="input-form" id="chatForm" onsubmit="sendMessage(event)">
                        <input 
                            type="text" 
                            class="input-field" 
                            id="questionInput" 
                            placeholder="Type your question here..."
                            autocomplete="off"
                        >
                        <button type="submit" class="send-button" id="sendButton">Send</button>
                    </form>
                </div>
            </div>
        </div>
        
        <div class="sidebar" id="sidebar">
            <!-- Screenshots will be displayed here -->
        </div>
    </div>
    
    <script>
        const mainContent = document.getElementById('mainContent');
        const sidebar = document.getElementById('sidebar');
        const questionInput = document.getElementById('questionInput');
        const sendButton = document.getElementById('sendButton');
        const pageTitle = document.getElementById('pageTitle');
        
        function formatTextWithCitations(text, resultIndex) {
            // Simple citation formatting - add superscript numbers
            // In a real implementation, you'd parse the text and add citations
            return text.split('\n').map(para => {
                if (para.trim()) {
                    // Add citation number at the end
                    return para + ' <span class="citation">' + (resultIndex + 1) + '</span>';
                }
                return para;
            }).join('\n');
        }
        
        function createSourceCard(sourceName, sourceType, index) {
            const card = document.createElement('div');
            card.className = 'source-card';
            
            const icon = document.createElement('div');
            icon.className = 'source-icon';
            icon.textContent = sourceType ? sourceType.charAt(0).toUpperCase() : '📄';
            
            const text = document.createElement('span');
            text.textContent = sourceName.length > 25 ? sourceName.substring(0, 22) + '...' : sourceName;
            
            const number = document.createElement('span');
            number.className = 'source-number';
            number.textContent = ' • ' + (index + 1);
            
            card.appendChild(icon);
            card.appendChild(text);
            card.appendChild(number);
            
            return card;
        }
        
        function cleanText(text) {
            if (!text) return '';
            
            // Remove excessive whitespace and normalize
            return text
                .replace(/\r\n/g, ' ')      // Replace Windows line breaks with space
                .replace(/\n/g, ' ')        // Replace Unix line breaks with space
                .replace(/\r/g, ' ')        // Replace old Mac line breaks with space
                .replace(/\s+/g, ' ')       // Replace multiple spaces with single space
                .replace(/\s+([.,;:!?])/g, '$1')  // Remove space before punctuation
                .replace(/([.,;:!?])\s+/g, '$1 ')  // Ensure single space after punctuation
                .replace(/\s*-\s*/g, ' - ') // Normalize dashes
                .trim();                    // Remove leading/trailing whitespace
        }
        
        function createAnswerSection(results, answerNumber = null) {
            const section = document.createElement('div');
            section.className = 'section answer-section';
            
            // Add answer number if provided
            const title = document.createElement('div');
            title.className = 'section-title';
            let titleText = '<svg class="section-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> Answer';
            if (answerNumber) {
                titleText = `<svg class="section-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> Answer ${answerNumber}`;
            }
            title.innerHTML = titleText;
            section.appendChild(title);
            
            const content = document.createElement('div');
            content.className = 'answer-content';
            
            // Process each result separately (now we only get one result per call)
            results.forEach((result, index) => {
                if (!result.text) return;
                
                const cleaned = cleanText(result.text);
                if (!cleaned) return;
                
                // Split into sentences
                const sentences = cleaned.split(/(?<=[.!?])\s+(?=[A-Z])/).filter(s => s.trim());
                
                // Group sentences into paragraphs (3-5 sentences per paragraph)
                const paragraphs = [];
                let currentPara = [];
                
                sentences.forEach((sentence, sentenceIndex) => {
                    const trimmed = sentence.trim();
                    if (!trimmed) return;
                    
                    currentPara.push(trimmed);
                    
                    // Create paragraph every 3-5 sentences, or at natural breaks
                    const isNaturalBreak = trimmed.match(/[.!?]$/) && 
                                          (sentenceIndex === sentences.length - 1 || 
                                           sentences[sentenceIndex + 1]?.match(/^[A-Z]/));
                    
                    if (currentPara.length >= 3 && (currentPara.length >= 5 || isNaturalBreak)) {
                        paragraphs.push(currentPara.join(' '));
                        currentPara = [];
                    }
                });
                
                // Add remaining sentences as last paragraph
                if (currentPara.length > 0) {
                    paragraphs.push(currentPara.join(' '));
                }
                
                // If no paragraphs created, use the whole text as one paragraph
                if (paragraphs.length === 0 && cleaned.trim()) {
                    paragraphs.push(cleaned.trim());
                }
                
                // Display paragraphs
                paragraphs.forEach((para, paraIndex) => {
                    // Check if it's a heading (short, starts with capital, no punctuation at end)
                    const isHeading = para.length < 100 && 
                                     para[0] === para[0].toUpperCase() &&
                                     !para.match(/[.!?]$/) &&
                                     !para.match(/\d+\s+\d+/); // No citation patterns
                    
                    if (isHeading && paraIndex === 0) {
                        const h2 = document.createElement('h2');
                        h2.textContent = para.trim();
                        content.appendChild(h2);
                    } else {
                        const p = document.createElement('p');
                        let paraText = para.trim();
                        
                        // Ensure proper sentence ending
                        if (!paraText.match(/[.!?]$/)) {
                            paraText += '.';
                        }
                        
                        // Add citation
                        if (answerNumber) {
                            paraText += ' <span class="citation">' + answerNumber + '</span>';
                        }
                        
                        p.innerHTML = paraText;
                        content.appendChild(p);
                    }
                });
            });
            
            section.appendChild(content);
            
            // Add footer with screenshot and link (use first result for footer info)
            if (results.length > 0) {
                const result = results[0];
                const footer = document.createElement('div');
                footer.className = 'answer-footer';
                
                // Add screenshot if available
                if (result.screenshot) {
                    const screenshotContainer = document.createElement('div');
                    screenshotContainer.className = 'answer-screenshot';
                    
                    // Create clickable link to screenshot
                    const screenshotLink = document.createElement('a');
                    screenshotLink.href = result.screenshot;
                    screenshotLink.target = '_blank';
                    screenshotLink.rel = 'noopener noreferrer';
                    screenshotLink.className = 'screenshot-link';
                    
                    const img = document.createElement('img');
                    img.src = result.screenshot;
                    img.alt = `Page ${result.page || ''} screenshot`;
                    img.className = 'answer-screenshot-img';
                    img.title = 'Click to view full size';
                    
                    screenshotLink.appendChild(img);
                    screenshotContainer.appendChild(screenshotLink);
                    footer.appendChild(screenshotContainer);
                }
                
                // Add link to source URL with page number
                const linkContainer = document.createElement('div');
                linkContainer.className = 'answer-link';
                
                if (result.source_url || result.local_source) {
                    const link = document.createElement('a');
                    link.className = 'answer-source-link';
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    
                    // Build URL with page anchor if page number exists
                    let linkUrl = result.source_url || result.local_source;
                    if (result.page && result.page > 0) {
                        // If it's a PDF URL, try to add page parameter
                        if (linkUrl.includes('.pdf') || linkUrl.includes('pdf')) {
                            // For PDFs, add #page=X anchor
                            linkUrl = linkUrl.split('#')[0] + '#page=' + result.page;
                        } else {
                            // For web pages, add ?page=X parameter
                            const separator = linkUrl.includes('?') ? '&' : '?';
                            linkUrl = linkUrl + separator + 'page=' + result.page;
                        }
                    }
                    
                    link.href = linkUrl;
                    link.innerHTML = '<svg class="link-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/></svg> View Source';
                    if (result.page) {
                        link.innerHTML += ` (Page ${result.page})`;
                    }
                    linkContainer.appendChild(link);
                }
                
                if (result.screenshot || (result.source_url || result.local_source)) {
                    footer.appendChild(linkContainer);
                    section.appendChild(footer);
                }
            }
            
            return section;
        }
        
        function createSourcesSection(results) {
            const section = document.createElement('div');
            section.className = 'section';
            
            const title = document.createElement('div');
            title.className = 'section-title';
            title.innerHTML = '<svg class="section-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg> Sources';
            section.appendChild(title);
            
            const container = document.createElement('div');
            container.className = 'sources-container';
            
            results.forEach((result, index) => {
                const sourceName = result.source_name || result.source_url || result.pdf_url || `Source ${index + 1}`;
                const sourceType = extractSourceType(result.source_url || result.pdf_url || '');
                const card = createSourceCard(sourceName, sourceType, index);
                container.appendChild(card);
            });
            
            if (results.length > 3) {
                const viewMore = document.createElement('button');
                viewMore.className = 'view-more';
                viewMore.textContent = 'View ' + (results.length - 3) + ' more';
                container.appendChild(viewMore);
            }
            
            section.appendChild(container);
            return section;
        }
        
        function createResearchProgressSection() {
            const section = document.createElement('div');
            section.className = 'section';
            
            const progress = document.createElement('div');
            progress.className = 'research-progress';
            
            const content = document.createElement('div');
            content.className = 'research-progress-content';
            content.innerHTML = '<svg class="section-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> Research Progress (2 steps)';
            
            const chevron = document.createElement('svg');
            chevron.className = 'chevron';
            chevron.setAttribute('viewBox', '0 0 24 24');
            chevron.setAttribute('fill', 'currentColor');
            chevron.innerHTML = '<path d="M16.59 8.59L12 13.17 7.41 8.59 6 10l6 6 6-6z"/>';
            
            progress.appendChild(content);
            progress.appendChild(chevron);
            section.appendChild(progress);
            
            return section;
        }
        
        function extractSourceType(url) {
            if (!url) return 'doc';
            if (url.includes('bnm')) return 'bnm';
            if (url.includes('financial')) return 'financialmarkets';
            if (url.includes('business')) return 'businesstoday';
            return 'doc';
        }
        
        function updateSidebar(results) {
            sidebar.innerHTML = '';
            
            const screenshots = results.filter(r => r.screenshot);
            
            // Add close button for mobile
            if (window.innerWidth <= 768 && screenshots.length > 0) {
                const closeBtn = document.createElement('button');
                closeBtn.className = 'sidebar-close';
                closeBtn.innerHTML = '×';
                closeBtn.onclick = () => sidebar.classList.remove('active');
                sidebar.appendChild(closeBtn);
            }
            
            screenshots.forEach((result, index) => {
                if (index === 0 && result.screenshot) {
                    // Main image
                    const img = document.createElement('img');
                    img.src = result.screenshot;
                    img.className = 'sidebar-image';
                    img.alt = 'Document screenshot';
                    sidebar.appendChild(img);
                } else if (result.screenshot) {
                    // Thumbnails
                    if (index === 1) {
                        const thumbnails = document.createElement('div');
                        thumbnails.className = 'sidebar-thumbnails';
                        sidebar.appendChild(thumbnails);
                    }
                    
                    const thumbnails = sidebar.querySelector('.sidebar-thumbnails');
                    if (thumbnails) {
                        const thumb = document.createElement('img');
                        thumb.src = result.screenshot;
                        thumb.className = 'sidebar-thumbnail';
                        thumb.alt = 'Thumbnail';
                        thumb.onclick = () => {
                            // On mobile, clicking thumbnail opens full image
                            if (window.innerWidth <= 768) {
                                const mainImg = sidebar.querySelector('.sidebar-image');
                                if (mainImg) {
                                    mainImg.src = result.screenshot;
                                    sidebar.scrollTop = 0;
                                }
                            }
                        };
                        thumbnails.appendChild(thumb);
                    }
                }
            });
            
            if (screenshots.length > 7) {
                const viewMore = document.createElement('button');
                viewMore.className = 'view-more';
                viewMore.textContent = 'View ' + (screenshots.length - 7) + ' more';
                sidebar.appendChild(viewMore);
            }
            
            // On mobile, add button to view screenshots if they exist
            if (window.innerWidth <= 768 && screenshots.length > 0) {
                addMobileScreenshotButton(screenshots.length);
            }
        }
        
        function addMobileScreenshotButton(count) {
            // Remove existing button if any
            const existingBtn = document.getElementById('mobileScreenshotBtn');
            if (existingBtn) {
                existingBtn.remove();
            }
            
            const btn = document.createElement('button');
            btn.id = 'mobileScreenshotBtn';
            btn.className = 'view-more';
            btn.style.cssText = 'position: fixed; bottom: 80px; right: 16px; z-index: 99; padding: 12px 16px; background: #007bff; color: white; border: none; border-radius: 24px; font-size: 14px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.3);';
            btn.textContent = `📷 View Screenshots (${count})`;
            btn.onclick = () => {
                sidebar.classList.add('active');
                document.body.style.overflow = 'hidden';
            };
            document.body.appendChild(btn);
        }
        
        // Close sidebar when clicking outside on mobile
        if (sidebar) {
            sidebar.addEventListener('click', (e) => {
                if (window.innerWidth <= 768 && e.target === sidebar) {
                    sidebar.classList.remove('active');
                    document.body.style.overflow = 'auto';
                }
            });
        }
        
        function showError(message) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error';
            errorDiv.textContent = '❌ ' + message;
            mainContent.appendChild(errorDiv);
        }
        
        function displayResults(question, results, naturalAnswer = null) {
            // Keep page title as "Al-Falah RAG Chatbox" - don't change it
            
            // Clear main content
            mainContent.innerHTML = '';
            
            if (!results || results.length === 0) {
                const noResults = document.createElement('div');
                noResults.className = 'empty-state';
                noResults.innerHTML = '<div class="empty-state-icon">🔍</div><p>No results found. Try rephrasing your question.</p>';
                mainContent.appendChild(noResults);
                return;
            }
            
            // Add question display below title
            const questionSection = document.createElement('div');
            questionSection.className = 'question-section';
            const questionText = document.createElement('div');
            questionText.className = 'question-text';
            questionText.textContent = question;
            questionSection.appendChild(questionText);
            mainContent.appendChild(questionSection);
            
            // Add natural answer prominently if available
            if (naturalAnswer) {
                const naturalAnswerSection = document.createElement('div');
                naturalAnswerSection.className = 'section answer-section';
                naturalAnswerSection.style.marginBottom = '32px';
                naturalAnswerSection.style.backgroundColor = '#f8f9fa';
                naturalAnswerSection.style.borderLeft = '4px solid #4CAF50';
                naturalAnswerSection.style.padding = '24px';
                
                const title = document.createElement('div');
                title.className = 'section-title';
                title.innerHTML = '<svg class="section-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg> Answer';
                naturalAnswerSection.appendChild(title);
                
                const content = document.createElement('div');
                content.className = 'answer-content';
                content.style.maxHeight = '600px';
                content.style.overflowY = 'auto';
                content.style.overflowX = 'hidden';
                content.style.paddingRight = '8px';
                
                const answerParagraph = document.createElement('p');
                answerParagraph.style.fontSize = '16px';
                answerParagraph.style.lineHeight = '1.6';
                answerParagraph.style.color = '#333';
                answerParagraph.style.margin = '0';
                answerParagraph.style.whiteSpace = 'pre-wrap';
                answerParagraph.style.wordWrap = 'break-word';
                answerParagraph.textContent = naturalAnswer;
                content.appendChild(answerParagraph);
                naturalAnswerSection.appendChild(content);
                
                mainContent.appendChild(naturalAnswerSection);
            }
            
            // Add Sources section
            // const sourcesSection = createSourcesSection(results);
            // mainContent.appendChild(sourcesSection);
            
            // // Add Research Progress section
            // const progressSection = createResearchProgressSection();
            // mainContent.appendChild(progressSection);
            
            // Add Answer sections - one for each result (only if no natural answer, or as supporting details)
            if (!naturalAnswer) {
                // If no natural answer, show individual results as before
                results.forEach((result, index) => {
                    const answerSection = createAnswerSection([result], index + 1);
                    mainContent.appendChild(answerSection);
                });
            } else {
                // If we have a natural answer, show results as "Supporting Details" or "Sources"
                const detailsSection = document.createElement('div');
                detailsSection.className = 'section';
                detailsSection.style.marginTop = '32px';
                
                const detailsTitle = document.createElement('div');
                detailsTitle.className = 'section-title';
                detailsTitle.innerHTML = '<svg class="section-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg> Supporting Details';
                detailsSection.appendChild(detailsTitle);
                
                results.forEach((result, index) => {
                    const answerSection = createAnswerSection([result], index + 1);
                    answerSection.style.marginTop = '16px';
                    detailsSection.appendChild(answerSection);
                });
                
                mainContent.appendChild(detailsSection);
            }
            
            // Update sidebar with screenshots
            updateSidebar(results);
        }
        
        function sendMessage(event) {
            event.preventDefault();
            
            const question = questionInput.value.trim();
            if (!question) return;
            
            // Keep title as "Al-Falah RAG Chatbox" - don't change it
            
            // Clear and show loading
            mainContent.innerHTML = '<div class="empty-state"><div class="loading" style="margin: 0 auto;"></div><p style="margin-top: 16px;">Searching...</p></div>';
            sidebar.innerHTML = '';
            
            sendButton.disabled = true;
            
            // Send request
            const formData = new FormData();
            formData.append('action', 'chat');
            formData.append('question', question);
            
            fetch('', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showError(data.error);
                    return;
                }
                
                // Check for natural answer in response
                const naturalAnswer = data.answer || null;
                displayResults(data.question, data.results || [], naturalAnswer);
            })
            .catch(error => {
                showError('Failed to get response: ' + error.message);
            })
            .finally(() => {
                sendButton.disabled = false;
                questionInput.focus();
            });
        }
        
        // Handle window resize
        let resizeTimer;
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                // Update sidebar visibility
                if (window.innerWidth > 768) {
                    if (sidebar) sidebar.classList.remove('active');
                    document.body.style.overflow = 'auto';
                    const mobileBtn = document.getElementById('mobileScreenshotBtn');
                    if (mobileBtn) mobileBtn.remove();
                }
            }, 250);
        });
        
        // Focus input on load
        questionInput.focus();
        
        // Prevent body scroll when sidebar is open on mobile
        if (sidebar) {
            const observer = new MutationObserver(() => {
                if (sidebar.classList.contains('active')) {
                    document.body.style.overflow = 'hidden';
                } else {
                    document.body.style.overflow = 'auto';
                }
            });
            observer.observe(sidebar, { attributes: true, attributeFilter: ['class'] });
        }
    </script>
</body>
</html>
