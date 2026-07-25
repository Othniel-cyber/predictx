from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers.coupon_router import router as coupon_router
from app.routers.web_router import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    try:
        from app.firebase_db import init_firebase
        init_firebase()
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Firebase init skipped")
    yield


app = FastAPI(title="PredictX API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(coupon_router)
app.include_router(web_router)


@app.get("/api")
def api_root():
    return {"message": "PredictX API - Pronostics football IA"}


@app.get("/api/update")
def update_data():
    from app.database import SessionLocal
    from app.services.data_collector import save_matches_to_db
    from app.services.prediction_engine import predict_all_upcoming_matches
    from app.services.coupon_service import generate_daily_coupon, update_coupon_results
    db = SessionLocal()
    try:
        save_matches_to_db(db)
        update_coupon_results(db)
        predictions = predict_all_upcoming_matches(db)
        coupon = generate_daily_coupon(db)
        return {
            "message": "Mise à jour terminée",
            "predictions": len(predictions),
            "coupon": coupon.id if coupon else None,
            "coupon_status": coupon.status if coupon else None,
        }
    finally:
        db.close()