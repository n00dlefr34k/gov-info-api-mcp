#!/usr/bin/env python
"""
FastAPI REST wrapper for GovInfo MCP tools
Run this separately to expose HTTP endpoints on port 8090
"""
from fastapi import FastAPI, Body, Path, Query
from fastapi.responses import JSONResponse
from datetime import datetime
import json
import uvicorn
import importlib.util
from pydantic import BaseModel, Field
from typing import List, Optional

# Load the MCP module with dots in the filename
spec = importlib.util.spec_from_file_location("gov_api_mcp", "gov.api.mcp.py")
gove_api_mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gove_api_mcp)

search = gove_api_mcp.search
search_synthesis = gove_api_mcp.search_synthesis
collections = gove_api_mcp.collections
collections_search_last_modified = gove_api_mcp.collections_search_last_modified
collections_search_last_modified_to_end_date = gove_api_mcp.collections_search_last_modified_to_end_date
package_summary = gove_api_mcp.package_summary
package_granulates = gove_api_mcp.package_granulates
published = gove_api_mcp.published
published_end = gove_api_mcp.published_end
related = gove_api_mcp.related
related_collection = gove_api_mcp.related_collection
package_granulates_summary = gove_api_mcp.package_granulates_summary

app = FastAPI(title="GovInfo REST API", version="1.0")

class MockContext:
    """Mock context for FastAPI endpoints"""
    def __init__(self):
        self.state = {}
    
    async def info(self, msg):
        print(f"✓ {msg}")
    
    async def error(self, msg):
        print(f"✗ {msg}")
    
    async def warn(self, msg):
        print(f"⚠ {msg}")
    
    async def get_state(self, key):
        return self.state.get(key)
    
    async def set_state(self, key, value):
        self.state[key] = value

@app.get("/")
async def root():
    """API root - returns status and endpoints"""
    return {
        "status": "running",
        "message": "GovInfo API Server",
        "endpoints": {
            "search": "POST /search with JSON body: {\"query\":\"term\", \"pageSize\":10, \"offsetMark\":\"*\", \"historical\":false}",
            "search_synthesis": "POST /search_synthesis with JSON body: {\"search_query\":\"term\", \"committees\":[\"list\"]}",
            "collections": "GET /collections",
            "collections_by_date": "GET /collections/<id>/<YYYY-MM-DD>?pageSize=<int>&offsetMark=<str>&congress=<int>&docClass=<str>&billVersion=<str>&courtCode=<str>&courtType=<str>&state=<str>&topic=<str>&isGLP=<str>&natureSuitCode=<str>&natureSuit=<str>",
            "collections_by_range": "GET /collections/<id>/<YYYY-MM-DD>/<YYYY-MM-DD>?pageSize=<int>&offsetMark=<str>&congress=<int>&docClass=<str>&billVersion=<str>&courtCode=<str>&courtType=<str>&state=<str>&topic=<str>&isGLP=<str>&natureSuitCode=<str>&natureSuit=<str>",
            "package_summary": "GET /package/<id>/summary",
            "package_granules": "GET /package/<id>/granules?pageSize=<int>&offsetMark=<str>",
            "package_granules_summary": "GET /package/<id>/granules/<granule_id>/summary?pageSize=<int>",
            "published": "GET /published/<YYYY-MM-DD>?collection=<str>&pageSize=<int>&offsetMark=<str>",
            "published_range": "GET /published/<YYYY-MM-DD>/<YYYY-MM-DD>?collection=<str>&pageSize=<int>&offsetMark=<str>",
            "related": "GET /related/<access_id>",
            "related_collection": "GET /related/<access_id>/<collection_id>"
        }
    }

@app.post("/search")
async def search_endpoint(
    query: str = Body(...), 
    pageSize: int = Body(10), 
    offsetMark: str = Body('*'), 
    historical: bool = Body(False), 
    sort: str = Body('desc'), 
    collection: list = Body(None)):
    """Search for documents."""
    try:
        ctx = MockContext()
        
        # Extract parameters from JSON body
       
        if not query:
            return JSONResponse(status_code=400, content={"error": "query parameter is required"})
        
       
        sort = None  # Will be handled via sorts array
        collection = None  # Will be embedded in query if needed
        
        result = await search(query, ctx, offsetMark, sort, collection, historical, pageSize)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/search_synthesis", summary="Synthesize search results for AI analysis", description="Performs a search and synthesizes the results into a concise summary with AI analysis. You can specify a search query and optionally filter by committees (collections). If no committees are provided, the system will attempt to auto-detect relevant collections based on the search query, all of the resources are downloaded and the content is returned.")
async def search_synthesis_endpoint(
    search_query: str = Body(..., description="Search query for synthesis", examples=["immigration policy", "healthcare reform", "climate change"]), 
    committees: list = Body(None, description="List of collection codes", examples=[["BILLS", "FR"], ["CFR"], None])
):
    """🎯 Synthesize search results into a concise summary with AI analysis
    
    Examples:
    - Immigration search: search_query="immigration policy" + committees=["BILLS", "FR"]  
    - Healthcare search: search_query="healthcare reform" + committees=["BILLS", "CREC"]
    - Auto discovery: search_query="climate change" (committees auto-detected)
    """
    try:
        ctx = MockContext()
        
        # Extract parameters from JSON body
        if not search_query:
            return JSONResponse(status_code=400, content={"error": "search_query parameter is required"})
        
        
        result = await search_synthesis(search_query, ctx,committees)
        if result:
            return JSONResponse(content={"synthesis": result})
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from synthesis"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/collections",summary="Get all available collections", description="Returns a list of all collections available in the GovInfo system, including their IDs and descriptions.")
async def collections_endpoint():
    """Get all available collections"""
    try:
        ctx = MockContext()
        result = await collections(ctx)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/collections/{collection_id}/{last_modified}", summary="Get collections modified after a specific date", description="Returns collections modified after the specified date in YYYY-MM-DD format."    )
async def collections_by_date_endpoint(collection_id: str = Path(description="Collection code"), last_modified: str = Path(description="Last modified date in YYYY-MM-DD format"), pageSize: int = Query(10, description="Number of results per page"), offsetMark: str = Query('*', description="Offset marker for pagination"),
                                       congress: int = Query(-1, description="Congress number"), docClass: str = Query('', description="Document class"), billVersion: str = Query('', description="Bill version"),
                                       courtCode: str = Query('', description="Court code"), courtType: str = Query('', description="Court type"), state: str = Query('', description="State code"),
                                       topic: str = Query('', description="Topic"), isGLP: str = Query('', description="Is GLP"), natureSuitCode: str = Query('', description="Nature suit code"),
                                       natureSuit: str = Query('', description="Nature suit")):
    """Get collections modified after date. Format: YYYY-MM-DD"""
    try:
        date_obj = datetime.strptime(last_modified, "%Y-%m-%d")
        ctx = MockContext()
        result = await collections_search_last_modified(collection_id, date_obj, ctx, pageSize, offsetMark,
                                                       congress, docClass, billVersion, courtCode, courtType,
                                                       state, topic, isGLP, natureSuitCode, natureSuit)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Date format must be YYYY-MM-DD"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/collections/{collection_id}/{start_date}/{end_date}", summary="Get collections modified within a date range", description="Returns collections modified within the specified date range in YYYY-MM-DD format.")
async def collections_by_range_endpoint(collection_id: str = Path(description="Collection code"), 
                                        start_date: str = Path(description="Start date in YYYY-MM-DD format"), 
                                        end_date: str = Path(description="End date in YYYY-MM-DD format"), 
                                        pageSize: int = Query(10, description="Number of results per page"), 
                                        offsetMark: str = Query('*', description="Offset marker for pagination"),
                                        congress: int = Query(-1, description="Congress number"), 
                                        docClass: str = Query('', description="Document class"), 
                                        billVersion: str = Query('', description="Bill version"),
                                        courtCode: str = Query('', description="Court code"), 
                                        courtType: str = Query('', description="Court type"), 
                                        state: str = Query('', description="State code"),
                                        topic: str = Query('', description="Topic"), 
                                        isGLP: str = Query('', description="Is GLP"), 
                                        natureSuitCode: str = Query('', description="Nature suit code"),
                                        natureSuit: str = Query('', description="Nature suit")):
    """Get collections modified within date range. Format: YYYY-MM-DD"""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        ctx = MockContext()
        result = await collections_search_last_modified_to_end_date(collection_id, start, end, ctx, pageSize, offsetMark,
                                                                   congress, docClass, billVersion, courtCode, courtType,
                                                                   state, topic, isGLP, natureSuitCode, natureSuit)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Date format must be YYYY-MM-DD"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/package/{package_id}/summary" , summary="Get package summary", description="Returns a summary of the specified package, including metadata and key information.")
async def package_summary_endpoint(package_id: str = Path(description="Package ID")):
    """Get package summary"""
    try:
        ctx = MockContext()
        result = await package_summary(package_id, ctx)
        if result:
            return JSONResponse(content=json.loads(result))     
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/package/{package_id}/granules", summary="Get package granules", description="Returns the granules for the specified package.")
async def package_granules_endpoint(package_id: str = Path(description="Package ID"), 
                                    pageSize: int = Query(10, description="Number of results per page"), 
                                    offsetMark: str = Query('*', description="Offset marker for pagination")):
    """Get granules for a package"""
    try:
        ctx = MockContext()
        result = await package_granulates(package_id, ctx, pageSize, offsetMark)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    
@app.get("/package/{package_id}/granules/{granules_id}/summary", summary="Get granules summary", description="Returns the summary for the specified granules within a package.")
async def package_granules_summary_endpoint(package_id: str = Path(description="Package ID"), 
                                            granules_id: str = Path(description="Granules ID"), 
                                            pageSize: int = Query(10, description="Number of results per page")):
    """Get granules summary for a package"""
    try:
        ctx = MockContext()
        result = await package_granulates_summary(package_id, granules_id, ctx, pageSize)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/published/{start_date}" , summary="Get published packages from a specific date", description="Returns packages published from the specified start date in YYYY-MM-DD format.")
async def published_endpoint(start_date: str = Path(description="Start date in YYYY-MM-DD format"), 
                             collection: str = Query(description="Collection code"), 
                             pageSize: int = Query(10, description="Number of results per page"), 
                             offsetMark: str = Query('*', description="Offset marker for pagination")):
    """Get published packages from date onwards. Format: YYYY-MM-DD"""
    try:
        date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        ctx = MockContext()
        result = await published(date_obj, collection, ctx, pageSize, offsetMark)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Date format must be YYYY-MM-DD"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/published/{start_date}/{end_date}" , summary="Get published packages within a date range", description="Returns packages published within the specified date range in YYYY-MM-DD format.")
async def published_range_endpoint(start_date: str = Path(description="Start date in YYYY-MM-DD format"), 
                                   end_date: str = Path(description="End date in YYYY-MM-DD format"), 
                                   collection: str = Query(description="Collection code"), 
                                   pageSize: int = Query(10, description="Number of results per page"), 
                                   offsetMark: str = Query('*', description="Offset marker for pagination")):
    """Get published packages within date range. Format: YYYY-MM-DD"""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        ctx = MockContext()
        result = await published_end(start, end, collection, ctx, pageSize, offsetMark)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Date format must be YYYY-MM-DD"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/related/{access_id}" , summary="Get related documents for an access ID", description="Returns documents related to the specified access ID (packageId or granuleId).")
async def related_endpoint(access_id: str = Path(description="The unique accessId (packageId or granuleId) for a given piece of GovInfo content")):
    """Get related documents for an access ID"""
    try:
        ctx = MockContext()
        result = await related(access_id, ctx)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/related/{access_id}/{collection_id}" , summary="Get related documents within a collection", description="Returns documents related to the specified access ID within a specific collection.")
async def related_collection_endpoint(
    access_id: str = Path(description="The unique accessId (packageId or granuleId) for a given piece of GovInfo content"),
    collection_id: str = Path(description="The unique collection id for a given collection of GovInfo content")
):
    """Get related documents within a collection"""
    try:
        ctx = MockContext()
        result = await related_collection(access_id, collection_id, ctx)
        if result:
            return JSONResponse(content=json.loads(result))
        else:
            return JSONResponse(status_code=500, content={"error": "Empty response from API"})
    except json.JSONDecodeError as e:
        return JSONResponse(status_code=500, content={"error": f"Invalid JSON response: {str(e)}"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    print("=" * 60)
    print("GovInfo REST API Server")
    print("=" * 60)
    print("Starting on http://0.0.0.0:8030")
    print("Swagger Docs: http://127.0.0.1:8030/docs")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8030)
