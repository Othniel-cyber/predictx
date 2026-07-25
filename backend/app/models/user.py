from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    subscription_type = Column(String, default="none")
    subscription_expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())