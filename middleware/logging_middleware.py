import time
import json
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import os
import uuid
from typing import Callable, Dict, Any, Optional, List, Set
import asyncio
from starlette.responses import StreamingResponse
import inspect
from functools import wraps

# 设置日志
logger = logging.getLogger(__name__)

# 获取环境变量
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_REQUEST_BODY = os.getenv("LOG_REQUEST_BODY", "true").lower() == "true"
LOG_RESPONSE_BODY = os.getenv("LOG_RESPONSE_BODY", "true").lower() == "true"
LOG_HEADERS = os.getenv("LOG_HEADERS", "true").lower() == "true"

# 用于在整个应用中访问当前请求ID的上下文变量
REQUEST_ID_CTX_KEY = "request_id"

# 存储被标记为需要记录日志的路由处理函数
_LOGGED_ROUTES: Set[Callable] = set()

def log_request(func):
    """
    装饰器，用于标记需要记录请求和响应日志的路由处理函数
    
    用法:
    @router.get("/my-route")
    @log_request
    async def my_route_handler():
        return {"message": "Hello World"}
    """
    _LOGGED_ROUTES.add(func)
    
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    
    return wrapper

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    中间件，用于记录标记了 @log_request 装饰器的路由的请求和响应信息
    """
    
    def __init__(self, app: ASGIApp, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or []
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查是否需要排除此路径
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # 检查当前路由处理函数是否被标记为需要记录日志
        route_handler = None
        for route in request.app.routes:
            if hasattr(route, "endpoint") and route.matches({"type": "http", "path": request.url.path, "method": request.method})[0]:
                route_handler = route.endpoint
                break
        
        # 如果路由处理函数没有被标记为需要记录日志，则直接调用下一个中间件
        if route_handler not in _LOGGED_ROUTES:
            return await call_next(request)
        
        # 记录请求开始时间
        start_time = time.time()
        
        # 生成请求ID (使用UUID)
        request_id = str(uuid.uuid4())
        
        # 将request_id添加到请求的状态中，以便路由处理函数可以访问
        request.state.request_id = request_id
        
        # 获取请求信息
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params)
        client_host = request.client.host if request.client else "unknown"
        
        # 记录请求头
        headers = {}
        if LOG_HEADERS:
            headers = {k.decode('utf-8'): v.decode('utf-8') for k, v in request.headers.raw}
            # 移除敏感信息
            if 'authorization' in headers:
                headers['authorization'] = "Bearer [REDACTED]"
        
        # 记录请求体
        body = None
        body_bytes = None
        if LOG_REQUEST_BODY and request.method in ["POST", "PUT", "PATCH"]:
            try:
                # 创建一个请求体的副本，而不是直接读取
                # 这样可以避免消耗原始请求流
                body_bytes = await request.body()
                
                # 尝试解析为 JSON 用于日志记录
                try:
                    body_str = body_bytes.decode('utf-8')
                    body = json.loads(body_str)
                except:
                    body = body_bytes.decode('utf-8')
            except Exception as e:
                logger.warning(f"[{request_id}] 无法读取请求体: {str(e)}")
        
        # 构建单行请求日志
        log_parts = [
            f"[{request_id}]",
            f"请求: {method} {path}",
        ]
        
        if query_params:
            log_parts.append(f"查询参数: {json.dumps(query_params, ensure_ascii=False)}")
        
        if headers and LOG_HEADERS:
            # 只记录关键头部信息，减少日志量
            important_headers = {k: v for k, v in headers.items() if k.lower() in ['content-type', 'user-agent', 'authorization', 'accept']}
            if important_headers:
                log_parts.append(f"头部: {json.dumps(important_headers, ensure_ascii=False)}")
        
        if body and LOG_REQUEST_BODY:
            log_parts.append(f"体: {json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else body}")
        
        # 记录单行请求日志
        logger.info(" | ".join(log_parts))
        
        # 处理请求
        try:
            # 如果我们读取了请求体，需要创建一个新的请求对象
            if body_bytes is not None:
                # 创建一个自定义的_receive函数，返回已保存的请求体
                async def receive():
                    return {"type": "http.request", "body": body_bytes}
                
                # 替换请求的_receive方法
                request._receive = receive
            
            response = await call_next(request)
            
            # 记录响应信息
            status_code = response.status_code
            response_headers = {}
            
            if LOG_HEADERS:
                response_headers = {k.decode('utf-8'): v.decode('utf-8') for k, v in response.headers.raw}
                # 只保留重要的响应头
                response_headers = {k: v for k, v in response_headers.items() if k.lower() in ['content-type', 'content-length', 'location']}
            
            # 处理响应体日志记录，但不修改原始响应
            if LOG_RESPONSE_BODY:
                # 检查内容类型和编码
                content_type = response.headers.get("content-type", "").lower()
                content_encoding = response.headers.get("content-encoding", "").lower()
                
                # 对于文本或JSON响应，尝试记录内容
                if content_type and ("json" in content_type or "text/" in content_type) and not content_encoding:
                    # 保存原始响应的body_iterator
                    original_iterator = response.body_iterator
                    collected_body = bytearray()
                    
                    # 创建一个新的迭代器，用于收集响应体
                    async def logging_iterator():
                        nonlocal collected_body
                        async for chunk in original_iterator:
                            collected_body.extend(chunk)
                            yield chunk
                    
                    # 创建一个后台任务，在响应完成后记录响应体
                    async def log_response_body():
                        try:
                            # 等待响应完成
                            await asyncio.sleep(0.1)
                            
                            # 尝试解析响应体
                            try:
                                body_str = collected_body.decode('utf-8')
                                
                                # 尝试解析为JSON
                                try:
                                    body_json = json.loads(body_str)
                                    
                                    # 记录JSON响应
                                    json_str = json.dumps(body_json, ensure_ascii=False)
                                    if len(json_str) > 1000:
                                        json_str = json_str[:1000] + "... <截断>"
                                    logger.debug(f"[{request_id}] 响应体 (JSON): {json_str}")
                                except json.JSONDecodeError:
                                    # 记录文本响应
                                    if len(body_str) > 1000:
                                        body_str = body_str[:1000] + "... <截断>"
                                    logger.debug(f"[{request_id}] 响应体 (文本): {body_str}")
                            except UnicodeDecodeError:
                                # 二进制数据
                                logger.debug(f"[{request_id}] 响应体: 二进制数据 (长度: {len(collected_body)} 字节)")
                        except Exception as e:
                            logger.warning(f"[{request_id}] 记录响应体时出错: {str(e)}")
                    
                    # 创建一个新的响应，保留原始响应的所有属性
                    new_response = StreamingResponse(
                        logging_iterator(),
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type
                    )
                    
                    # 添加后台任务
                    asyncio.create_task(log_response_body())
                    
                    # 使用新的响应
                    response = new_response
                else:
                    # 对于二进制或压缩内容，只记录内容类型和长度
                    content_length = response.headers.get("content-length", "未知")
                    logger.debug(f"[{request_id}] 响应体: 二进制或压缩内容 (类型: {content_type}, 编码: {content_encoding}, 长度: {content_length})")
            
            # 计算处理时间
            process_time = time.time() - start_time
            
            # 构建单行响应日志
            log_parts = [
                f"[{request_id}]",
                f"响应: {status_code}",
                f"处理时间: {process_time:.4f}秒"
            ]
            
            if response_headers and LOG_HEADERS:
                log_parts.append(f"头部: {json.dumps(response_headers, ensure_ascii=False)}")
            
            # 记录单行响应日志 (不包含响应体，响应体由background任务处理)
            logger.info(" | ".join(log_parts))
            
            return response
        except Exception as e:
            # 记录异常信息
            process_time = time.time() - start_time
            logger.error(f"[{request_id}] 请求处理异常: {str(e)} | 处理时间: {process_time:.4f}秒", exc_info=True)
            raise 

# 辅助函数，用于获取当前请求的ID
def get_request_id(request: Request) -> str:
    """
    从请求对象中获取请求ID
    """
    return getattr(request.state, "request_id", "unknown")
