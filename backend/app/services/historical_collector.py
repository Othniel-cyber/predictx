from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.match import Match
from app.models.team import Team
from app.services.api_client import get_matches_by_date
from app.services.league_config import TOP_LEAGUES, SEASONS

HISTORICAL_DAYS = 120


def extract_score(match):
    status = match.get("status", {})
    home_data = match.get("home", {})
    away_data = match.get("away", {})
    if isinstance(status, dict) and status.get("finished"):
        hs = home_data.get("score") if isinstance(home_data, dict) else None
        aws = away_data.get("score") if isinstance(away_data, dict) else None
        return hs, aws
    if isinstance(status, dict) and status.get("cancelled"):
        hs = home_data.get("score") if isinstance(home_data, dict) else None
        aws = away_data.get("score") if isinstance(away_data, dict) else None
        return hs, aws
    return None, None


def map_status(status):
    if not status:
        return "SCHEDULED"
    if isinstance(status, dict):
        if status.get("cancelled"):
            return "CANCELLED"
        if status.get("finished"):
            return "FINISHED"
        if status.get("started"):
            return "LIVE"
    return "SCHEDULED"


def get_or_create_team(db: Session, fotmob_id, name):
    if not name:
        return None
    team = db.query(Team).filter_by(api_id=fotmob_id).first()
    if not team:
        team = db.query(Team).filter_by(name=name).first()
    if not team:
        team = Team(api_id=fotmob_id, name=name)
        db.add(team)
        db.commit()
        db.refresh(team)
    elif not team.api_id:
        team.api_id = fotmob_id
        db.commit()
    return team


def collect_historical_matches(db: Session, days_back=HISTORICAL_DAYS):
    today = datetime.now()
    total = 0

    for offset in range(days_back, 0, -1):
        day = today - timedelta(days=offset)
        date_str = day.strftime("%Y%m%d")
        try:
            data = get_matches_by_date(date_str)
        except Exception:
            continue
        for league in data.get("leagues", []):
            lname = league.get("name", "")
            for m in league.get("matches", []):
                api_id = m.get("id")
                if not api_id:
                    continue
                existing = db.query(Match).filter_by(api_id=api_id).first()
                if existing:
                    continue
                home_data = m.get("home", {})
                away_data = m.get("away", {})
                home_team = get_or_create_team(db, home_data.get("id"), home_data.get("name", ""))
                away_team = get_or_create_team(db, away_data.get("id"), away_data.get("name", ""))
                if not home_team or not away_team:
                    continue
                hs, aws = extract_score(m)
                st = m.get("status", {})
                utc_time = st.get("utcTime") if isinstance(st, dict) else None
                try:
                    match_date = datetime.fromisoformat(utc_time.replace("Z", "")) if utc_time else day
                except Exception:
                    match_date = day
                match = Match(
                    api_id=api_id,
                    competition=lname,
                    home_team_id=home_team.id,
                    away_team_id=away_team.id,
                    home_team_name=home_team.name,
                    away_team_name=away_team.name,
                    date=match_date,
                    status=map_status(st),
                    home_score=hs,
                    away_score=aws,
                )
                db.add(match)
                total += 1
        db.commit()

    return total