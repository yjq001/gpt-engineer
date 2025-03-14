#!/usr/bin/env python
"""
环境检查脚本

这个脚本用于检查WebSocket API所需的环境配置，确保所有必要的依赖和设置都正确。
"""

import os
import sys
import importlib
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_python_version():
    """检查Python版本"""
    logger.info(f"Python版本: {sys.version}")
    if sys.version_info < (3, 7):
        logger.error("Python版本过低，需要Python 3.7或更高版本")
        return False
    return True

def check_dependencies():
    """检查依赖包"""
    required_packages = [
        "fastapi",
        "uvicorn",
        "websockets",
        "openai",
        "langchain",
        "langchain_openai",
        "dotenv"
    ]
    
    all_installed = True
    for package in required_packages:
        try:
            importlib.import_module(package)
            logger.info(f"✓ {package} 已安装")
        except ImportError:
            logger.error(f"✗ {package} 未安装")
            all_installed = False
    
    if not all_installed:
        logger.info("请使用以下命令安装缺失的依赖:")
        logger.info("pip install fastapi uvicorn websockets openai langchain langchain_openai python-dotenv")
    
    return all_installed

def check_openai_sdk():
    """检查OpenAI SDK版本和配置"""
    try:
        import openai
        logger.info(f"OpenAI SDK版本: {openai.__version__}")
        
        # 检查是否为新版本SDK
        if hasattr(openai, "__version__") and openai.__version__.startswith("1."):
            logger.info("检测到OpenAI SDK 1.0+版本")
            
            # 检查是否有RateLimitError属性
            if hasattr(openai, "RateLimitError"):
                logger.info("✓ openai.RateLimitError 可用")
            else:
                logger.warning("✗ openai.RateLimitError 不可用，但这在新版SDK中是正常的")
                logger.info("已修复代码以适应新版SDK")
        else:
            logger.info("检测到OpenAI SDK 0.x版本")
            
            # 检查是否有error.RateLimitError属性
            if hasattr(openai, "error") and hasattr(openai.error, "RateLimitError"):
                logger.info("✓ openai.error.RateLimitError 可用")
            else:
                logger.warning("✗ openai.error.RateLimitError 不可用")
                logger.warning("这可能会导致代码运行错误")
        
        return True
    except ImportError:
        logger.error("未安装OpenAI SDK")
        return False

def check_env_variables():
    """检查环境变量"""
    from dotenv import load_dotenv
    
    # 加载环境变量
    load_dotenv()
    
    # 检查必要的环境变量
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        logger.warning("未设置OPENAI_API_KEY环境变量")
        logger.info("请在.env文件中设置OPENAI_API_KEY")
        return False
    else:
        # 检查API密钥格式
        if openai_api_key.startswith("sk-") and len(openai_api_key) > 20:
            logger.info("✓ OPENAI_API_KEY 格式正确")
        else:
            logger.warning("OPENAI_API_KEY 格式可能不正确")
    
    # 检查其他环境变量
    model_name = os.getenv("MODEL_NAME", "gpt-4o")
    logger.info(f"MODEL_NAME: {model_name}")
    
    temperature = os.getenv("TEMPERATURE", "0.1")
    logger.info(f"TEMPERATURE: {temperature}")
    
    # 检查Claude模型
    if "claude" in model_name.lower():
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            logger.warning("使用Claude模型但未设置ANTHROPIC_API_KEY环境变量")
            return False
    
    # 检查Azure
    azure_endpoint = os.getenv("AZURE_ENDPOINT")
    if azure_endpoint:
        logger.info(f"AZURE_ENDPOINT: {azure_endpoint}")
    
    return True

def check_project_structure():
    """检查项目结构"""
    # 检查关键文件
    required_files = [
        "web_server.py",
        "routes/websocket_api.py",
        "static/code_generator.html"
    ]
    
    all_files_exist = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            logger.info(f"✓ {file_path} 存在")
        else:
            logger.error(f"✗ {file_path} 不存在")
            all_files_exist = False
    
    # 检查项目目录
    projects_dir = Path("projects")
    if not projects_dir.exists():
        logger.info("创建projects目录")
        projects_dir.mkdir(exist_ok=True)
    
    return all_files_exist

def main():
    """主函数"""
    logger.info("开始环境检查...")
    
    checks = [
        ("Python版本", check_python_version),
        ("依赖包", check_dependencies),
        ("OpenAI SDK", check_openai_sdk),
        ("环境变量", check_env_variables),
        ("项目结构", check_project_structure)
    ]
    
    all_passed = True
    for name, check_func in checks:
        logger.info(f"\n检查 {name}...")
        if not check_func():
            all_passed = False
    
    if all_passed:
        logger.info("\n✅ 所有检查通过！WebSocket API应该可以正常工作。")
        logger.info("运行以下命令启动服务器:")
        logger.info("python web_server.py")
    else:
        logger.warning("\n⚠️ 部分检查未通过。请修复上述问题后再尝试运行WebSocket API。")
        logger.info("参考TROUBLESHOOTING.md获取更多帮助。")

if __name__ == "__main__":
    main() 
