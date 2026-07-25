from sqlalchemy import Column, Integer, ForeignKey, Float, DateTime, String
from sqlalchemy.sql import func

from app.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), unique=True)
    home_expected_goals = Column(Float)
    away_expected_goals = Column(Float)
    prob_home = Column(Float)
    prob_draw = Column(Float)
    prob_away = Column(Float)
    prob_over_25 = Column(Float)
    prob_under_25 = Column(Float)
    prob_over_35 = Column(Float)
    prob_under_35 = Column(Float)
    prob_over_45 = Column(Float)
    prob_under_45 = Column(Float)
    prob_gg = Column(Float)
    prob_ng = Column(Float)
    prob_dc_1x = Column(Float)
    prob_dc_12 = Column(Float)
    prob_dc_2x = Column(Float)
    best_market = Column(String)
    best_prediction = Column(String)
    best_probability = Column(Float)
    confidence_score = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())