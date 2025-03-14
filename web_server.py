import os
import sys
from pathlib import Path
import dotenv
import logging

# 加载环境变量
dotenv.load_dotenv()

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
logging.basicConfig(
    level=LOG_LEVELS.get(LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info(f"日志级别设置为: {LOG_LEVEL}")

# 检查必要的依赖
try:
    import dotenv
except ImportError:
    logger.error("错误: 缺少python-dotenv包。请运行 'pip install python-dotenv'")
    sys.exit(1)

logger.info("已加载环境变量")

# 检查API密钥
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "your_openai_api_key_here":
    logger.warning("警告: 未设置有效的OpenAI API密钥。请在.env文件中设置OPENAI_API_KEY。")

# 检查数据库URL
db_url = os.getenv("DATABASE_URL")
if db_url:
    logger.debug(f"数据库URL: {db_url}")
else:
    logger.warning("未设置DATABASE_URL环境变量，将使用默认值")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 添加GPT-Engineer到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
logger.info("已添加当前目录到Python路径")

# Import our custom modules
from routes.rest_api import router as rest_router
from routes.websocket_api import router as websocket_router
from middleware import RequestLoggingMiddleware

# 获取CORS配置
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
logger.info(f"CORS允许的源: {CORS_ORIGINS}")

# 创建FastAPI应用
app = FastAPI(
    title="GPT-Engineer API",
    description="GPT-Engineer RESTful API",
    version="1.0.0"
)
logger.info("FastAPI应用已创建")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # 从环境变量获取允许的源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS中间件已配置")

# 添加请求日志中间件
app.add_middleware(
    RequestLoggingMiddleware,
    exclude_paths=["/static/"]  # 排除静态文件路径
)
logger.info("请求日志中间件已配置 - 使用 @log_request 装饰器标记需要记录日志的路由")

# 检查static目录是否存在
static_dir = Path("static")
if not static_dir.exists():
    logger.warning("static目录不存在，正在创建...")
    static_dir.mkdir(exist_ok=True)
    
    # 创建一个简单的index.html文件
    index_html = static_dir / "index.html"
    with open(index_html, "w") as f:
        f.write("""<!DOCTYPE html>
<html>
<head>
    <title>GPT-Engineer Web Interface</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
        h1 { color: #333; }
        .container { max-width: 800px; margin: 0 auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1>GPT-Engineer Web Interface</h1>
        <p>Welcome to the GPT-Engineer Web Interface!</p>
        <p>Visit <a href="/test">Test Page</a> to test the API and WebSocket functionality.</p>
    </div>
</body>
</html>""")
    
    # 创建test.html文件如果不存在
    test_html = static_dir / "test.html"
    if not test_html.exists():
        logger.warning("test.html不存在，请确保创建此文件以提供测试界面")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
logger.info("静态文件已挂载")

# Include routers
app.include_router(rest_router)
app.include_router(websocket_router)
logger.info("路由已注册")

# Main entry point
if __name__ == "__main__":
    import uvicorn
    logger.info("启动 Web 服务器...")
    uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=True) 
