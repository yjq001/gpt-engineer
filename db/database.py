from peewee import PostgresqlDatabase, Model, SqliteDatabase
from playhouse.pool import PooledPostgresqlDatabase
import os
from dotenv import load_dotenv
from fastapi import Depends
import logging
import sys
import time
import urllib.parse
from utils import PeeweeLoggerMiddleware

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
logging.basicConfig(level=LOG_LEVELS.get(LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)
logger.debug("数据库模块初始化")

# 配置SQL日志
sql_logger = logging.getLogger('sql')
sql_logger.setLevel(LOG_LEVELS.get(LOG_LEVEL, logging.INFO))

# 数据库连接 URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://etl:gf_etl_2023@etlpg.test.db.gf.com.cn:15432/etl")
# 获取schema
DB_SCHEMA = os.getenv("DB_SCHEMA", "easyllms")

# 连接池配置
DB_POOL_MAX_CONNECTIONS = int(os.getenv("DB_POOL_MAX_CONNECTIONS", "5"))
DB_POOL_STALE_TIMEOUT = int(os.getenv("DB_POOL_STALE_TIMEOUT", "300"))  # 5分钟
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30分钟

# SQL日志配置
LOG_SQL = os.getenv("LOG_SQL", "true").lower() == "true"

logger.debug(f"数据库连接池配置: 最大连接数={DB_POOL_MAX_CONNECTIONS}, 超时时间={DB_POOL_STALE_TIMEOUT}秒, 回收时间={DB_POOL_RECYCLE}秒")
logger.info(f"使用数据库schema: {DB_SCHEMA}")
logger.info(f"SQL日志记录: {'启用' if LOG_SQL else '禁用'}")

# 创建 Peewee 数据库实例
db = None

try:
    # 根据数据库URL类型创建相应的数据库实例
    if DATABASE_URL.startswith("postgresql://"):
        logger.debug(f"尝试连接到 PostgreSQL 数据库: {DATABASE_URL}")
        
        # 解析数据库URL
        parsed_url = urllib.parse.urlparse(DATABASE_URL)
        
        # 获取数据库名称
        db_name = parsed_url.path.lstrip('/')
        
        # 获取用户名和密码
        db_user = parsed_url.username
        db_password = parsed_url.password
        
        # 获取主机和端口
        db_host = parsed_url.hostname
        db_port = parsed_url.port or 5432
        
        # 检查是否使用pooler端点
        is_pooler = '-pooler' in db_host if db_host else False
        
        # 连接参数
        db_params = {
            'user': db_user,
            'password': db_password,
            'host': db_host,
            'port': db_port,
            'max_connections': DB_POOL_MAX_CONNECTIONS,
            'stale_timeout': DB_POOL_STALE_TIMEOUT,
            'timeout': 5,  # 连接超时时间
            'autocommit': True  # 启用自动提交
        }
        
        # 只有在非pooler端点时才设置search_path
        if not is_pooler:
            db_params['options'] = f'-c search_path={DB_SCHEMA}'
            logger.info(f"使用非pooler端点，设置search_path={DB_SCHEMA}")
        else:
            logger.info(f"使用pooler端点，不设置search_path参数")
            
            # 对于pooler端点，我们需要在每次查询后执行SET search_path
            # 这将在模型的Meta类中处理
        
        # 使用连接池
        db = PooledPostgresqlDatabase(
            db_name,
            **db_params
        )
        logger.info(f"PostgreSQL 连接池已创建，最大连接数: {DB_POOL_MAX_CONNECTIONS}, 自动提交: {'已启用' if getattr(db, 'autocommit', True) else '已禁用'}")
    else:
        logger.error(f"不支持的数据库 URL 格式: {DATABASE_URL}")
except Exception as e:
    logger.error(f"创建数据库实例时出错: {str(e)}")

# 创建内存数据库作为回退
if db is None:
    logger.warning("无法创建数据库连接，使用 SQLite 内存数据库作为回退")
    db = SqliteDatabase(':memory:')
    logger.info("已创建 SQLite 内存数据库作为回退")

# 启用SQL日志记录
if LOG_SQL and db is not None:
    try:
        # 创建SQL日志中间件
        sql_logger_middleware = PeeweeLoggerMiddleware(db)
        logger.info("SQL日志中间件已创建")
    except Exception as e:
        logger.error(f"创建SQL日志中间件时出错: {str(e)}")

# 基础模型类
class BaseModel(Model):
    class Meta:
        database = db
        schema = DB_SCHEMA  # 设置schema

    @classmethod
    def initialize(cls):
        """初始化模型，设置schema"""
        # 检查是否使用pooler端点
        if db and hasattr(db, '_connect_kwargs') and 'host' in db._connect_kwargs:
            db_host = db._connect_kwargs['host']
            is_pooler = '-pooler' in db_host if db_host else False
            
            # 对于pooler端点，我们需要在连接后手动设置schema
            if is_pooler and not db.is_closed():
                try:
                    # 手动执行SET search_path
                    db.execute_sql(f"SET search_path TO {DB_SCHEMA}")
                    logger.debug(f"已手动设置search_path为{DB_SCHEMA}")
                except Exception as e:
                    logger.error(f"设置search_path时出错: {str(e)}")

# 获取数据库连接的依赖函数
async def get_db():
    try:
        logger.debug("尝试获取数据库连接")
        if db.is_closed():
            logger.debug("数据库连接已关闭，尝试重新连接")
            db.connect()
            logger.debug("数据库连接已打开")
            # 初始化模型
            BaseModel.initialize()
        else:
            logger.debug("数据库连接已存在")
        yield
    except Exception as e:
        logger.error(f"连接数据库时出错: {str(e)}", exc_info=True)
        raise
    finally:
        if not db.is_closed():
            logger.debug("关闭数据库连接")
            db.close()
            logger.debug("数据库连接已关闭")

# 连接池状态监控函数
def get_pool_status():
    """获取数据库连接池状态信息"""
    try:
        is_connected = not db.is_closed() if db else False
        status = {
            "is_connected": is_connected,
            "database_type": type(db).__name__ if db else "None",
            "schema": DB_SCHEMA
        }
        
        # 如果是连接池，添加连接池特定的信息
        if isinstance(db, PooledPostgresqlDatabase) and hasattr(db, '_in_use') and hasattr(db, '_connections'):
            status.update({
                "in_use": len(db._in_use),
                "available": len(db._connections),
                "max_connections": DB_POOL_MAX_CONNECTIONS,
                "autocommit": getattr(db, 'autocommit', True)  # 获取autocommit设置
            })
            
        return status
    except Exception as e:
        logger.error(f"获取数据库状态时出错: {str(e)}")
        return {"error": f"获取数据库状态时出错: {str(e)}"}
