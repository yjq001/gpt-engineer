from fastapi import APIRouter, Request, Response, HTTPException, Query
import httpx
import logging
import urllib.parse
from typing import Optional
import os
from middleware import log_request

# 设置日志
logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/api/proxy", tags=["proxy"])

# 是否禁用SSL验证
DISABLE_SSL_VERIFY = os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true"

@router.get("/forward")
@log_request
async def proxy_request(
    request: Request,
    url: str = Query(..., description="要转发的URL (需要进行URL编码)"),
    method: Optional[str] = Query("GET", description="请求方法"),
):
    """
    通用的HTTP/HTTPS请求转发接口 (GET方法)
    
    - **url**: 要转发的URL (需要进行URL编码)
    - **method**: 请求方法 (默认为GET)
    
    其他参数将作为查询参数传递给目标URL
    """
    return await _proxy_request(request, url, method)

@router.post("/forward")
async def proxy_request_post(
    request: Request,
    url: str = Query(..., description="要转发的URL (需要进行URL编码)"),
    method: Optional[str] = Query("POST", description="请求方法"),
):
    """
    通用的HTTP/HTTPS请求转发接口 (POST方法)
    
    - **url**: 要转发的URL (需要进行URL编码)
    - **method**: 请求方法 (默认为POST)
    
    请求体将原样转发给目标URL
    """
    return await _proxy_request(request, url, method)

# 添加一个新的路径，直接处理请求，不经过中间件
@router.get("/direct")
@log_request
async def proxy_request_direct_get(
    request: Request,
    url: str = Query(..., description="要转发的URL (需要进行URL编码)"),
    method: Optional[str] = Query("GET", description="请求方法"),
):
    """
    直接转发HTTP/HTTPS请求，绕过中间件处理 (GET方法)
    
    - **url**: 要转发的URL (需要进行URL编码)
    - **method**: 请求方法 (默认为GET)
    
    其他参数将作为查询参数传递给目标URL
    """
    return await _proxy_request_direct(request, url, method)

@router.post("/direct")
@log_request
async def proxy_request_direct_post(
    request: Request,
    url: str = Query(..., description="要转发的URL (需要进行URL编码)"),
    method: Optional[str] = Query("POST", description="请求方法"),
):
    """
    直接转发HTTP/HTTPS请求，绕过中间件处理 (POST方法)
    
    - **url**: 要转发的URL (需要进行URL编码)
    - **method**: 请求方法 (默认为POST)
    
    请求体将原样转发给目标URL
    """
    return await _proxy_request_direct(request, url, method)

async def _proxy_request(request: Request, url: str, method: str):
    """
    内部函数，处理请求转发逻辑
    """
    try:
        # 解码URL
        decoded_url = urllib.parse.unquote(url)
        logger.info(f"转发请求到: {decoded_url}, 方法: {method}")
        
        # 获取所有查询参数，除了url和method
        params = {}
        for key, value in request.query_params.items():
            if key not in ["url", "method"]:
                params[key] = value
        
        # 获取请求头，但排除一些特定的头
        headers = {}
        for key, value in request.headers.items():
            # 排除与主机相关的头和特定的头
            if key.lower() not in ["host", "connection", "content-length", "content-md5", "content-type"]:
                headers[key] = value
        
        # 获取请求体（如果有）
        body = None
        if method.upper() in ["POST", "PUT", "PATCH"]:
            body = await request.body()
        
        # 创建httpx客户端，禁用SSL验证
        async with httpx.AsyncClient(verify=False) as client:
            # 发送请求
            response = await client.request(
                method=method.upper(),
                url=decoded_url,
                params=params,
                headers=headers,
                content=body,
                follow_redirects=True,
                timeout=30.0
            )
            
            # 创建响应
            from starlette.responses import Response
            
            # 使用Response直接返回原始响应
            headers_dict = dict(response.headers)
            
            # 移除可能导致问题的头
            for header in ["transfer-encoding", "content-encoding", "content-length"]:
                if header in headers_dict:
                    del headers_dict[header]
            
            # 直接返回响应内容
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=headers_dict,
                media_type=response.headers.get("content-type")
            )
        
    except Exception as e:
        logger.error(f"转发请求失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"转发请求失败: {str(e)}")

async def _proxy_request_direct(request: Request, url: str, method: str):
    """
    内部函数，直接处理请求转发逻辑，绕过中间件
    """
    try:
        # 解码URL
        decoded_url = urllib.parse.unquote(url)
        logger.info(f"直接转发请求到: {decoded_url}, 方法: {method}")
        
        # 获取所有查询参数，除了url和method
        params = {}
        for key, value in request.query_params.items():
            if key not in ["url", "method"]:
                params[key] = value
        
        # 获取请求头，但排除一些特定的头
        headers = {}
        for key, value in request.headers.items():
            # 排除与主机相关的头和特定的头
            if key.lower() not in ["host", "connection", "content-length", "content-md5", "content-type"]:
                headers[key] = value
        
        # 获取请求体（如果有）
        body = None
        if method.upper() in ["POST", "PUT", "PATCH"]:
            body = await request.body()
        
        # 创建httpx客户端，禁用SSL验证
        async with httpx.AsyncClient(verify=False) as client:
            # 发送请求
            response = await client.request(
                method=method.upper(),
                url=decoded_url,
                params=params,
                headers=headers,
                content=body,
                follow_redirects=True,
                timeout=30.0
            )
            
            # 创建响应
            from starlette.responses import StreamingResponse, Response
            
            # 使用StreamingResponse直接返回原始响应
            headers_dict = dict(response.headers)
            
            # 移除可能导致问题的头
            for header in ["transfer-encoding", "content-encoding", "content-length"]:
                if header in headers_dict:
                    del headers_dict[header]
            
            # 直接返回响应内容，不使用流式响应
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=headers_dict,
                media_type=response.headers.get("content-type")
            )
    
    except Exception as e:
        logger.error(f"直接转发请求失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"直接转发请求失败: {str(e)}") 
