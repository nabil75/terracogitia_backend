import asyncio
from pathlib import Path
import shutil
from unittest import result
from fastapi import APIRouter, File, HTTPException, UploadFile
from typing import List
from fastapi import Response
from fastapi.responses import FileResponse
import whisper
import json
from io import StringIO
from openai import BaseModel
from uuid import uuid4
from queries import *
from fastapi import APIRouter, HTTPException
from typing import List
from models import Theme, SubTheme
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, MetaData, Table, select
from sqlalchemy.orm import sessionmaker


router = APIRouter(prefix="/themes", tags=["themes"])

model = whisper.load_model("base")
DATA_DIR = Path("data/audio")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Modèle Pydantic pour la réponse
class SubTheme(BaseModel):
    id: int
    label: str
    description: str

class Theme(BaseModel):
    id: int
    label: str
    tagline: str
    description: str
    subThemes: List[SubTheme]



@router.post("/get_transcribe_audio")
async def get_transcribe_audio(audio: UploadFile = File(...)):
    
    # 1️⃣ fichier temporaire
    temp_path = Path(f"temp_{uuid4()}.webm")

    with temp_path.open("wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    # 2️⃣ id unique définitif
    audio_id = uuid4()
    final_path = DATA_DIR / f"{audio_id}.webm"

    try:
        # 3️⃣ transcription
        result = model.transcribe(str(temp_path), language="fr")
        text = result["text"]

        # 4️⃣ sauvegarde définitive
        shutil.move(str(temp_path), final_path)

    finally:
        # 5️⃣ sécurité si une erreur survient
        if temp_path.exists():
            temp_path.unlink()

    return {
        "id": str(audio_id),
        "text": text
    }

@router.get("/get_audio_file/{id_audio}")
def get_audio(id_audio: str):

    audio_path = DATA_DIR / f"{id_audio}.webm"

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio introuvable")

    return FileResponse(
        path=audio_path,
        media_type="audio/webm",
        filename=f"{id_audio}.webm"
    )

@router.get("/all_themes", response_model=List[Theme])
async def get_all_themes():
    try :
        query = """
            SELECT json_agg(theme_data)
            FROM (
                SELECT 
                    t.id_theme AS id,
                    t.label,
                    t.tagline,
                    t.description,
                    COALESCE(
                        json_agg(
                            json_build_object(
                                'id', s.id_subtheme,
                                'label', s.label,
                                'description', s.description
                            )
                        ) FILTER (WHERE s.id_subtheme IS NOT NULL),
                        '[]'::json
                    ) AS "subThemes"
                FROM theme t
                LEFT JOIN subtheme s ON s.id_theme = t.id_theme
                GROUP BY t.id_theme, t.label, t.tagline, t.description
                ORDER BY t.id_theme
            ) theme_data;
        """

        result = await postgres_select_query(query)

        data = result[0]["json_agg"]

        # Sécurité : si c’est une string
        if isinstance(data, str):
            data = json.loads(data)

        return data or []

    except Exception as e:
        print("ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{theme_id}", status_code=204)
async def delete_theme(theme_id: int):
    try:
        await postgres_delete_query(
            "DELETE FROM theme WHERE id_theme = $1",
            theme_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/getQuestionsBySubTheme/{subtheme_id}")
async def getQuestionsBySubTheme(subtheme_id: int):
    try:
        rows = await postgres_select_query(
            "SELECT * FROM question WHERE id_subtheme = $1",
            subtheme_id,
        )
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))