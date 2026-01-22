# Vertex AI Setup Guide

This guide will help you set up Vertex AI Vector Search for the crawler.

## Quick Configuration Reference

When creating your Vector Search index, use these recommended settings:

| Setting | Value | Notes |
|---------|-------|-------|
| **Dimensions** | `768` | Required for text-embedding-005 |
| **Algorithm Type** | `Tree-AH` | Best for most use cases |
| **Approximate Neighbors Count** | `50` | Good starting point (adjust based on dataset size) |
| **Distance Measure** | `DOT_PRODUCT` | Recommended for normalized embeddings |

**Approximate Neighbors Count Guidelines:**
- Small datasets (< 10K): `10-50`
- Medium datasets (10K-100K): `50-100` ⭐ **Recommended**
- Large datasets (> 100K): `100-200`

## Prerequisites

1. **Google Cloud Project** with billing enabled
2. **Vertex AI API** enabled
3. **Service Account** with appropriate permissions

## Step 1: Enable Required APIs

Enable the following APIs in your Google Cloud project:

```bash
# Enable Vertex AI API
gcloud services enable aiplatform.googleapis.com

# Enable Vector Search API (if separate)
gcloud services enable vectorsearch.googleapis.com
```

Or via Google Cloud Console:
1. Go to [APIs & Services > Library](https://console.cloud.google.com/apis/library)
2. Search for "Vertex AI API" and enable it
3. Search for "Vector Search API" and enable it (if available)

## Step 2: Create a Service Account

1. Go to [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Click "Create Service Account"
3. Name it (e.g., `crawler-service-account`)
4. Grant the following roles:
   - **Vertex AI User** (`roles/aiplatform.user`)
   - **Storage Object Viewer** (if using Cloud Storage)
5. Click "Done"

## Step 3: Create Service Account Key

1. Click on the service account you just created
2. Go to "Keys" tab
3. Click "Add Key" > "Create new key"
4. Choose "JSON" format
5. Download the key file
6. **Save it securely** (e.g., `~/.config/gcloud/crawler-key.json`)

## Step 4: Create Vertex AI Vector Search Index

### Option A: Using Google Cloud Console

1. Go to [Vertex AI > Vector Search](https://console.cloud.google.com/vertex-ai/vector-search)
2. Click "Create Index"
3. Configure the following settings:

#### Required Settings:

- **Index Name**: e.g., `crawler-index`
- **Region**: e.g., `us-central1` (must match your project region)

#### Vector Configuration:

- **Dimensions**: `768`
  - This is **required** for `text-embedding-005` model
  - Do not change this value

#### Algorithm Configuration:

- **Algorithm Type**: Choose based on your needs:
  - **Tree-AH** (Tree-based Approximate Hierarchical) - **Recommended**
    - Best for: Most use cases, datasets of any size
    - Speed: Fast approximate search
    - Accuracy: Good balance (configurable)
    - Use when: You have > 10K vectors or need fast queries
  - **Brute Force** (Exact Search)
    - Best for: Small datasets (< 10K vectors)
    - Speed: Slower (exact search)
    - Accuracy: 100% accurate
    - Use when: You need exact results and have small dataset

- **Approximate Neighbors Count**: `50` (recommended starting value)
  - **What it means**: Number of nearest neighbors to consider during search
  - **Impact**: 
    - Higher values = More accurate results but slower queries
    - Lower values = Faster queries but potentially less accurate
  - **Recommended values by dataset size**:
    - Small datasets (< 10K vectors): `10-50`
    - Medium datasets (10K-100K): `50-100`
    - Large datasets (> 100K): `100-200`
  - **Starting point**: `50` (good balance for most cases)
  - **Note**: You can adjust this later based on your query performance needs

#### Distance Measure:

- **DOT_PRODUCT** - **Recommended**
  - Best for normalized embeddings (which text-embedding-005 produces)
  - Faster computation
  - Works well with cosine similarity when vectors are normalized
- **COSINE**
  - Good for similarity search
  - Requires normalized vectors
  - Slightly slower than DOT_PRODUCT
- **EUCLIDEAN_DISTANCE**
  - Standard distance metric
  - Use if you need actual distance measurements

4. Click "Create"

**Quick Configuration Summary:**
```
Dimensions: 768
Algorithm Type: Tree-AH
Approximate Neighbors Count: 50
Distance Measure: DOT_PRODUCT
```

### Option B: Using gcloud CLI

```bash
# Create index
gcloud ai indexes create \
  --display-name="crawler-index" \
  --metadata-file=index-metadata.json \
  --region=us-central1 \
  --project=YOUR_PROJECT_ID
```

Create `index-metadata.json`:
```json
{
  "contentsDeltaUri": "gs://your-bucket/index",
  "config": {
    "dimensions": 768,
    "approximateNeighborsCount": 50,
    "distanceMeasureType": "DOT_PRODUCT",
    "algorithmConfig": {
      "treeAhConfig": {
        "leafNodeEmbeddingCount": 500,
        "leafNodesToSearchPercent": 10
      }
    }
  }
}
```

**Configuration Recommendations:**

- **Dimensions**: `768` (required for text-embedding-005)
- **Distance Measure**: 
  - `DOT_PRODUCT` (recommended) - Faster, works well with normalized embeddings
  - `COSINE` - Good for similarity search, requires normalized vectors
  - `EUCLIDEAN_DISTANCE` - Standard distance metric
- **Algorithm Type**:
  - **Tree-AH** (Tree-based Approximate Hierarchical) - Recommended for most cases
    - Fast approximate search
    - Good for datasets of any size
    - Configurable accuracy vs speed tradeoff
  - **Brute Force** - Use only for very small datasets (< 10K vectors)
    - Most accurate but slowest
    - No approximation, exact search
- **Approximate Neighbors Count**: 
  - This is the number of nearest neighbors to consider during search
  - Higher values = more accurate but slower
  - Lower values = faster but less accurate
  - **Recommended values**:
    - Small datasets (< 10K vectors): `10-50`
    - Medium datasets (10K-100K): `50-100`
    - Large datasets (> 100K): `100-200`
    - **Default/Starting value**: `50` (good balance)

## Step 5: Create Index Endpoint

1. Go to [Vertex AI > Vector Search > Index Endpoints](https://console.cloud.google.com/vertex-ai/vector-search/endpoints)
2. Click "Create Endpoint"
3. Configure:
   - **Endpoint Name**: e.g., `crawler-endpoint`
   - **Region**: Same as your index (e.g., `us-central1`)
4. Click "Create"
5. **Deploy your index** to the endpoint:
   - Click on the endpoint
   - Click "Deploy Index"
   - Select your index
   - Configure deployment (min replica count, etc.)
   - Click "Deploy"

## Step 6: Get Your Configuration Values

After creating the index and endpoint, you'll need:

1. **Project ID**: Your GCP project ID
2. **Location**: Region where you created the index (e.g., `us-central1`)
3. **Index ID**: Found in the index details page (format: `1234567890123456789`)
4. **Endpoint ID**: Found in the endpoint details page (format: `1234567890123456789`)
5. **Service Account Key Path**: Path to your downloaded JSON key file

## Step 7: Configure .env File

Edit your `.env` file with the values from Step 6:

```bash
# Vertex AI Configuration
VERTEX_PROJECT_ID=your-project-id
VERTEX_LOCATION=us-central1
VERTEX_INDEX_ID=1234567890123456789
VERTEX_INDEX_ENDPOINT=1234567890123456789

# Google Cloud Credentials
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json
```

## Step 8: Test the Setup

Run the test script to verify your configuration:

```bash
python test_vertex_ai.py
```

Or test with a small crawl:

```bash
python crawler.py --test --test-sources resources/sources_test.json
```

## Troubleshooting

### Error: "Permission denied"
- Ensure your service account has `roles/aiplatform.user` role
- Verify the service account key path is correct

### Error: "Index not found"
- Verify `VERTEX_INDEX_ID` is correct
- Ensure the index is in the same region as `VERTEX_LOCATION`

### Error: "Endpoint not found"
- Verify `VERTEX_INDEX_ENDPOINT` is correct
- Ensure the endpoint is deployed and active
- Check that the index is deployed to the endpoint

### Error: "API not enabled"
- Enable Vertex AI API in your project
- Wait a few minutes for the API to be fully enabled

## Alternative: Using Vertex AI Search (Managed)

If you prefer a managed solution, you can use Vertex AI Search instead:

1. Go to [Vertex AI Search](https://console.cloud.google.com/gen-app-builder)
2. Create a new data store
3. Configure ingestion
4. Use the Search API instead of Vector Search

## Cost Considerations

- **Embedding API**: ~$0.0001 per 1K characters
- **Vector Search**: Storage and query costs vary by region
- **Index Endpoint**: Charges for deployed replicas

Monitor usage in [Cloud Billing](https://console.cloud.google.com/billing)

## Next Steps

Once configured, run the crawler in production mode:

```bash
python crawler.py
```

The crawler will:
1. Extract and chunk content
2. Generate embeddings using Vertex AI
3. Upload to your Vector Search index
4. Make the data available for RAG queries
