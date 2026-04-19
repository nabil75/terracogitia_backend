import asyncio
import json
from pathlib import Path
import sys

# Ajoute le chemin racine du projet au PYTHONPATH
sys.path.append(str(Path(__file__).parent.parent))
from database import init_db, close_db
from queries import postgres_insert_query

async def insert_question(libelle, type_question, id_subtheme):
    query = """
    INSERT INTO question (libelle, type, id_subtheme)
    VALUES ($1, $2, $3)
    RETURNING id_question;
    """
    id_question = await postgres_insert_query(query, libelle, type_question, id_subtheme)
    return id_question

async def insert_options(options, id_question, id_subtheme):
    for option in options:
        query = """
        INSERT INTO option (libelle, id_question, id_subtheme)
        VALUES ($1, $2, $3);
        """
        await postgres_insert_query(query, option, id_question, id_subtheme)

async def process_questions_from_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        questions = json.load(file)

    for question in questions:
        libelle = question["libelle"]
        type_question = question["type"]
        id_subtheme = question["id_subtheme"]
        options = question["options"]

        id_question = await insert_question(libelle, type_question, id_subtheme)
        if id_question:
            await insert_options(options, id_question, id_subtheme)

async def main():
    # Initialise le pool de connexions
    await init_db()

    # Appelle votre fonction principale
    await process_questions_from_json("questions.json")

    # Ferme le pool de connexions
    await close_db()

if __name__ == "__main__":
    asyncio.run(main())