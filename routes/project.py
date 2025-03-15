from fastapi import APIRouter, HTTPException, BackgroundTasks, Body, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import os
import logging
from typing import Dict, List, Optional, Union, Literal
import json
import shutil
import uuid
from db.models import Project, ProjectType, ProjectCollaboration, CollaborationStatus, User
from db.database import get_db
from peewee import fn, DoesNotExist, JOIN
from datetime import datetime, timedelta
from pydantic import BaseModel

# 设置日志记录
logger = logging.getLogger(__name__)

# Create router with /api/project prefix
router = APIRouter(prefix="/api/project", tags=["Project API"])


# Project routes

@router.get("/{project_id}")
async def get_project(project_id: str, db=Depends(get_db)):
    """获取项目详情"""
    project_path = Path(f"projects/{project_id}")
    
    # 初始化响应
    response = {
        "project_id": project_id,
        "exists": False,
        "file_count": 0,
        "db_record": None
    }
    
    # 获取数据库中的项目信息
    try:
        db_project = Project.get_or_none(Project.id == project_id)
        if db_project:
            response["db_record"] = db_project.to_dict()
    except Exception as e:
        logger.error(f"查询数据库项目记录失败 {project_id}: {str(e)}")
    
    # 检查并统计项目文件夹信息
    try:
        if project_path.exists():
            file_count = len(list(project_path.glob("**/*")))
            response.update({
                "exists": True,
                "file_count": file_count
            })
    except Exception as e:
        logger.error(f"获取项目文件统计失败 {project_id}: {str(e)}")
    
    return response


@router.get("/{project_id}/files")
async def get_project_files(project_id: str):
    """获取项目下的所有文件列表"""
    project_path = Path(f"projects/{project_id}")
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
    
    try:
        # 获取所有文件
        file_list = []
        for file_path in project_path.glob("**/*"):
            if file_path.is_file():
                relative_path = str(file_path.relative_to(project_path)).replace("\\", "/")
                file_info = {
                    "path": relative_path,
                    "size": file_path.stat().st_size,
                    "modified": file_path.stat().st_mtime
                }
                file_list.append(file_info)
        
        return {
            "project_id": project_id,
            "files": file_list
        }
    except Exception as e:
        logger.error(f"获取项目文件列表失败 {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取项目文件列表失败: {str(e)}")


@router.get("/{project_id}/file")
async def get_file_content(project_id: str, file_path: str):
    """获取项目中指定文件的内容"""
    project_path = Path(f"projects/{project_id}")
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
    
    # 防止路径穿越攻击
    file_path = file_path.replace("..", "")
    full_file_path = project_path / file_path
    
    if not full_file_path.exists() or not full_file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件 {file_path} 不存在")
    
    try:
        # 读取文件内容
        with open(full_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        return {
            "project_id": project_id,
            "file_path": file_path,
            "content": content
        }
    except UnicodeDecodeError:
        # 如果是二进制文件
        return {
            "project_id": project_id,
            "file_path": file_path,
            "content": "[二进制文件，无法显示内容]",
            "is_binary": True
        }
    except Exception as e:
        logger.error(f"读取文件内容失败 {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"读取文件内容失败: {str(e)}")


@router.post("/{project_id}/file")
async def update_file_content(
    project_id: str, 
    file_path: str, 
    content: str = Body(..., embed=True)
):
    """修改并保存项目中指定文件的内容"""
    project_path = Path(f"projects/{project_id}")
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
    
    # 防止路径穿越攻击
    file_path = file_path.replace("..", "")
    full_file_path = project_path / file_path
    
    # 如果文件不存在，检查是否需要创建目录
    if not full_file_path.exists():
        try:
            # 确保父目录存在
            full_file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"创建目录失败 {full_file_path.parent}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"创建目录失败: {str(e)}")
    
    try:
        # 写入文件内容
        with open(full_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return {
            "project_id": project_id,
            "file_path": file_path,
            "status": "success",
            "message": "文件内容已更新"
        }
    except Exception as e:
        logger.error(f"保存文件内容失败 {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存文件内容失败: {str(e)}")


@router.delete("/{project_id}/file")
async def delete_file(project_id: str, file_path: str):
    """删除项目中指定的文件"""
    project_path = Path(f"projects/{project_id}")
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
    
    # 防止路径穿越攻击
    file_path = file_path.replace("..", "")
    full_file_path = project_path / file_path
    
    if not full_file_path.exists() or not full_file_path.is_file():
        raise HTTPException(status_code=404, detail=f"文件 {file_path} 不存在")
    
    try:
        # 尝试多种方法删除文件
        delete_success = False
        
        # 方法1: 使用os.remove
        try:
            os.remove(str(full_file_path))
            delete_success = True
            logger.info(f"使用os.remove成功删除文件: {full_file_path}")
        except Exception as e:
            logger.warning(f"使用os.remove删除失败: {str(e)}")
        
        # 方法2: 使用Path.unlink (如果方法1失败)
        if not delete_success:
            try:
                full_file_path.unlink(missing_ok=True)
                delete_success = True
                logger.info(f"使用Path.unlink成功删除文件: {full_file_path}")
            except Exception as e:
                logger.warning(f"使用Path.unlink删除失败: {str(e)}")
        
        if delete_success:
            return {
                "project_id": project_id,
                "file_path": file_path,
                "status": "success",
                "message": "文件已删除"
            }
        else:
            raise HTTPException(status_code=500, detail=f"删除文件失败，请尝试手动删除")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文件失败 {file_path}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除文件失败: {str(e)}")


@router.get("/list")
async def list_projects(
    project_type: Optional[str] = Query(None, description="项目类型，可选值：story/game/tools/videos"),
    limit: int = Query(10, ge=1, le=100, description="返回的项目数量，范围1-100"),
    db=Depends(get_db)
):
    """获取项目列表
    
    Args:
        project_type: 可选的项目类型过滤
        limit: 返回的项目数量，默认10，最大100
    """
    try:
        # 构建查询
        query = Project.select().order_by(Project.updated_at.desc())
        
        # 如果指定了项目类型，添加类型过滤
        if project_type:
            if project_type not in [t.value for t in ProjectType]:
                logger.warning(f"无效的项目类型: {project_type}")
                return {"projects": [], "total": 0}
            query = query.where(Project.type == project_type)
        
        # 获取总数
        total = query.count()
        
        # 限制返回数量并转换为列表
        projects = [p.to_dict() for p in query.limit(limit)]
        
        return {
            "total": total,
            "projects": projects
        }
        
    except Exception as e:
        logger.error(f"获取项目列表失败: {str(e)}")
        return {
            "total": 0,
            "projects": []
        }

@router.get("/public/recent")
async def list_recent_public_projects(
    limit: int = Query(10, ge=1, le=100, description="返回的项目数量，范围1-100"),
    db=Depends(get_db)
):
    """获取最近三年的公开项目
    
    Args:
        limit: 返回的项目数量，默认10，最大100
    """
    try:
        # 计算三年前的日期
        three_years_ago = datetime.now() - timedelta(days=3*365)
        
        # 构建查询
        query = (Project
                .select()
                .where(
                    (Project.is_public == True) &  # 只查询公开项目
                    (Project.created_at >= three_years_ago)  # 最近三年创建的
                )
                .order_by(Project.created_at.desc()))  # 按创建时间倒序
        
        # 获取总数
        total = query.count()
        
        # 限制返回数量并转换为列表
        projects = [p.to_dict() for p in query.limit(limit)]
        
        return {
            "total": total,
            "projects": projects
        }
        
    except Exception as e:
        logger.error(f"获取最近公开项目失败: {str(e)}")
        return {
            "total": 0,
            "projects": []
        }

class CollaborationRequest(BaseModel):
    """项目合作申请请求模型"""
    user_id: str
    message: Optional[str] = None

@router.post("/{project_id}/collaborate")
async def apply_for_collaboration(
    project_id: str,
    request: CollaborationRequest,
    db=Depends(get_db)
):
    """申请参与项目
    
    Args:
        project_id: 项目ID
        request: 申请信息，包含用户ID和可选的申请留言
    """
    try:
        # 检查项目是否存在
        try:
            project = Project.get_by_id(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="项目不存在")
        
        # 检查项目是否允许参与
        if not project.is_public:
            raise HTTPException(status_code=403, detail="该项目不允许参与")
            
        # 检查用户是否已经是项目参与者
        existing_collaboration = (ProjectCollaboration
            .select()
            .where(
                (ProjectCollaboration.project == project) &
                (ProjectCollaboration.collaborator == request.user_id) &
                (ProjectCollaboration.status == CollaborationStatus.JOINED.value)
            )
            .first())
            
        if existing_collaboration:
            raise HTTPException(status_code=400, detail="您已经是项目参与者")
            
        # 检查是否有待处理的申请
        pending_application = (ProjectCollaboration
            .select()
            .where(
                (ProjectCollaboration.project == project) &
                (ProjectCollaboration.collaborator == request.user_id) &
                (ProjectCollaboration.status == CollaborationStatus.APPLIED.value)
            )
            .first())
            
        if pending_application:
            raise HTTPException(status_code=400, detail="您已经申请过该项目，请等待审核")
        
        # 创建新的合作申请记录
        collaboration = ProjectCollaboration.create(
            id=str(uuid.uuid4()),
            project=project,
            collaborator=request.user_id,
            status=CollaborationStatus.APPLIED.value,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            join_time=None,  # 加入时间在审核通过后设置
            message=request.message
        )
        
        return {
            "status": "success",
            "collaboration_id": collaboration.id,
            "message": "申请已提交，请等待审核",
            "created_at": collaboration.created_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理项目参与申请失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理申请失败: {str(e)}")

@router.get("/collaborations")
async def get_collaboration_records(
    user_id: str,
    record_type: Literal["received", "sent"] = Query(..., description="查询类型：received(收到的申请) / sent(发起的申请)"),
    db=Depends(get_db)
):
    """获取用户的项目合作申请记录
    
    Args:
        user_id: 用户ID
        record_type: 记录类型，received-收到的申请，sent-发起的申请
    """
    try:
        # 计算三年前的日期
        three_years_ago = datetime.now() - timedelta(days=3*365)
        
        # 构建基础查询
        base_query = (ProjectCollaboration
                     .select(ProjectCollaboration, Project, User)
                     .join(Project)
                     .join(User, on=(User.id == ProjectCollaboration.collaborator))
                     .where(ProjectCollaboration.created_at >= three_years_ago))
        
        # 根据查询类型添加条件
        if record_type == "received":
            # 查询用户作为项目创建者收到的申请
            query = base_query.where(Project.creator_id == user_id)
        else:
            # 查询用户发起的申请
            query = base_query.where(ProjectCollaboration.collaborator == user_id)
            
        # 按创建时间倒序排序
        query = query.order_by(ProjectCollaboration.created_at.desc())
        
        # 准备响应数据
        records = []
        for record in query:
            records.append({
                "id": record.id,
                "project": {
                    "id": record.project.id,
                    "name": record.project.name,
                    "type": record.project.type,
                    "description": record.project.description
                },
                "applicant": {
                    "id": record.collaborator.id,
                    "name": record.collaborator.name
                },
                "status": record.status,
                "message": record.message,
                "created_at": record.created_at.isoformat(),
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
                "join_time": record.join_time.isoformat() if record.join_time else None
            })
        
        return {
            "total": len(records),
            "collaborations": records
        }
        
    except Exception as e:
        logger.error(f"获取合作申请记录失败: {str(e)}")
        return {
            "total": 0,
            "collaborations": []
        }

class CollaborationAction(BaseModel):
    """项目合作申请处理请求模型"""
    action: Literal["approve", "reject"]  # 处理动作：approve-同意，reject-拒绝
    message: Optional[str] = None  # 可选的处理备注

@router.post("/collaborations/{collaboration_id}/handle")
async def handle_collaboration_request(
    collaboration_id: str,
    action: CollaborationAction,
    user_id: str = Query(..., description="当前操作用户ID"),
    db=Depends(get_db)
):
    """处理项目合作申请
    
    Args:
        collaboration_id: 申请记录ID
        action: 处理动作（approve/reject）
        user_id: 当前操作用户ID（必须是项目创建者）
    """
    try:
        # 获取申请记录
        try:
            collaboration = (ProjectCollaboration
                           .select(ProjectCollaboration, Project)
                           .join(Project)
                           .where(ProjectCollaboration.id == collaboration_id)
                           .get())
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="申请记录不存在")
        
        # 验证操作权限（必须是项目创建者）
        if collaboration.project.creator_id != user_id:
            raise HTTPException(status_code=403, detail="您没有权限处理该申请")
        
        # 检查申请状态
        if collaboration.status != CollaborationStatus.APPLIED.value:
            raise HTTPException(status_code=400, detail="该申请已被处理")
        
        # 更新申请状态
        now = datetime.now()
        if action.action == "approve":
            # 同意申请
            collaboration.status = CollaborationStatus.JOINED.value
            collaboration.join_time = now
            # 更新项目参与者数量
            collaboration.project.participants_count += 1
            collaboration.project.save()
        else:
            # 拒绝申请
            collaboration.status = CollaborationStatus.REJECTED.value
            
        collaboration.updated_at = now
        collaboration.message = action.message  # 更新处理备注
        collaboration.save()
        
        return {
            "status": "success",
            "collaboration_id": collaboration_id,
            "action": action.action,
            "message": f"已{action.action == 'approve' and '同意' or '拒绝'}申请",
            "updated_at": now.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理项目合作申请失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理申请失败: {str(e)}")

@router.post("/{project_id}/like")
async def like_project(
    project_id: str,
    user_id: str = Query(..., description="点赞用户ID"),
    db=Depends(get_db)
):
    """项目点赞
    
    Args:
        project_id: 项目ID
        user_id: 点赞用户ID
    """
    try:
        # 获取项目信息
        try:
            project = Project.get_by_id(project_id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="项目不存在")
        
        # 更新点赞数
        project.likes_count += 1
        project.save()
        
        return {
            "status": "success",
            "project_id": project_id,
            "likes_count": project.likes_count,
            "message": "点赞成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理项目点赞失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"点赞失败: {str(e)}")
