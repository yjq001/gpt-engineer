from fastapi import APIRouter

from routes.user import router as user_router
from routes.project import router as project_router
from routes.general import router as general_router
from routes.auth import router as auth_router
from routes.proxy import router as proxy_router

# Create main router
router = APIRouter()

# Include modular routers
router.include_router(user_router)
router.include_router(project_router)
router.include_router(general_router)
router.include_router(auth_router)
router.include_router(proxy_router)
