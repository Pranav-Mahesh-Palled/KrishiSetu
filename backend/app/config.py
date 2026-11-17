"""Application configuration and environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Locate and load .env file from project root or current working directory
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

DATA_GOV_API_KEY = os.getenv(
    "DATA_GOV_API_KEY",
    # OGD India public sample / demo resource key
    "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b",
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./krishisetu.db")
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
