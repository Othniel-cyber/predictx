from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.match import Match
from app.models.team import Team
from app.services.api_client import get_matches_by_date


def get_or_create_team(db: Session, fotmob_id, name):
    if not name:
        return None
    if not fotmob_id or fotmob_id == 0:
        fotmob_id = None
    team = db.query(Team).filter_by(api_id=fotmob_id).first()
    if not team:
        team = db.query(Team).filter_by(name=name).first()
    if not team:
        team = Team(api_id=fotmob_id, name=name, crest_url=f"https://images.fotmob.com/image_resources/logo/teamlogo/{fotmob_id}.png" if fotmob_id else None)
        try:
            db.add(team)
            db.commit()
            db.refresh(team)
        except IntegrityError:
            db.rollback()
            existing = db.query(Team).filter_by(api_id=fotmob_id).first()
            if existing:
                return existing
            existing = db.query(Team).filter_by(name=name).first()
            if existing:
                return existing
            db.add(team)
            db.commit()
            db.refresh(team)
    elif not team.api_id:
        team.api_id = fotmob_id
        team.crest_url = f"https://images.fotmob.com/image_resources/logo/teamlogo/{fotmob_id}.png"
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            other = db.query(Team).filter_by(api_id=fotmob_id).first()
            if other:
                return other
            team.api_id = fotmob_id
            db.commit()
    return team


def extract_score(match):
    status = match.get("status", {})
    home_data = match.get("home", {})
    away_data = match.get("away", {})
    hs = home_data.get("score") if isinstance(home_data, dict) else None
    aws = away_data.get("score") if isinstance(away_data, dict) else None
    if isinstance(status, dict) and status.get("finished"):
        return hs, aws
    if isinstance(status, dict) and status.get("cancelled"):
        return hs, aws
    return None, None


def map_status(fotmob_status):
    if not fotmob_status:
        return "SCHEDULED"
    if fotmob_status.get("cancelled"):
        return "CANCELLED"
    if fotmob_status.get("finished"):
        return "FINISHED"
    if fotmob_status.get("started"):
        return "LIVE"
    return "SCHEDULED"


def save_matches_to_db(db: Session, days_back=2, days_forward=5):
    today = datetime.now()
    for offset in range(-days_back, days_forward + 1):
        day = today + timedelta(days=offset)
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
                ts = m.get("timeTS")
                if ts:
                    match_date = datetime.fromtimestamp(ts / 1000)
                else:
                    match_date = day
                match = Match(
                    api_id=api_id,
                    competition=lname,
                    home_team_id=home_team.id,
                    away_team_id=away_team.id,
                    home_team_name=home_team.name,
                    away_team_name=away_team.name,
                    date=match_date,
                    status=map_status(m.get("status", {})),
                    home_score=hs,
                    away_score=aws,
                )
                db.add(match)
        db.commit()
    fix_match_dates(db)


def fix_match_dates(db: Session):
    import requests
    matches = db.query(Match).filter(Match.date == Match.date).all()
    for match in matches:
        if not match.api_id:
            continue
        try:
            data = requests.get(
                f"https://www.fotmob.com/api/data/matchDetails?id={match.api_id}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            ).json()
            utc = data.get("header", {}).get("status", {}).get("utcTime") or data.get("header", {}).get("utcTime")
            if utc:
                from datetime import timezone
                match.date = datetime.fromisoformat(utc.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass
    db.commit()


def refresh_live_scores(db: Session):
    import requests
    live = db.query(Match).filter(Match.status == "LIVE").all()
    for m in live:
        if not m.api_id:
            continue
        try:
            data = requests.get(
                f"https://www.fotmob.com/api/data/matchDetails?id={m.api_id}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            ).json()
            header = data.get("header", {})
            status = header.get("status", {})
            if status.get("finished"):
                m.status = "FINISHED"
            elif not status.get("started"):
                m.status = "SCHEDULED"
            home = header.get("home", data.get("home", {}))
            away = header.get("away", data.get("away", {}))
            if isinstance(home, dict) and home.get("score") is not None:
                m.home_score = home["score"]
            if isinstance(away, dict) and away.get("score") is not None:
                m.away_score = away["score"]
        except Exception:
            pass
    db.commit()