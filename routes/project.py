from fastapi import APIRouter, HTTPException, BackgroundTasks, Body, Depends
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import os
import logging
from typing import Dict, List, Optional, Union
import json
import shutil

# 设置日志记录
logger = logging.getLogger(__name__)

# Create router with /api/project prefix
router = APIRouter(prefix="/api/project", tags=["Project API"])


# Project routes

@router.get("/{project_id}")
async def get_project(project_id: str):
    """获取项目详情"""
    project_path = Path(f"projects/{project_id}")
    
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"项目 {project_id} 不存在")
    
    # 统计项目信息
    try:
        file_count = len(list(project_path.glob("**/*")))
        return {
            "project_id": project_id,
            "exists": True,
            "file_count": file_count
        }
    except Exception as e:
        logger.error(f"获取项目信息失败 {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取项目信息失败: {str(e)}")


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
