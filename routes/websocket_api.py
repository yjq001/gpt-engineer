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

# 导入GPT Engineer核心组件
from gpt_engineer.core.ai import AI
from gpt_engineer.core.prompt import Prompt
from gpt_engineer.core.default.disk_memory import DiskMemory
from gpt_engineer.core.preprompts_holder import PrepromptsHolder
from gpt_engineer.core.default.steps import gen_code, improve_fn
from gpt_engineer.core.files_dict import FilesDict
from gpt_engineer.core.default.paths import PREPROMPTS_PATH

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

# 创建AI代码生成器
class CodeGenerator:
    def __init__(self):
        self.model_name = os.getenv("MODEL_NAME", "gpt-4o")
        self.temperature = float(os.getenv("TEMPERATURE", "0.1"))
        self.azure_endpoint = os.getenv("AZURE_ENDPOINT", None)
        
        # 检查API密钥
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("未设置OPENAI_API_KEY环境变量，代码生成功能可能无法正常工作")
        
        # 检查模型名称
        if "claude" in self.model_name.lower():
            self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            if not self.anthropic_key:
                logger.warning("使用Claude模型但未设置ANTHROPIC_API_KEY环境变量，代码生成功能可能无法正常工作")
        
        logger.info(f"初始化代码生成器: model={self.model_name}, temperature={self.temperature}")
        
    async def generate_code(self, project_id: str, prompt_text: str) -> Dict[str, str]:
        """根据提示生成代码"""
        try:
            # 创建项目目录
            project_path = Path(f"projects/{project_id}")
            project_path.mkdir(parents=True, exist_ok=True)
            
            # 初始化AI和内存
            try:
                ai = AI(
                    model_name=self.model_name,
                    temperature=self.temperature,
                    azure_endpoint=self.azure_endpoint
                )
                logger.info(f"AI实例已创建: model={self.model_name}")
            except Exception as e:
                logger.error(f"创建AI实例时出错: {str(e)}")
                return {"error": f"创建AI实例时出错: {str(e)}"}
            
            memory = DiskMemory(project_path)
            
            # 创建提示
            prompt = Prompt(prompt_text)
            
            # 获取预设提示
            try:
                preprompts_holder = PrepromptsHolder(PREPROMPTS_PATH)
                logger.info(f"已加载预设提示: {PREPROMPTS_PATH}")
            except Exception as e:
                logger.error(f"加载预设提示时出错: {str(e)}")
                return {"error": f"加载预设提示时出错: {str(e)}"}
            
            # 检查项目目录是否已存在文件，决定是新建项目还是改进现有项目
            existing_files = list(project_path.glob("**/*"))
            existing_files = [f for f in existing_files if f.is_file()]
            
            if existing_files:
                # 项目已存在，使用improve_fn改进现有项目
                logger.info(f"项目 {project_id} 已存在，使用improve_fn改进现有项目")
                
                # 加载现有文件到FilesDict
                files_dict = {}
                for file_path in existing_files:
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            relative_path = file_path.relative_to(project_path)
                            files_dict[str(relative_path)] = f.read()
                    except UnicodeDecodeError:
                        logger.warning(f"跳过二进制文件: {file_path}")
                
                files_dict = FilesDict(files_dict)
                
                # 使用improve_fn改进现有项目
                try:
                    files_dict = improve_fn(ai, prompt, files_dict, memory, preprompts_holder)
                    logger.info(f"代码改进成功: {len(files_dict)} 个文件")
                except Exception as e:
                    logger.error(f"改进代码时出错: {str(e)}")
                    return {"error": f"改进代码时出错: {str(e)}"}
            else:
                # 项目不存在或为空，使用gen_code生成新项目
                logger.info(f"项目 {project_id} 不存在或为空，使用gen_code生成新项目")
                try:
                    files_dict = gen_code(ai, prompt, memory, preprompts_holder)
                    logger.info(f"代码生成成功: {len(files_dict)} 个文件")
                except Exception as e:
                    logger.error(f"生成代码时出错: {str(e)}")
                    return {"error": f"生成代码时出错: {str(e)}"}
            
            # 将生成的代码保存到项目目录
            try:
                for file_path, content in files_dict.items():
                    full_path = project_path / file_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(full_path, "w", encoding="utf-8") as f:
                        f.write(content)
                logger.info(f"所有文件已保存到: {project_path}")
            except Exception as e:
                logger.error(f"保存文件时出错: {str(e)}")
                return {"error": f"保存文件时出错: {str(e)}"}
            
            logger.info(f"项目 {project_id} 代码处理完成，共 {len(files_dict)} 个文件")
            return files_dict
        except Exception as e:
            logger.error(f"处理代码时出错: {str(e)}")
            return {"error": str(e)}

# 创建代码生成器实例
code_generator = CodeGenerator()

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
        
        # 检查API密钥
        if not os.getenv("OPENAI_API_KEY"):
            await websocket.send_json({
                "type": "warning",
                "message": "警告: 未设置OPENAI_API_KEY环境变量，代码生成功能可能无法正常工作"
            })
        
        # Check if project exists and send project info
        project_exists = False
        try:
            project_path = Path(f"projects/{project_id}")
            if project_path.exists():
                # 检查是否有文件
                existing_files = list(project_path.glob("**/*"))
                existing_files = [f for f in existing_files if f.is_file()]
                
                if existing_files:
                    project_exists = True
                    # 获取项目文件列表
                    files = [str(f.relative_to(project_path)) for f in existing_files]
                    await websocket.send_json({
                        "type": "project_info",
                        "project_id": project_id,
                        "files": files,
                        "is_existing_project": True
                    })
                    logger.debug(f"现有项目信息已发送: project_id={project_id}")
                else:
                    await websocket.send_json({
                        "type": "project_info",
                        "project_id": project_id,
                        "files": [],
                        "is_existing_project": False
                    })
                    logger.debug(f"空项目信息已发送: project_id={project_id}")
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
            
            # 解析消息
            try:
                message = json.loads(data)
                message_type = message.get("type", "")
                
                # 处理不同类型的消息
                if message_type == "chat":
                    # 处理聊天消息，生成代码
                    prompt_text = message.get("content", "")
                    if prompt_text:
                        # 发送处理状态
                        if project_exists:
                            await websocket.send_json({
                                "type": "status",
                                "status": "processing",
                                "message": "正在改进现有项目代码，请稍候..."
                            })
                        else:
                            await websocket.send_json({
                                "type": "status",
                                "status": "processing",
                                "message": "正在生成新项目代码，请稍候..."
                            })
                        
                        # 异步生成代码
                        files_dict = await code_generator.generate_code(project_id, prompt_text)
                        
                        # 检查是否有错误
                        if "error" in files_dict:
                            await websocket.send_json({
                                "type": "error",
                                "message": f"生成代码时出错: {files_dict['error']}"
                            })
                        else:
                            # 发送生成的代码
                            await websocket.send_json({
                                "type": "code_generated",
                                "project_id": project_id,
                                "files": [
                                    {"path": path, "content": content}
                                    for path, content in files_dict.items()
                                ],
                                "is_improved": project_exists
                            })
                            
                            # 更新project_exists状态，因为现在项目肯定存在了
                            project_exists = True
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "聊天内容不能为空"
                        })
                elif message_type == "get_file":
                    # 获取文件内容
                    file_path = message.get("path", "")
                    if file_path:
                        try:
                            full_path = Path(f"projects/{project_id}/{file_path}")
                            if full_path.exists() and full_path.is_file():
                                with open(full_path, "r", encoding="utf-8") as f:
                                    content = f.read()
                                await websocket.send_json({
                                    "type": "file_content",
                                    "path": file_path,
                                    "content": content
                                })
                            else:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": f"文件不存在: {file_path}"
                                })
                        except Exception as e:
                            await websocket.send_json({
                                "type": "error",
                                "message": f"获取文件内容时出错: {str(e)}"
                            })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"不支持的消息类型: {message_type}"
                    })
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "无效的JSON格式"
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
