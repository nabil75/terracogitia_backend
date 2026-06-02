import json
import os

import openai
from mistralai.client import Mistral


async def evaluate_response_with_mistral(subtheme: str, question: str, response: str):
    api_key = os.environ["MISTRAL_API_KEY"]
    client = Mistral(api_key=api_key)
    prompt = """
                    Tu es un expert en """ + subtheme + """. Ton objectif est d'examiner la réponse d'un participant à une question spécifique : """ + question + """. Ton analyse doit être factuelle, claire et pédagogique. Elle doit mettre en évidence les points clés à retenir.
                    Voici la réponse du participant : """ + response + """.
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
                    """
    chat_response = client.chat.complete(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = chat_response.choices[0].message.content
    try:
        start_index = response_text.index("{")
        end_index = response_text.rindex("}") + 1
        json_content = response_text[start_index:end_index]
        response_json = json.loads(json_content)
        return {
            "pertinence": response_json["evaluation"]["pertinence"]["analyse"],
            "pertinence_note": response_json["evaluation"]["pertinence"]["note_partielle"],
            "precision": response_json["evaluation"]["precision"]["analyse"],
            "precision_note": response_json["evaluation"]["precision"]["note_partielle"],
            "clarte": response_json["evaluation"]["clarte"]["analyse"],
            "clarte_note": response_json["evaluation"]["clarte"]["note_partielle"],
            "note": response_json["note"],
            "synthese_points_forts": response_json["synthese"]["points_forts"],
            "synthese_points_faibles": response_json["synthese"]["points_faibles"],
            "synthese_conseils_pedagogiques": response_json["synthese"]["conseils_pedagogiques"],
        }
    except (ValueError, json.JSONDecodeError):
        return "Erreur : Impossible d'extraire le JSON."
    except openai.RateLimitError:
        return "Rate limit reached. Waiting..."

