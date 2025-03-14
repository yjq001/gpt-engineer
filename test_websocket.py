#!/usr/bin/env python
"""
WebSocket API测试脚本

这个脚本用于测试WebSocket API的代码生成功能。
它会连接到WebSocket服务器，发送一个聊天消息，然后等待代码生成结果。
"""

import asyncio
import json
import logging
import sys
import websockets
import argparse
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_websocket(server_url, project_id, prompt):
    """测试WebSocket连接和代码生成功能"""
    ws_url = f"{server_url}/ws/{project_id}"
    logger.info(f"连接到WebSocket服务器: {ws_url}")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            logger.info("WebSocket连接已建立")
            
            # 接收初始连接消息
            response = await websocket.recv()
            logger.info(f"收到消息: {response}")
            
            # 接收项目信息消息（如果有）
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                logger.info(f"收到项目信息: {response}")
            except asyncio.TimeoutError:
                logger.info("没有收到项目信息，可能是新项目")
            
            # 发送聊天消息
            message = {
                "type": "chat",
                "content": prompt
            }
            logger.info(f"发送聊天消息: {message}")
            await websocket.send(json.dumps(message))
            
            # 等待并处理响应
            while True:
                response = await websocket.recv()
                response_data = json.loads(response)
                logger.info(f"收到响应类型: {response_data.get('type')}")
                
                if response_data.get("type") == "code_generated":
                    logger.info(f"代码生成完成，共 {len(response_data.get('files', []))} 个文件")
                    
                    # 创建输出目录
                    output_dir = Path(f"output/{project_id}")
                    output_dir.mkdir(parents=True, exist_ok=True)
                    
                    # 保存生成的文件
                    for file_info in response_data.get("files", []):
                        file_path = file_info.get("path")
                        content = file_info.get("content")
                        
                        if file_path and content:
                            full_path = output_dir / file_path
                            full_path.parent.mkdir(parents=True, exist_ok=True)
                            
                            with open(full_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            
                            logger.info(f"已保存文件: {full_path}")
                    
                    logger.info(f"所有文件已保存到: {output_dir}")
                    break
                
                elif response_data.get("type") == "error":
                    logger.error(f"错误: {response_data.get('message')}")
                    break
                
                elif response_data.get("type") == "status" and response_data.get("status") == "processing":
                    logger.info("正在生成代码，请稍候...")
    
    except Exception as e:
        logger.error(f"WebSocket连接错误: {str(e)}")
        return False
    
    return True

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="测试WebSocket API的代码生成功能")
    parser.add_argument("--server", default="ws://localhost:8000", help="WebSocket服务器URL")
    parser.add_argument("--project", default=f"test-project", help="项目ID")
    parser.add_argument("--prompt", default="创建一个简单的Python计算器程序，支持加减乘除操作", help="代码生成提示")
    
    args = parser.parse_args()
    
    # 运行测试
    asyncio.run(test_websocket(args.server, args.project, args.prompt))

if __name__ == "__main__":
    main() 
