# Google Cloud Authentication Setup

This guide will help you set up authentication for Vertex AI.

## Option 1: Service Account (Recommended for Production)

### Step 1: Create Service Account

1. Go to [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Click "Create Service Account"
3. Fill in:
   - **Name**: `crawler-service-account`
   - **Description**: Service account for crawler
4. Click "Create and Continue"

### Step 2: Grant Permissions

Add these roles:
- **Vertex AI User** (`roles/aiplatform.user`)
- **Storage Object Viewer** (if using Cloud Storage)

Click "Continue" then "Done"

### Step 3: Create and Download Key

1. Click on the service account you just created
2. Go to "Keys" tab
3. Click "Add Key" > "Create new key"
4. Choose **JSON** format
5. Download the key file (e.g., `crawler-key.json`)
6. **Save it securely** (e.g., `~/.config/gcloud/crawler-key.json`)

### Step 4: Update .env File

Edit your `.env` file:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/crawler-key.json
```

**Example:**
```bash
GOOGLE_APPLICATION_CREDENTIALS=/Users/saiful/.config/gcloud/crawler-key.json
```

### Step 5: Verify Authentication

```bash
python3 test_vertex_ai.py
```

## Option 2: User Authentication (For Development)

If you prefer to use your personal Google account:

### Step 1: Install gcloud CLI

```bash
# macOS
brew install google-cloud-sdk

# Or download from: https://cloud.google.com/sdk/docs/install
```

### Step 2: Authenticate

```bash
gcloud auth login
```

This will open a browser window for you to sign in.

### Step 3: Set Application Default Credentials

```bash
gcloud auth application-default login
```

### Step 4: Set Your Project

```bash
gcloud config set project YOUR_PROJECT_ID
```

### Step 5: Verify

```bash
python3 test_vertex_ai.py
```

## Option 3: Set Credentials in Code (Not Recommended)

You can also set credentials programmatically, but this is less secure:

```python
import os
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/path/to/key.json'
```

## Troubleshooting

### Error: "Unable to authenticate your request"

**Solution 1: Check GOOGLE_APPLICATION_CREDENTIALS path**
```bash
# Verify the path exists
ls -la $GOOGLE_APPLICATION_CREDENTIALS

# Or check in Python
python3 -c "import os; print(os.getenv('GOOGLE_APPLICATION_CREDENTIALS'))"
```

**Solution 2: Verify the JSON file is valid**
```bash
python3 -c "import json; json.load(open('/path/to/key.json'))"
```

**Solution 3: Check file permissions**
```bash
chmod 600 /path/to/crawler-key.json
```

**Solution 4: Use gcloud auth**
```bash
gcloud auth application-default login
```

### Error: "Permission denied" or "Access denied"

- Ensure your service account has `roles/aiplatform.user` role
- Verify the service account email matches the one in your key file
- Check that Vertex AI API is enabled in your project

### Error: "Project not found"

- Verify `VERTEX_PROJECT_ID` in `.env` matches your actual project ID
- Run: `gcloud projects list` to see your projects

## Quick Setup Checklist

- [ ] Service account created (or gcloud auth completed)
- [ ] Service account has `roles/aiplatform.user` role
- [ ] Key file downloaded (JSON format)
- [ ] `GOOGLE_APPLICATION_CREDENTIALS` set in `.env` file
- [ ] Path to key file is correct and file exists
- [ ] Key file has correct permissions (600)
- [ ] `test_vertex_ai.py` runs successfully

## Testing Authentication

Run the test script:

```bash
python3 test_vertex_ai.py
```

If authentication is working, you should see:
```
✅ Authentication successful
   Authenticated as: your-service-account@project.iam.gserviceaccount.com
   Project: your-project-id
```

## Security Best Practices

1. **Never commit** your service account key file to git
2. Keep key files in a secure location (e.g., `~/.config/gcloud/`)
3. Use environment variables, not hardcoded paths
4. Rotate keys periodically
5. Use least-privilege principle (only grant necessary roles)
