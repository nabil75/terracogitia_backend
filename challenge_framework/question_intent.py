"""Heuristiques d'intention de question pour le choix d'opération et de mécanique."""

from __future__ import annotations

import re

_EXPLANATION_QUESTION_RE = re.compile(
    r"(?i)"
    r"(qu['' ]est-ce|qu['' ]est|"
    r"c['' ]est quoi|"
    r"d[ée]cri(?:vez|re|re)|d[ée]crire|"
    r"expliquez|expliquer|"
    r"en quoi consiste|"
    r"[àa] quoi sert|"
    r"(?:le\s+)?r[ôo]le\s+(?:du|de|d['' ]|of\s+)|"
    r"quelle\s+est\s+(?:la\s+)?fonction|"
    r"comment (?:utiliser|s['' ]en servir|employer|fonctionne)|"
    r"what is|what are|define|definition|"
    r"describe|explain(?:ing)?|"
    r"what does|consist of|used for|purpose of|how to use|how does|"
    r"role of|function of)"
)

_FILENAME_RE = re.compile(r"\b([\w.-]+\.(?:py|js|ts|tsx|html|css|json|yaml|yml|md))\b", re.I)


def is_explanation_question(text: str) -> bool:
    """Question visant à expliquer / définir un objet, concept ou entité."""
    return bool(_EXPLANATION_QUESTION_RE.search(str(text or "").strip()))


def is_role_question(text: str) -> bool:
    """Question portant sur le rôle ou la fonction d'un élément."""
    label = str(text or "").strip()
    if not label:
        return False
    return bool(
        re.search(
            r"(?i)"
            r"d[ée]cri(?:vez|re|re).*(?:r[ôo]le|fonction)|"
            r"(?:r[ôo]le|fonction)\s+(?:du|de|d['' ]|of\s+)|"
            r"describe\s+(?:the\s+)?role|explain\s+(?:the\s+)?role|"
            r"what\s+(?:is\s+)?(?:the\s+)?role",
            label,
        )
    )


def resolve_operation_for_question(
    question_label: str,
    explicit_operation: str | None = None,
) -> str:
    """Résout l'opération cognitive la plus adaptée au libellé de la question.

    Les signaux linguistiques forts (comparer, expliquer) priment sur une
    opération explicite générique ou potentiellement mal taguée en base.
    """
    explicit = (explicit_operation or "").strip().lower()
    label = (question_label or "").strip()
    label_l = label.lower()

    # Signaux forts issus du libellé — prioritaires sur le tag DB.
    if (
        re.search(r"\bdiff[ée]rence\b", label_l)
        or re.search(r"\bcompar", label_l)
        or re.search(r"\bversus\b", label_l)
        or re.search(r"\bvs\.?\b", label_l)
    ):
        return "comparer"
    if (
        re.search(r"\bclass", label_l)
        or re.search(r"\bcatégoris", label_l)
        or re.search(r"\bcategor", label_l)
        or re.search(r"\bregroup", label_l)
        or re.search(r"\btri(?:er|ez|age)?\b", label_l)
        or re.search(r"\brang(?:er|ez)\b", label_l)
    ):
        return "classer"
    if (
        re.search(r"\bassoci", label_l)
        or re.search(r"\breli(?:er|ez|e)\b", label_l)
        or re.search(r"\bcorrespond", label_l)
        or re.search(r"\bappari", label_l)
        or re.search(r"\bmatch(?:er|ing)?\b", label_l)
        or re.search(r"\bcoupl", label_l)
    ):
        return "associer"
    if (
        re.search(r"\bordonn", label_l)
        or re.search(r"\bséquenc", label_l)
        or re.search(r"\bsequenc", label_l)
        or re.search(r"\bchronolog", label_l)
        or re.search(r"\bétapes?\b", label_l)
        or re.search(r"\betapes?\b", label_l)
        or re.search(r"\bhiérarch", label_l)
        or re.search(r"\bhierarch", label_l)
        or re.search(r"\bplus ancien\b", label_l)
        or re.search(r"\bplus récent\b", label_l)
        or re.search(r"\bordre\b", label_l)
    ):
        return "ordonner"
    if (
        re.search(r"\bcompl[eé]t", label_l)
        or re.search(r"\blacune", label_l)
        or re.search(r"\bmanquant", label_l)
        or re.search(r"\bmissing\b", label_l)
        or re.search(r"\bblank\b", label_l)
        or re.search(r"\btrou\b", label_l)
        or re.search(r"\bremplir\b", label_l)
        or re.search(r"\bfill(?:\s+in)?\b", label_l)
        or re.search(r"\b______+", label_l)
    ):
        return "completer"
    if (
        re.search(r"\btransform", label_l)
        or re.search(r"\bconvert", label_l)
        or re.search(r"\breformul", label_l)
        or re.search(r"\breécrit", label_l)
        or re.search(r"\breecrit", label_l)
        or re.search(r"\brewrite", label_l)
        or re.search(r"\bvoix (active|passive)", label_l)
        or re.search(r"\bpassive voice", label_l)
        or re.search(r"\bpourcentage", label_l)
        or re.search(r"\bpercent", label_l)
        or re.search(r"\béquivalen", label_l)
        or re.search(r"\bequivalen", label_l)
    ):
        return "transformer"
    if is_explanation_question(label):
        return "expliquer"

    if explicit and explicit != "identifier":
        return explicit
    return explicit or "identifier"


def _clean_entity(raw: str) -> str:
    entity = raw.strip(" ?.!,;:")
    file_match = _FILENAME_RE.search(entity)
    if file_match:
        return file_match.group(1)
    return entity[:80]


def extract_comparison_pair(
    question_label: str, object_meta: dict | None = None
) -> tuple[str, str] | None:
    """Extrait deux éléments à comparer depuis un libellé de question."""
    label = str(question_label or "").strip()
    if not label:
        return None

    filenames = _FILENAME_RE.findall(label)
    if len(filenames) >= 2:
        return filenames[0], filenames[1]

    patterns = [
        r"(?i)compar(?:ez|er|aison)\s+(?:le\s+contenu\s+des\s+)?(?:fichiers?\s+)?(.+?)\s+(?:et|and|vs\.?|versus|/)\s+(.+?)(?:\s+dans|\s+in\b|\?|$)",
        r"(?i)diff[ée]rence(?:s)?\s+entre\s+(.+?)\s+(?:et|and)\s+(.+?)(?:\s+dans|\s+in\b|\?|$)",
        r"(?i)(?:opposez|contrast(?:ez|e)?)\s+(.+?)\s+(?:et|and|vs\.?|versus|/)\s+(.+?)(?:\s+dans|\s+in\b|\?|$)",
        r"(?i)(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\s+dans|\s+in\b|\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, label)
        if match:
            left = _clean_entity(match.group(1))
            right = _clean_entity(match.group(2))
            # Nettoyage des restes du type « les fichiers X »
            left = re.sub(r"(?i)^(le|la|les|un|une|the|a|an)\s+", "", left).strip()
            right = re.sub(r"(?i)^(le|la|les|un|une|the|a|an)\s+", "", right).strip()
            left = re.sub(r"(?i)^(fichiers?|files?|modules?)\s+", "", left).strip()
            right = re.sub(r"(?i)^(fichiers?|files?|modules?)\s+", "", right).strip()
            if left and right and left.lower() != right.lower():
                return left[:80], right[:80]

    concepts = (object_meta or {}).get("concepts_vises")
    if isinstance(concepts, list):
        cleaned = [str(c).strip() for c in concepts if isinstance(c, str) and str(c).strip()]
        if len(cleaned) >= 2:
            return cleaned[0][:80], cleaned[1][:80]
    return None


def extract_focus_entity(question_label: str, object_meta: dict | None = None) -> str:
    """Extrait l'entité conceptuelle cible (objet à expliquer)."""
    label = str(question_label or "").strip()
    if not label:
        concepts = (object_meta or {}).get("concepts_vises")
        if isinstance(concepts, list):
            for raw in concepts:
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()[:80]
        return "cet élément"

    patterns = [
        r"(?i)d[ée]cri(?:vez|re|re)\s+(?:le\s+)?(?:r[ôo]le\s+(?:du\s+|de\s+|d['' ])?)?(?:fichier\s+|script\s+|module\s+)?(.+?)(?:\s+dans|\s+in\b|\?|$)",
        r"(?i)(?:quel(?:le)?\s+est\s+)?(?:le\s+)?(?:r[ôo]le\s+(?:du\s+|de\s+|d['' ])?)(?:fichier\s+|script\s+)?(.+?)(?:\s+dans|\s+in\b|\?|$)",
        r"(?i)(?:quelle\s+est\s+)?(?:la\s+)?fonction\s+(?:du\s+|de\s+|d['' ])?(?:fichier\s+)?(.+?)(?:\s+dans|\s+in\b|\?|$)",
        r"(?i)qu['' ]est-ce qu['' ]?(?:un[e]?|le|la|l['' ])?\s*(.+?)\s*\??$",
        r"(?i)qu['' ]est-ce que\s*(.+?)\s*\??$",
        r"(?i)c['' ]est quoi\s*(?:un[e]?|le|la|l['' ])?\s*(.+?)\s*\??$",
        r"(?i)(?:d[ée]finir|d[ée]finition de)\s*(?:un[e]?|le|la|l['' ])?\s*(.+?)\s*\??$",
        r"(?i)[àa] quoi sert\s*(?:un[e]?|le|la|l['' ])?\s*(.+?)\s*\??$",
        r"(?i)en quoi consiste\s*(?:un[e]?|le|la|l['' ])?\s*(.+?)\s*\??$",
        r"(?i)explain(?:ing)?\s+(?:the\s+)?(?:role\s+of\s+)?(?:file\s+)?(.+?)(?:\s+in\b|\?|$)",
        r"(?i)describe\s+(?:the\s+)?(?:role\s+of\s+)?(?:file\s+)?(.+?)(?:\s+in\b|\?|$)",
        r"(?i)what is\s*(?:an?\s+)?(.+?)\s*\??$",
    ]
    for pattern in patterns:
        match = re.search(pattern, label)
        if match:
            entity = _clean_entity(match.group(1))
            if entity:
                return entity

    file_match = _FILENAME_RE.search(label)
    if file_match:
        return file_match.group(1)

    concepts = (object_meta or {}).get("concepts_vises")
    if isinstance(concepts, list):
        for raw in concepts:
            if isinstance(raw, str) and raw.strip():
                return raw.strip()[:80]

    if len(label) <= 80:
        return label
    return label[:80].rstrip() + "…"
