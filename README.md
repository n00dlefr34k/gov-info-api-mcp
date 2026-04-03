# GovInfo API MCP Server

A Model Context Protocol (MCP) server and REST API wrapper for accessing the GovInfo API. This tool provides easy access to government documents, bills, regulations, and related information through both MCP protocol and HTTP REST endpoints.

The government api is located here https://api.govinfo.gov/docs/

This is not the govenments mcp they have their own here 
https://github.com/usgpo/api/blob/main/docs/mcp.md

I wanted one that exposes all of the apis endpoints for deep research.

I highly suggest understanding the data structures before making promts. The mcp handels the api limits for you but it should be as targeted as possible. 


## Features

- 🔍 **Advanced Search**: Search government documents with filtering, sorting, and pagination
- 📚 **Collections**: Browse all available GovInfo collections
- 📋 **Package Details**: Get metadata and granule information for specific documents
- 📅 **Date Filtering**: Find documents by publication or modification dates
- 🔗 **Relationships**: Discover related documents across collections
- ⏱️ **Rate Limiting**: Built-in rate limiting (1000 calls/hour)
- 🌐 **Dual Interface**: Use via MCP protocol or simple HTTP REST endpoints

## Setup

### 1. Get Your API Key

1. Go to [api.data.gov](https://api.data.gov)
2. Sign up for a free API key
3. Request the GovInfo API access
4. Copy your API key

### 2. Configure Environment

Create a `.env` file in the project root:

```env
GOV_API_KEY=your_api_key_here
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Running the Servers

### Option 1: REST API Server Only (Recommended for Testing)

```bash
python api_server.py
```

Server runs on: `http://127.0.0.1:8030`

Swagger Docs: `http://127.0.0.1:8030/docs`

### Option 2: MCP Server Only

```bash
python gov.api.mcp.py
```

### Option 3: Run Both Simultaneously

In terminal 1:
```bash
python gov.api.mcp.py
```

In terminal 2:
```bash
python api_server.py
```

## REST API Endpoints

### Search Documents

**Endpoint**: `POST /search`

**Parameters** (query parameters or form data):
- `query` (required): Search query (e.g., "congress bills")
- `offsetMark` (optional): Pagination marker (default: "*")
- `sort` (optional): Sort field (publishDate, lastModified, title)
- `collection` (optional): Collection list to search (BILLS, CFR, FR, etc.)
- `historical` (optional): Include historical documents (true/false, default: false)
- `pageSize` (optional): Results per page (default: 10)

**Example**:
```bash
curl -X POST "http://127.0.0.1:8030/search?query=border+security&collection=BILLS&pageSize=50"
```

### Search Synthesis

**Endpoint**: `POST /search_synthesis`

**Description**: 🎯 Synthesize search results into a concise summary with AI analysis

**Parameters** (JSON body):
- `search_query` (required): Search query for synthesis
- `committees` (optional): List of collection codes (e.g., ["BILLS", "FR"])

**Examples**:
```bash
# Immigration search with specific collections
curl -X POST "http://127.0.0.1:8030/search_synthesis" \
  -H "Content-Type: application/json" \
  -d '{"search_query": "immigration policy", "committees": ["BILLS", "FR"]}'

# Healthcare search with auto-detection
curl -X POST "http://127.0.0.1:8030/search_synthesis" \
  -H "Content-Type: application/json" \
  -d '{"search_query": "healthcare reform"}'
```

### Get Collections

**Endpoint**: `GET /collections`

Returns all available GovInfo collections.

**Example**:
```bash
curl "http://127.0.0.1:8030/collections"
```

### Search Collection by Date

**Endpoint**: `GET /collections/{collection_id}/{last_modified}`

**Parameters**:
- `collection_id`: Collection identifier (e.g., USCODE, BILLS)
- `last_modified`: Date in YYYY-MM-DD format
- `pageSize` (optional): Results per page (default: 10)
- `offsetMark` (optional): Pagination marker (default: "*")
- `congress` (optional): Congress number (default: -1)
- `docClass` (optional): Document class
- `billVersion` (optional): Bill version
- `courtCode` (optional): Court code
- `courtType` (optional): Court type
- `state` (optional): State
- `topic` (optional): Topic
- `isGLP` (optional): GLP status
- `natureSuitCode` (optional): Nature of suit code
- `natureSuit` (optional): Nature of suit

**Example**:
```bash
curl "http://127.0.0.1:8030/collections/USCODE/2025-01-01?pageSize=20&congress=118"
```

### Search Collection by Date Range

**Endpoint**: `GET /collections/{collection_id}/{start_date}/{end_date}`

**Parameters**:
- `collection_id`: Collection identifier
- `start_date`: Start date (YYYY-MM-DD)
- `end_date`: End date (YYYY-MM-DD)
- `pageSize` (optional): Results per page (default: 10)
- `offsetMark` (optional): Pagination marker (default: "*")
- Additional filtering parameters: `congress`, `docClass`, `billVersion`, `courtCode`, `courtType`, `state`, `topic`, `isGLP`, `natureSuitCode`, `natureSuit`

**Example**:
```bash
curl "http://127.0.0.1:8030/collections/BILLS/2024-01-01/2024-12-31?pageSize=50"
```

### Package Summary

**Endpoint**: `GET /package/{package_id}/summary`

Get detailed metadata for a specific package.

**Example**:
```bash
curl "http://127.0.0.1:8030/package/BILLS-118hr123ih/summary"
```

### Package Granules

**Endpoint**: `GET /package/{package_id}/granules`

Get all granules (sub-documents) for a package.

**Parameters**:
- `package_id`: Package identifier
- `pageSize` (optional): Results per page (default: 10)
- `offsetMark` (optional): Pagination marker (default: "*")

**Example**:
```bash
curl "http://127.0.0.1:8030/package/BILLS-118hr123ih/granules?pageSize=50"
```

### Package Granule Summary

**Endpoint**: `GET /package/{package_id}/granules/{granule_id}/summary`

Get summary for a specific granule within a package.

**Parameters**:
- `package_id`: Package identifier
- `granule_id`: Granule identifier
- `pageSize` (optional): Results per page (default: 10)

**Example**:
```bash
curl "http://127.0.0.1:8030/package/BILLS-118hr123ih/granules/BILLS-118hr123ih-1/summary"
```

### Published Documents

**Endpoint**: `GET /published/{start_date}`

Get documents published on or after a specific date.

**Parameters**:
- `start_date`: Date in YYYY-MM-DD format
- `collection` (required): Collection identifier
- `pageSize` (optional): Results per page (default: 10)
- `offsetMark` (optional): Pagination marker (default: "*")

**Example**:
```bash
curl "http://127.0.0.1:8030/published/2025-01-01?collection=BILLS&pageSize=100"
```

### Published Range

**Endpoint**: `GET /published/{start_date}/{end_date}`

Get documents published within a date range.

**Parameters**:
- `start_date`: Start date in YYYY-MM-DD format
- `end_date`: End date in YYYY-MM-DD format
- `collection` (required): Collection identifier
- `pageSize` (optional): Results per page (default: 10)
- `offsetMark` (optional): Pagination marker (default: "*")

**Example**:
```bash
curl "http://127.0.0.1:8030/published/2024-01-01/2024-12-31?collection=FR&pageSize=50"
```

### Related Documents

**Endpoint**: `GET /related/{access_id}`

Find documents related to a specific access ID.

**Example**:
```bash
curl "http://127.0.0.1:8030/related/BILLS-118hr123ih"
```

### Related Documents in Collection

**Endpoint**: `GET /related/{access_id}/{collection_id}`

Find related documents within a specific collection.

**Example**:
```bash
curl "http://127.0.0.1:8030/related/BILLS-118hr123ih/USCODE"
```

## Testing with Postman

1. Import the collection or manually create requests for each endpoint
2. Use the examples above as templates
3. Replace `{API_KEY}` with your actual key (handled automatically by the server)
4. Test each endpoint with your desired parameters

## Rate Limiting

- **Limit**: 1000 API calls per hour
- **Status**: Automatically tracked across all requests
- **Warning**: Server will return `{"error": "API limit reached"}` when limit is exceeded
- **Reset**: Counter resets every hour

## Common Issues

### API Key Not Found
**Error**: `"API key not found"`
**Solution**: Create a `.env` file with `GOV_API_KEY=your_key_here`

### 404 Errors on Endpoints
**Issue**: Using collection names instead of document IDs
**Solution**: Use valid IDs (e.g., BILLS-118hr123ih, not USCODE for related documents)

### 400 Bad Request
**Issue**: Incorrect date format
**Solution**: Use YYYY-MM-DD format for dates

### Empty Response
**Issue**: Valid request but no matching results
**Solution**: Try different search parameters or date ranges

## Architecture

### Two-Server Design

1. **gov.api.mcp.py** - FastMCP Server
   - Implements MCP protocol for AI assistants
   - Runs on port 8090 with MCP transport
   - Ideal for integration with Claude and other AI tools

2. **api_server.py** - FastAPI Server
   - Exposes simple REST HTTP endpoints
   - Imports and wraps tool functions from MCP server
   - Easier for testing and direct HTTP clients
   - Swagger UI at `/docs`

### Data Flow

```
HTTP Request → api_server.py → MCP Tool Functions → GovInfo API
    ↓
  JSON Response
```

## Available Collections

Common GovInfo collections:

- **BILLS**: Congressional Bills
- **USCODE**: U.S. Code
- **STATUE**: U.S. Statutes
- **CFR**: Code of Federal Regulations
- **FR**: Federal Register
- **GOVPUB**: Government Publications
- **PPP**: Presidential Papers

## Examples

### Search for Bills About Energy

```bash
curl -X POST "http://127.0.0.1:8030/search?query=energy+efficiency&collection=BILLS&sort=publishDate&pageSize=50"
```

### Find Federal Register Documents from Last Month

```bash
curl "http://127.0.0.1:8030/published/2024-12-01?collection=FR&pageSize=200"
```

### Get CFR Changes in 2025

```bash
curl "http://127.0.0.1:8030/published/2025-01-01?collection=CFR"
```

### Synthesize Immigration Policy Research

```bash
curl -X POST "http://127.0.0.1:8030/search_synthesis" \
  -H "Content-Type: application/json" \
  -d '{"search_query": "immigration reform legislation", "committees": ["BILLS", "CREC"]}'
```

## Support

For issues with the GovInfo API itself, see [api.govinfo.gov](https://api.govinfo.gov)

For questions about this wrapper, check the code comments or submit an issue.

## License

This project wraps the publicly accessible GovInfo API provided by the U.S. Government.
