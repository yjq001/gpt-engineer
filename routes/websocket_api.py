from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Any
import json
from pathlib import Path
import asyncio
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
logger.debug("WebSocket API 模块初始化")

# Create router
router = APIRouter(tags=["WebSocket API"])

# Connection manager for WebSockets
class ConnectionManager:
    def __init__(self):
        # project_id -> list of connected websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}
        logger.debug("ConnectionManager 初始化")

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.info(f"WebSocket 连接已建立: project_id={project_id}")
        logger.debug(f"当前连接数: {len(self.active_connections[project_id])}")

    def disconnect(self, project_id: str, websocket: WebSocket):
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
                logger.info(f"WebSocket 连接已断开: project_id={project_id}")
                logger.debug(f"剩余连接数: {len(self.active_connections[project_id])}")
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
                logger.info(f"项目的所有 WebSocket 连接已断开: project_id={project_id}")

    async def send_message(self, project_id: str, message: dict):
        """向项目的所有连接发送消息（已弃用，请使用 send_personal_message）"""
        if project_id in self.active_connections:
            disconnected_websockets = []
            for websocket in self.active_connections[project_id]:
                try:
                    await websocket.send_json(message)
                    logger.debug(f"消息已发送: project_id={project_id}, type={message.get('type')}")
                except Exception as e:
                    logger.error(f"发送消息时出错: {str(e)}")
                    disconnected_websockets.append(websocket)
            
            # Clean up disconnected websockets
            for websocket in disconnected_websockets:
                self.disconnect(project_id, websocket)
    
    async def send_personal_message(self, message: dict, project_id: str):
        """向项目的所有连接发送消息"""
        if project_id in self.active_connections:
            disconnected_websockets = []
            for websocket in self.active_connections[project_id]:
                try:
                    await websocket.send_json(message)
                    logger.debug(f"个人消息已发送: project_id={project_id}, type={message.get('type')}")
                except Exception as e:
                    logger.error(f"发送个人消息时出错: {str(e)}")
                    disconnected_websockets.append(websocket)
            
            # Clean up disconnected websockets
            for websocket in disconnected_websockets:
                self.disconnect(project_id, websocket)

# Create connection manager instance
manager = ConnectionManager()

@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for real-time communication"""
    await manager.connect(project_id, websocket)
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "message": "WebSocket connection established"
        })
        logger.debug(f"初始连接消息已发送: project_id={project_id}")
        
        # Check if project exists and send project info
        try:
            project = 1
            if project:
                await websocket.send_json({
                    "type": "project_info",
                    "project": project
                })
                logger.debug(f"项目信息已发送: project_id={project_id}")
        except Exception as e:
            logger.error(f"获取项目信息时出错: {str(e)}")
            await websocket.send_json({
                "type": "error",
                "message": f"获取项目信息时出错: {str(e)}"
            })
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            logger.debug(f"收到客户端消息: project_id={project_id}, data={data[:100]}...")
            
            # Process message using service
            try:
                await websocket.send_json({
                "type": "error",
                "message": f"获取项目信息时出错: {str(e)}"
            })
            except Exception as e:
                logger.error(f"处理聊天消息时出错: {str(e)}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"处理聊天消息时出错: {str(e)}"
                })
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket 连接断开: project_id={project_id}")
        manager.disconnect(project_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket 错误: {str(e)}")
        manager.disconnect(project_id, websocket)

# Export the manager for use in other modules
__all__ = ["router", "manager"] 
