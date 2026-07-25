from sqlalchemy import Column, Integer, String

from app.database import Base


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    api_id = Column(Integer, unique=True, nullable=True)
    name = Column(String, nullable=False)
    short_name = Column(String)
    crest_url = Column(String)