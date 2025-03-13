from fastapi import APIRouter
from fastapi.responses import FileResponse

# Create router for general routes
router = APIRouter(tags=["General"])

# Root endpoint
@router.get("/")
async def get_index():
    """Return the main page"""
    return FileResponse("static/test.html")

# Test page endpoint
@router.get("/test")
async def get_test_page():
    """Return the test page"""
    return FileResponse("static/test.html") 
