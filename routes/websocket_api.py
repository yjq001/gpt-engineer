from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional, Any, Union
import json
from pathlib import Path
import asyncio
import logging
import os
import re
import difflib
from dotenv import load_dotenv
from langchain.callbacks.base import BaseCallbackHandler
from gpt_engineer.core.files_dict import FilesDict

# 加载环境变量，强制覆盖已存在的环境变量
load_dotenv(override=True)

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
from gpt_engineer.tools.custom_steps import clarified_gen
from langchain.schema import HumanMessage, SystemMessage

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
    
    def delete_file(self, file_path, project_path):
        """尝试使用多种方法删除文件"""
        full_path = project_path / file_path
        if not full_path.exists():
            logger.warning(f"要删除的文件不存在: {full_path}")
            return True  # 文件不存在也视为删除成功
        
        # 记录删除尝试
        logger.info(f"尝试删除文件: {full_path}")
        
        # 尝试多种删除方法
        delete_methods = [
            self._delete_with_os_remove,
            self._delete_with_path_unlink,
            self._delete_with_empty_file,
            self._delete_with_system_command,
            self._delete_with_wait_and_retry
        ]
        
        for method in delete_methods:
            try:
                if method(full_path):
                    return True
            except Exception as e:
                logger.warning(f"使用方法 {method.__name__} 删除文件失败: {str(e)}")
        
        logger.error(f"所有删除方法都失败，无法删除文件: {full_path}")
        return False
    
    def _delete_with_os_remove(self, file_path):
        """使用os.remove删除文件"""
        try:
            os.remove(str(file_path))
            logger.info(f"使用os.remove成功删除文件: {file_path}")
            return True
        except Exception as e:
            logger.warning(f"使用os.remove删除失败: {str(e)}")
            return False
    
    def _delete_with_path_unlink(self, file_path):
        """使用Path.unlink删除文件"""
        try:
            file_path.unlink(missing_ok=True)
            logger.info(f"使用Path.unlink成功删除文件: {file_path}")
            return True
        except Exception as e:
            logger.warning(f"使用Path.unlink删除失败: {str(e)}")
            return False
    
    def _delete_with_empty_file(self, file_path):
        """通过清空文件内容来"删除"文件"""
        try:
            with open(str(file_path), 'w') as f:
                f.write('')  # 清空文件内容
            logger.info(f"已清空文件内容: {file_path}")
            
            # 再次尝试删除已清空的文件
            try:
                os.remove(str(file_path))
                logger.info(f"清空后使用os.remove成功删除文件: {file_path}")
                return True
            except Exception:
                pass
            
            return True  # 即使无法物理删除，清空内容也算成功
        except Exception as e:
            logger.warning(f"清空文件内容失败: {str(e)}")
            return False
    
    def _delete_with_system_command(self, file_path):
        """使用系统命令删除文件"""
        try:
            import subprocess
            if os.name == 'nt':  # Windows
                subprocess.run(['del', '/f', '/q', str(file_path)], shell=True, check=False)
            else:  # Unix/Linux/Mac
                subprocess.run(['rm', '-f', str(file_path)], check=False)
            
            # 检查文件是否已删除
            if not file_path.exists():
                logger.info(f"使用系统命令成功删除文件: {file_path}")
                return True
            else:
                logger.warning(f"使用系统命令删除文件后，文件仍然存在: {file_path}")
                return False
        except Exception as e:
            logger.warning(f"使用系统命令删除文件失败: {str(e)}")
            return False
    
    def _delete_with_wait_and_retry(self, file_path):
        """等待一段时间后再次尝试删除（处理文件锁定情况）"""
        try:
            import time
            time.sleep(1)  # 等待1秒
            
            # 再次尝试删除
            try:
                os.remove(str(file_path))
                logger.info(f"等待后使用os.remove成功删除文件: {file_path}")
                return True
            except Exception:
                pass
            
            try:
                file_path.unlink(missing_ok=True)
                logger.info(f"等待后使用Path.unlink成功删除文件: {file_path}")
                return True
            except Exception:
                pass
            
            return False
        except Exception as e:
            logger.warning(f"等待后删除文件失败: {str(e)}")
            return False
    
    def should_delete_file(self, file_name, ai_output):
        """检查AI输出中是否提到删除特定文件"""
        file_name_lower = file_name.lower()
        ai_output_lower = ai_output.lower()
        
        # 检查文件名是否在AI输出中
        if file_name_lower not in ai_output_lower:
            return False
        
        # 检查是否有删除相关的关键词
        delete_keywords = ["remove", "delete", "删除", "清除", "移除", "去掉", "不需要"]
        for keyword in delete_keywords:
            # 检查关键词是否在文件名附近
            if keyword in ai_output_lower:
                # 简单检查关键词是否在文件名附近（前后200个字符）
                file_pos = ai_output_lower.find(file_name_lower)
                keyword_pos = ai_output_lower.find(keyword)
                if abs(file_pos - keyword_pos) < 200:
                    logger.info(f"AI输出中提到删除文件 {file_name}，关键词: {keyword}")
                    return True
        
        # 检查Git diff格式中的删除标记
        # 在Git diff中，`--- filename` 后跟 `+++ /dev/null` 表示文件被删除
        import re
        diff_pattern = f"---\\s+{re.escape(file_name_lower)}\\s*?\\n\\s*?\\+\\+\\+\\s+/dev/null"
        if re.search(diff_pattern, ai_output_lower):
            logger.info(f"在Git diff格式中检测到文件 {file_name} 被删除")
            return True
            
        # 检查是否在diff块中提到删除该文件
        diff_blocks = re.findall(r"```diff(.*?)```", ai_output_lower, re.DOTALL)
        for block in diff_blocks:
            if file_name_lower in block and "/dev/null" in block:
                logger.info(f"在diff块中检测到文件 {file_name} 被删除")
                return True
        
        return False
    
    def extract_files_to_delete(self, ai_output):
        """从AI输出中提取需要删除的文件列表"""
        files_to_delete = []
        ai_output_lower = ai_output.lower()
        
        # 从Git diff格式中提取需要删除的文件
        import re
        # 匹配 "--- filename" 后跟 "+++ /dev/null" 的模式
        diff_patterns = re.findall(r"---\s+(.*?)\s*?\n\s*?\+\+\+\s+/dev/null", ai_output_lower)
        for file_path in diff_patterns:
            if file_path and file_path != "/dev/null":
                files_to_delete.append(file_path)
                logger.info(f"从Git diff格式中提取到需要删除的文件: {file_path}")
        
        # 从文本描述中提取需要删除的文件
        delete_keywords = ["remove", "delete", "删除", "清除", "移除", "去掉"]
        for keyword in delete_keywords:
            # 查找包含删除关键词的句子
            keyword_positions = [m.start() for m in re.finditer(keyword, ai_output_lower)]
            for pos in keyword_positions:
                # 提取关键词前后的文本（大约200个字符）
                start = max(0, pos - 100)
                end = min(len(ai_output_lower), pos + 100)
                context = ai_output_lower[start:end]
                
                # 在上下文中查找可能的文件名（带扩展名的单词）
                file_candidates = re.findall(r'\b[\w\-\.]+\.\w+\b', context)
                for file in file_candidates:
                    if file not in files_to_delete and not file.startswith("/dev/null"):
                        files_to_delete.append(file)
                        logger.info(f"从文本描述中提取到需要删除的文件: {file}")
        
        return files_to_delete
        
    async def clarify_requirements(self, websocket: WebSocket, project_id: str, prompt_text: str) -> List[Any]:
        """与用户交互，澄清需求"""
        try:
            # 创建WebSocket回调处理器
            websocket_handler = WebSocketStreamingCallbackHandler(
                websocket=websocket,
                project_id=project_id,
                manager=manager
            )
            
            # 创建AI实例，添加WebSocket回调处理器
            ai = AI(
                model_name=self.model_name,
                temperature=self.temperature,
                azure_endpoint=self.azure_endpoint,
                streaming=True  # 确保启用流式输出
            )
            
            # 替换默认的回调处理器
            llm = ai.llm
            if hasattr(llm, 'callbacks') and llm.callbacks:
                llm.callbacks = [websocket_handler]
            else:
                setattr(llm, 'callbacks', [websocket_handler])
            
            # 通知前端AI已准备就绪
            await websocket.send_json({
                "type": "ai_ready",
                "model": self.model_name,
                "project_id": project_id
            })
            
            # 检测用户可能的语言偏好
            preferred_languages = self._detect_language_preference(prompt_text)
            
            # 创建系统提示
            system_prompt = """你是一个经验丰富的软件工程师。你的任务是帮助用户澄清他们的项目需求。
            请提出问题，以便更好地理解用户想要构建的内容。
            如果需求已经足够清晰，请回复"Nothing to clarify"。
            """
            
            # 创建项目目录
            project_path = Path(f"projects/{project_id}")
            project_path.mkdir(parents=True, exist_ok=True)
            
            # 初始化AI和内存
            memory = DiskMemory(project_path)
            prompt = Prompt(prompt_text)
            
            # 获取预设提示
            preprompts_holder = PrepromptsHolder(PREPROMPTS_PATH)
            preprompts = preprompts_holder.get_preprompts()
            
            # 开始澄清对话
            messages = [SystemMessage(content=preprompts["clarify"])]
            user_input = prompt.text
            
            # 发送初始状态
            await websocket.send_json({
                "type": "clarify_start",
                "message": "开始需求澄清对话，AI将询问一些问题以确保理解您的需求。"
            })
            
            # 如果有语言偏好，在第一次对话中明确指出
            if preferred_languages:
                language_preference = f"我注意到您可能希望使用 {', '.join(preferred_languages)} 来实现这个项目。我会在生成代码时考虑这一点。"
                await websocket.send_json({
                    "type": "clarify_info",
                    "message": language_preference
                })
            
            while True:
                try:
                    messages = ai.next(messages, user_input, step_name="clarify_requirements")
                    if not messages or len(messages) == 0:
                        logger.error("AI返回的消息为空")
                        await websocket.send_json({
                            "type": "error",
                            "message": "AI返回的消息为空"
                        })
                        return None
                        
                    msg = messages[-1].content.strip()
                    
                    # 检查是否完成澄清
                    if "nothing to clarify" in msg.lower():
                        await websocket.send_json({
                            "type": "clarify_complete",
                            "message": msg
                        })
                        break
                    
                    if msg.lower().startswith("no"):
                        await websocket.send_json({
                            "type": "clarify_complete",
                            "message": "没有需要澄清的内容。"
                        })
                        break
                    
                    # 发送AI的问题给客户端
                    await websocket.send_json({
                        "type": "clarify_question",
                        "message": msg
                    })
                    
                    # 等待客户端回答
                    try:
                        client_response = await websocket.receive_text()
                        response_data = json.loads(client_response)
                        user_input = response_data.get("content", "")
                        
                        # 检查用户是否跳过
                        if not user_input or user_input.lower() == "c":
                            await websocket.send_json({
                                "type": "clarify_info",
                                "message": "让AI做出自己的假设并继续。"
                            })
                            
                            messages = ai.next(
                                messages,
                                "Make your own assumptions and state them explicitly before starting",
                                step_name="clarify_requirements"
                            )
                            
                            if messages and len(messages) > 0:
                                # 发送AI的假设给客户端
                                await websocket.send_json({
                                    "type": "clarify_assumptions",
                                    "message": messages[-1].content.strip()
                                })
                                break
                            else:
                                logger.error("AI在生成假设时返回空消息")
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "AI在生成假设时返回空消息"
                                })
                                return None
                        
                        # 添加提示，询问是否还有其他不清楚的地方
                        user_input += """
                            \n\n
                            Is anything else unclear? If yes, ask another question.\n
                            Otherwise state: "Nothing to clarify"
                            """
                    except json.JSONDecodeError:
                        logger.error("无效的JSON格式")
                        await websocket.send_json({
                            "type": "error",
                            "message": "无效的JSON格式"
                        })
                        return None
                    except Exception as e:
                        logger.error(f"处理客户端响应时出错: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "message": f"处理客户端响应时出错: {str(e)}"
                        })
                        return None
                except Exception as e:
                    logger.error(f"AI对话过程中出错: {str(e)}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"AI对话过程中出错: {str(e)}"
                    })
                    return None
            
            # 返回澄清后的消息历史
            return messages
        except Exception as e:
            logger.error(f"需求澄清过程中出错: {str(e)}")
            await websocket.send_json({
                "type": "error",
                "message": f"需求澄清过程中出错: {str(e)}"
            })
            return None
        
    async def generate_code(self, project_id: str, prompt_text: str, websocket: WebSocket = None, use_clarify: bool = True) -> Dict[str, str]:
        """根据提示生成代码"""
        try:
            logger.info(f"开始生成代码: project_id={project_id}, use_clarify={use_clarify}")
            logger.debug(f"提示文本: {prompt_text[:100]}...")
            
            # 创建项目目录
            project_path = Path(f"projects/{project_id}")
            project_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"项目目录已创建/确认: {project_path}")
            
            # 初始化AI和内存
            try:
                # 创建WebSocket回调处理器
                websocket_handler = None
                if websocket:
                    logger.info("创建WebSocket回调处理器")
                    websocket_handler = WebSocketStreamingCallbackHandler(
                        websocket=websocket,
                        project_id=project_id,
                        manager=manager
                    )
                
                # 创建AI实例，添加WebSocket回调处理器
                logger.info(f"创建AI实例: model={self.model_name}, temperature={self.temperature}")
                ai = AI(
                    model_name=self.model_name,
                    temperature=self.temperature,
                    azure_endpoint=self.azure_endpoint,
                    streaming=True  # 确保启用流式输出
                )
                
                # 如果有WebSocket连接，替换默认的回调处理器
                if websocket_handler:
                    # 获取AI实例的llm对象
                    llm = ai.llm
                    logger.debug("替换AI实例的回调处理器")
                    # 替换回调处理器
                    if hasattr(llm, 'callbacks') and llm.callbacks:
                        llm.callbacks = [websocket_handler]
                    else:
                        # 如果没有callbacks属性，尝试设置
                        setattr(llm, 'callbacks', [websocket_handler])
                
                logger.info(f"AI实例已创建: model={self.model_name}, streaming={True}")
                
                # 通知前端AI已准备就绪
                if websocket:
                    await websocket.send_json({
                        "type": "ai_ready",
                        "model": self.model_name,
                        "project_id": project_id
                    })
                    logger.debug("已通知前端AI准备就绪")
            except Exception as e:
                logger.error(f"创建AI实例时出错: {str(e)}", exc_info=True)
                return {"error": f"创建AI实例时出错: {str(e)}"}
            
            logger.info("初始化内存和提示")
            memory = DiskMemory(project_path)
            prompt = Prompt(prompt_text)
            
            # 获取预设提示
            try:
                logger.debug(f"加载预设提示: {PREPROMPTS_PATH}")
                preprompts_holder = PrepromptsHolder(PREPROMPTS_PATH)
                logger.info(f"已加载预设提示: {PREPROMPTS_PATH}")
            except Exception as e:
                logger.error(f"加载预设提示时出错: {str(e)}", exc_info=True)
                return {"error": f"加载预设提示时出错: {str(e)}"}
            
            # 检查项目目录是否已存在文件
            try:
                logger.info("扫描项目目录查找现有文件")
                existing_files = list(project_path.glob("**/*"))
                existing_files = [f for f in existing_files if f.is_file()]
                logger.info(f"找到 {len(existing_files)} 个现有文件")
                for f in existing_files:
                    logger.debug(f"现有文件: {f}")
            except Exception as e:
                logger.error(f"扫描项目文件时出错: {str(e)}", exc_info=True)
                return {"error": f"扫描项目文件时出错: {str(e)}"}
            
            # 如果启用了澄清模式且提供了websocket，先进行需求澄清
            if use_clarify and websocket:
                logger.info("开始需求澄清过程")
                await websocket.send_json({
                    "type": "status",
                    "status": "clarifying",
                    "message": "正在澄清需求..."
                })
                
                clarify_messages = await self.clarify_requirements(websocket, project_id, prompt_text)
                if clarify_messages is None:
                    logger.error("需求澄清过程失败")
                    return {"error": "需求澄清过程失败"}
                
                logger.info("需求澄清完成，更新提示")
                # 更新提示，包含澄清的内容
                clarified_prompt_text = prompt_text + "\n\n--- 澄清的需求 ---\n"
                for msg in clarify_messages[1:]:  # 跳过系统消息
                    if msg.type == "human":
                        clarified_prompt_text += f"\n用户: {msg.content}"
                    else:
                        clarified_prompt_text += f"\nAI: {msg.content}"
                prompt = Prompt(clarified_prompt_text)
                logger.debug(f"更新后的提示文本: {clarified_prompt_text[:100]}...")
                
                await websocket.send_json({
                    "type": "status",
                    "status": "processing",
                    "message": "需求澄清完成，正在生成代码..."
                })
            
            try:
                if existing_files:
                    logger.info("处理现有项目的代码改进")
                    # 加载现有文件到FilesDict
                    files_dict = {}
                    files_dict_before = {}
                    for file_path in existing_files:
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                relative_path = str(file_path.relative_to(project_path)).replace("\\", "/")
                                content = f.read()
                                files_dict[relative_path] = content
                                files_dict_before[relative_path] = content
                                logger.debug(f"已加载文件: {relative_path}")
                        except Exception as e:
                            logger.error(f"读取文件时出错 {file_path}: {str(e)}")
                            continue
                    
                    # 确保files_dict是有效的FilesDict对象
                    if not files_dict:
                        logger.info("创建空的FilesDict")
                        files_dict = FilesDict({})
                    elif not isinstance(files_dict, FilesDict):
                        logger.info("将dict转换为FilesDict")
                        files_dict = FilesDict(files_dict)
                    
                    # 发送状态更新
                    if websocket:
                        await websocket.send_json({
                            "type": "status",
                            "status": "improving",
                            "message": "正在改进现有代码..."
                        })
                    
                    # 执行改进
                    logger.info("开始执行代码改进")
                    files_dict = improve_fn(ai, prompt, files_dict, memory, preprompts_holder)
                    if not files_dict:
                        logger.error("代码改进失败: improve_fn返回None")
                        return {"error": "代码改进失败"}
                    logger.info(f"代码改进成功: {len(files_dict)} 个文件")
                else:
                    logger.info("开始生成新项目代码")
                    # 新项目，初始化空的files_dict
                    files_dict = FilesDict({})
                    files_dict_before = {}
                    
                    # 发送状态更新
                    if websocket:
                        await websocket.send_json({
                            "type": "status",
                            "status": "generating",
                            "message": "正在生成新代码..."
                        })
                    
                    # 执行代码生成
                    logger.info("开始执行代码生成")
                    files_dict = gen_code(ai, prompt, memory, preprompts_holder)
                    if not files_dict:
                        logger.error("代码生成失败: gen_code返回None")
                        return {"error": "代码生成失败"}
                    logger.info(f"代码生成成功: {len(files_dict)} 个文件")
                
                # 处理文件变更并发送WebSocket通知
                logger.info("开始处理文件变更")
                added_files, modified_files, deleted_files = await self._process_file_changes(
                    project_path, files_dict_before, files_dict, websocket
                )
                logger.info(f"文件变更处理完成: 新增={len(added_files)}, 修改={len(modified_files)}, 删除={len(deleted_files)}")
                
                # 发送完成通知
                if websocket:
                    await websocket.send_json({
                        "type": "status",
                        "status": "completed",
                        "message": "代码生成完成",
                        "stats": {
                            "added": len(added_files),
                            "modified": len(modified_files),
                            "deleted": len(deleted_files),
                            "total": len(files_dict)
                        }
                    })
                
                # 返回结果
                return {
                    "success": True,
                    "message": "代码生成成功",
                    "files": list(files_dict.keys()),
                    "stats": {
                        "added": len(added_files),
                        "modified": len(modified_files),
                        "deleted": len(deleted_files),
                        "total": len(files_dict)
                    }
                }
            except Exception as e:
                logger.error(f"代码生成过程中出错: {str(e)}", exc_info=True)
                if websocket:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"代码生成过程中出错: {str(e)}"
                    })
                return {"error": f"代码生成过程中出错: {str(e)}"}
        
        except Exception as e:
            logger.error(f"生成代码时出错: {str(e)}", exc_info=True)
            if websocket:
                await websocket.send_json({
                    "type": "error",
                    "message": f"生成代码时出错: {str(e)}"
                })
            return {"error": str(e)}

    def _detect_language_preference(self, prompt_text: str) -> List[str]:
        """检测用户可能的语言偏好"""
        preferred_languages = []
        
        # 检查常见的编程语言关键词
        language_keywords = {
            "HTML": ["html", "网页", "前端"],
            "CSS": ["css", "样式", "前端"],
            "JavaScript": ["javascript", "js", "前端", "nodejs", "node.js", "react", "vue", "angular"],
            "Python": ["python", "django", "flask", "fastapi", "pytorch", "tensorflow"],
            "Java": ["java", "spring", "android"],
            "C++": ["c++", "cpp"],
            "C#": ["c#", "csharp", ".net", "dotnet"],
            "Go": ["golang", "go语言"],
            "Rust": ["rust", "cargo"],
            "PHP": ["php", "laravel", "wordpress"],
            "Ruby": ["ruby", "rails"],
            "Swift": ["swift", "ios"],
            "Kotlin": ["kotlin", "android"],
            "TypeScript": ["typescript", "ts"]
        }
        
        prompt_lower = prompt_text.lower()
        
        # 检查每种语言的关键词
        for language, keywords in language_keywords.items():
            for keyword in keywords:
                if keyword in prompt_lower:
                    if language not in preferred_languages:
                        preferred_languages.append(language)
                    break
        
        # 特殊处理：如果提到"java"但不是"javascript"的上下文
        if "java" in prompt_lower and "script" not in prompt_lower and "js" not in prompt_lower:
            if "Java" not in preferred_languages:
                preferred_languages.append("Java")
        
        return preferred_languages
        
    async def _process_file_changes(self, project_path: Path, files_dict_before: Dict[str, str], files_dict: Dict[str, str], websocket: WebSocket = None):
        """处理文件变更并发送WebSocket通知"""
        added_files = []
        modified_files = []
        deleted_files = []
        
        # 检查新增和修改的文件
        for path, content in files_dict.items():
            # 跳过处理 /dev/null 路径，这是 Git 差异格式的一部分，不是真实文件
            if "/dev/null" in path or "\\dev\\null" in path:
                logger.warning(f"跳过处理 Git 差异格式路径: {path}")
                continue
                
            if path not in files_dict_before:
                added_files.append(path)
                # 发送文件添加通知
                if websocket:
                    await websocket.send_json({
                        "type": "file_added",
                        "file_path": path,
                        "content": content
                    })
            elif files_dict_before[path] != content:
                modified_files.append(path)
                # 发送文件修改通知
                if websocket:
                    # 计算差异
                    old_content = files_dict_before[path]
                    diff = self._generate_diff(old_content, content, path)
                    await websocket.send_json({
                        "type": "file_modified",
                        "file_path": path,
                        "diff": diff,
                        "content": content
                    })
        
        # 检查并删除不再需要的文件
        for path in files_dict_before:
            if path not in files_dict:
                # 直接尝试删除文件
                full_path = project_path / path
                if full_path.exists():
                    try:
                        logger.info(f"尝试删除文件: {full_path}")
                        os.remove(str(full_path))
                        logger.info(f"成功删除文件: {full_path}")
                        deleted_files.append(path)
                        # 发送文件删除通知
                        if websocket:
                            await websocket.send_json({
                                "type": "file_deleted",
                                "file_path": path
                            })
                    except Exception as e:
                        logger.warning(f"使用os.remove删除失败: {str(e)}")
                        try:
                            full_path.unlink(missing_ok=True)
                            logger.info(f"使用Path.unlink成功删除文件: {full_path}")
                            deleted_files.append(path)
                            # 发送文件删除通知
                            if websocket:
                                await websocket.send_json({
                                    "type": "file_deleted",
                                    "file_path": path
                                })
                        except Exception as e2:
                            logger.error(f"删除文件失败: {str(e2)}")
        
        # 保存新的和修改的文件
        for file_path, content in files_dict.items():
            try:
                full_path = project_path / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)
                if file_path in added_files:
                    logger.info(f"已添加新文件: {full_path}")
                elif file_path in modified_files:
                    logger.info(f"已更新文件: {full_path}")
            except Exception as e:
                logger.error(f"保存文件时出错 {file_path}: {str(e)}")
                # 发送错误通知
                if websocket:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"保存文件时出错 {file_path}: {str(e)}"
                    })
                continue
        
        return added_files, modified_files, deleted_files
    
    def _generate_diff(self, old_content: str, new_content: str, file_path: str) -> str:
        """生成文件差异"""
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f'a/{file_path}',
            tofile=f'b/{file_path}',
            lineterm=''
        )
        
        return '\n'.join(diff)

# 创建代码生成器实例
code_generator = CodeGenerator()

# 自定义WebSocket回调处理器
class WebSocketStreamingCallbackHandler(BaseCallbackHandler):
    """
    自定义回调处理器，用于捕获AI生成的流式输出并通过WebSocket发送给前端
    """
    
    def __init__(self, websocket: WebSocket, project_id: str, manager: 'ConnectionManager'):
        """初始化回调处理器"""
        self.websocket = websocket
        self.project_id = project_id
        self.manager = manager
        self.current_token_buffer = ""
        self.current_file_buffer = {}
        self.current_file = None
        self.in_code_block = False
        self.code_language = None
        self.file_content = ""
        self.file_path = None
        self.step_count = 0
        self.total_steps = 4  # 假设总共4个主要步骤
        
    async def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs):
        """LLM开始时的处理"""
        await self.manager.send_personal_message({
            "type": "step",
            "step": "开始生成代码",
            "message": "AI模型已启动，开始处理您的请求...",
            "status": "running"
        }, self.project_id)
        
        # 重置进度
        await self.manager.send_personal_message({
            "type": "progress",
            "progress": 0
        }, self.project_id)

    async def on_llm_new_token(self, token: str, **kwargs):
        """处理新的token"""
        # 将token添加到缓冲区
        self.current_token_buffer += token
        
        # 发送流式消息
        await self.manager.send_personal_message({
            "type": "stream",
            "content": token,
            "done": False
        }, self.project_id)
        
        # 检测代码块的开始和结束
        if "```" in self.current_token_buffer:
            # 处理代码块
            await self._process_code_blocks()
            
        # 检测文件路径模式
        file_path_match = re.search(r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)[:：]', self.current_token_buffer)
        if file_path_match and not self.in_code_block:
            potential_file_path = file_path_match.group(1)
            if self._is_valid_file_path(potential_file_path):
                self.file_path = potential_file_path
                self.file_content = ""
                # 发送文件操作消息
                await self.manager.send_personal_message({
                    "operation": "file",
                    "action": "create",
                    "path": self.file_path,
                    "status": "running"
                }, self.project_id)
        
        # 更新进度
        self.step_count += 1
        progress = min(95, int((self.step_count / 100) * 100))  # 保留最后5%给完成步骤
        await self.manager.send_personal_message({
            "type": "progress",
            "progress": progress
        }, self.project_id)

    async def on_llm_end(self, response, **kwargs):
        """LLM响应结束时的处理"""
        # 清空缓冲区
        self.current_token_buffer = ""
        
        # 发送流式消息结束标记
        await self.manager.send_personal_message({
            "type": "stream",
            "content": "",
            "done": True
        }, self.project_id)
        
        # 发送所有文件的最终版本
        for file_path, content in self.current_file_buffer.items():
            await self.manager.send_personal_message({
                "operation": "file",
                "action": "update",
                "path": file_path,
                "content": content,
                "status": "completed"
            }, self.project_id)
        
        # 发送完成状态
        await self.manager.send_personal_message({
            "type": "step",
            "step": "代码生成完成",
            "message": "所有文件已生成完毕",
            "status": "completed"
        }, self.project_id)
        
        # 发送100%进度
        await self.manager.send_personal_message({
            "progress": 100
        }, self.project_id)
        
        # 清空文件缓冲区
        self.current_file_buffer = {}

    async def on_llm_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs):
        """处理LLM错误"""
        await self.manager.send_personal_message({
            "type": "error",
            "message": str(error)
        }, self.project_id)

    async def _process_code_blocks(self):
        """处理代码块"""
        # 使用正则表达式匹配代码块
        pattern = r"```(\w*)\n(.*?)```"
        matches = re.findall(pattern, self.current_token_buffer, re.DOTALL)
        
        for lang, code in matches:
            # 清除已处理的代码块
            self.current_token_buffer = self.current_token_buffer.replace(f"```{lang}\n{code}```", "", 1)
            
            # 如果有文件路径，将代码与文件关联
            if self.file_path:
                # 发送文件更新消息
                await self.manager.send_personal_message({
                    "operation": "file",
                    "action": "update",
                    "path": self.file_path,
                    "content": code,
                    "status": "running"
                }, self.project_id)
                
                # 如果有之前的文件内容，计算差异
                if self.file_path in self.current_file_buffer:
                    old_content = self.current_file_buffer[self.file_path]
                    diff = self._generate_diff(old_content, code, self.file_path)
                    
                    # 发送文件变更消息
                    await self.manager.send_personal_message({
                        "operation": "file",
                        "action": "update",
                        "path": self.file_path,
                        "content": code,
                        "diff": diff,
                        "status": "running"
                    }, self.project_id)
                
                # 更新缓冲区
                self.current_file_buffer[self.file_path] = code
                self.file_path = None  # 重置文件路径，等待下一个文件
            else:
                # 没有文件路径，发送普通代码块
                await self.manager.send_personal_message({
                    "type": "step",
                    "step": "生成代码片段",
                    "content": code,
                    "language": lang,
                    "status": "running"
                }, self.project_id)
    
    def _is_valid_file_path(self, path: str) -> bool:
        """检查是否是有效的文件路径"""
        # 简单检查是否包含有效的文件扩展名
        valid_extensions = ['.py', '.js', '.html', '.css', '.txt', '.md', '.json', '.xml', 
                           '.yml', '.yaml', '.ini', '.cfg', '.conf', '.sh', '.bat', '.ps1', 
                           '.java', '.c', '.cpp', '.h', '.cs', '.go', '.rs', '.ts', '.jsx', 
                           '.tsx', '.vue', '.php', '.rb', '.pl', '.swift', '.kt', '.scala']
        
        return any(path.endswith(ext) for ext in valid_extensions)
    
    def _generate_diff(self, old_content: str, new_content: str, file_path: str) -> str:
        """生成文件差异"""
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f'a/{file_path}',
            tofile=f'b/{file_path}',
            lineterm=''
        )
        
        return '\n'.join(diff)

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
                    use_clarify = message.get("use_clarify", True)  # 默认使用澄清模式
                    
                    if prompt_text:
                        # 发送处理状态
                        if project_exists:
                            if use_clarify:
                                await websocket.send_json({
                                    "type": "status",
                                    "status": "clarifying",
                                    "message": "正在启动需求澄清对话..."
                                })
                            else:
                                await websocket.send_json({
                                    "type": "status",
                                    "status": "processing",
                                    "message": "正在改进现有项目代码，请稍候..."
                                })
                        else:
                            if use_clarify:
                                await websocket.send_json({
                                    "type": "status",
                                    "status": "clarifying",
                                    "message": "正在启动需求澄清对话..."
                                })
                            else:
                                await websocket.send_json({
                                    "type": "status",
                                    "status": "processing",
                                    "message": "正在生成新项目代码，请稍候..."
                                })
                        
                        # 异步生成代码，传入websocket以支持交互式澄清
                        files_dict = await code_generator.generate_code(
                            project_id, 
                            prompt_text, 
                            websocket=websocket,
                            use_clarify=use_clarify
                        )
                        
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
                elif message_type == "clarify_response":
                    # 这个消息类型由客户端在澄清对话中发送，在clarify_requirements方法中处理
                    # 这里不需要额外处理
                    pass
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
