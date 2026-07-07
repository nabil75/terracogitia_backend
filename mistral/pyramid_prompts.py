"""Constitution partagée de la pyramide des savoirs (prompts Mistral Terra Cogitia)."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

PYRAMID_LEVELS: tuple[str, ...] = (
    "faits_observables",
    "lois_relations",
    "schemes_operatoires",
    "principes_generateurs",
    "structures_abstraites",
    "metacadres_theoriques",
)

TRANSFORMATIONS_COGNITIVES: tuple[str, ...] = (
    "observer",
    "comparer",
    "relier",
    "resoudre",
    "generaliser",
    "modeliser",
    "critiquer",
    "integrer",
)

# Alias français / libellés historiques → clés canoniques snake_case
_PYRAMID_ALIASES: dict[str, str] = {
    "faits observables": "faits_observables",
    "faits_observable": "faits_observables",
    "lois et relations": "lois_relations",
    "lois relations": "lois_relations",
    "schemes operatoires": "schemes_operatoires",
    "schèmes opératoires": "schemes_operatoires",
    "schemas operatoires": "schemes_operatoires",
    "principes generateurs": "principes_generateurs",
    "principes générateurs": "principes_generateurs",
    "structures abstraites": "structures_abstraites",
    "metacadres theoriques": "metacadres_theoriques",
    "métacadres théoriques": "metacadres_theoriques",
    "metacadres théoriques": "metacadres_theoriques",
}

PYRAMID_CONSTITUTION = """
CONSTITUTION — PYRAMIDE DES SAVOIRS (Terra Cogitia)

Les 6 niveaux sont des clés EXACTES (snake_case, sans variante) :

1. faits_observables
   — Phénomènes directement observables, expériences, constats empiriques.
   — Opérations mentales dominantes : percevoir, décrire, reconnaître, constater.
   — Interdit : généraliser sans observation, invoquer une théorie abstraite.

2. lois_relations
   — Règles, mécanismes, causalités, relations entre phénomènes.
   — Opérations : comparer, expliquer pourquoi, relier cause-effet, prédire dans un cadre donné.
   — Interdit : se limiter à une procédure sans expliciter le mécanisme.

3. schemes_operatoires
   — Méthodes, procédures, stratégies, résolution de problèmes.
   — Opérations : appliquer, choisir une méthode, exécuter, dépanner.
   — Interdit : rester au niveau descriptif sans démarche opératoire.

4. principes_generateurs
   — Idées fondamentales, invariants, mécanismes profonds unifiant plusieurs méthodes.
   — Opérations : généraliser, identifier un invariant, transférer à un cas nouveau.
   — Interdit : lister des recettes sans principe unificateur.

5. structures_abstraites
   — Modèles mentaux, architectures conceptuelles, représentations globales du domaine.
   — Opérations : modéliser, structurer, cartographier, représenter un système.
   — Interdit : confondre avec un simple résumé encyclopédique.

6. metacadres_theoriques
   — Visions globales, limites des modèles, cadres interprétatifs, liens interdisciplinaires.
   — Opérations : critiquer un modèle, comparer des cadres, situer les limites, intégrer.
   — Interdit : dogmatisme, présentation d'un seul cadre comme absolu.

RÈGLES TRANSVERSALES :
- Progression : concret → abstrait (1 → 6), sauf entité explicitement marquée "revision" ou "synthese".
- Chaque entité a un niveau_pyramide_dominant (1 clé) et peut lister niveaux_secondaires (0–2 clés).
- Aucun niveau ne doit être absent de l'ensemble produit si le périmètre le permet.
- Les questions DOIVENT porter niveau_pyramide (clé exacte), pas un libellé vague.
""".strip()


# Grille des grandes familles (catégories) par niveau de pyramide.
# Sert à sélectionner et expliciter les parcours : CHAQUE famille pertinente
# pour la discipline peut donner lieu à UN parcours ancré sur le niveau correspondant.
PYRAMID_FAMILIES_GRID = """
GRILLE DES FAMILLES PAR NIVEAU (pour sélectionner et expliciter les parcours)

Principe : pour le niveau pyramide visé, passe en revue les familles ci-dessous.
CHAQUE famille pertinente au regard du thème/de la discipline peut donner lieu à UN parcours
distinct (ancré sur le niveau_pyramide_dominant correspondant). Ignore les familles non pertinentes.
N'invente pas de famille hors liste ; réutilise ces intitulés comme angle du parcours.

1. faits_observables — grandes catégories universelles :
   1.01 Entités — objets/éléments qui existent dans le domaine. (Quels sont les objets fondamentaux ?)
   1.02 Propriétés — caractéristiques observables des entités. (Quelles caractéristiques décrivent une entité ?)
   1.03 États — situations dans lesquelles une entité peut se trouver. (Dans quels états observables ?)
   1.04 Événements — changements observables. (Quels événements peuvent survenir ?)
   1.05 Actions — opérations réalisables. (Que peut-on faire dans ce domaine ?)
   1.06 Flux — ce qui circule entre les entités. (Qu'est-ce qui transite dans le système ?)
   1.07 Mesures — indicateurs observables. (Que peut-on mesurer ?)
   1.08 Artefacts — productions du domaine (documents, logiciels, livrables, modèles…). (Quels artefacts sont produits ?)

2. lois_relations — grandes familles de relations entre faits :
   2.01 Causalité — un fait produit/influence/empêche un autre. (Qu'est-ce qui provoque ce phénomène ? Ses conséquences ?)
   2.02 Corrélation — deux faits évoluent ensemble sans causalité démontrée. (Quels phénomènes varient ensemble ?)
   2.03 Dépendance — un fait n'existe que si un autre est présent. (Quelles conditions d'existence ?)
   2.04 Composition — un phénomène est constitué d'autres. (Quels éléments constitutifs ?)
   2.05 Hiérarchie — spécialisation/généralisation d'un fait. (Quelle catégorie englobe ce phénomène ?)
   2.06 Fonctionnelle — une variation entraîne une variation déterminée d'un autre. (Comment une grandeur influence-t-elle une autre ?)
   2.07 Temporelle — ordre d'apparition des faits. (Quelle séquence ? Quelles étapes respecter ?)
   2.08 Équivalence — deux faits expriment la même réalité. (Existe-t-il une autre représentation ?)
   2.09 Contrainte — un fait limite/encadre un autre. (Quelles limites ? Quels facteurs bloquants ?)
   2.10 Opposition — deux faits incompatibles/antagonistes. (Quels compromis ? Quels objectifs en conflit ?)

3. schemes_operatoires — façons d'agir efficacement (plus générales qu'une procédure, plus concrètes qu'un principe) :
   3.01 Observation — recueillir/produire l'information pertinente. (Que regarder ? Que mesurer ? Que distinguer ?)
   3.02 Diagnostic — comprendre une situation existante. (Que se passe-t-il ? Quelle cause ? Où est le problème ?)
   3.03 Décomposition — réduire la complexité. (Comment découper le problème ? Quels sous-systèmes ?)
   3.04 Transformation — faire évoluer un état vers un autre. (Comment modifier le système ? Produire le résultat ?)
   3.05 Optimisation — améliorer une solution. (Comment faire mieux ? Réduire les coûts ?)
   3.06 Contrôle et validation — vérifier qualité/conformité. (Est-ce correct ? cohérent ? fiable ?)
   3.07 Prédiction — anticiper. (Que va-t-il se passer ? Quelles conséquences ?)
   3.08 Conception — créer ce qui n'existe pas encore. (Comment construire ? Quelle architecture ?)
   3.09 Décision — choisir entre plusieurs possibilités. (Quelle option ? Quels critères ?)
   3.10 Intégration — combiner plusieurs éléments en un ensemble cohérent. (Comment articuler des sous-systèmes ? Réconcilier des points de vue ?)

4. principes_generateurs — mécanismes fondamentaux produisant/expliquant les phénomènes et lois :
   4.01 Conservation — quelque chose est maintenu malgré les transformations. (Qu'est-ce qui reste invariant ?)
   4.02 Interaction — les phénomènes émergent des interactions entre entités. (Qu'est-ce qui agit sur quoi ?)
   4.03 Transformation — les objets changent de forme/d'état. (Comment une forme devient-elle une autre ?)
   4.04 Régulation — le système ajuste son comportement. (Comment le système se maintient-il ?)
   4.05 Émergence — des propriétés globales apparaissent à partir d'éléments simples. (Comment apparaissent les structures globales ?)
   4.06 Sélection — parmi plusieurs possibilités, certaines sont retenues. (Comment certaines possibilités sont-elles retenues ?)

5. structures_abstraites — formes organisationnelles profondes sous-tendant faits, lois, méthodes, principes :
   5.01 Ontologiques — types d'entités fondamentales et propriétés essentielles. (Qu'est-ce qui existe ?)
   5.02 Relationnelles — liens, dépendances, connexions entre entités. (Qu'est-ce qui est relié ?)
   5.03 Hiérarchiques — niveaux d'organisation, relations d'inclusion. (Qu'est-ce qui est inclus dans quoi ?)
   5.04 Dynamiques — transformations, processus, évolutions dans le temps. (Qu'est-ce qui se transforme ?)
   5.05 Systémiques — ensembles d'éléments en interaction. (Qu'est-ce qui interagit ?)
   5.06 Émergentes — apparition de propriétés/structures globales non présentes au niveau des composants. (Qu'est-ce qui apparaît à partir des interactions ?)

6. metacadres_theoriques — façons fondamentales d'interpréter, organiser et produire le savoir lui-même :
   6.01 Ontologiques — ce qui existe. (Que sont les choses ?)
   6.02 Épistémologiques — ce qui permet de connaître. (Comment savons-nous ?)
   6.03 Structurels — ce qui organise. (Comment les éléments s'articulent-ils ?)
   6.04 Dynamiques — ce qui transforme. (Comment les phénomènes évoluent-ils ?)
   6.05 Pragmatiques — ce qui guide l'action. (Comment agir efficacement ?)
   6.06 Réflexifs — ce qui examine les cadres eux-mêmes. (Comment examiner nos propres cadres ?)
""".strip()


def _ascii_fold(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalize_pyramid_level(raw: Any) -> str | None:
    """Normalise un niveau de pyramide vers une clé snake_case canonique."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s in PYRAMID_LEVELS:
        return s
    lower = _ascii_fold(s.lower())
    if lower in PYRAMID_LEVELS:
        return lower
    if lower in _PYRAMID_ALIASES:
        return _PYRAMID_ALIASES[lower]
    compact = re.sub(r"[\s\-]+", "_", lower)
    compact = re.sub(r"[^\w]", "", compact)
    if compact in PYRAMID_LEVELS:
        return compact
    for alias, key in _PYRAMID_ALIASES.items():
        if alias.replace(" ", "_") == compact or alias.replace(" ", "") == compact.replace("_", ""):
            return key
    return None


def normalize_pyramid_level_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = normalize_pyramid_level(item)
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def normalize_transformation_cognitive(raw: Any) -> str | None:
    if raw is None:
        return None
    s = _ascii_fold(str(raw).strip().lower())
    s = s.replace("é", "e").replace("è", "e").replace("ê", "e")
    s = re.sub(r"[\s\-]+", "_", s)
    if s in TRANSFORMATIONS_COGNITIVES:
        return s
    if s == "résoudre":
        return "resoudre"
    if s == "généraliser":
        return "generaliser"
    if s == "modéliser":
        return "modeliser"
    return None


# Verbes d'opération cognitive (distincts des niveaux pyramide)
_COGNITIVE_OPERATION_ALIASES: dict[str, str] = {
    "observe": "observer",
    "decrire": "decrire",
    "describe": "decrire",
    "identifier": "identifier",
    "reconnaitre": "reconnaitre",
    "reconnaître": "reconnaitre",
    "constater": "constater",
    "percevoir": "percevoir",
    "expliquer": "expliquer",
    "explique": "expliquer",
    "comprendre": "comprendre",
    "comprehension": "comprendre",
    "analyser": "analyser",
    "analyze": "analyser",
    "relier": "relier",
    "comparer": "comparer",
    "predire": "predire",
    "prédire": "predire",
    "appliquer": "appliquer",
    "executer": "executer",
    "exécuter": "executer",
    "choisir": "choisir",
    "corriger": "corriger",
    "transferer": "transferer",
    "transférer": "transferer",
    "unifier": "unifier",
    "structurer": "structurer",
    "representer": "representer",
    "représenter": "representer",
    "cartographier": "cartographier",
    "evaluer": "evaluer",
    "évaluer": "evaluer",
}

COGNITIVE_OPERATION_FAMILIES: dict[str, tuple[str, ...]] = {
    "observation": (
        "observer",
        "decrire",
        "identifier",
        "reconnaitre",
        "constater",
        "percevoir",
    ),
    "comprehension": (
        "expliquer",
        "comprendre",
        "analyser",
        "relier",
        "comparer",
        "predire",
    ),
    "application": (
        "appliquer",
        "executer",
        "resoudre",
        "choisir",
        "corriger",
    ),
    "generalisation": (
        "generaliser",
        "transferer",
        "unifier",
    ),
    "modelisation": (
        "modeliser",
        "structurer",
        "representer",
        "cartographier",
    ),
    "reflexion": (
        "critiquer",
        "integrer",
        "evaluer",
    ),
}

_OPERATION_TO_FAMILY: dict[str, str] = {
    op: family
    for family, ops in COGNITIVE_OPERATION_FAMILIES.items()
    for op in ops
}


def normalize_cognitive_operation(raw: Any) -> str | None:
    """
    Normalise un verbe d'opération cognitive (operation_cognitive / niveau_cognitif).
    Ne confond pas avec un niveau de pyramide.
    """
    if raw is None:
        return None
    if normalize_pyramid_level(raw):
        return None
    canonical = normalize_transformation_cognitive(raw)
    if canonical:
        return canonical
    s = _ascii_fold(str(raw).strip().lower())
    s = re.sub(r"[^\w\s\-]", " ", s)
    s = re.sub(r"[\s\-]+", "_", s).strip("_")
    if not s:
        return None
    if s in _COGNITIVE_OPERATION_ALIASES:
        return _COGNITIVE_OPERATION_ALIASES[s]
    if s in _OPERATION_TO_FAMILY:
        return s
    first = s.split("_")[0]
    if first in _COGNITIVE_OPERATION_ALIASES:
        return _COGNITIVE_OPERATION_ALIASES[first]
    if first in _OPERATION_TO_FAMILY:
        return first
    if len(first) >= 4 and first not in PYRAMID_LEVELS:
        return first
    return None


def cognitive_operation_family(operation: str | None) -> str:
    if not operation:
        return "other"
    return _OPERATION_TO_FAMILY.get(operation, "other")


def dominants_from_entity(entity: dict) -> str | None:
    """Extrait le niveau dominant (nouveau ou legacy)."""
    if not isinstance(entity, dict):
        return None
    dom = normalize_pyramid_level(
        entity.get("niveau_pyramide_dominant") or entity.get("niveau_pyramide")
    )
    return dom


def json_dumps_safe(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
