from peewee import PostgresqlDatabase, Model, SqliteDatabase
from playhouse.pool import PooledPostgresqlDatabase
import os
from dotenv import load_dotenv
from fastapi import Depends
import logging
import sys
import time

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

# 连接池配置
DB_POOL_MAX_CONNECTIONS = int(os.getenv("DB_POOL_MAX_CONNECTIONS", "5"))
DB_POOL_STALE_TIMEOUT = int(os.getenv("DB_POOL_STALE_TIMEOUT", "300"))  # 5分钟
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30分钟

logger.debug(f"数据库连接池配置: 最大连接数={DB_POOL_MAX_CONNECTIONS}, 超时时间={DB_POOL_STALE_TIMEOUT}秒, 回收时间={DB_POOL_RECYCLE}秒")

# 创建 Peewee 数据库实例
db = None

try:
    # 根据数据库URL类型创建相应的数据库实例
    if DATABASE_URL.startswith("postgresql://"):
        logger.info(f"尝试连接到 PostgreSQL 数据库: {DATABASE_URL}")
        
        # 解析数据库 URL 获取连接参数
        db_parts = DATABASE_URL.replace("postgresql://", "").split("/")
        if len(db_parts) >= 2:
            db_name = db_parts[1]
            db_auth_host = db_parts[0].split("@")
            if len(db_auth_host) >= 2:
                db_host_port = db_auth_host[1].split(":")
                db_host = db_host_port[0]
                # 检查是否指定了端口
                db_port = int(db_host_port[1]) if len(db_host_port) > 1 else 5432
                
                db_auth = db_auth_host[0].split(":")
                if len(db_auth) >= 2:
                    db_user = db_auth[0]
                    db_password = db_auth[1]
                    
                    # 创建 Peewee 数据库连接池
                    logger.info(f"创建 PostgreSQL 数据库连接池: {db_host}:{db_port}/{db_name}")
                    logger.debug(f"用户名: {db_user}, 密码: {'*' * len(db_password)}")
                    
                    # 使用连接池
                    db = PooledPostgresqlDatabase(
                        db_name,
                        user=db_user,
                        password=db_password,
                        host=db_host,
                        port=db_port,
                        max_connections=DB_POOL_MAX_CONNECTIONS,
                        stale_timeout=DB_POOL_STALE_TIMEOUT,
                        timeout=5,  # 连接超时时间
                    )
                    logger.info(f"PostgreSQL 连接池已创建，最大连接数: {DB_POOL_MAX_CONNECTIONS}")
                else:
                    logger.error("数据库 URL 格式错误: 无法解析用户名和密码")
            else:
                logger.error("数据库 URL 格式错误: 无法解析主机")
        else:
            logger.error("数据库 URL 格式错误: 无法解析数据库名")
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
        if db.is_closed():
            db.connect()
            logger.debug("数据库连接已打开")
        yield
    except Exception as e:
        logger.error(f"连接数据库时出错: {str(e)}")
    finally:
        if not db.is_closed():
            db.close()
            logger.debug("数据库连接已关闭")

# 初始化数据库表
def init_db():
    try:
        # 尝试连接数据库
        if db.is_closed():
            db.connect()
            logger.info("数据库连接已建立")
        
        # 测试执行简单查询
        try:
            logger.debug("执行测试查询: SELECT 1")
            cursor = db.execute_sql('SELECT 1')
            result = cursor.fetchone()
            if result and result[0] == 1:
                logger.info("数据库查询测试成功")
            else:
                logger.warning("数据库查询测试返回意外结果")
        except Exception as query_err:
            logger.error(f"数据库查询测试失败: {str(query_err)}")
            logger.warning("将使用基本功能，但数据库相关功能可能不可用")
            return
            
        # 导入模型并创建表
        try:
            from db.models import User
            logger.debug("创建数据库表: User")
            db.create_tables([User], safe=True)
            logger.info("数据库表初始化成功")
        except ImportError as import_err:
            logger.error(f"导入模型时出错: {str(import_err)}")
        except Exception as table_err:
            logger.error(f"创建表时出错: {str(table_err)}")
        
    except Exception as e:
        logger.error(f"初始化数据库时出错: {str(e)}")
        logger.warning("应用程序将继续运行，但数据库功能可能不可用")
    finally:
        # 确保关闭连接
        if not db.is_closed():
            db.close()
            logger.info("数据库连接已关闭")

# 连接池状态监控函数
def get_pool_status():
    """获取连接池状态信息"""
    if hasattr(db, '_in_use') and hasattr(db, '_connections'):
        return {
            "in_use": len(db._in_use),
            "available": len(db._connections),
            "max_connections": DB_POOL_MAX_CONNECTIONS
        }
    return {"error": "不是连接池数据库或无法获取连接池状态"}
