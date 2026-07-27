import os
from dotenv import load_dotenv

load_dotenv()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "2290140305483")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./predictx.db")
FIREBASE_KEY_PATH = os.getenv("FIREBASE_KEY_PATH", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,https://predictx.onrender.com")
API_UPDATE_KEY = os.getenv("API_UPDATE_KEY", "")