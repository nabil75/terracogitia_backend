"""Tests des heuristiques d'intention de question."""

from challenge_framework.generator import (
    _filter_contextual_pairs,
    _is_generic_challenge_token,
    build_investigation_content,
)
from challenge_framework.question_intent import (
    extract_focus_entity,
    is_explanation_question,
    resolve_operation_for_question,
)


MANAGE_PY_QUESTION = (
    "Décrivez le rôle du fichier manage.py dans un projet Django."
)


def test_describe_role_is_explanation_question():
    assert is_explanation_question(MANAGE_PY_QUESTION)


def test_describe_role_resolves_to_expliquer():
    assert resolve_operation_for_question(MANAGE_PY_QUESTION, "identifier") == "expliquer"


def test_extract_manage_py_from_role_question():
    assert extract_focus_entity(MANAGE_PY_QUESTION) == "manage.py"


def test_generic_tokens_are_filtered():
    assert _is_generic_challenge_token("Catégorie B")
    assert _is_generic_challenge_token("Zone principale")
    assert not _is_generic_challenge_token("manage.py")


def test_filter_contextual_pairs_removes_placeholders():
    pairs = [
        ("Catégorie B", "Zone principale"),
        ("manage.py", "Point d'entrée CLI"),
    ]
    filtered = _filter_contextual_pairs(pairs)
    assert filtered == [("manage.py", "Point d'entrée CLI")]


def test_investigation_content_uses_manage_py_statements():
    content = build_investigation_content(
        label=MANAGE_PY_QUESTION,
        object_meta={},
        operation="expliquer",
        difficulty=2,
    )
    texts = " ".join(s["text_fr"] for s in content["statements"])
    assert "manage.py" in texts
    assert "Catégorie" not in texts
    assert content["focus_entity"] == "manage.py"


def test_memory_pairs_from_investigation_challenge():
    from challenge_framework.generator import extract_memory_pair_candidates

    content = build_investigation_content(
        label=MANAGE_PY_QUESTION,
        object_meta={},
        operation="expliquer",
        difficulty=2,
    )
    pairs = extract_memory_pair_candidates(content)
    assert len(pairs) >= 2
    assert all(right in ("Vrai", "Faux") for _, right in pairs)
    assert any("manage.py" in left for left, _ in pairs)
