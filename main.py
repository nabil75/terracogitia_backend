from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers.theme import router as theme_router, subthemes_router
from routers.evaluation import router as evaluation_router
from routers.discipline import router as discipline_router
from routers.question  import router as question_router
from routers.discovering import router as discovering_router
from routers.auth import router as auth_router
from routers.advanced_evaluation import router as advanced_evaluation_router
from database import init_db, close_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🔵 Startup
    await init_db()
    print("Database pool created")

    yield

    # 🔴 Shutdown
    await close_db()
    print("Database pool closed")

app = FastAPI(lifespan=lifespan)

_discover_media_dir = Path(__file__).resolve().parent / "data" / "discover_media"
_discover_media_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/media/discover",
    StaticFiles(directory=str(_discover_media_dir)),
    name="discover_media",
)

# Configure CORS
origins = [
    "http://localhost:4200",  # Angular frontend
    "http://127.0.0.1:4200",
    # Add more origins as needed, e.g., "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

app.include_router(theme_router)
app.include_router(subthemes_router)
app.include_router(evaluation_router)
app.include_router(discipline_router)
app.include_router(discovering_router)
app.include_router(question_router)
app.include_router(auth_router)
app.include_router(advanced_evaluation_router)

