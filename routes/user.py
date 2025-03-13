from fastapi import APIRouter, Depends, HTTPException
from typing import Dict
import logging
from db.database import get_db
from db.models import User
from peewee import DoesNotExist, OperationalError

# 设置日志
logger = logging.getLogger(__name__)

# Create router with /api/user prefix
router = APIRouter(prefix="/api/user", tags=["User API"])

# User routes
@router.get("/{user_id}")
async def get_user_by_id(user_id: str, _=Depends(get_db)):
    """根据 ID 获取用户"""
    try:
        try:
            user = User.get(User.id == user_id)
            return user.to_dict()
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="用户未找到")
    except OperationalError as e:
        logger.error(f"数据库操作错误: {str(e)}")
        raise HTTPException(status_code=503, detail="数据库服务暂时不可用")
    except Exception as e:
        logger.error(f"获取用户时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}") 
