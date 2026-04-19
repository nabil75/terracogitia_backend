
import os

from fastapi import APIRouter, HTTPException
from openai import OpenAI, RateLimitError
import json
import ast
import re
import openai
from mistralai.client import Mistral
from pydantic import BaseModel

import config

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

client = OpenAI(api_key=config.OPENAI_API_KEY)

class EvaluateResponseRequest(BaseModel):
    subtheme: str
    question: str
    response: str


async def _evaluate(subtheme: str, question: str, response: str):
    api_key = os.environ["MISTRAL_API_KEY"]
    client = Mistral(api_key=api_key)

    prompt = """
                    Tu es un expert en """+subtheme+""". Ton objectif est d'examiner la réponse d'un participant à une question spécifique : """+question+""". Ton analyse doit être factuelle, claire et pédagogique. Elle doit mettre en évidence les points clés à retenir.
                    Voici la réponse du participant : """+response+""".
                    Analyse cette réponse en te basant sur les critères suivants :
                    1. Pertinence : La réponse est-elle pertinente par rapport à la question posée ?
                    2. Précision : La réponse est-elle précise et factuellement correcte ?
                    3. Clarté : La réponse est-elle claire et bien structurée ?
                    4. Points clés : Quels sont les points clés à retenir de cette réponse ?
                    Fournis une analyse détaillée en utilisant ces critères, et souligne les éléments importants que le participant devrait retenir pour améliorer sa compréhension du sujet.
                    En fonction de ton évaluation, donne une note de 0 à 100 à la réponse du participant.
                    IMPORTANT :
                    - Réponds avec du JSON STRICT uniquement.
                    - N'ajoute AUCUN bloc markdown, AUCUN backtick, AUCUN texte avant/après.
                    - La clé "evaluation" doit être un OBJET structuré (pas une chaîne).
                    Fournis ta réponse exactement avec ce format JSON :
                    {
                        "evaluation": {
                            "pertinence": {
                                "analyse": "texte",
                                "note_partielle": 0-100
                            },
                            "précision": {
                                "analyse": "texte",
                                "note_partielle": 0-100
                            },
                            "clarté": {
                                "analyse": "texte",
                                "note_partielle": 0-100
                            },
                            "synthèse": {
                                "points_forts": ["..."],
                                "points_faibles": ["..."],
                                "conseils_pédagogiques": ["..."]
                            }
                        },
                        "note": 0-100,
                        "points_clés": ["point clé 1", "point clé 2", "point clé 3"]
                    }
                    """

    model_candidates = []
    configured_model = os.environ.get("MISTRAL_MODEL")
    if configured_model:
        model_candidates.append(configured_model)
    model_candidates.extend(["mistral-medium-latest", "mistral-small-latest", "mistral-medium"])

    seen_models = set()
    deduped_models = []
    for candidate in model_candidates:
        if candidate not in seen_models:
            deduped_models.append(candidate)
            seen_models.add(candidate)

    chat_response = None
    last_error = None
    for model_name in deduped_models:
        try:
            chat_response = client.chat.complete(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            )
            break
        except RateLimitError as e:
            raise HTTPException(
                status_code=429,
                detail="Rate limit atteint pour le service d'évaluation."
            ) from e
        except Exception as e:
            last_error = e
            continue

    if chat_response is None:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur du service d'évaluation IA: {str(last_error)}"
        ) from last_error

    response_text = chat_response.choices[0].message.content
    print("Réponse brute du modèle d'évaluation :", response_text)
    if isinstance(response_text, list):
        response_text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in response_text
        )

    print("Réponse brute du modèle d'évaluation :", response_text)
    response_text = (response_text or "").strip()

    # The model can return extra text around JSON, so extract the JSON object.
    parsed = {}
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        try:
            start_index = response_text.index("{")
            end_index = response_text.rindex("}") + 1
            json_block = response_text[start_index:end_index]
            try:
                parsed = json.loads(json_block)
            except json.JSONDecodeError:
                # Some model outputs are Python-like dicts (single quotes, etc.).
                parsed = ast.literal_eval(json_block)
        except (ValueError, SyntaxError, json.JSONDecodeError):
            parsed = {}

    if not isinstance(parsed, dict):
        parsed = {}

    def _extract_json_object_from_text(raw_text):
        if not isinstance(raw_text, str):
            return None
        text = raw_text.strip()
        if not text:
            return None

        # Remove markdown fences if present: ```json ... ``` or ``` ... ```
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            loaded = json.loads(text)
            return loaded if isinstance(loaded, dict) else None
        except json.JSONDecodeError:
            pass

        try:
            start_index = text.index("{")
            end_index = text.rindex("}") + 1
            json_block = text[start_index:end_index]
            try:
                loaded = json.loads(json_block)
            except json.JSONDecodeError:
                loaded = ast.literal_eval(json_block)
            return loaded if isinstance(loaded, dict) else None
        except (ValueError, SyntaxError, json.JSONDecodeError):
            return None

    evaluation_raw = (
        parsed.get("evaluation")
        or parsed.get("analyse")
        or parsed.get("analysis")
        or ""
    )

    # Accept multiple model shapes:
    # 1) evaluation is already a dict with pertinence/précision/clarté
    # 2) evaluation is a string containing a JSON object (often fenced)
    # 3) top-level object contains nested { "evaluation": {...}, "note": ..., "points_clés": ... } as text
    nested_from_evaluation = None
    if isinstance(evaluation_raw, dict):
        evaluation_value = evaluation_raw
    else:
        nested_from_evaluation = _extract_json_object_from_text(str(evaluation_raw))
        if isinstance(nested_from_evaluation, dict):
            if isinstance(nested_from_evaluation.get("evaluation"), dict):
                evaluation_value = nested_from_evaluation.get("evaluation")
            elif any(
                key in nested_from_evaluation
                for key in ("pertinence", "précision", "clarte", "clarté")
            ):
                evaluation_value = nested_from_evaluation
            else:
                evaluation_value = str(evaluation_raw).strip()
        else:
            evaluation_value = str(evaluation_raw).strip()

    raw_note = parsed.get("note")
    if raw_note is None and isinstance(nested_from_evaluation, dict):
        raw_note = nested_from_evaluation.get("note")
    note_value = None
    if isinstance(raw_note, bool):
        note_value = None
    elif isinstance(raw_note, (int, float)):
        note_value = int(raw_note)
    elif isinstance(raw_note, str):
        match_note = re.search(r"(\d{1,3})", raw_note)
        if match_note:
            note_value = int(match_note.group(1))

    if note_value is None:
        # Fallback: if "note" key is malformed/missing, try from full model answer.
        match_note = re.search(r"(\d{1,3})\s*(?:/|sur)?\s*100", response_text, flags=re.IGNORECASE)
        if match_note:
            note_value = int(match_note.group(1))

    if note_value is None:
        note_value = 0
    note_value = max(0, min(100, note_value))

    raw_points = (
        parsed.get("points_clés")
        or parsed.get("points_cles")
        or parsed.get("points clés")
        or parsed.get("points_cles_a_retenir")
        or []
    )
    if (raw_points is None or raw_points == []) and isinstance(nested_from_evaluation, dict):
        raw_points = (
            nested_from_evaluation.get("points_clés")
            or nested_from_evaluation.get("points_cles")
            or nested_from_evaluation.get("points clés")
            or nested_from_evaluation.get("points_cles_a_retenir")
            or []
        )

    if raw_points is None:
        raw_points = []
    if isinstance(raw_points, str):
        raw_points = [item.strip("- \t") for item in raw_points.split("\n") if item.strip()]
    elif not isinstance(raw_points, list):
        raw_points = [str(raw_points)]

    points_cles_value = [str(item).strip() for item in raw_points if str(item).strip()]

    if not evaluation_value:
        # Keep response usable even if the model misses the expected key.
        evaluation_value = response_text

    return {
        "evaluation": evaluation_value,
        "note": note_value,
        "points_clés": points_cles_value,
    }

@router.get("/evaluate_response/{subtheme}/{question}/{response}")
async def evaluate_response(subtheme: str, question: str, response: str):
    return await _evaluate(subtheme, question, response)


@router.post("/evaluate_response")
async def evaluate_response_post(payload: EvaluateResponseRequest):
    return await _evaluate(payload.subtheme, payload.question, payload.response)


async def auto_generate_questionnaire_mistral(role, objet_comprendre, objet_mesurer, finalite, selectedThemes, modelSelected):
    api_key = os.environ["MISTRAL_API_KEY"]
    model = modelSelected

    client = Mistral(api_key=api_key)

    chat_response = client.chat.complete(
        model= model,
        messages = [
            {

            },
        ]
    )

    response_text = chat_response.choices[0].message.content
    # Extraction et affichage du JSON
    try:
        start_index = response_text.index("{")
        end_index = response_text.rindex("}") + 1
        json_content = response_text[start_index:end_index]

        # Charger le contenu JSON et afficher
        questionnaire_json = json.loads(json_content)
        # print(json.dumps(questionnaire_json, indent=2, ensure_ascii=False))
        content = json.dumps(questionnaire_json, indent=2, ensure_ascii=False)
        return content

    except (ValueError, json.JSONDecodeError):
        content="Erreur : Impossible d'extraire le JSON."
    except openai.RateLimitError as e:
        content = "Rate limit reached. Waiting..."

    return content