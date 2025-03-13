from peewee import PostgresqlDatabase, Model, SqliteDatabase
from playhouse.pool import PooledPostgresqlDatabase
import os
from dotenv import load_dotenv
from fastapi import Depends
import logging
import sys
import time
import urllib.parse

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

# 数据库连接 URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://etl:gf_etl_2023@etlpg.test.db.gf.com.cn:15432/etl")
# 获取schema
DB_SCHEMA = os.getenv("DB_SCHEMA", "easyllms")

# 连接池配置
DB_POOL_MAX_CONNECTIONS = int(os.getenv("DB_POOL_MAX_CONNECTIONS", "5"))
DB_POOL_STALE_TIMEOUT = int(os.getenv("DB_POOL_STALE_TIMEOUT", "300"))  # 5分钟
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30分钟

logger.debug(f"数据库连接池配置: 最大连接数={DB_POOL_MAX_CONNECTIONS}, 超时时间={DB_POOL_STALE_TIMEOUT}秒, 回收时间={DB_POOL_RECYCLE}秒")
logger.info(f"使用数据库schema: {DB_SCHEMA}")

# 创建 Peewee 数据库实例
db = None

try:
    # 根据数据库URL类型创建相应的数据库实例
    if DATABASE_URL.startswith("postgresql://"):
        logger.info(f"尝试连接到 PostgreSQL 数据库: {DATABASE_URL}")
        
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
        
        # 使用标准的PostgresqlDatabase
        db = PostgresqlDatabase(
            db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
            options=f'-c search_path={DB_SCHEMA}'  # 设置schema
        )
        logger.info(f"PostgreSQL 数据库连接已创建")
    else:
        logger.error(f"不支持的数据库 URL 格式: {DATABASE_URL}")
except Exception as e:
    logger.error(f"创建数据库实例时出错: {str(e)}")

# 创建内存数据库作为回退
if db is None:
    logger.warning("无法创建数据库连接，使用 SQLite 内存数据库作为回退")
    db = SqliteDatabase(':memory:')
    logger.info("已创建 SQLite 内存数据库作为回退")

# 不要使用自定义连接状态类，使用 Peewee 默认的连接状态管理
# 这样可以避免 'PeeweeConnectionState' object has no attribute 'reset' 错误

# 基础模型类
class BaseModel(Model):
    class Meta:
        database = db

# 获取数据库连接的依赖函数
async def get_db():
    try:
        logger.debug("尝试获取数据库连接")
        if db.is_closed():
            logger.debug("数据库连接已关闭，尝试重新连接")
            db.connect()
            logger.debug("数据库连接已打开")
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
    """获取数据库连接状态信息"""
    try:
        is_connected = not db.is_closed() if db else False
        return {
            "is_connected": is_connected,
            "database_type": type(db).__name__ if db else "None",
            "schema": DB_SCHEMA
        }
    except Exception as e:
        logger.error(f"获取数据库状态时出错: {str(e)}")
        return {"error": f"获取数据库状态时出错: {str(e)}"}
