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
        
    async def clarify_requirements(self, websocket: WebSocket, project_id: str, prompt_text: str):
        """与用户进行需求澄清对话"""
        try:
            # 创建项目目录
            project_path = Path(f"projects/{project_id}")
            project_path.mkdir(parents=True, exist_ok=True)
            
            # 检查是否有语言偏好
            preferred_languages = []
            if "html" in prompt_text.lower() or "css" in prompt_text.lower() or "javascript" in prompt_text.lower():
                preferred_languages = ["HTML", "CSS", "JavaScript"]
            elif "java" in prompt_text.lower() and "script" not in prompt_text.lower():
                preferred_languages = ["Java"]
            elif "c++" in prompt_text.lower() or "cpp" in prompt_text.lower():
                preferred_languages = ["C++"]
            elif "c#" in prompt_text.lower() or "csharp" in prompt_text.lower():
                preferred_languages = ["C#"]
            
            # 初始化AI和内存
            ai = AI(
                model_name=self.model_name,
                temperature=self.temperature,
                azure_endpoint=self.azure_endpoint
            )
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
                messages = ai.next(messages, user_input, step_name="clarify_requirements")
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
                client_response = await websocket.receive_text()
                try:
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
                        
                        # 发送AI的假设给客户端
                        await websocket.send_json({
                            "type": "clarify_assumptions",
                            "message": messages[-1].content.strip()
                        })
                        break
                    
                    # 添加提示，询问是否还有其他不清楚的地方
                    user_input += """
                        \n\n
                        Is anything else unclear? If yes, ask another question.\n
                        Otherwise state: "Nothing to clarify"
                        """
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "无效的JSON格式"
                    })
                    user_input = "Continue with what you have."
            
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
            prompt = Prompt(prompt_text)
            
            # 获取预设提示
            try:
                preprompts_holder = PrepromptsHolder(PREPROMPTS_PATH)
                logger.info(f"已加载预设提示: {PREPROMPTS_PATH}")
            except Exception as e:
                logger.error(f"加载预设提示时出错: {str(e)}")
                return {"error": f"加载预设提示时出错: {str(e)}"}
            
            # 检查项目目录是否已存在文件，决定是新建项目还是改进现有项目
            try:
                existing_files = list(project_path.glob("**/*"))
                existing_files = [f for f in existing_files if f.is_file()]
            except Exception as e:
                logger.error(f"扫描项目文件时出错: {str(e)}")
                return {"error": f"扫描项目文件时出错: {str(e)}"}
            
            if existing_files:
                # 项目已存在，使用improve_fn改进现有项目
                logger.info(f"项目 {project_id} 已存在，使用improve_fn改进现有项目")
                
                # 如果启用了澄清模式且提供了websocket，先进行需求澄清
                if use_clarify and websocket:
                    clarify_messages = await self.clarify_requirements(websocket, project_id, prompt_text)
                    if clarify_messages:
                        # 更新提示，包含澄清的内容
                        clarified_prompt_text = prompt_text + "\n\n--- 澄清的需求 ---\n"
                        for msg in clarify_messages[1:]:  # 跳过系统消息
                            if msg.type == "human":
                                clarified_prompt_text += f"\n用户: {msg.content}"
                            else:
                                clarified_prompt_text += f"\nAI: {msg.content}"
                        prompt = Prompt(clarified_prompt_text)
                        
                        await websocket.send_json({
                            "type": "status",
                            "status": "processing",
                            "message": "需求澄清完成，正在改进现有项目代码..."
                        })
                
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
                    except UnicodeDecodeError:
                        logger.warning(f"跳过二进制文件: {file_path}")
                    except Exception as e:
                        logger.error(f"读取文件时出错 {file_path}: {str(e)}")
                        continue
                
                files_dict = FilesDict(files_dict)
                files_dict_before = FilesDict(files_dict_before)
                
                # 使用improve_fn改进现有项目
                try:
                    # 如果提供了websocket，发送改进进度更新
                    if websocket:
                        await websocket.send_json({
                            "type": "status",
                            "status": "improving",
                            "message": "正在分析现有代码并生成改进方案..."
                        })
                    
                    # 执行改进
                    files_dict = improve_fn(ai, prompt, files_dict, memory, preprompts_holder)
                    logger.info(f"代码改进成功: {len(files_dict)} 个文件")
                    
                    # 处理文件变更
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
                        elif files_dict_before[path] != content:
                            modified_files.append(path)
                    
                    # 直接删除不再需要的文件
                    for path in files_dict_before:
                        if path not in files_dict:
                            full_path = project_path / path
                            logger.info(f"检测到需要删除的文件: {full_path}")
                            
                            try:
                                # 如果文件存在，直接删除
                                if full_path.exists():
                                    # 先尝试清空文件内容
                                    try:
                                        with open(str(full_path), 'w') as f:
                                            f.write('')
                                        logger.info(f"已清空文件内容: {full_path}")
                                    except Exception as e:
                                        logger.warning(f"清空文件内容失败: {str(e)}")
                                    
                                    # 然后删除文件
                                    import os
                                    os.remove(str(full_path))
                                    logger.info(f"成功删除文件: {full_path}")
                                    deleted_files.append(path)
                                else:
                                    logger.warning(f"要删除的文件不存在: {full_path}")
                                    deleted_files.append(path)  # 文件不存在也视为删除成功
                            except Exception as e:
                                logger.error(f"删除文件失败: {str(e)}")
                    
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
                            continue
                    
                    # 如果提供了websocket，发送差异报告
                    if websocket:
                        await websocket.send_json({
                            "type": "diff_report",
                            "added": added_files,
                            "modified": modified_files,
                            "deleted": deleted_files
                        })
                    
                except Exception as e:
                    logger.error(f"改进代码时出错: {str(e)}")
                    return {"error": f"改进代码时出错: {str(e)}"}
            else:
                # 项目不存在或为空，使用gen_code生成新项目
                try:
                    if use_clarify and websocket:
                        # 使用澄清模式
                        clarify_messages = await self.clarify_requirements(websocket, project_id, prompt_text)
                        if not clarify_messages:
                            return {"error": "需求澄清过程失败"}
                        
                        # 更新提示，包含澄清的内容
                        clarified_prompt_text = prompt_text + "\n\n--- 澄清的需求 ---\n"
                        for msg in clarify_messages[1:]:  # 跳过系统消息
                            if msg.type == "human":
                                clarified_prompt_text += f"\n用户: {msg.content}"
                            else:
                                clarified_prompt_text += f"\nAI: {msg.content}"
                        prompt = Prompt(clarified_prompt_text)
                        
                        await websocket.send_json({
                            "type": "status",
                            "status": "generating",
                            "message": "需求澄清完成，正在生成代码..."
                        })
                        
                        # 使用标准生成模式，但带有澄清后的提示
                        files_dict = gen_code(ai, prompt, memory, preprompts_holder)
                    else:
                        # 使用标准生成模式
                        files_dict = gen_code(ai, prompt, memory, preprompts_holder)
                    
                    # 保存生成的代码
                    for file_path, content in files_dict.items():
                        try:
                            full_path = project_path / file_path
                            full_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(full_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            logger.info(f"已生成文件: {full_path}")
                        except Exception as e:
                            logger.error(f"保存文件时出错 {file_path}: {str(e)}")
                            continue
                    
                    logger.info(f"代码生成成功: {len(files_dict)} 个文件")
                except Exception as e:
                    logger.error(f"生成代码时出错: {str(e)}")
                    return {"error": f"生成代码时出错: {str(e)}"}
            
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
