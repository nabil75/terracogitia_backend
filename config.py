from dotenv import load_dotenv
import os

# Charger le fichier .env
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("La clé OPENAI_API_KEY est manquante dans le fichier .env")