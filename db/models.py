from peewee import CharField, DateTimeField, IntegerField
from db.database import BaseModel

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
