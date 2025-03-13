from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
import logging
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 获取日志级别配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}

# 设置日志
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVELS.get(LOG_LEVEL, logging.INFO))

# 导入数据库模块
from db.database import get_pool_status

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

# Database pool status endpoint
@router.get("/api/status/db")
async def get_db_status():
    """获取数据库连接池状态"""
    try:
        status = get_pool_status()
        logger.debug(f"数据库连接池状态: {status}")
        return JSONResponse(content=status)
    except Exception as e:
        logger.error(f"获取数据库连接池状态时出错: {str(e)}")
        return JSONResponse(
            content={"error": f"获取数据库连接池状态时出错: {str(e)}"},
            status_code=500
        ) 
