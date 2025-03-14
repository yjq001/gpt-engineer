import logging
import time
import contextvars
import uuid
from typing import Optional, Any, Dict

# 创建一个上下文变量，用于存储当前请求ID
request_id_var = contextvars.ContextVar('request_id', default=None)

# 设置日志
logger = logging.getLogger('sql')

def set_request_id(request_id: str) -> None:
    """
    设置当前请求的ID
    
    Args:
        request_id: 请求ID
    """
    request_id_var.set(request_id)

def get_current_request_id() -> Optional[str]:
    """
    获取当前请求的ID
    
    Returns:
        str: 请求ID，如果没有则返回None
    """
    return request_id_var.get()

class SQLQueryLogger:
    """
    SQL查询日志记录器
    """
    
    @staticmethod
    def log_query(query, params=None):
        """
        记录SQL查询
        
        Args:
            query: SQL查询语句
            params: 查询参数
        """
        request_id = get_current_request_id() or "no-request-id"
        
        # 格式化SQL查询
        if params:
            try:
                # 尝试格式化查询
                formatted_query = query % params
            except:
                formatted_query = f"{query} (params: {params})"
        else:
            formatted_query = query
        
        # 记录SQL查询
        logger.info(f"[{request_id}] SQL: {formatted_query}")
        
    @staticmethod
    def log_execution_time(query, params=None, execution_time=None):
        """
        记录SQL查询执行时间
        
        Args:
            query: SQL查询语句
            params: 查询参数
            execution_time: 执行时间（秒）
        """
        request_id = get_current_request_id() or "no-request-id"
        
        # 格式化SQL查询
        if params:
            try:
                # 尝试格式化查询
                formatted_query = query % params
            except:
                formatted_query = f"{query} (params: {params})"
        else:
            formatted_query = query
        
        # 记录SQL查询执行时间
        if execution_time is not None:
            logger.info(f"[{request_id}] SQL执行时间: {execution_time:.6f}秒 | 查询: {formatted_query}")

class PeeweeLoggerMiddleware:
    """
    Peewee日志中间件，用于记录所有SQL查询
    """
    
    def __init__(self, database):
        """
        初始化中间件
        
        Args:
            database: Peewee数据库实例
        """
        self.database = database
        self.logger = SQLQueryLogger()
        
        # 保存原始的execute_sql方法
        self.original_execute_sql = database.execute_sql
        
        # 替换execute_sql方法
        database.execute_sql = self.execute_sql
    
    def execute_sql(self, sql, params=None, commit=None, *args, **kwargs):
        """
        执行SQL查询并记录日志
        
        Args:
            sql: SQL查询语句
            params: 查询参数
            commit: 是否提交事务
            *args: 其他参数
            **kwargs: 其他关键字参数
            
        Returns:
            查询结果
        """
        # 记录SQL查询
        self.logger.log_query(sql, params)
        
        # 记录执行时间
        start_time = time.time()
        
        try:
            # 执行SQL查询
            cursor = self.original_execute_sql(sql, params, commit, *args, **kwargs)
            
            # 计算执行时间
            execution_time = time.time() - start_time
            
            # 记录执行时间
            self.logger.log_execution_time(sql, params, execution_time)
            
            return cursor
        except Exception as e:
            # 计算执行时间
            execution_time = time.time() - start_time
            
            # 记录执行时间和错误
            request_id = get_current_request_id() or "no-request-id"
            logger.error(f"[{request_id}] SQL执行错误: {str(e)} | 执行时间: {execution_time:.6f}秒 | 查询: {sql}", exc_info=True)
            
            # 重新抛出异常
            raise 
