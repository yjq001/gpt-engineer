import os
import sys
import asyncio
import uuid
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import json
import shutil
import dotenv
import re
import time

# 检查必要的依赖
try:
    import dotenv
except ImportError:
    print("错误: 缺少python-dotenv包。请运行 'pip install python-dotenv'")
    sys.exit(1)

# 加载环境变量
dotenv.load_dotenv()

# 检查API密钥
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "your_openai_api_key_here":
    print("警告: 未设置有效的OpenAI API密钥。请在.env文件中设置OPENAI_API_KEY。")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# 添加GPT-Engineer到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gpt_engineer.core.ai import AI
from gpt_engineer.core.default.disk_memory import DiskMemory
from gpt_engineer.core.default.steps import gen_code, gen_entrypoint
from gpt_engineer.core.preprompts_holder import PrepromptsHolder
from gpt_engineer.core.prompt import Prompt
from gpt_engineer.core.default.paths import PREPROMPTS_PATH

# 创建FastAPI应用
app = FastAPI(title="GPT-Engineer Web Interface")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境中应限制为您的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket连接管理
class ConnectionManager:
    def __init__(self):
        # 项目ID -> 连接列表
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, project_id: str, websocket: WebSocket):
        """添加新的WebSocket连接"""
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        print(f"WebSocket连接已添加: {project_id}, 当前连接数: {len(self.active_connections[project_id])}")
    
    def disconnect(self, project_id: str, websocket: WebSocket):
        """移除WebSocket连接"""
        if project_id in self.active_connections:
            if websocket in self.active_connections[project_id]:
                self.active_connections[project_id].remove(websocket)
                print(f"WebSocket连接已移除: {project_id}, 剩余连接数: {len(self.active_connections[project_id])}")
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
                print(f"项目的所有WebSocket连接已移除: {project_id}")
    
    async def send_message(self, project_id: str, message: dict):
        """向项目的所有连接发送消息"""
        if project_id in self.active_connections:
            print(f"准备发送消息: {project_id}, 类型: {message.get('type')}, 连接数: {len(self.active_connections[project_id])}")
            disconnected_websockets = []
            for connection in self.active_connections[project_id]:
                try:
                    await connection.send_json(message)
                    print(f"消息已发送: {project_id}, 类型: {message.get('type')}")
                except Exception as e:
                    print(f"发送消息失败: {project_id}, 错误: {str(e)}")
                    # 如果发送失败，标记连接为断开
                    disconnected_websockets.append(connection)
            
            # 移除断开的连接
            for websocket in disconnected_websockets:
                self.disconnect(project_id, websocket)
        else:
            print(f"没有活跃的连接来发送消息: {project_id}, 类型: {message.get('type')}")

# 创建连接管理器实例
manager = ConnectionManager()

# 项目目录
WEB_PROJECTS_DIR = Path("web_projects")
WEB_PROJECTS_DIR.mkdir(exist_ok=True)

# 请求模型
class PromptRequest(BaseModel):
    prompt: str
    model: Optional[str] = "gpt-4"
    temperature: Optional[float] = 0.1

# 自定义AI类，添加WebSocket回调
class WebSocketAI(AI):
    def __init__(self, project_id: str, **kwargs):
        # 确保streaming=True
        kwargs['streaming'] = True
        super().__init__(**kwargs)
        self.project_id = project_id
        self.current_step = None
        self.current_content = ""
        self.is_code_block = False
        self.current_file = None
        self.code_buffer = ""
        print(f"WebSocketAI初始化: {project_id}, 模型: {kwargs.get('model_name')}")
    
    def next(self, messages, prompt=None, *, step_name=None):
        """重写next方法，添加WebSocket回调"""
        print(f"WebSocketAI.next调用: {self.project_id}, 步骤: {step_name}")
        
        # 重置状态
        self.current_step = step_name
        self.current_content = ""
        self.is_code_block = False
        self.current_file = None
        self.code_buffer = ""
        
        # 发送步骤开始消息
        asyncio.create_task(
            manager.send_message(
                self.project_id, 
                {
                    "type": "step_start",
                    "step": step_name
                }
            )
        )
        
        # 使用流式模式调用API
        result = super().next(messages, prompt, step_name=step_name)
        
        # 获取最后一条消息
        last_message = result[-1].content
        
        # 打印大模型的完整响应
        print(f"\n{'='*50}")
        print(f"大模型响应 (步骤: {step_name}):")
        print(f"{'='*50}")
        print(last_message)
        print(f"{'='*50}\n")
        
        print(f"WebSocketAI生成消息: {self.project_id}, 步骤: {step_name}, 长度: {len(last_message)}")
        
        # 发送步骤完成消息
        asyncio.create_task(
            manager.send_message(
                self.project_id, 
                {
                    "type": "step_complete",
                    "step": step_name,
                    "content": last_message
                }
            )
        )
        
        return result
    
    def on_token(self, token: str):
        """处理每个生成的token"""
        if not token:
            return
            
        # 发送token更新
        asyncio.create_task(
            manager.send_message(
                self.project_id, 
                {
                    "type": "token",
                    "step": self.current_step,
                    "token": token,
                    "is_code": self.is_code_block
                }
            )
        )
        
        # 累加到当前内容
        self.current_content += token
        
        # 检测代码块开始
        if not self.is_code_block and "```" in token:
            self.is_code_block = True
            self.code_buffer = ""
            
            # 尝试从后续内容中提取文件名
            file_match = re.search(r"```(\w+)\s+([a-zA-Z0-9_.-]+\.\w+)", self.current_content)
            if file_match:
                self.current_file = file_match.group(2)
                print(f"检测到代码块开始，可能的文件名: {self.current_file}")
        
        # 检测代码块结束
        elif self.is_code_block and "```" in token:
            self.is_code_block = False
            
            # 如果有文件名，发送文件更新
            if self.current_file:
                print(f"代码块结束，更新文件: {self.current_file}, 大小: {len(self.code_buffer)}")
                asyncio.create_task(
                    manager.send_message(
                        self.project_id, 
                        {
                            "type": "file_update",
                            "file": self.current_file,
                            "content": self.code_buffer
                        }
                    )
                )
                self.current_file = None
            self.code_buffer = ""
        
        # 在代码块内，累加到代码缓冲区
        elif self.is_code_block:
            self.code_buffer += token

# 路由：创建新项目
@app.post("/api/projects")
async def create_project(request: PromptRequest, background_tasks: BackgroundTasks):
    """创建新项目并开始代码生成"""
    project_id = str(uuid.uuid4())
    project_dir = WEB_PROJECTS_DIR / project_id
    project_dir.mkdir(exist_ok=True)
    
    # 保存提示到文件
    with open(project_dir / "prompt", "w", encoding="utf-8") as f:
        f.write(request.prompt)
    
    # 在后台任务中运行代码生成
    background_tasks.add_task(
        generate_code_background, 
        project_id=project_id, 
        prompt=request.prompt,
        model=request.model,
        temperature=request.temperature
    )
    
    return {"project_id": project_id}

# 后台任务：生成代码
async def generate_code_background(project_id: str, prompt: str, model: str, temperature: float):
    """在后台运行代码生成过程"""
    project_dir = WEB_PROJECTS_DIR / project_id
    print(f"开始生成代码: {project_id}, 模型: {model}, 温度: {temperature}")
    print(f"项目目录: {project_dir}")
    print(f"用户提示: {prompt}")
    
    try:
        # 检查API密钥
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            raise ValueError("未设置有效的OpenAI API密钥。请在.env文件中设置OPENAI_API_KEY。")
        
        # 初始化内存接口
        memory = DiskMemory(project_dir)
        
        # 创建AI实例
        print(f"创建AI实例: {project_id}")
        ai = WebSocketAI(
            project_id=project_id,
            model_name=model,
            temperature=temperature,
            streaming=True  # 确保使用流式输出
        )
        
        # 初始化预设提示
        print(f"初始化预设提示: {project_id}")
        preprompts_holder = PrepromptsHolder(PREPROMPTS_PATH)
        
        # 创建提示对象
        prompt_obj = Prompt(prompt)
        
        # 发送开始消息
        print(f"发送开始消息: {project_id}")
        await manager.send_message(
            project_id, 
            {
                "type": "status",
                "status": "processing",
                "message": "开始生成代码..."
            }
        )
        
        # 生成代码
        print(f"开始生成代码: {project_id}")
        try:
            print(f"调用gen_code步骤: {project_id}")
            files_dict = gen_code(ai, prompt_obj, memory, preprompts_holder)
            print(f"代码生成完成: {project_id}, 文件数: {len(files_dict)}")
            print(f"生成的文件列表: {', '.join(files_dict.keys())}")
        except Exception as e:
            print(f"代码生成失败: {project_id}, 错误: {str(e)}")
            raise e
        
        # 生成入口点
        print(f"开始生成入口点: {project_id}")
        try:
            print(f"调用gen_entrypoint步骤: {project_id}")
            entrypoint_files = gen_entrypoint(ai, prompt_obj, files_dict, memory, preprompts_holder)
            print(f"入口点生成完成: {project_id}, 文件数: {len(entrypoint_files)}")
            if entrypoint_files:
                print(f"生成的入口点文件: {', '.join(entrypoint_files.keys())}")
        except Exception as e:
            print(f"入口点生成失败: {project_id}, 错误: {str(e)}")
            raise e
        
        # 合并文件字典
        files_dict.update(entrypoint_files)
        
        # 创建workspace目录
        workspace_dir = project_dir / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        
        # 写入文件
        print(f"开始写入文件: {project_id}, 文件数: {len(files_dict)}")
        for file_path, content in files_dict.items():
            # 创建目录结构
            full_path = workspace_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件内容
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            print(f"写入文件: {file_path}, 大小: {len(content)} 字节")
        
        # 发送完成消息
        print(f"发送完成消息: {project_id}")
        await manager.send_message(
            project_id, 
            {
                "type": "complete",
                "files": [{"name": name, "content": content} for name, content in files_dict.items()]
            }
        )
        
        # 发送状态更新
        await manager.send_message(
            project_id, 
            {
                "type": "status",
                "status": "completed",
                "message": "代码生成完成！"
            }
        )
        
    except Exception as e:
        print(f"代码生成过程出错: {project_id}, 错误: {str(e)}")
        print(f"错误详情: {type(e).__name__}")
        import traceback
        print(traceback.format_exc())
        
        # 发送错误消息
        await manager.send_message(
            project_id, 
            {
                "type": "error",
                "message": str(e)
            }
        )
        
        # 发送状态更新
        await manager.send_message(
            project_id, 
            {
                "type": "status",
                "status": "failed",
                "message": f"代码生成失败: {str(e)}"
            }
        )

# WebSocket路由
@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """WebSocket连接处理"""
    print(f"新的WebSocket连接: {project_id}")
    await manager.connect(project_id, websocket)
    
    try:
        # 发送初始状态消息
        print(f"发送初始状态消息: {project_id}")
        await websocket.send_json({
            "type": "status",
            "status": "connected",
            "message": "WebSocket连接已建立"
        })
        
        # 检查API密钥
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            print(f"WebSocket连接 {project_id} 的API密钥无效")
            await websocket.send_json({
                "type": "error",
                "message": "未设置有效的OpenAI API密钥。请在.env文件中设置OPENAI_API_KEY。"
            })
            await websocket.send_json({
                "type": "status",
                "status": "failed",
                "message": "代码生成失败: API密钥无效"
            })
        
        # 检查项目目录是否存在
        project_dir = WEB_PROJECTS_DIR / project_id
        print(f"检查项目目录: {project_dir}, 存在: {project_dir.exists()}")
        if project_dir.exists():
            # 读取prompt文件
            prompt_file = project_dir / "prompt"
            if prompt_file.exists():
                with open(prompt_file, "r", encoding="utf-8") as f:
                    prompt = f.read()
                
                print(f"发送prompt: {project_id}, {prompt[:50]}...")
                await websocket.send_json({
                    "type": "prompt",
                    "prompt": prompt
                })
            
            # 检查workspace目录
            workspace_dir = project_dir / "workspace"
            print(f"检查workspace目录: {workspace_dir}, 存在: {workspace_dir.exists()}")
            if workspace_dir.exists():
                # 收集所有文件
                files = []
                print(f"开始收集文件: {project_id}")
                
                for root, _, filenames in os.walk(workspace_dir):
                    for filename in filenames:
                        file_path = Path(root) / filename
                        rel_path = file_path.relative_to(workspace_dir)
                        
                        try:
                            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                                content = f.read()
                            
                            files.append({
                                "name": str(rel_path),
                                "content": content
                            })
                            print(f"收集文件: {rel_path}, 大小: {len(content)} 字节")
                        except Exception as e:
                            print(f"读取文件失败: {rel_path}, 错误: {str(e)}")
                
                if files:
                    print(f"发送文件列表: {project_id}, 文件数: {len(files)}")
                    print(f"文件列表: {', '.join(f['name'] for f in files)}")
                    await websocket.send_json({
                        "type": "complete",
                        "files": files
                    })
                    
                    await websocket.send_json({
                        "type": "status",
                        "status": "completed",
                        "message": "代码生成完成！"
                    })
        
        # 保持连接活跃
        while True:
            data = await websocket.receive_text()
            print(f"收到WebSocket消息: {project_id}, 内容: {data[:100]}...")
            
            try:
                # 尝试解析JSON
                message = json.loads(data)
                print(f"解析WebSocket消息: {project_id}, 类型: {message.get('type', 'unknown')}")
                
                # 处理不同类型的消息
                if message.get('type') == 'ping':
                    print(f"收到ping消息，发送pong响应: {project_id}")
                    await websocket.send_json({"type": "pong"})
                elif message.get('type') == 'chat':
                    # 处理聊天消息
                    await handle_chat_message(websocket, project_id, message.get('message', ''), project_dir)
            except json.JSONDecodeError:
                print(f"WebSocket消息不是有效的JSON: {project_id}")
            
    except WebSocketDisconnect:
        print(f"WebSocket断开连接: {project_id}")
        manager.disconnect(project_id, websocket)
    except Exception as e:
        print(f"WebSocket处理异常: {project_id}, 错误: {str(e)}")
        import traceback
        print(traceback.format_exc())
        manager.disconnect(project_id, websocket)

async def handle_chat_message(websocket: WebSocket, project_id: str, message: str, project_dir: Path):
    """处理聊天消息"""
    print(f"处理聊天消息: {project_id}, 消息: {message[:100]}...")
    
    try:
        # 检查API密钥
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            raise ValueError("未设置有效的OpenAI API密钥。请在.env文件中设置OPENAI_API_KEY。")
        
        # 初始化内存接口
        memory = DiskMemory(project_dir)
        
        # 创建AI实例
        ai = WebSocketAI(
            project_id=project_id,
            model_name="gpt-4",  # 使用GPT-4处理聊天
            temperature=0.7,     # 适当提高温度，使回复更加灵活
            streaming=True       # 确保使用流式输出
        )
        
        # 读取项目文件
        workspace_dir = project_dir / "workspace"
        files_dict = {}
        
        if workspace_dir.exists():
            for root, _, filenames in os.walk(workspace_dir):
                for filename in filenames:
                    file_path = Path(root) / filename
                    rel_path = file_path.relative_to(workspace_dir)
                    
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
                        files_dict[str(rel_path)] = content
                    except Exception as e:
                        print(f"读取文件失败: {rel_path}, 错误: {str(e)}")
        
        # 构建系统提示
        system_prompt = """你是一个AI编程助手，正在帮助用户开发一个项目。
你可以回答问题、解释代码、提供建议，以及根据用户的要求修改代码。
当用户要求修改代码时，你应该明确指出要修改的文件和修改内容。
使用以下格式来修改代码：

修改文件: <文件名>
```
<新的文件内容>
```

你可以访问项目中的所有文件，并且可以创建新文件。
"""
        
        # 构建文件列表消息
        files_message = "项目中的文件:\n"
        for file_name in files_dict.keys():
            files_message += f"- {file_name}\n"
        
        # 构建消息历史
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": files_message}
        ]
        
        # 添加用户消息
        messages.append({"role": "user", "content": message})
        
        # 发送AI思考中状态
        await manager.send_message(
            project_id, 
            {
                "type": "step_start",
                "step": "chat"
            }
        )
        
        # 调用AI生成回复
        ai.current_step = "chat"
        response = ai.next(messages, step_name="chat")
        
        # 获取回复内容
        reply = response[-1].content
        
        # 解析回复中的代码修改
        file_updates = []
        file_pattern = r"修改文件: ([^\n]+)\n```[^\n]*\n([\s\S]+?)\n```"
        
        for match in re.finditer(file_pattern, reply):
            file_name = match.group(1).strip()
            file_content = match.group(2)
            
            # 添加到文件更新列表
            file_updates.append({
                "file": file_name,
                "content": file_content
            })
            
            # 更新文件
            file_path = workspace_dir / file_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)
            
            print(f"更新文件: {file_name}, 大小: {len(file_content)} 字节")
        
        # 发送聊天回复
        await manager.send_message(
            project_id, 
            {
                "type": "chat_response",
                "message": reply,
                "file_updates": file_updates
            }
        )
        
        # 发送步骤完成消息
        await manager.send_message(
            project_id, 
            {
                "type": "step_complete",
                "step": "chat",
                "content": reply
            }
        )
        
    except Exception as e:
        print(f"处理聊天消息失败: {project_id}, 错误: {str(e)}")
        import traceback
        print(traceback.format_exc())
        
        # 发送错误消息
        await manager.send_message(
            project_id, 
            {
                "type": "error",
                "message": f"处理聊天消息失败: {str(e)}"
            }
        )

# 获取项目信息
@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """获取项目信息"""
    project_dir = WEB_PROJECTS_DIR / project_id
    
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 读取prompt文件
    prompt_file = project_dir / "prompt"
    prompt = ""
    if prompt_file.exists():
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read()
    
    # 收集生成的文件
    files = []
    workspace_dir = project_dir / "workspace"
    if workspace_dir.exists():
        for root, _, filenames in os.walk(workspace_dir):
            for filename in filenames:
                file_path = Path(root) / filename
                rel_path = file_path.relative_to(workspace_dir)
                
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                files.append({
                    "name": str(rel_path),
                    "content": content
                })
    
    return {
        "id": project_id,
        "prompt": prompt,
        "files": files
    }

# 创建前端目录
FRONTEND_DIR = Path("frontend")
FRONTEND_DIR.mkdir(exist_ok=True)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# 提供前端HTML
@app.get("/")
async def get_index():
    """提供前端HTML页面"""
    return FileResponse("frontend/index.html")

# 提供项目页面
@app.get("/project/{project_id}")
async def get_project_page(project_id: str):
    """提供项目页面"""
    return FileResponse("frontend/index.html")

# 启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=True) 
