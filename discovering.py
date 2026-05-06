import os
from typing import List, Optional
import json
from fastapi import APIRouter, HTTPException
from openai import OpenAI, RateLimitError
from mistralai.client import Mistral
import openai
from pydantic import BaseModel

from queries import postgres_insert_query, postgres_select_query

router = APIRouter(prefix="/discovering", tags=["discovering"])

@router.get("/get_proposition_for_question/{question}/{subtheme}")
async def get_proposition_for_question(question: str, subtheme: str):
    api_key = os.environ["MISTRAL_API_KEY"]
    model = "mistral-large-latest"

    client = Mistral(api_key=api_key)

    prompt = """
                    Tu es un expert en """+subtheme+""". Ton objectif est de prooser une réponse à la question suivante : """+question+""". Ta proposition doit être claire et pédagogique. Elle doit mettre en évidence les points clés à retenir.
                    IMPORTANT :
                    - Réponds avec du JSON STRICT uniquement.
                    - N'ajoute AUCUN bloc markdown, AUCUN backtick, AUCUN texte avant/après.
                    - Le résultat doit être un OBJET structuré (pas une chaîne).
                    Fournis ta réponse exactement avec ce format JSON :
                    {
                        "reponse": "..........",
                        "points clés": []
                    }
                    """

    chat_response = client.chat.complete(
        model= model,
        messages = [
            {
                "role": "user",
                "content": prompt
            },
        ]
    )

    response_text = chat_response.choices[0].message.content
    # Extraction et affichage du JSON
    try:
        start_index = response_text.index("{")
        end_index = response_text.rindex("}") + 1
        json_content = response_text[start_index:end_index]
        response_json = json.loads(json_content)
        result = {
            "reponse": response_json["reponse"],
            "points_cles": response_json["points clés"]
        }
        return result

    except (ValueError, json.JSONDecodeError):
        content="Erreur : Impossible d'extraire le JSON."
    except openai.RateLimitError as e:
        content = "Rate limit reached. Waiting..."

    
    return content