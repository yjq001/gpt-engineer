from fastapi import APIRouter, Depends, HTTPException, Header, Request, status, Form
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import os
import jwt
import time
import logging
from datetime import datetime, timedelta
from google.oauth2 import id_token
from google.auth.transport import requests
from db.models import User
from pydantic import BaseModel
import json

# 设置日志
logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/api/auth", tags=["auth"])

# 环境变量
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret_key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 1440  # 24小时
# 是否禁用SSL验证（仅用于测试环境）
DISABLE_SSL_VERIFY = os.getenv("DISABLE_SSL_VERIFY", "false").lower() == "true"

if DEV_MODE:
    logger.warning("开发模式已启用，某些安全检查将被跳过")
    
# 始终禁用SSL验证
logger.warning("SSL验证已禁用，这可能会导致安全风险")
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# OAuth2 密码流
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/google", auto_error=False)

# 请求模型
class GoogleAuthRequest(BaseModel):
    idToken: str

# 响应模型
class UserResponse(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    picture: Optional[str] = None

class AuthResponse(BaseModel):
    user: UserResponse
    token: str

class MessageResponse(BaseModel):
    message: str

# 创建JWT令牌
def create_jwt_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

# 从Authorization头部获取令牌
async def get_token_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization.replace("Bearer ", "")
    return None

# 验证JWT令牌
async def verify_token(token: Optional[str] = Depends(oauth2_scheme), header_token: Optional[str] = Depends(get_token_from_header)):
    # 优先使用OAuth2获取的令牌，如果没有则使用头部令牌
    final_token = token or header_token
    
    if not final_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌"
        )
    
    try:
        payload = jwt.decode(final_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证令牌"
            )
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证令牌已过期"
        )
    except jwt.PyJWTError as e:
        logger.error(f"JWT解码错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌"
        )

# Google登录验证
@router.post("/google", response_model=AuthResponse)
async def google_login(request: GoogleAuthRequest):
    try:
        logger.info("开始处理Google登录请求")
        
        # 获取令牌
        token = request.idToken
        logger.info(f"从JSON请求体中获取到idToken，长度: {len(token)}")
        
        # 记录令牌类型和长度（不记录令牌内容）
        logger.info(f"收到ID令牌，类型: {type(token).__name__}, 长度: {len(token)}")
        
        # 开发模式下，允许使用测试令牌
        if DEV_MODE and token == "test-token":
            logger.warning("使用测试令牌登录，仅用于开发环境")
            # 使用测试用户信息
            user_id = "test-user-id"
            email = "test@example.com"
            name = "Test User"
            picture = "https://example.com/test-user.jpg"
        else:
            # 验证Google ID令牌
            try:
                # 使用自定义的transport请求对象，禁用SSL验证
                from google.auth.transport.requests import Request as AuthRequest
                import ssl
                import requests as requests_lib  # 重命名以避免与google.auth.transport.requests冲突
                
                # 创建一个不验证SSL的上下文
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                # 创建一个会话并禁用SSL验证
                session = requests_lib.Session()
                session.verify = False
                
                # 使用自定义的请求对象
                http = AuthRequest()
                # 手动设置session属性
                http.session = session
                
                idinfo = id_token.verify_oauth2_token(
                    token, http, GOOGLE_CLIENT_ID)
                logger.debug("使用禁用SSL验证的方式验证了Google ID令牌")
                
                logger.debug(f"成功验证Google ID令牌，包含字段: {', '.join(idinfo.keys())}")
            except Exception as e:
                logger.error(f"验证Google ID令牌失败: {str(e)}")
                logger.error("Google登录验证失败:", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="身份验证失败"
                )

            # 检查令牌是否有效
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                logger.error(f"无效的令牌颁发者: {idinfo['iss']}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="身份验证失败：无效的令牌颁发者"
                )

            # 获取用户信息
            user_id = idinfo['sub']
            email = idinfo.get('email')
            name = idinfo.get('name')
            picture = idinfo.get('picture')
            logger.debug(f"从Google ID令牌中获取到用户信息: id={user_id}, email={email}, name={name}")

        # 查找或创建用户
        try:
            user = User.get(User.id == user_id)
            logger.debug(f"找到现有用户: id={user_id}, name={user.name}")
            # 更新用户信息
            user.name = name
            user.email = email
            user.picture = picture
            user.updateat = datetime.now()
            user.times = user.times + 1 if user.times else 1
            user.save()
            logger.debug(f"更新用户信息: id={user_id}, times={user.times}")
        except User.DoesNotExist:
            # 创建新用户
            logger.debug(f"创建新用户: id={user_id}, name={name}")
            user = User.create(
                id=user_id,
                name=name,
                email=email,
                picture=picture,
                creatat=datetime.now(),
                updateat=datetime.now(),
                times=1
            )

        # 创建JWT令牌
        token = create_jwt_token(user_id)
        logger.debug(f"为用户 {user_id} 创建JWT令牌，长度: {len(token)}")

        # 返回用户信息和令牌
        return {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "picture": user.picture
            },
            "token": token
        }
    except Exception as e:
        logger.error(f"Google登录验证失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="身份验证失败"
        )

# 获取当前用户信息
@router.get("/user", response_model=dict)
async def get_current_user(user_id: str = Depends(verify_token)):
    try:
        user = User.get(User.id == user_id)
        return {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "picture": user.picture
            }
        }
    except User.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

# 用户登出
@router.post("/logout", response_model=MessageResponse)
async def logout(user_id: str = Depends(verify_token)):
    # 在实际应用中，可能需要将令牌添加到黑名单
    # 这里简单返回成功消息
    return {"message": "成功登出"}

# 测试路由
@router.get("/test", response_model=MessageResponse)
async def test_auth():
    return {"message": "认证路由正常工作"} 
