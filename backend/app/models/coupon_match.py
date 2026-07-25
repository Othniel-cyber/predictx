from sqlalchemy import Column, Integer, String, ForeignKey

from app.database import Base


class CouponMatch(Base):
    __tablename__ = "coupon_matches"

    id = Column(Integer, primary_key=True)
    coupon_id = Column(Integer, ForeignKey("coupons.id"))
    match_id = Column(Integer, ForeignKey("matches.id"))
    prediction_id = Column(Integer, ForeignKey("predictions.id"))
    status = Column(String, default="PENDING")