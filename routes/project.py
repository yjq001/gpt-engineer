from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pathlib import Path


# Create router with /api/project prefix
router = APIRouter(prefix="/api/project", tags=["Project API"])


# Project routes

@router.get("/{project_id}")
async def get_project(project_id: str):
    """Get project details by ID"""
    
    return 1
