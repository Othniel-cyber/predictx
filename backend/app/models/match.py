from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float

from app.database import Base


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    api_id = Column(Integer, unique=True)
    competition = Column(String)
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    away_team_id = Column(Integer, ForeignKey("teams.id"))
    home_team_name = Column(String)
    away_team_name = Column(String)
    date = Column(DateTime)
    status = Column(String, default="SCHEDULED")
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)