import time
import json
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import os
import uuid
from typing import Callable, Dict, Any, Optional
from utils.sql_logger import set_request_id

# 设置日志
logger = logging.getLogger(__name__)

# 获取环境变量
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_REQUEST_BODY = os.getenv("LOG_REQUEST_BODY", "true").lower() == "true"
LOG_RESPONSE_BODY = os.getenv("LOG_RESPONSE_BODY", "true").lower() == "true"
LOG_HEADERS = os.getenv("LOG_HEADERS", "true").lower() == "true"
# 是否在日志中显示敏感信息（如idToken）
LOG_SENSITIVE_INFO = os.getenv("LOG_SENSITIVE_INFO", "false").lower() == "true"

# 用于在整个应用中访问当前请求ID的上下文变量
REQUEST_ID_CTX_KEY = "request_id"

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    中间件，用于记录所有 RESTful API 的请求和响应信息
    """
    
    def __init__(self, app: ASGIApp, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or []
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查是否需要排除此路径
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        # 记录请求开始时间
        start_time = time.time()
        
        # 生成请求ID (使用UUID)
        request_id = str(uuid.uuid4())
        
        # 将request_id添加到请求的状态中，以便路由处理函数可以访问
        request.state.request_id = request_id
        
        # 设置请求ID到上下文变量，以便SQL日志记录器可以访问
        set_request_id(request_id)
        
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
                    body_for_log = json.loads(body_str)
                    # 如果是登录请求，处理敏感信息（仅用于日志记录）
                    if path.endswith('/auth/google') and 'idToken' in body_for_log:
                        # 创建一个副本用于日志记录，不修改原始数据
                        body = body_for_log.copy()
                        if not LOG_SENSITIVE_INFO:
                            # 在非调试模式下隐藏敏感信息
                            body['idToken'] = "[REDACTED]"
                        else:
                            # 在调试模式下显示完整信息，但添加警告
                            logger.debug(f"[{request_id}] 警告：日志中包含敏感信息(idToken)，仅用于调试目的")
                    else:
                        body = body_for_log
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
            
            # 记录响应体
            response_body = None
            if LOG_RESPONSE_BODY:
                response_body_bytes = b""
                async for chunk in response.body_iterator:
                    response_body_bytes += chunk
                
                # 创建新的响应
                response = Response(
                    content=response_body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
                
                # 尝试解析为 JSON
                try:
                    response_body = json.loads(response_body_bytes.decode('utf-8'))
                    # 如果是登录响应，处理敏感信息
                    if path.endswith('/auth/google') and 'token' in response_body:
                        if not LOG_SENSITIVE_INFO:
                            # 在非调试模式下隐藏敏感信息
                            response_body['token'] = "[REDACTED]"
                        else:
                            # 在调试模式下显示完整信息，但添加警告
                            logger.debug(f"[{request_id}] 警告：日志中包含敏感信息(JWT token)，仅用于调试目的")
                except:
                    try:
                        response_body = response_body_bytes.decode('utf-8')
                    except:
                        response_body = "<无法解码的二进制数据>"
            
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
            
            if response_body and LOG_RESPONSE_BODY:
                # 如果响应体太长，截断它
                if isinstance(response_body, str) and len(response_body) > 1000:
                    response_body = response_body[:1000] + "... <截断>"
                elif isinstance(response_body, (dict, list)):
                    response_body_str = json.dumps(response_body, ensure_ascii=False)
                    if len(response_body_str) > 1000:
                        response_body = "<响应体太长，已截断>"
                    else:
                        response_body = response_body_str
                
                log_parts.append(f"体: {response_body}")
            
            # 记录单行响应日志
            logger.info(" | ".join(log_parts))
            
            return response
        except Exception as e:
            # 记录异常信息
            process_time = time.time() - start_time
            logger.error(f"[{request_id}] 请求处理异常: {str(e)} | 处理时间: {process_time:.4f}秒", exc_info=True)
            raise 
