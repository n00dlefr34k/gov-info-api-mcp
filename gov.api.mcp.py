"""
Gov API MCP ServerThis MCP provides tools to interact with the GovInfo API, including search, collection queries, package and granule details, publication date queries, and relationship discovery. It includes automatic rate limiting to manage API usage effectively. Use the provided tools to retrieve and analyze government documents and metadata from the GovInfo API.
"""
import logging
import os
import requests
import json
import re
import html
from fastmcp import FastMCP

from fastmcp.server import Context
from fastmcp.prompts import Message
from datetime import datetime   
from dotenv import load_dotenv
from urllib.parse import quote
from thefuzz import fuzz
from stop_words import get_stop_words


load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('gov_api_mcp.log')  # File output
    ]
)
logger = logging.getLogger(__name__)

# Log startup
logger.info("Starting Gov API MCP Server")

API_KEY = os.getenv("GOV_API_KEY")
if not API_KEY:
    logger.error("GOV_API_KEY environment variable not found!")
    raise ValueError("GOV_API_KEY must be set in environment variables")
else:
    logger.info("API key loaded successfully")
API_CALL_LIMIT_PER_HOUR = 36000  # Hourly rate limit
SESSION_IDS = []  # To track unique sessions for rate limiting
BASE_URL = "https://api.govinfo.gov"  # Base URL for GovInfo API
DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ" # ISO 8601 format for date-time strings
DATE_TIME_FORMAT_NO_TIME = "%Y-%m-%d" # Date format without time for endpoints that only require date
# Set up the server
mcp = FastMCP(
    name="Gov API MCP",
    instructions="""🏛️ **COMPREHENSIVE U.S. GOVERNMENT DOCUMENTS ACCESS**

This MCP server provides powerful access to 7.7+ million official U.S. government documents through the GovInfo API. Tested and optimized for research, legislative tracking, and policy analysis.

## 📊 **MASSIVE DATASET COVERAGE**
• **285,173** Congressional Bills (BILLS)
• **2,093,585** U.S. Court Opinions (USCOURTS) 
• **7,729,064** Code of Federal Regulations granules (CFR)
• **22,687** Federal Register issues (FR)
• **40 total collections** including Presidential documents, GAO reports, Congressional Record, and more

## 🔍 **CORE TOOL CATEGORIES**

### **Search & Discovery**
• `search` - Full-text search across all collections with filtering (collection, historical, sort)
• `collections` - Get all 40 available document collections with counts
• `rate_limit_status` - Monitor API usage (36,000/hour server limit, 1,000/hour local tracking)

### **Date-Based Queries**
• `published` - Recent documents from specific date forward
• `published_end` - Documents published within date ranges
• `collections_search_last_modified` - Recently modified documents in collections
• `collections_search_last_modified_to_end_date` - Modified documents in date ranges

### **Document Details**
• `package_summary` - Complete metadata (sponsors, committees, bill status, download links)
• `package_granulates` - List sections within large documents (CFR volumes have ~1,300 granules)
• `package_granulates_summary` - Detailed section metadata with section ranges

### **Relationship Discovery**
• `related` - Find connected documents across collections (bill versions, status, history)
• `related_collection` - Targeted relationships within specific collections

## ⚡ **PERFORMANCE & LIMITS**
• **Automatic rate limiting** with server header tracking + local fallback
• **Real-time monitoring** of API usage and limits
• **Optimized for high-volume** legislative research and analysis
• **Smart error handling** with detailed logging and recovery

## 🎯 **KEY USE CASES**
• **Legislative Tracking**: Monitor bill progress, find sponsors/committees
• **Regulatory Research**: Navigate CFR sections, track Federal Register updates  
• **Court Opinion Analysis**: Search 2M+ court decisions with advanced filtering
• **Policy Research**: Cross-reference documents across government branches
• **Real-time Monitoring**: Track new publications and document modifications

## 📋 **ESSENTIAL COLLECTION CODES**
• **BILLS** - Congressional legislation
• **CFR** - Code of Federal Regulations (7.7M granules)
• **FR** - Federal Register (daily government notices)
• **USCOURTS** - Federal court opinions
• **CREC** - Congressional Record
• **PLAW** - Public Laws
• **GAOREPORTS** - Government Accountability Office
• **PPP** - Presidential Papers

## 🚀 **OPTIMIZATION TIPS**
• Start with `collections` to understand available document types
• Use specific collection codes in `search` for targeted results
• Apply date ranges for recent legislative activity
• Use `package_summary` for comprehensive bill analysis
• Leverage `related` tools for complete document tracking

**Ready for production legislative research and government document analysis!**""",
    version="1.0",
    mask_error_details=False,  # Show detailed errors for debugging
    strict_input_validation=True,  # Validate inputs strictly
    list_page_size=100,  # Default page size for listings
    tasks=False,  # Disable background tasks for simplicity
)

async def update_rate_limit_from_headers(ctx: Context, response_headers: dict) -> None:
    """Update rate limit info from API response headers"""
    try:
        # Extract rate limit headers (case-insensitive)
        rate_limit = None
        rate_remaining = None
        
        for header, value in response_headers.items():
            header_lower = header.lower()
            if header_lower in ['x-ratelimit-limit', 'x-rate-limit-limit']:
                rate_limit = int(value)
            elif header_lower in ['x-ratelimit-remaining', 'x-rate-limit-remaining']:
                rate_remaining = int(value)
        
        if rate_limit and rate_remaining is not None:
            await ctx.set_state("api_rate_limit", rate_limit)
            await ctx.set_state("api_rate_remaining", rate_remaining)
            await ctx.set_state("rate_limit_updated", datetime.now().timestamp())
            
            # Log rate limit status
            logger.info(f"Rate limit status: {rate_remaining}/{rate_limit} requests remaining")
            
            # Warn if running low
            if rate_remaining < 50:
                await ctx.warn(f"API rate limit warning: Only {rate_remaining} requests remaining this hour")
            
    except (ValueError, TypeError) as e:
        logger.debug(f"Could not parse rate limit headers: {e}")
    except Exception as e:
        logger.error(f"Error updating rate limit from headers: {e}")

async def handel_api_limits(ctx: Context) -> bool:
    """Check API limits using actual server response headers when available, fallback to local tracking"""
    try:
        # First check if we have recent rate limit data from API headers
        api_rate_limit = await ctx.get_state("api_rate_limit")
        api_rate_remaining = await ctx.get_state("api_rate_remaining")
        rate_limit_updated = await ctx.get_state("rate_limit_updated") or 0
        
        # If we have recent rate limit data (within last 5 minutes), use it
        if (api_rate_limit and api_rate_remaining is not None and 
            datetime.now().timestamp() - rate_limit_updated < 300):
            
            if api_rate_remaining <= 0:
                logger.warning(f"API rate limit exceeded according to server headers: 0/{api_rate_limit}")
                await ctx.warn("API rate limit exceeded according to server. Please wait before making more requests.")
                return False
            
            logger.debug(f"Using server rate limit data: {api_rate_remaining}/{api_rate_limit} remaining")
            return True
        
        # Fallback to local tracking if no recent server data
        apicalls = await ctx.get_state("apicalls") or 0
        ttl = await ctx.get_state("ttl") or datetime.now().timestamp() + 3600  # Set TTL for 1 hour
        
        if datetime.now().timestamp() > ttl:
            apicalls = 0
            ttl = datetime.now().timestamp() + 3600
            logger.info("API call counter reset for new hour")
            
        apicalls += 1
        
        if apicalls > API_CALL_LIMIT_PER_HOUR:
            logger.warning(f"Local API limit exceeded. Current calls: {apicalls}")
            await ctx.warn("Local API call limit exceeded. Please wait before making more requests.")
            return False
            
        await ctx.set_state("apicalls", apicalls)
        await ctx.set_state("ttl", ttl)
        logger.debug(f"Local tracking - API calls this hour: {apicalls}/{API_CALL_LIMIT_PER_HOUR}")
        return True
        
    except Exception as e:
        logger.error(f"Error in handel_api_limits: {str(e)}", exc_info=True)
        return False 

async def get_downlaod(url:str) -> str:
    """Helper function to get text content from download link"""
    try:
        html_text = requests.get(url+f'?api_key={API_KEY}').text
        # Strip HTML tags and decode HTML entities
        clean_text = re.sub(r'<[^>]+>', '', html_text)
        clean_text = html.unescape(clean_text)
        # Remove extra whitespace and normalize line breaks
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        return clean_text
    except Exception as e:
        logger.error(f"Error in get_downlaod: {str(e)}", exc_info=True)
        return ""

@mcp.tool(name="search_related", description="Find related search results highlighting key committees and sponsors.")
async def search_related(search_query:str, ctx: Context, committees:list = None) -> str:
    """Find related search results highlighting key committees and sponsors."""
    try:
        logger.debug(f"Fuzzy match ratio for search query with tool calls '{search_query}' ")
        await ctx.info(f"Fuzzy match ratio for search query with tool calls '{search_query}'")
        collection_codes = []
        if not committees:

            # Get all collections and find matches using fuzzy matching
            list_of_collections = await collections(ctx) 
            collections_data = json.loads(list_of_collections)
            logger.debug(f"going through  '{json.dumps(collection_codes) if collection_codes else '[]'}'")
            await ctx.info(f"going through  '{json.dumps(collection_codes) if collection_codes else '[]'}'")

            #remove stop words from search query for better matching
            get_stop_words_list = get_stop_words('en')
            words = re.findall(r'\b\w+\b', search_query.lower())
            filtered_words = [w for w in words.split(' ') if w not in get_stop_words_list]
            
            # Extract collection codes that match search query terms
            for collection in collections_data.get('collections', []):
                collection_name = collection.get('collectionName', '')
                collection_code = collection.get('collectionCode', '')
                
                # Check first 7 words for matches
                for query_word in filtered_words.split(' ')[:7]:  
                    ratio = fuzz.ratio(collection_name.lower(), query_word.lower())
                    if ratio > 40:
                        collection_codes.append(collection_code)
                        break

            # Remove duplicates
            collection_codes = list(set(collection_codes))  
        else:
            collection_codes = committees
            logger.debug(f"Using provided committees: {json.dumps(collection_codes)}")
            await ctx.info(f"Using provided committees: {json.dumps(collection_codes)}")
        logger.debug(f"Final committees list: {json.dumps(collection_codes)}")
        await ctx.info(f"Final committees list: {json.dumps(collection_codes)}")
        # Perform search with identified collection codes
        search_results = await search(search_query, ctx, collection=collection_codes)
        search_results_json = json.loads(search_results)

        results_list=[]
        
        for result in search_results_json.get('results', []):
            item = {}
            if 'download' in result:
                if('txtLink' in result['download']):
                    clean_text = await get_downlaod(result['download']['txtLink'])
                    item['text'] = clean_text[:500]   
                   
            if 'packageId' in result.get('resultPackage', {}):
                item['package_id'] = result['packageId']
            if 'granuleId' in result:
                item['granule_id'] = result['granuleId']
            if 'collectionCode' in result:
                item['collection_code'] = result['collectionCode']
            if 'title' in result:
                item['title'] = result['title']
            if 'collectionCode' in result:
                item['collection_code'] = result['collectionCode']
            if 'governmentAuthor' in result:
                item['government_author'] = result['governmentAuthor']
            if 'relatedLink' in result:
                item['related'] = await get_downlaod(result['relatedLink'])
            results_list.append(item)
        #await ctx.set_state("search_results", results_list)
        await ctx.info("Search related results generated successfully")
        return results_list
    except Exception as e:
        logger.error(f"Error in search_related: {str(e)}", exc_info=True)
        return f"Error generating search related results: {str(e)}"

@mcp.tool(name="get_recently_published", description="Find related search results highlighting key committees and sponsors.")
async def get_recently_published(start_date: str, ctx: Context, committees:str = None) -> str:
    """Find recently published results."""
    try:
       
        collection_codes = ''
        if committees:
            collection_codes = committees
            logger.debug(f"Using provided committees: {json.dumps(collection_codes)}")
            await ctx.info(f"Using provided committees: {json.dumps(collection_codes)}")
        date_obj = None
        try:
            date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            return "error Date format must be YYYY-MM-DD";
        # Perform search with identified collection codes
        search_results = await published(date_obj,collection=collection_codes, ctx=ctx)
        search_results_json = json.loads(search_results)

        results_list=[]
        
        for result in search_results_json.get('packages', []):
            item = {}
            if 'packageLink' in result:
                clean_text = await get_downlaod(result['packageLink'])
                item['text'] = clean_text[:500]   
            if 'packageId' in result.get('resultPackage', {}):
                item['package_id'] = result['packageId']
            if 'lastModified' in result:
                item['lastModified'] = result['lastModified']
            if 'title' in result:
                item['title'] = result['title']
           
            results_list.append(item)
        #await ctx.set_state("search_results", results_list)
        await ctx.info("Search recently_published generated successfully")
        return results_list
    except Exception as e:
        logger.error(f"Error in get_recently_published: {str(e)}", exc_info=True)
        return f"Error generating get_recently_published results: {str(e)}"

@mcp.tool(name="search_synthesis", description="Synthesize search results into a concise summary highlighting key committees and sponsors.")
async def search_synthesis(search_query:str, ctx: Context, committees:list = None) -> str:
    """Synthesize search results into a concise summary highlighting key committees and sponsors."""
    try:
        logger.debug(f"Fuzzy match ratio for search query with tool calls '{search_query}' ")
        await ctx.info(f"Fuzzy match ratio for search query with tool calls '{search_query}'")
        collection_codes = []
        if not committees:

            # Get all collections and find matches using fuzzy matching
            list_of_collections = await collections(ctx) 
            collections_data = json.loads(list_of_collections)
            logger.debug(f"going through  '{json.dumps(collection_codes) if collection_codes else '[]'}'")
            await ctx.info(f"going through  '{json.dumps(collection_codes) if collection_codes else '[]'}'")

            #remove stop words from search query for better matching
            get_stop_words_list = get_stop_words('en')
            words = re.findall(r'\b\w+\b', search_query.lower())
            filtered_words = [w for w in words.split(' ') if w not in get_stop_words_list]
            
            # Extract collection codes that match search query terms
            for collection in collections_data.get('collections', []):
                collection_name = collection.get('collectionName', '')
                collection_code = collection.get('collectionCode', '')
                
                # Check first 7 words for matches
                for query_word in filtered_words.split(' ')[:7]:  
                    ratio = fuzz.ratio(collection_name.lower(), query_word.lower())
                    if ratio > 40:
                        collection_codes.append(collection_code)
                        break

            # Remove duplicates
            collection_codes = list(set(collection_codes))  
        else:
            collection_codes = committees
            logger.debug(f"Using provided committees: {json.dumps(collection_codes)}")
            await ctx.info(f"Using provided committees: {json.dumps(collection_codes)}")
        logger.debug(f"Final committees list: {json.dumps(collection_codes)}")
        await ctx.info(f"Final committees list: {json.dumps(collection_codes)}")
        # Perform search with identified collection codes
        search_results = await search(search_query, ctx, collection=collection_codes)
        search_results_json = json.loads(search_results)

        results_list=[]
        
        for result in search_results_json.get('results', []):
            item = {}
            if 'download' in result:
                if('txtLink' in result['download']):
                    html_text = requests.get(result['download']['txtLink']+f'?api_key={API_KEY}').text
                    # Strip HTML tags and decode HTML entities
                    clean_text = re.sub(r'<[^>]+>', '', html_text)
                    clean_text = html.unescape(clean_text)
                    # Remove extra whitespace and normalize line breaks
                    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
                    item['text'] = clean_text[:500]
            if 'packageId' in result.get('resultPackage', {}):
                item['package_id'] = result['packageId']
            if 'granuleId' in result:
                item['granule_id'] = result['granuleId']
            if 'collectionCode' in result:
                item['collection_code'] = result['collectionCode']
            if 'title' in result:
                item['title'] = result['title']
            if 'collectionCode' in result:
                item['collection_code'] = result['collectionCode']
            if 'governmentAuthor' in result:
                item['government_author'] = result['governmentAuthor']
            results_list.append(item)
        #await ctx.set_state("search_results", results_list)
        await ctx.info("Search synthesis results generated successfully")
        return results_list
    except Exception as e:
        logger.error(f"Error in search_synthesis: {str(e)}", exc_info=True)
        return f"Error generating search_synthesis results: {str(e)}"

@mcp.tool(name="search", 
          description="🔍 POWERFUL FULL-TEXT SEARCH across 7.7+ million government documents. Search congressional bills, federal regulations, court opinions, presidential documents, and more. Returns document metadata with direct links to HTML, PDF, XML, and ZIP formats. Tested: 643,573 results for 'congressional bills', 9,299 for 'border security'. Use 'collection' parameter to filter (BILLS, CFR, FR, USCOURTS, etc.), 'historical=false' for current documents only, 'sort' by lastModified/publishDate/title, and 'page_size' up to 100.")
async def search(query: str, ctx: Context, offset_mark: str = None, sort: str = None, collection: list = None, historical: bool = True, page_size: int = 10) -> str:
    """Search for documents on GovInfo using search queries with optional pagination, sorting, and filtering."""
    try:
        if await handel_api_limits(ctx):  # Increment the API call counter and check if limit is reached    
            url = f"{BASE_URL}/search"
            
            # Build query with collection and historical filters if provided
            search_query = query
            if collection:
                search_query = ''
                for collName in collection:
                    search_query += f"(collection:({collName}) OR "
                search_query = f"{search_query} AND {query}"
            
            # Build payload matching GovInfo API format (from official swagger)
            payload = {
                "query": search_query,
                "pageSize": page_size,
                "offsetMark": offset_mark if offset_mark is not None else "*",
                "historical": historical,
                "resultLevel": "default"
            }
            
            # Add sorts array if sort specified
            if sort:
                sorts = []
                if "publishDate" in sort:
                    order = "DESC" if "desc" in sort else "ASC"
                    sorts.append({"field": "publishDate", "sortOrder": order})
                elif "lastModified" in sort:
                    order = "DESC" if "desc" in sort else "ASC"
                    sorts.append({"field": "lastModified", "sortOrder": order})
                elif "title" in sort:
                    order = "DESC" if "desc" in sort else "ASC"
                    sorts.append({"field": "title", "sortOrder": order})
                else:
                    sorts.append({"field": "relevancy", "sortOrder": "DESC"})
                
                if sorts:
                    payload["sorts"] = sorts
            else:
                # Default sort by relevancy (as per swagger)
                payload["sorts"] = [{"field": "relevancy", "sortOrder": "DESC"}]
            parms = {
                'api_key':{API_KEY}
            }
            # API key goes in query parameter (as per swagger)
            url_with_key = f"{url}"
            
            headers = {
                'accept': 'application/json',
                'Content-Type': 'application/json'
            }
            
            # Debug: Log the full request details
           
            logger.info(f"Headers: {dict(headers)}")
            logger.info(f"Payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url_with_key, json=payload, params=parms, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            logger.info(f"Search API call successful for query: {query}")
            await ctx.info(f"Search completed for query: {query}")
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
        return json.dumps(response.json())
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in search function: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in search function: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})

@mcp.tool(name="collections", 
          description="📚 GET ALL 40 GOVERNMENT DOCUMENT COLLECTIONS with counts. Essential starting point for targeted searches. Returns collection codes and names for: BILLS (285,173 congressional bills), USCOURTS (2.1M court opinions), CFR (6,577 packages with 7.7M granules), FR (22,687 Federal Register issues), CREC (Congressional Record), PLAW (Public Laws), and 34 more collections. Use collection codes in other search tools for precise filtering.")
async def collections(ctx: Context) -> str:
    """Get list of all available collections."""
    try:
        if await handel_api_limits(ctx):  # Increment the API call counter and check if limit is reached
            url = f"{BASE_URL}/collections"
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': API_KEY
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            await ctx.info("Collections list retrieved successfully")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})   
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in collections function: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in collections function: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})

@mcp.tool(name="collections_search_last_modified",  
          description="📅 FIND RECENTLY MODIFIED DOCUMENTS in specific collections since a given date. Perfect for tracking legislative updates and document changes. Tested: 245 bills modified since 2026-03-25. Supports advanced filtering by congress (119 for current), docClass (hr/s for bills), billVersion, courtCode/Type, state, topic, and more. Use with BILLS, CFR, FR, or any collection code from the collections tool.")
async def collections_search_last_modified(collection_id : str ,last_modified:datetime, ctx: Context,page_size:int = 10, offsetMark : str = '*',
                                           congress: int =-1,docClass:str = '', billVersion:str ='',courtCode:str = '',courtType:str='',
                                           state:str = '',topic:str='',isGLP:str='',natureSuitCode:str = '',natureSuit:str = '') -> str:
    """Search for documents in a collection modified after a specific date."""
    try:
        if await handel_api_limits(ctx):  # Increment the API call counter and check if limit is reached
            # Format the date and encode it for URL path
            formatted_date = last_modified.strftime(DATE_TIME_FORMAT)
            encoded_date = quote(formatted_date)
            
            #base api url with collection and date in the path
            url = f"{BASE_URL}/collections/{collection_id}/{encoded_date}"
            
            #headers with API key
            headers = {
                'accept': 'application/json'
                
            }
           
            # Build parameters dictionary - requests will handle URL encoding automatically
            params = {
                'offsetMark': offsetMark,
                'pageSize': page_size,
                'api_key': API_KEY
            }

            # Add optional parameters only if they have values
            if congress != -1:
                try:
                    params['congress'] = int(congress)
                except ValueError:
                    pass
            if docClass:
                params['docClass'] = docClass
            if billVersion:
                params['billVersion'] = billVersion
            if courtCode:
                params['courtCode'] = courtCode      
            if courtType:
                params['courtType'] = courtType     
            if state:
                params['state'] = state
            if topic:
                params['topic'] = topic
            if isGLP:
                    try:
                        params['isGLP'] = bool(isGLP)
                    except ValueError:
                        pass
            if natureSuitCode:
                params['natureSuitCode'] = natureSuitCode
            if natureSuit:
                params['natureSuit'] = natureSuit
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            logger.info(f"Collections search successful for collection: {collection_id}")
            await ctx.info(f"Collection {collection_id} search completed")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in collections_search_last_modified: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in collections_search_last_modified: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})

@mcp.tool(name="collections_search_last_modified_to_end_date", 
        description="📊 FIND DOCUMENTS MODIFIED IN DATE RANGE within specific collections. Excellent for analyzing legislative activity periods or document update patterns. Tested: 221 bills modified between 2026-03-20 and 2026-03-25. Same advanced filtering as collections_search_last_modified. Ideal for tracking congressional sessions, regulatory updates, or court opinion releases within specific timeframes.")
async def collections_search_last_modified_to_end_date(collection_id : str ,start_date:datetime,end_date:datetime,ctx: Context,page_size:int = 10, offsetMark : str = '*',
                                                       congress: int =-1,docClass:str = '', billVersion:str ='',courtCode:str = '',courtType:str='',
                                                        state:str = '',topic:str='',isGLP:str='',natureSuitCode:str = '',natureSuit:str = '') -> str:
    """Search for documents in a collection modified between start and end dates."""
    try:
        if await handel_api_limits(ctx):  # Increment the API call counter and check if limit is reached
            
            # Format the dates and encode them for URL path
            formatted_start = start_date.strftime(DATE_TIME_FORMAT)
            formatted_end = end_date.strftime(DATE_TIME_FORMAT)
            encoded_start = quote(formatted_start)
            encoded_end = quote(formatted_end)

            #base api url with collection and encoded start and end dates in the path
            url = f"{BASE_URL}/collections/{collection_id}/{encoded_start}/{encoded_end}"
            
            # Build parameters dictionary - requests will handle URL encoding automatically
            params = {
                'offsetMark': offsetMark,
                'pageSize': page_size,
                'api_key': API_KEY
            }

            # Add optional parameters only if they have values
            if congress != -1:
                try:
                    params['congress'] = int(congress)
                except ValueError:
                    pass
            if docClass:
                params['docClass'] = docClass
            if billVersion:
                params['billVersion'] = billVersion
            if courtCode:
                params['courtCode'] = courtCode      
            if courtType:
                params['courtType'] = courtType     
            if state:
                params['state'] = state
            if topic:
                params['topic'] = topic
            if isGLP:
                    try:
                        params['isGLP'] = bool(isGLP)
                    except ValueError:
                        pass
            if natureSuitCode:
                params['natureSuitCode'] = natureSuitCode
            if natureSuit:
                params['natureSuit'] = natureSuit

            #headers with API key
            headers = {
                'accept': 'application/json',
                'x-api-key': API_KEY
            }
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            logger.info(f"Collections search successful for collection: {collection_id}")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in collections_search_last_modified: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in collections_search_last_modified: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.tool(name="package_summary", 
          description="📋 GET COMPLETE PACKAGE METADATA including sponsors, committees, bill status, and download links. Returns comprehensive details like title, congress, chamber, bill type, members (sponsors/cosponsors with party/state), committees assigned, and direct links to HTML, PDF, XML, ZIP formats. Tested with Border Security Investment Act (HR 445) showing 7 sponsors, 2 committees, 8 pages. Essential for detailed bill analysis.")
async def package_summary(package_id: str ,ctx: Context) -> str:
    """Get a JSON summary for a specific package."""
    try:
        if await handel_api_limits(ctx):  # Increment the API call counter and check if limit is reached
            
            #base api url with package id in the path
            url = f"{BASE_URL}/packages/{package_id}/summary"
            
            #headers with API key
            headers = {
                'Content-Type': 'application/json',
            }
            params = {
                'api_key': API_KEY
            }
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            logger.info(f"Package summary retrieved for: {package_id}")
            await ctx.info(f"Package summary retrieved for: {package_id}")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in package_summary: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in package_summary: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.tool(name="package_granulates", 
          description="🔍 LIST DOCUMENT SECTIONS (granules) within large documents. Bills typically have no granules (single document), but CFR and large publications are split into sections. Tested: CFR-2025-title8-vol1 has 1,298 granules including Table of Contents, Department chapters, and individual regulation sections. Use for navigating complex regulatory documents with pagination support.")
async def package_granulates(package_id: str,ctx: Context, page_size: int = 10, offsetMark : str = '*') -> str:
    """Get a list of granules associated with a package."""
    try:
        if await handel_api_limits(ctx):  # Increment the API call counter and check if limit is reached

            #base api url with package id in the path
            url = f"{BASE_URL}/packages/{package_id}/granules"
            
            # Build parameters dictionary - requests will handle URL encoding automatically
            params = {
                'offsetMark': offsetMark,
                'pageSize': page_size,
                'api_key': API_KEY
            }
            
            #headers with API key
            headers = {
                'Content-Type': 'application/json',
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            logger.info(f"Package granules retrieved for: {package_id}")
            await ctx.info(f"Package granules retrieved for: {package_id}")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in package_granulates: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in package_granulates: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})

    
@mcp.tool(name="package_granulates_summary", 
          description="📖 GET DETAILED SECTION METADATA for specific document granules. Returns title, heading, section ranges (e.g., § 1.1 to § 392.4), granule class (NODE/TOC), and download links for HTML, PDF, XML formats. Tested: CFR Department of Homeland Security chapter shows complete section coverage with direct access links. Perfect for accessing specific regulation sections within large CFR volumes.")
async def package_granulates_summary(package_id: str,granules_id:str,ctx: Context, page_size: int = 10) -> str:
    """Get a summary of granules associated with a package."""
    try:
        if await handel_api_limits(ctx):  # Increment the API call counter and check if limit is reached
            #base api url with package id and granules id in the path
            url = f"{BASE_URL}/packages/{package_id}/granules/{granules_id}/summary"


            # Build parameters dictionary - requests will handle URL encoding automatically
            params = {
                'api_key': API_KEY
                }

            #headers with API key
            headers = {
                'accept': 'application/json',
                'x-api-key': API_KEY
            }

            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            logger.info(f"Package granules summary retrieved for: {package_id}, granules: {granules_id}")
            await ctx.info(f"Package granules summary retrieved for: {package_id}, granules: {granules_id}")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in collections_search_last_modified: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in collections_search_last_modified: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.tool(name="published", 
          description="📅 GET RECENTLY PUBLISHED DOCUMENTS from specific date forward. Track new government publications in real-time. Tested: 130 bills published since 2026-03-20, including latest bills from current congress (119). Filter by collection (BILLS, FR, CFR, etc.) with pagination. Perfect for monitoring new legislation, Federal Register notices, court decisions, or any government document type.")
async def published(start_date: datetime,collection:str, ctx: Context, page_size: int = 10, offsetMark : str = '*') -> str:
    """Retrieve list of packages based on publication date (from start date onwards)."""
    try:
        if await handel_api_limits(ctx):  # Increment the API call counter and check if limit is reached
            
            # Format the date and encode it for URL path
            formatted_date = start_date.strftime(DATE_TIME_FORMAT_NO_TIME)
            encoded_date = quote(formatted_date)
            logger.info(f"Published packages retrieved from: {formatted_date}")
            #base api url with encoded date in the path
            url = f"{BASE_URL}/published/{encoded_date}"
            logger.info(f"Published packages collections: {collection}")
            # Build parameters dictionary - requests will handle URL encoding automatically
            params = {
                'offsetMark': offsetMark,
                'pageSize': page_size,
                'collection': collection,
                'api_key': API_KEY
                
            }
            
            #headers with API key
            headers = {
                'accept': 'application/json'
            }
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            logger.info(f"Published packages retrieved from: {response.url}")
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            logger.info(f"Published packages retrieved from: {formatted_date}")
            await ctx.info(f"Published packages retrieved from: {formatted_date}")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in published: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in published: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.tool(name="published_end", 
          description="📊 GET PUBLICATIONS IN SPECIFIC DATE RANGE for analyzing publication patterns and legislative activity periods. Tested: 66 bills published between 2026-03-25 and 2026-03-29, including latest International Transgender Day of Visibility resolution (2026-03-27). Excellent for tracking congressional session activity, regulatory publication periods, or court decision releases within specific timeframes.")
async def published_end(start_date: datetime,end_date: datetime ,collection: str, ctx: Context, page_size: int = 10, offsetMark : str = '*') -> str:
    """Retrieve list of packages published within a date range."""
    try:
        if await handel_api_limits(ctx): # Increment the API call counter and check if limit is reached
            
            # Format the dates and encode them for URL path
            formatted_start = start_date.strftime(DATE_TIME_FORMAT_NO_TIME)
            formatted_end = end_date.strftime(DATE_TIME_FORMAT_NO_TIME)
            encoded_start = quote(formatted_start)
            encoded_end = quote(formatted_end)
            
            #base api url with encoded start and end dates in the path
            url = f"{BASE_URL}/published/{encoded_start}/{encoded_end}"
            
            # Build parameters dictionary - requests will handle URL encoding automatically
            params = {
                'offsetMark': offsetMark,
                'pageSize': page_size,
                'api_key': API_KEY,
                'collection': collection
            }
            
            #headers with API key
            headers = {
                'accept': 'application/json'
            }
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            logger.info(f"Published packages retrieved from {formatted_start} to {formatted_end}")
            await ctx.info(f"Published packages retrieved from {formatted_start} to {formatted_end}")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in published_end: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in published_end: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.tool(name="related", 
          description="🔗 DISCOVER RELATED DOCUMENTS across collections. Input any package ID to find connected documents like bill status, different bill versions, congressional record mentions, and bill history. Tested: BILLS-119hr445ih links to BILLSTATUS (status tracking), BILLS (other versions), HOB (bill history), and CREC (Congressional Record references). Essential for comprehensive bill tracking and legislative research.")
async def related(access_id: str ,ctx: Context) -> str:
    """Get a list of relationships for a given access ID."""
    try:
        if await handel_api_limits(ctx): # Increment the API call counter and check if limit is reached
            #base api url with access id in the path
            url = f"{BASE_URL}/related/{access_id}"

            # Build parameters dictionary - requests will handle URL encoding automatically
            params = {
                'api_key': API_KEY
                }
           
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            await ctx.info(f"Related documents retrieved for access ID: {access_id}")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in related: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in related: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.tool(name="related_collection", 
          description="🎯 FIND RELATED DOCUMENTS IN SPECIFIC COLLECTION. More targeted than general 'related' tool - focuses on connections within one collection type. Tested: BILLS-119hr445ih in BILLSTATUS collection returns current bill status package (BILLSTATUS-119hr445) with last modification date. Perfect for tracking specific relationships like bill-to-status, regulation-to-amendments, or court-opinion-to-appeals.")
async def related_collection(access_id: str,collention_id:str ,ctx: Context) -> str:
    """Get a list of relationships for a given access ID within a specific collection."""
    try:
        if await handel_api_limits(ctx): # Increment the API call counter and check if limit is reached
            
            #base api url with access id and collection id in the path
            url = f"{BASE_URL}/related/{access_id}/{collention_id}"

            # Build parameters dictionary - requests will handle URL encoding automatically
            params = {
                'api_key': API_KEY
                }
            
            #headers with API key
            headers = {
                'accept': '*/*',
                'x-api-key': API_KEY
            }

            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            
            # Update rate limit info from response headers
            await update_rate_limit_from_headers(ctx, response.headers)
            
            await ctx.info(f"Related documents retrieved for access ID: {access_id} in collection: {collention_id}")
            return json.dumps(response.json())
        else:
            logger.warning("API limit reached")
            return json.dumps({"error": "API limit reached"})
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error in related_collection: {str(e)}", exc_info=True)
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"Unexpected error in related_collection: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.tool(name="rate_limit_status", 
          description="⚡ MONITOR API USAGE and rate limits in real-time. Shows server limits (36,000/hour), remaining calls (35,907), and local tracking (1,000/hour limit). Includes timestamps for rate limit resets. Essential for high-volume applications to avoid hitting API limits. Both server-side and local rate limiting are tracked and displayed for comprehensive usage monitoring.")
async def rate_limit_status(ctx: Context) -> str:
    """Check current API rate limit status and usage information."""
    try:
        # Get rate limit data from API headers (if available)
        api_rate_limit = await ctx.get_state("api_rate_limit")
        api_rate_remaining = await ctx.get_state("api_rate_remaining")
        rate_limit_updated = await ctx.get_state("rate_limit_updated") or 0
        
        # Get local tracking data
        local_apicalls = await ctx.get_state("apicalls") or 0
        local_ttl = await ctx.get_state("ttl") or 0
        
        status = {
            "timestamp": datetime.now().isoformat(),
            "server_data": {
                "available": bool(api_rate_limit and api_rate_remaining is not None),
                "limit": api_rate_limit,
                "remaining": api_rate_remaining,
                "last_updated": datetime.fromtimestamp(rate_limit_updated).isoformat() if rate_limit_updated > 0 else None
            },
            "local_tracking": {
                "calls_this_hour": local_apicalls,
                "local_limit": API_CALL_LIMIT_PER_HOUR,
                "hour_resets_at": datetime.fromtimestamp(local_ttl).isoformat() if local_ttl > 0 else None
            }
        }
        
        # Add usage recommendations
        if api_rate_remaining is not None:
            if api_rate_remaining < 50:
                status["warning"] = f"Low rate limit remaining: {api_rate_remaining} requests left"
            elif api_rate_remaining < 100:
                status["notice"] = f"Moderate usage: {api_rate_remaining} requests remaining"
        
        logger.info(f"Rate limit status checked: {api_rate_remaining}/{api_rate_limit} server, {local_apicalls}/{API_CALL_LIMIT_PER_HOUR} local")
        await ctx.info("Rate limit status retrieved")
        
        return json.dumps(status, indent=2)
        
    except Exception as e:
        logger.error(f"Error checking rate limit status: {str(e)}", exc_info=True)
        return json.dumps({"error": f"Error checking rate limit status: {str(e)}"})


@mcp.prompt(
        name="Mcp capabilities",
        description="describes what is available from this MCP including API rate limit monitoring"  ,
        tags=["gov info api", "tools", "research", "documents", "collections", "packages", "granules", "publication dates", "relationships", "rate limiting"],
        meta={"version": "1.1"}
        
    ) 
def descripbe_capablilties() -> list[Message]:
    """describes the tools available in this MCP."""

    messages = [ 
        Message(role="assistant", content="You are a helpful assistant that can call the following tools to interact with the GovInfo API:"),
        Message(role="assistant", content="SEARCH & DISCOVERY:"),
        Message(role="assistant", content="1. search(query, offset_mark?, sort?, collection?, historical?): Advanced search for government documents with optional pagination (offsetMark), sorting (publishDate:desc/asc, lastModified:desc/asc, title:desc/asc), collection filtering (e.g., 'BILLS', 'CFR', 'FR'), and historical document inclusion."),
        Message(role="assistant", content="2. collections(): List all available GovInfo collections with metadata including package and granule counts."),
        Message(role="assistant", content="COLLECTION-SPECIFIC QUERIES:"),
        Message(role="assistant", content="3. collections_search_last_modified(collection_id, last_modified): Find documents in a collection modified after a specific date."),
        Message(role="assistant", content="4. collections_search_last_modified_to_end_date(collection_id, start_date, end_date): Find documents in a collection modified within a date range."),
        Message(role="assistant", content="PACKAGE & GRANULE DETAILS:"),
        Message(role="assistant", content="5. package_summary(package_id): Get detailed JSON metadata summary for a specific package (e.g., 'BILLS-118hr123ih')."),
        Message(role="assistant", content="6. package_granulates(package_id): Get list of granule records associated with a package."),
        Message(role="assistant", content="PUBLICATION DATE QUERIES:"),
        Message(role="assistant", content="7. published(start_date): Retrieve packages published on or after a specific date."),
        Message(role="assistant", content="8. published_end(start_date, end_date): Retrieve packages published within a date range."),
        Message(role="assistant", content="RELATIONSHIP DISCOVERY:"),
        Message(role="assistant", content="9. related(access_id): Find all documents related to a specific access ID."),
        Message(role="assistant", content="10. related_collection(access_id, collection_id): Find documents related to an access ID within a specific collection."),
        Message(role="assistant", content="RATE LIMITING:"),
        Message(role="assistant", content="All tools include automatic rate limiting (1000 calls/hour). Monitor API call counts to avoid hitting rate limits.")
    ]
    return messages


if __name__ == "__main__":
    import sys
    
    # Allow setting log level from command line: python gov.api.mcp.py --log-level DEBUG
    log_level = logging.INFO
    if len(sys.argv) > 2 and sys.argv[1] == "--log-level":
        level_name = sys.argv[2].upper()
        if hasattr(logging, level_name):
            log_level = getattr(logging, level_name)
            logger.setLevel(log_level)
            logger.info(f"Log level set to {level_name}")
    
    logger.info("Starting MCP server on HTTP port 8090")
    try:
        #local configuration for development - in production, use environment variables or config files for API_KEY
        mcp.run(transport="http", port=8090)
        # production configuration example fro http protocl:
        #mcp.run(transport="http", port=8090, host="0.0.0.0", ssl_cert="/path/to/cert.pem", ssl_key="/path/to/key.pem")
        #mcp.run(transport="stdio", port=8090, host="0.0.0.0", ssl_cert="/path/to/cert.pem", ssl_key="/path/to/key.pem")
        #mcp.run(transport="sse", port=8090, host="0.0.0.0", ssl_cert="/path/to/cert.pem", ssl_key="/path/to/key.pem")
        # default fastmcp configuration
        #mcp.run()
    except Exception as e:
        logger.error(f"Failed to start MCP server: {str(e)}", exc_info=True)
        raise