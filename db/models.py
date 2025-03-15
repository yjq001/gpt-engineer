from peewee import CharField, DateTimeField, IntegerField, BooleanField, TextField, ForeignKeyField, DecimalField, JSONField
from db.database import BaseModel
import datetime
import enum

class CollaborationStatus(enum.Enum):
    """合作状态枚举"""
    APPLIED = 'applied'  # 已申请
    JOINED = 'joined'   # 已参与
    REJECTED = 'rejected'  # 已拒绝

class ProjectType(enum.Enum):
    """项目类型枚举"""
    STORY = 'story'   # 故事类型
    GAME = 'game'    # 游戏类型
    TOOLS = 'tools'   # 工具类型
    VIDEOS = 'videos'  # 视频类型

class OrderStatus(enum.Enum):
    """订单状态枚举"""
    PENDING = 'pending'      # 待支付
    PAID = 'paid'           # 已支付
    CANCELLED = 'cancelled'  # 已取消
    REFUNDED = 'refunded'   # 已退款

class User(BaseModel):
    id = CharField(primary_key=True, max_length=32)
    name = CharField(max_length=100, index=True)
    email = CharField(max_length=100, null=True)
    picture = CharField(max_length=200, null=True)
    creatat = DateTimeField(column_name='creatat', null=True)
    updateat = DateTimeField(null=True)
    times = IntegerField(default=0)

    class Meta:
        table_name = 'users'  # 指定表名为users

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "picture": self.picture,
            "creatat": self.creatat.isoformat() if self.creatat else None,
            "updateat": self.updateat.isoformat() if self.updateat else None,
            "times": self.times
        } 

class Project(BaseModel):
    """项目模型"""
    id = CharField(primary_key=True, max_length=36)  # 项目ID
    name = CharField(max_length=100, index=True)  # 项目名称
    description = TextField(null=True)  # 项目描述
    type = CharField(max_length=20, default=ProjectType.STORY.value)  # 项目类型
    created_at = DateTimeField(default=datetime.datetime.now)  # 创建时间
    updated_at = DateTimeField(default=datetime.datetime.now)  # 更新时间
    creator_id = ForeignKeyField(User, backref='projects', column_name='creator_id')  # 创建者ID
    is_public = BooleanField(default=False)  # 是否公开
    likes_count = IntegerField(default=0)  # 点赞数
    participants_count = IntegerField(default=1)  # 参与者数量

    class Meta:
        table_name = 'projects'  # 指定表名为projects

    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "creator_id": self.creator_id.id,
            "is_public": self.is_public,
            "likes_count": self.likes_count,
            "participants_count": self.participants_count
        }
        
    def save(self, *args, **kwargs):
        """保存时自动更新更新时间"""
        self.updated_at = datetime.datetime.now()
        return super(Project, self).save(*args, **kwargs) 

class ProjectCollaboration(BaseModel):
    """项目合作模型"""
    id = CharField(primary_key=True, max_length=36)  # 合作记录ID
    project = ForeignKeyField(Project, backref='collaborations', column_name='project_id')  # 项目ID
    collaborator = ForeignKeyField(User, backref='collaborations', column_name='collaborator_id')  # 合作者ID
    join_time = DateTimeField(null=True)  # 参与时间
    status = CharField(max_length=20, default=CollaborationStatus.APPLIED.value)  # 合作状态
    created_at = DateTimeField(default=datetime.datetime.now)  # 创建时间
    updated_at = DateTimeField(default=datetime.datetime.now)  # 更新时间

    class Meta:
        table_name = 'project_collaborations'  # 指定表名
        indexes = (
            # 创建联合唯一索引，确保同一用户不能重复申请同一项目
            (('project', 'collaborator'), True),
        )

    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "project_id": self.project.id,
            "collaborator_id": self.collaborator.id,
            "join_time": self.join_time.isoformat() if self.join_time else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    def save(self, *args, **kwargs):
        """保存时自动更新更新时间"""
        self.updated_at = datetime.datetime.now()
        return super(ProjectCollaboration, self).save(*args, **kwargs)

class Order(BaseModel):
    """订单模型"""
    id = CharField(primary_key=True, max_length=36)  # 订单ID
    user = ForeignKeyField(User, backref='orders', column_name='user_id')  # 用户ID
    amount = DecimalField(max_digits=10, decimal_places=2)  # 付款金额，最大支持8位整数，2位小数
    status = CharField(max_length=20, default=OrderStatus.PENDING.value)  # 订单状态
    payment_time = DateTimeField(null=True)  # 付款时间
    created_at = DateTimeField(default=datetime.datetime.now)  # 创建时间
    updated_at = DateTimeField(default=datetime.datetime.now)  # 更新时间
    extra_info = JSONField(null=True)  # 其他信息，JSON格式

    class Meta:
        table_name = 'orders'  # 指定表名
        indexes = (
            # 创建用户ID索引，方便查询用户订单
            (('user_id',), False),
            # 创建状态索引，方便查询不同状态的订单
            (('status',), False),
        )

    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "user_id": self.user.id,
            "user_name": self.user.name,  # 添加用户名
            "amount": float(self.amount),  # Decimal 转为 float
            "status": self.status,
            "payment_time": self.payment_time.isoformat() if self.payment_time else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "extra_info": self.extra_info
        }

    def save(self, *args, **kwargs):
        """保存时自动更新更新时间"""
        self.updated_at = datetime.datetime.now()
        return super(Order, self).save(*args, **kwargs) 
