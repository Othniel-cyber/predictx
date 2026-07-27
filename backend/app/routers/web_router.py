import secrets
from datetime import datetime
import hashlib

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.team import Team
from app.models.prediction import Prediction
from app.models.match import Match
from app.models.coupon import Coupon
from app.models.coupon_match import CouponMatch
from app.config import ADMIN_PASSWORD, WHATSAPP_NUMBER
from app.services.coupon_service import generate_daily_coupon
from app.firebase_db import get_user, get_user_by_email, create_user, update_subscription, remove_subscription, get_all_users, search_users, get_auth, init_firebase

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["WHATSAPP_NUMBER"] = WHATSAPP_NUMBER


def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def _csrf_token(request: Request):
    token = request.cookies.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
    return token


def verify_csrf(request: Request, csrf: str = Form("")):
    stored = request.cookies.get("csrf_token")
    if not stored or stored != csrf:
        raise HTTPException(status_code=403, detail="CSRF token invalide")


def get_session_user(request: Request):
    uid = request.cookies.get("user_id")
    if uid:
        return get_user(uid)
    return None


def is_subscribed(user):
    if not user:
        return False
    if user.get("subscription_type") == "none":
        return False
    if user.get("subscription_expiry"):
        if isinstance(user["subscription_expiry"], datetime):
            if user["subscription_expiry"] < datetime.now():
                return False
    return True


_firebase_status = None

def firebase_available():
    global _firebase_status
    if _firebase_status is not None:
        return _firebase_status
    from app.config import FIREBASE_KEY_JSON
    if not FIREBASE_KEY_JSON:
        _firebase_status = False
        return False
    try:
        from app.firebase_db import get_db
        db = get_db()
        for doc in db.collection("_probe").limit(1).stream():
            pass
        _firebase_status = True
    except Exception:
        _firebase_status = False
    return _firebase_status


def get_logo_url(team_id, db):
    if not team_id:
        return None
    team = db.query(Team).filter_by(id=team_id).first()
    if team and team.crest_url:
        return team.crest_url
    if team and team.api_id:
        return f"https://images.fotmob.com/image_resources/logo/teamlogo/{team.api_id}.png"
    return None


def get_initials(name):
    parts = name.split() if name else ["?"]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()[:2]
    return (parts[0][:2]).upper()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request)
    subscribed = True

    generate_daily_coupon(db)
    coupon = db.query(Coupon).order_by(Coupon.date.desc()).first()

    coupon_matches = []
    if coupon and subscribed:
        for cm in db.query(CouponMatch).filter_by(coupon_id=coupon.id).all():
            m = db.query(Match).filter_by(id=cm.match_id).first()
            p = db.query(Prediction).filter_by(id=cm.prediction_id).first()
            if m and p:
                coupon_matches.append({
                    "match_id": m.id,
                    "home_team": m.home_team_name, "away_team": m.away_team_name,
                    "home_logo": get_logo_url(m.home_team_id, db),
                    "away_logo": get_logo_url(m.away_team_id, db),
                    "home_initials": get_initials(m.home_team_name),
                    "away_initials": get_initials(m.away_team_name),
                    "competition": m.competition, "date": m.date,
                    "best_market": p.best_market,
                    "best_probability": round(p.best_probability * 100, 1),
                    "confidence_score": p.confidence_score, "status": cm.status,
                    "home_score": m.home_score, "away_score": m.away_score,
                })

    total_preds = db.query(Prediction).count()
    total_coupons = db.query(Coupon).count()
    total_leagues = db.query(Match.competition).distinct().count()
    mois = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"]
    jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    now = datetime.now()
    today_date = f"{jours[now.weekday()]} {now.day} {mois[now.month-1]} {now.year}"

    return templates.TemplateResponse(request, "index.html", {
        "coupon": coupon, "coupon_matches": coupon_matches,
        "today_date": today_date,
        "stats": {"total_predictions": total_preds, "total_coupons": total_coupons, "total_leagues": total_leagues},
        "subscribed": subscribed,
        "session": {"user_id": user.get("id") if user else None},
    })


@router.get("/predictions", response_class=HTMLResponse)
def predictions_page(request: Request, all: bool = False, db: Session = Depends(get_db)):
    user = get_session_user(request)
    subscribed = True

    query = db.query(Prediction).join(Match)
    if not all:
        query = query.filter(Match.status == "SCHEDULED")
    preds = query.order_by(Prediction.confidence_score.desc()).all()

    by_league = {}
    for p in preds:
        m = db.query(Match).filter_by(id=p.match_id).first()
        if not m:
            continue
        league = m.competition or "Autres"
        if league not in by_league:
            by_league[league] = []
        by_league[league].append({
            "match": m,
            "prediction": p,
            "home_logo": get_logo_url(m.home_team_id, db),
            "away_logo": get_logo_url(m.away_team_id, db),
        })

    return templates.TemplateResponse(request, "predictions.html", {
        "predictions_by_league": by_league,
        "subscribed": subscribed,
        "all": all,
        "session": {"user_id": user.get("id") if user else None},
    })


@router.get("/history", response_class=HTMLResponse)
def history(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request)
    coupons = db.query(Coupon).order_by(Coupon.date.desc()).limit(30).all()

    result = []
    for c in coupons:
        items = []
        for cm in db.query(CouponMatch).filter_by(coupon_id=c.id).all():
            m = db.query(Match).filter_by(id=cm.match_id).first()
            p = db.query(Prediction).filter_by(id=cm.prediction_id).first()
            items.append({
                "match": m,
                "prediction": p,
                "status": cm.status,
                "home_logo": get_logo_url(m.home_team_id, db) if m else None,
                "away_logo": get_logo_url(m.away_team_id, db) if m else None,
            })
        result.append({"id": c.id, "date": c.date, "status": c.status, "won_bets": c.won_bets, "total_bets": c.total_bets, "matches": items})

    return templates.TemplateResponse(request, "history.html", {
        "coupons": result,
        "session": {"user_id": user.get("id") if user else None},
    })


@router.get("/subscribe", response_class=HTMLResponse)
def subscribe(request: Request):
    return templates.TemplateResponse(request, "subscribe.html", {"session": {"user_id": None}}) 


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"session": {"user_id": None}})


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    user_data = get_user_by_email(email)
    if not user_data or user_data.get("password") != hash_password(password):
        return templates.TemplateResponse(request, "login.html", {"session": {"user_id": None}, "error": "Email ou mot de passe incorrect"})
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(key="user_id", value=user_data["id"], max_age=86400 * 365)
    return resp


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"session": {"user_id": None}})


@router.post("/register")
def register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    existing = get_user_by_email(email)
    if existing:
        return templates.TemplateResponse(request, "register.html", {"session": {"user_id": None}, "error": "Cet email est déjà utilisé"})
    auth = get_auth()
    user = auth.create_user(email=email, password=password, display_name=name)
    create_user(user.uid, name, email)
    from app.firebase_db import get_db as get_fb_db
    get_fb_db().collection("users").document(user.uid).update({"password": hash_password(password)})
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(key="user_id", value=user.uid, max_age=86400 * 365)
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("user_id")
    return resp


@router.get("/account", response_class=HTMLResponse)
def account(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "account.html", {"user": user, "session": {"user_id": user.get("id")}})


@router.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, db: Session = Depends(get_db)):
    total_preds = db.query(Prediction).count()
    total = db.query(CouponMatch).count()
    won = db.query(CouponMatch).filter(CouponMatch.status == "WON").count()
    total_coupons = db.query(Coupon).count()
    overall_acc = round((won / total * 100) if total else 0, 1)

    leagues = db.query(Match.competition).distinct().all()
    league_stats = []
    for (league,) in leagues:
        if not league:
            continue
        total_l = db.query(CouponMatch).join(Prediction).join(Match).filter(Match.competition == league).count()
        won_l = db.query(CouponMatch).join(Prediction).join(Match).filter(
            Match.competition == league, CouponMatch.status == "WON"
        ).count()
        league_stats.append({"league": league, "total": total_l, "correct": won_l, "accuracy": round((won_l / total_l * 100) if total_l else 0, 1)})
    league_stats.sort(key=lambda x: x["accuracy"], reverse=True)

    confidence_stats = []
    for level in range(10, 0, -1):
        total_l = db.query(CouponMatch).join(Prediction).filter(Prediction.confidence_score == level).count()
        won_l = db.query(CouponMatch).join(Prediction).filter(
            Prediction.confidence_score == level, CouponMatch.status == "WON"
        ).count()
        confidence_stats.append({"level": level, "total": total_l, "correct": won_l, "accuracy": round((won_l / total_l * 100) if total_l else 0, 1)})

    return templates.TemplateResponse(request, "stats.html", {
        "stats": {"overall_accuracy": overall_acc, "total_predictions": total_preds, "total_coupons": total_coupons, "model_accuracy": 90.9},
        "league_stats": league_stats,
        "confidence_stats": confidence_stats,
        "session": {"user_id": None},
    })


@router.get("/top-picks", response_class=HTMLResponse)
def top_picks(request: Request, min_confidence: int = 0, db: Session = Depends(get_db)):
    user = get_session_user(request)
    subscribed = True
    query = db.query(Prediction).join(Match).filter(Match.status == "SCHEDULED")
    if min_confidence > 0:
        query = query.filter(Prediction.confidence_score >= min_confidence)
    preds = query.order_by(Prediction.confidence_score.desc(), Prediction.best_probability.desc()).limit(30).all()
    predictions = []
    for p in preds:
        m = db.query(Match).filter_by(id=p.match_id).first()
        if m:
            predictions.append({
                "match": m,
                "prediction": p,
                "home_logo": get_logo_url(m.home_team_id, db),
                "away_logo": get_logo_url(m.away_team_id, db),
            })
    return templates.TemplateResponse(request, "top_picks.html", {
        "predictions": predictions, "min_confidence": min_confidence,
        "subscribed": subscribed,
        "session": {"user_id": user.get("id") if user else None},
    })


@router.get("/live", response_class=HTMLResponse)
def live_matches(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request)
    from app.services.data_collector import refresh_live_scores
    refresh_live_scores(db)
    live = db.query(Match).filter(Match.status == "LIVE").all()
    live_matches = []
    for m in live:
        p = db.query(Prediction).filter_by(match_id=m.id).first()
        live_matches.append({
            "match": m,
            "prediction": p,
            "home_logo": get_logo_url(m.home_team_id, db),
            "away_logo": get_logo_url(m.away_team_id, db),
        })
    return templates.TemplateResponse(request, "live.html", {
        "live_matches": live_matches,
        "subscribed": True,
        "session": {"user_id": user.get("id") if user else None},
    })


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse(request, "settings.html", {
        "user": user, "success": None, "error": None, "session": {"user_id": user.get("id")},
    })


@router.post("/settings")
def update_settings(request: Request, name: str = Form(None), email: str = Form(None),
                    current_password: str = Form(None), new_password: str = Form(None)):
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/login")

    from app.firebase_db import get_db as get_fb_db
    fb_db = get_fb_db()
    uid = user["id"]
    updates = {}

    if name:
        updates["name"] = name
    if email:
        existing = get_user_by_email(email)
        if existing and existing.get("id") != uid:
            return templates.TemplateResponse(request, "settings.html", {"session": {"user_id": uid}, "user": user, "success": None, "error": "Cet email est déjà utilisé"})
        updates["email"] = email

    if current_password and new_password:
        if user.get("password") != hash_password(current_password):
            return templates.TemplateResponse(request, "settings.html", {"session": {"user_id": uid}, "user": user, "success": None, "error": "Mot de passe actuel incorrect"})
        updates["password"] = hash_password(new_password)

    if updates:
        fb_db.collection("users").document(uid).update(updates)
        user.update(updates)

    return templates.TemplateResponse(request, "settings.html", {"session": {"user_id": uid}, "user": user, "success": "Paramètres mis à jour avec succès", "error": None})


@router.get("/contact", response_class=HTMLResponse)
def contact(request: Request):
    return templates.TemplateResponse(request, "contact.html", {"session": {"user_id": None}})


@router.get("/cgu", response_class=HTMLResponse)
def cgu(request: Request):
    return templates.TemplateResponse(request, "cgu.html", {"session": {"user_id": None}})


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, password: str = None, search: str = None):
    logged_in = request.cookies.get("admin_token") == hash_password(ADMIN_PASSWORD)
    users = []
    if logged_in and search:
        users = search_users(search)
    elif logged_in:
        users = get_all_users()
    csrf = _csrf_token(request)
    resp = templates.TemplateResponse(request, "admin.html", {
        "logged_in": logged_in, "users": users, "search": search, "session": {"user_id": None}, "csrf_token": csrf,
    })
    resp.set_cookie(key="csrf_token", value=csrf, max_age=86400, httponly=True, samesite="lax")
    return resp


@router.post("/admin")
def admin_login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        resp = RedirectResponse(url="/admin", status_code=303)
        resp.set_cookie(key="admin_token", value=hash_password(ADMIN_PASSWORD), max_age=86400)
        return resp
    return templates.TemplateResponse(request, "admin.html", {"session": {"user_id": None}, "logged_in": False})


@router.post("/admin/unlock")
def admin_unlock(request: Request, user_id: str = Form(...), plan: str = Form(...), csrf: str = Form("")):
    verify_csrf(request, csrf)
    update_subscription(user_id, plan)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/lock")
def admin_lock(request: Request, user_id: str = Form(...), csrf: str = Form("")):
    verify_csrf(request, csrf)
    remove_subscription(user_id)
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/api/subscription-status")
def subscription_status(request: Request):
    user = get_session_user(request)
    if not user:
        return {"subscribed": False, "authenticated": False}
    return {
        "subscribed": is_subscribed(user),
        "authenticated": True,
        "subscription_type": user.get("subscription_type", "none"),
        "subscription_expiry": str(user.get("subscription_expiry")) if user.get("subscription_expiry") else None,
    }


@router.get("/match/{match_id}", response_class=HTMLResponse)
def match_detail(request: Request, match_id: int, db: Session = Depends(get_db)):
    user = get_session_user(request)
    subscribed = is_subscribed(user)
    m = db.query(Match).filter_by(id=match_id).first()
    if not m:
        return templates.TemplateResponse(request, "404.html", {"session": {"user_id": user.get("id") if user else None}})
    p = db.query(Prediction).filter_by(match_id=match_id).first()

    h2h = []
    if m.home_team_id and m.away_team_id:
        h2h = db.query(Match).filter(
            Match.id != match_id,
            Match.home_score.isnot(None),
            Match.away_score.isnot(None),
            ((Match.home_team_id == m.home_team_id) & (Match.away_team_id == m.away_team_id)) |
            ((Match.home_team_id == m.away_team_id) & (Match.away_team_id == m.home_team_id))
        ).order_by(Match.date.desc()).limit(10).all()

    return templates.TemplateResponse(request, "match_detail.html", {
        "match": m,
        "prediction": p,
        "h2h": h2h,
        "subscribed": subscribed,
        "home_logo": get_logo_url(m.home_team_id, db),
        "away_logo": get_logo_url(m.away_team_id, db),
        "session": {"user_id": user.get("id") if user else None},
    })