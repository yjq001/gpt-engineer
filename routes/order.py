from fastapi import APIRouter, HTTPException, Request, Depends
from db.models import Order, OrderStatus, User
from db.database import get_db
import stripe
import json
import logging
from datetime import datetime
import os
from typing import Optional
import uuid

# 设置日志记录
logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(prefix="/api/order", tags=["Order API"])

# 配置Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

@router.post("/webhook")
async def stripe_webhook(request: Request, db=Depends(get_db)):
    """处理来自Stripe的Webhook回调
    
    主要处理以下事件：
    - payment_intent.succeeded: 支付成功
    - payment_intent.payment_failed: 支付失败
    """
    try:
        # 获取原始请求数据
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        try:
            # 验证Webhook签名
            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            logger.error(f"Invalid payload: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid payload")
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid signature: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid signature")
            
        # 获取事件数据
        event_data = event.data.object
        
        # 根据事件类型处理
        if event.type == "payment_intent.succeeded":
            await handle_successful_payment(event_data)
        elif event.type == "payment_intent.payment_failed":
            await handle_failed_payment(event_data)
            
        return {"status": "success", "message": f"Processed {event.type}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理Stripe webhook失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def handle_successful_payment(payment_intent):
    """处理支付成功的情况"""
    try:
        # 从metadata中获取用户信息
        user_id = payment_intent.metadata.get("user_id")
        if not user_id:
            logger.error("Payment intent missing user_id in metadata")
            return
            
        # 创建订单记录
        order = Order.create(
            id=str(uuid.uuid4()),
            user=user_id,
            amount=payment_intent.amount / 100,  # Stripe金额是以分为单位
            status=OrderStatus.COMPLETED.value,
            payment_time=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            extra_info={
                "stripe_payment_intent_id": payment_intent.id,
                "stripe_payment_method": payment_intent.payment_method_types[0],
                "currency": payment_intent.currency,
                "description": payment_intent.description
            }
        )
        
        logger.info(f"Successfully created order {order.id} for payment {payment_intent.id}")
        
    except Exception as e:
        logger.error(f"处理成功支付失败: {str(e)}")
        raise

async def handle_failed_payment(payment_intent):
    """处理支付失败的情况"""
    try:
        # 从metadata中获取用户信息
        user_id = payment_intent.metadata.get("user_id")
        if not user_id:
            logger.error("Payment intent missing user_id in metadata")
            return
            
        # 创建失败的订单记录
        order = Order.create(
            id=str(uuid.uuid4()),
            user=user_id,
            amount=payment_intent.amount / 100,
            status=OrderStatus.FAILED.value,
            payment_time=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            extra_info={
                "stripe_payment_intent_id": payment_intent.id,
                "stripe_payment_method": payment_intent.payment_method_types[0],
                "currency": payment_intent.currency,
                "description": payment_intent.description,
                "error": payment_intent.last_payment_error.message if payment_intent.last_payment_error else "Unknown error"
            }
        )
        
        logger.info(f"Recorded failed payment order {order.id} for payment {payment_intent.id}")
        
    except Exception as e:
        logger.error(f"处理失败支付失败: {str(e)}")
        raise

@router.get("/list")
async def list_orders(
    user_id: str,
    status: Optional[str] = None,
    db=Depends(get_db)
):
    """获取用户订单列表
    
    Args:
        user_id: 用户ID
        status: 可选的订单状态过滤
    """
    try:
        # 构建查询
        query = Order.select().where(Order.user == user_id)
        
        # 添加状态过滤
        if status:
            if status not in [s.value for s in OrderStatus]:
                raise HTTPException(status_code=400, detail="无效的订单状态")
            query = query.where(Order.status == status)
            
        # 按创建时间倒序排序
        query = query.order_by(Order.created_at.desc())
        
        # 转换为列表
        orders = [order.to_dict() for order in query]
        
        return {
            "total": len(orders),
            "orders": orders
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取订单列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{order_id}")
async def get_order(
    order_id: str,
    user_id: str,
    db=Depends(get_db)
):
    """获取订单详情
    
    Args:
        order_id: 订单ID
        user_id: 用户ID（用于验证权限）
    """
    try:
        # 查询订单
        try:
            order = Order.get_by_id(order_id)
        except DoesNotExist:
            raise HTTPException(status_code=404, detail="订单不存在")
            
        # 验证权限
        if order.user.id != user_id:
            raise HTTPException(status_code=403, detail="无权访问此订单")
            
        return order.to_dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取订单详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 
