from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / '.env')

HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '8000'))
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')

ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv('ALLOWED_ORIGINS', '*').split(',') if origin.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ['*']

DATABASE_URL = os.getenv('DATABASE_URL', f"sqlite+aiosqlite:///{(BASE_DIR / 'jarvis.db').as_posix()}")

FIREBASE_CREDENTIALS = os.getenv('FIREBASE_CREDENTIALS', str(BASE_DIR / 'firebase-credentials.json'))

OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3')

VOSK_MODEL_PATH = os.getenv('VOSK_MODEL_PATH', str(BASE_DIR / 'models' / 'vosk-model-small-en-us'))

INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME', '')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD', '')

MUSIC_DIR = os.getenv('MUSIC_DIR', str(Path.home() / 'Music'))

FACES_DIR = BASE_DIR / 'faces'
FACES_DIR.mkdir(parents=True, exist_ok=True)

FACE_RECOGNITION_MODEL = os.getenv('FACE_RECOGNITION_MODEL', 'VGG-Face')
FACE_DETECTION_BACKEND = os.getenv('FACE_DETECTION_BACKEND', 'opencv')
FACE_DISTANCE_THRESHOLD = float(os.getenv('FACE_DISTANCE_THRESHOLD', '0.4'))
