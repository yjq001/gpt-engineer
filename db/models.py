from peewee import CharField
from db.database import BaseModel

class User(BaseModel):
    id = CharField(primary_key=True, index=True)
    name = CharField(index=True)

    class Meta:
        table_name = 'users'  # 指定表名为users

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name
        } 
