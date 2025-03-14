import logging
from fastapi import Request
from typing import Optional, Any

# 设置日志
logger = logging.getLogger(__name__)

def get_request_id(request: Optional[Request] = None) -> str:
    """
    获取当前请求的ID
    
    Args:
        request: FastAPI请求对象，如果为None，则返回"no-request-id"
        
    Returns:
        str: 请求ID
    """
    if request is None:
        return "no-request-id"
    
    return getattr(request.state, "request_id", "no-request-id")

class RequestIDLogger:
    """
    带有请求ID的日志记录器
    """
    
    def __init__(self, logger_name: str):
        """
        初始化日志记录器
        
        Args:
            logger_name: 日志记录器名称
        """
        self.logger = logging.getLogger(logger_name)
    
    def _format_message(self, request: Optional[Request], message: str) -> str:
        """
        格式化日志消息，添加请求ID
        
        Args:
            request: FastAPI请求对象
            message: 日志消息
            
        Returns:
            str: 格式化后的日志消息
        """
        request_id = get_request_id(request)
        return f"[{request_id}] {message}"
    
    def debug(self, message: str, request: Optional[Request] = None, *args: Any, **kwargs: Any) -> None:
        """
        记录DEBUG级别日志
        
        Args:
            message: 日志消息
            request: FastAPI请求对象
            *args: 其他参数
            **kwargs: 其他关键字参数
        """
        self.logger.debug(self._format_message(request, message), *args, **kwargs)
    
    def info(self, message: str, request: Optional[Request] = None, *args: Any, **kwargs: Any) -> None:
        """
        记录INFO级别日志
        
        Args:
            message: 日志消息
            request: FastAPI请求对象
            *args: 其他参数
            **kwargs: 其他关键字参数
        """
        self.logger.info(self._format_message(request, message), *args, **kwargs)
    
    def warning(self, message: str, request: Optional[Request] = None, *args: Any, **kwargs: Any) -> None:
        """
        记录WARNING级别日志
        
        Args:
            message: 日志消息
            request: FastAPI请求对象
            *args: 其他参数
            **kwargs: 其他关键字参数
        """
        self.logger.warning(self._format_message(request, message), *args, **kwargs)
    
    def error(self, message: str, request: Optional[Request] = None, *args: Any, **kwargs: Any) -> None:
        """
        记录ERROR级别日志
        
        Args:
            message: 日志消息
            request: FastAPI请求对象
            *args: 其他参数
            **kwargs: 其他关键字参数
        """
        self.logger.error(self._format_message(request, message), *args, **kwargs)
    
    def critical(self, message: str, request: Optional[Request] = None, *args: Any, **kwargs: Any) -> None:
        """
        记录CRITICAL级别日志
        
        Args:
            message: 日志消息
            request: FastAPI请求对象
            *args: 其他参数
            **kwargs: 其他关键字参数
        """
        self.logger.critical(self._format_message(request, message), *args, **kwargs)

# 创建日志记录器实例
def get_logger(logger_name: str) -> RequestIDLogger:
    """
    获取带有请求ID的日志记录器
    
    Args:
        logger_name: 日志记录器名称
        
    Returns:
        RequestIDLogger: 带有请求ID的日志记录器
    """
    return RequestIDLogger(logger_name) 
