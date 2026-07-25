from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.sql import func

from app.database import Base


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, server_default=func.now())
    status = Column(String, default="PENDING")
    total_bets = Column(Integer, default=0)
    won_bets = Column(Integer, default=0)
    is_public = Column(Integer, default=1)