
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.theme import router as theme_router
from routers.evaluation import router as evaluation_router
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


# Configure CORS
origins = [
    "http://localhost:4200",  # Angular frontend
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
app.include_router(evaluation_router)

