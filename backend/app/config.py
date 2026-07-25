import os
from dotenv import load_dotenv

load_dotenv()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    raise ValueError("ADMIN_PASSWORD must be set in .env file")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "2290140305483")
DATABASE_URL = "sqlite:///./predictx.db"