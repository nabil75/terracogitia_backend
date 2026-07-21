"""Seed catalog tables for cognitive challenges."""

import json

from challenge_framework.catalog_seed import (
    ACHIEVEMENTS,
    COGNITIVE_OPERATIONS,
    COMPATIBILITY_MATRIX,
    GAME_MECHANICS,
)
from queries import postgres_select_query


async def seed_challenge_catalog(conn) -> None:
    for op in COGNITIVE_OPERATIONS:
        await conn.execute(
            """
            INSERT INTO cognitive_operation_catalog (
                operation_key, family, label_fr, label_en,
                definition_fr, definition_en, evaluates_fr, evaluates_en,
                pyramid_levels, examples
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10::jsonb)
            ON CONFLICT (operation_key) DO UPDATE SET
                family = EXCLUDED.family,
                label_fr = EXCLUDED.label_fr,
                label_en = EXCLUDED.label_en,
                definition_fr = EXCLUDED.definition_fr,
                definition_en = EXCLUDED.definition_en,
                evaluates_fr = EXCLUDED.evaluates_fr,
                evaluates_en = EXCLUDED.evaluates_en,
                pyramid_levels = EXCLUDED.pyramid_levels,
                examples = EXCLUDED.examples
            """,
            op["key"],
            op["family"],
            op["label_fr"],
            op["label_en"],
            op["definition_fr"],
            op["definition_en"],
            op["evaluates_fr"],
            op["evaluates_en"],
            json.dumps(op["pyramid_levels"]),
            json.dumps(op["examples"]),
        )

    for mech in GAME_MECHANICS:
        await conn.execute(
            """
            INSERT INTO game_mechanic_catalog (
                mechanic_key, label_fr, label_en,
                description_fr, description_en,
                advantages_fr, limitations_fr,
                compatible_operations, compatible_pyramid_levels
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb)
            ON CONFLICT (mechanic_key) DO UPDATE SET
                label_fr = EXCLUDED.label_fr,
                label_en = EXCLUDED.label_en,
                description_fr = EXCLUDED.description_fr,
                description_en = EXCLUDED.description_en,
                advantages_fr = EXCLUDED.advantages_fr,
                limitations_fr = EXCLUDED.limitations_fr,
                compatible_operations = EXCLUDED.compatible_operations,
                compatible_pyramid_levels = EXCLUDED.compatible_pyramid_levels
            """,
            mech["key"],
            mech["label_fr"],
            mech["label_en"],
            mech["description_fr"],
            mech["description_en"],
            mech["advantages_fr"],
            mech["limitations_fr"],
            json.dumps(mech["compatible_operations"]),
            json.dumps(mech["compatible_pyramid_levels"]),
        )

    for operation, mechanic, score in COMPATIBILITY_MATRIX:
        await conn.execute(
            """
            INSERT INTO operation_mechanic_compatibility (operation_key, mechanic_key, score)
            VALUES ($1, $2, $3)
            ON CONFLICT (operation_key, mechanic_key) DO UPDATE SET score = EXCLUDED.score
            """,
            operation,
            mechanic,
            score,
        )

    for ach in ACHIEVEMENTS:
        await conn.execute(
            """
            INSERT INTO achievement_definition (
                achievement_key, title_fr, title_en,
                description_fr, description_en, criteria, xp_reward
            ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7)
            ON CONFLICT (achievement_key) DO UPDATE SET
                title_fr = EXCLUDED.title_fr,
                title_en = EXCLUDED.title_en,
                description_fr = EXCLUDED.description_fr,
                description_en = EXCLUDED.description_en,
                criteria = EXCLUDED.criteria,
                xp_reward = EXCLUDED.xp_reward
            """,
            ach["key"],
            ach["title_fr"],
            ach["title_en"],
            ach["description_fr"],
            ach["description_en"],
            json.dumps(ach["criteria"]),
            ach["xp_reward"],
        )


async def get_compatibility_matrix() -> list[dict]:
    rows = await postgres_select_query(
        """
        SELECT operation_key AS operation, mechanic_key AS mechanic, score
        FROM operation_mechanic_compatibility
        ORDER BY operation_key, mechanic_key
        """
    )
    return [dict(r) for r in rows]
