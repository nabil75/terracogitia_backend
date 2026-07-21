"""Catalogue seed data for the cognitive challenge framework."""

PYRAMID_LEVELS = [
    "faits_observables",
    "lois_relations",
    "schemes_operatoires",
    "principes_generateurs",
    "structures_abstraites",
    "metacadres_theoriques",
]

COGNITIVE_OPERATIONS = [
    {
        "key": "identifier",
        "family": "perception",
        "label_fr": "Identifier",
        "label_en": "Identify",
        "definition_fr": "Repérer et nommer un élément pertinent dans un ensemble.",
        "definition_en": "Detect and name a relevant element within a set.",
        "evaluates_fr": "Reconnaissance, discrimination visuelle ou conceptuelle.",
        "evaluates_en": "Recognition, visual or conceptual discrimination.",
        "pyramid_levels": ["faits_observables", "lois_relations"],
        "examples": [
            {"domain": "sciences", "example_fr": "Identifier une cellule dans un schéma"},
            {"domain": "histoire", "example_fr": "Identifier une période sur une frise"},
        ],
    },
    {
        "key": "comparer",
        "family": "perception",
        "label_fr": "Comparer",
        "label_en": "Compare",
        "definition_fr": "Mettre en regard des éléments selon un ou plusieurs critères.",
        "definition_en": "Contrast elements using one or more criteria.",
        "evaluates_fr": "Similarité, différence, pertinence des critères.",
        "evaluates_en": "Similarity, difference, criterion relevance.",
        "pyramid_levels": ["faits_observables", "lois_relations"],
        "examples": [
            {"domain": "maths", "example_fr": "Comparer deux fonctions sur un intervalle"},
            {"domain": "langues", "example_fr": "Comparer deux temps verbaux"},
        ],
    },
    {
        "key": "classer",
        "family": "organisation",
        "label_fr": "Classer",
        "label_en": "Classify",
        "definition_fr": "Regrouper des éléments selon une règle ou catégorie.",
        "definition_en": "Group elements according to a rule or category.",
        "evaluates_fr": "Catégorisation, choix de la règle de classement.",
        "evaluates_en": "Categorization, classification rule choice.",
        "pyramid_levels": ["faits_observables", "lois_relations", "schemes_operatoires"],
        "examples": [
            {"domain": "biologie", "example_fr": "Classer des espèces en vertébrés / invertébrés"},
            {"domain": "info", "example_fr": "Classer des structures de données"},
        ],
    },
    {
        "key": "associer",
        "family": "organisation",
        "label_fr": "Associer",
        "label_en": "Associate",
        "definition_fr": "Relier des éléments par une relation pertinente.",
        "definition_en": "Link elements through a relevant relation.",
        "evaluates_fr": "Mapping conceptuel, liaison cause-effet ou structure.",
        "evaluates_en": "Conceptual mapping, causal or structural links.",
        "pyramid_levels": ["lois_relations", "schemes_operatoires"],
        "examples": [
            {"domain": "physique", "example_fr": "Associer force et accélération"},
            {"domain": "économie", "example_fr": "Associer offre et demande"},
        ],
    },
    {
        "key": "ordonner",
        "family": "organisation",
        "label_fr": "Ordonner",
        "label_en": "Order",
        "definition_fr": "Placer des éléments dans une séquence ou hiérarchie.",
        "definition_en": "Place elements in a sequence or hierarchy.",
        "evaluates_fr": "Ordre logique, causal ou chronologique.",
        "evaluates_en": "Logical, causal, or chronological order.",
        "pyramid_levels": ["lois_relations", "schemes_operatoires", "principes_generateurs"],
        "examples": [
            {"domain": "histoire", "example_fr": "Ordonner des événements"},
            {"domain": "algo", "example_fr": "Ordonner des étapes d'un algorithme"},
        ],
    },
    {
        "key": "completer",
        "family": "transformation",
        "label_fr": "Compléter",
        "label_en": "Complete",
        "definition_fr": "Remplir une lacune dans une structure partielle.",
        "definition_en": "Fill a gap in a partial structure.",
        "evaluates_fr": "Pattern, règle implicite, cohérence locale.",
        "evaluates_en": "Pattern, implicit rule, local coherence.",
        "pyramid_levels": ["faits_observables", "lois_relations", "schemes_operatoires"],
        "examples": [
            {"domain": "maths", "example_fr": "Compléter une suite logique"},
            {"domain": "langues", "example_fr": "Compléter une phrase avec le bon temps"},
        ],
    },
    {
        "key": "transformer",
        "family": "transformation",
        "label_fr": "Transformer",
        "label_en": "Transform",
        "definition_fr": "Appliquer une opération modifiant la forme en préservant l'invariant.",
        "definition_en": "Apply an operation changing form while preserving invariants.",
        "evaluates_fr": "Invariance, opérations réversibles ou composées.",
        "evaluates_en": "Invariance, reversible or composed operations.",
        "pyramid_levels": ["schemes_operatoires", "principes_generateurs"],
        "examples": [
            {"domain": "géométrie", "example_fr": "Appliquer une symétrie"},
            {"domain": "chimie", "example_fr": "Équilibrer une réaction"},
        ],
    },
    {
        "key": "construire",
        "family": "construction",
        "label_fr": "Construire",
        "label_en": "Construct",
        "definition_fr": "Assembler des éléments en un artefact cohérent.",
        "definition_en": "Assemble elements into a coherent artifact.",
        "evaluates_fr": "Synthèse, cohérence structurelle.",
        "evaluates_en": "Synthesis, structural coherence.",
        "pyramid_levels": ["schemes_operatoires", "principes_generateurs", "structures_abstraites"],
        "examples": [
            {"domain": "info", "example_fr": "Construire un graphe orienté"},
            {"domain": "philosophie", "example_fr": "Construire un argument valide"},
        ],
    },
    {
        "key": "diagnostiquer",
        "family": "diagnostic",
        "label_fr": "Diagnostiquer",
        "label_en": "Diagnose",
        "definition_fr": "Identifier la cause ou l'erreur dans un système dysfonctionnel.",
        "definition_en": "Identify the cause or error in a faulty system.",
        "evaluates_fr": "Analyse d'erreur, raisonnement causal.",
        "evaluates_en": "Error analysis, causal reasoning.",
        "pyramid_levels": ["schemes_operatoires", "principes_generateurs"],
        "examples": [
            {"domain": "info", "example_fr": "Trouver le bug dans un algorithme"},
            {"domain": "médecine", "example_fr": "Diagnostiquer à partir de symptômes"},
        ],
    },
    {
        "key": "simuler",
        "family": "simulation",
        "label_fr": "Simuler",
        "label_en": "Simulate",
        "definition_fr": "Explorer un comportement dans un modèle ou scénario.",
        "definition_en": "Explore behavior within a model or scenario.",
        "evaluates_fr": "Prédiction, conséquences de paramètres.",
        "evaluates_en": "Prediction, parameter consequences.",
        "pyramid_levels": ["lois_relations", "principes_generateurs", "metacadres_theoriques"],
        "examples": [
            {"domain": "physique", "example_fr": "Simuler la chute libre"},
            {"domain": "économie", "example_fr": "Simuler l'effet d'une taxe"},
        ],
    },
    {
        "key": "optimiser",
        "family": "optimisation",
        "label_fr": "Optimiser",
        "label_en": "Optimize",
        "definition_fr": "Choisir la meilleure option selon contraintes et critères.",
        "definition_en": "Choose the best option given constraints and criteria.",
        "evaluates_fr": "Trade-offs, allocation de ressources.",
        "evaluates_en": "Trade-offs, resource allocation.",
        "pyramid_levels": ["principes_generateurs", "structures_abstraites"],
        "examples": [
            {"domain": "maths", "example_fr": "Optimiser une fonction sous contrainte"},
            {"domain": "gestion", "example_fr": "Planifier un budget limité"},
        ],
    },
    {
        "key": "expliquer",
        "family": "discours",
        "label_fr": "Expliquer",
        "label_en": "Explain",
        "definition_fr": "Produire une justification structurée d'un phénomène.",
        "definition_en": "Produce a structured justification of a phenomenon.",
        "evaluates_fr": "Compréhension profonde, chaîne causale.",
        "evaluates_en": "Deep understanding, causal chain.",
        "pyramid_levels": ["lois_relations", "principes_generateurs", "metacadres_theoriques"],
        "examples": [
            {"domain": "sciences", "example_fr": "Expliquer la photosynthèse"},
            {"domain": "droit", "example_fr": "Expliquer l'application d'une norme"},
        ],
    },
    {
        "key": "evaluer",
        "family": "discours",
        "label_fr": "Évaluer",
        "label_en": "Evaluate",
        "definition_fr": "Porter un jugement argumenté sur validité ou qualité.",
        "definition_en": "Make a reasoned judgment on validity or quality.",
        "evaluates_fr": "Critique, critères explicites.",
        "evaluates_en": "Critique, explicit criteria.",
        "pyramid_levels": ["principes_generateurs", "structures_abstraites", "metacadres_theoriques"],
        "examples": [
            {"domain": "philosophie", "example_fr": "Évaluer la solidité d'un argument"},
            {"domain": "art", "example_fr": "Évaluer une œuvre selon des critères"},
        ],
    },
    {
        "key": "choisir_cadre",
        "family": "meta",
        "label_fr": "Choisir un cadre d'interprétation",
        "label_en": "Choose interpretive frame",
        "definition_fr": "Sélectionner le modèle ou cadre théorique le plus pertinent.",
        "definition_en": "Select the most relevant model or theoretical frame.",
        "evaluates_fr": "Métacognition, épistémologie appliquée.",
        "evaluates_en": "Metacognition, applied epistemology.",
        "pyramid_levels": ["structures_abstraites", "metacadres_theoriques"],
        "examples": [
            {"domain": "SHS", "example_fr": "Choisir marxiste vs.webérien pour analyser un fait"},
            {"domain": "physique", "example_fr": "Choisir modèle classique vs.relativiste"},
        ],
    },
]

GAME_MECHANICS = [
    {
        "key": "drag_drop",
        "label_fr": "Glisser-déposer",
        "label_en": "Drag and drop",
        "description_fr": "Placer des éléments dans des zones cibles.",
        "description_en": "Place items into target zones.",
        "advantages_fr": "Intuitif, spatial, feedback immédiat.",
        "limitations_fr": "Moins adapté au raisonnement long ; ne force pas à expliciter une règle de classement.",
        "compatible_operations": ["identifier", "classer", "associer", "ordonner", "completer"],
        "compatible_pyramid_levels": ["faits_observables", "lois_relations", "schemes_operatoires"],
    },
    {
        "key": "sorting_lab",
        "label_fr": "Laboratoire de tri",
        "label_en": "Sorting lab",
        "description_fr": (
            "Répartir des éléments dans des catégories : appliquer ou découvrir "
            "une règle de regroupement, avec feedback et cohérence globale."
        ),
        "description_en": (
            "Assign items to categories: apply or discover a grouping rule, "
            "with feedback and global coherence checks."
        ),
        "advantages_fr": (
            "Évalue l'identification d'une propriété commune et son application "
            "cohérente — cœur de l'opération classer."
        ),
        "limitations_fr": "Plus long que le glisser-déposer simple ; contenu catégoriel à générer.",
        "compatible_operations": ["classer"],
        "compatible_pyramid_levels": [
            "faits_observables",
            "lois_relations",
            "schemes_operatoires",
            "principes_generateurs",
            "structures_abstraites",
        ],
    },
    {
        "key": "knowledge_bridges",
        "label_fr": "Ponts du savoir",
        "label_en": "Knowledge bridges",
        "description_fr": (
            "Relier des éléments sources à des cibles selon une relation donnée : "
            "construction explicite de liens entre deux colonnes."
        ),
        "description_en": (
            "Link source items to targets according to a given relation: "
            "explicit bridge-building between two columns."
        ),
        "advantages_fr": (
            "Évalue la mise en relation — cœur de l'opération associer — "
            "plutôt que la simple sélection par élimination."
        ),
        "limitations_fr": "Moins adapté aux relations multiples ou aux réseaux (variantes avancées).",
        "compatible_operations": ["associer"],
        "compatible_pyramid_levels": [
            "faits_observables",
            "lois_relations",
            "schemes_operatoires",
            "principes_generateurs",
        ],
    },
    {
        "key": "matching",
        "label_fr": "Association",
        "label_en": "Matching",
        "description_fr": "Relier des paires ou groupes correspondants (sélection rapide).",
        "description_en": "Link matching pairs or groups (quick selection).",
        "advantages_fr": "Évalue relations multiples rapidement.",
        "limitations_fr": (
            "Peut devenir trivial par élimination ; n'oblige pas à construire "
            "explicitement un lien comme les Ponts du savoir."
        ),
        "compatible_operations": ["associer", "comparer", "classer", "identifier"],
        "compatible_pyramid_levels": ["faits_observables", "lois_relations", "principes_generateurs"],
    },
    {
        "key": "comparator",
        "label_fr": "Comparateur expert",
        "label_en": "Expert comparator",
        "description_fr": (
            "Comparer deux éléments critère par critère : relation "
            "(similaire / différent / partiel), justification, matrice, puis synthèse."
        ),
        "description_en": (
            "Compare two items criterion by criterion: relation "
            "(similar / different / partial), justification, matrix, then synthesis."
        ),
        "advantages_fr": (
            "Reproduit le processus mental de comparaison : critères, écarts, "
            "justification et conclusion globale."
        ),
        "limitations_fr": "Plus long qu'une association ; contenu riche à générer.",
        "compatible_operations": ["comparer"],
        "compatible_pyramid_levels": [
            "faits_observables",
            "lois_relations",
            "schemes_operatoires",
            "principes_generateurs",
        ],
    },
    {
        "key": "memory",
        "label_fr": "Memory",
        "label_en": "Memory",
        "description_fr": "Retrouver des paires identiques ou associées.",
        "description_en": "Find identical or associated pairs.",
        "advantages_fr": "Renforce mémorisation active.",
        "limitations_fr": "Risque de mémorisation superficielle.",
        "compatible_operations": ["identifier", "comparer", "associer"],
        "compatible_pyramid_levels": ["faits_observables"],
    },
    {
        "key": "sequence_frieze",
        "label_fr": "Frise à reconstituer",
        "label_en": "Sequence frieze",
        "description_fr": (
            "Reconstruire une séquence à partir de cartes mélangées : "
            "ordre chronologique, procédural, hiérarchique ou logique."
        ),
        "description_en": (
            "Rebuild a sequence from shuffled cards: "
            "chronological, procedural, hierarchical, or logical order."
        ),
        "advantages_fr": (
            "Évalue la construction d'un enchaînement cohérent — "
            "cœur de l'opération ordonner — avec feedback par position."
        ),
        "limitations_fr": "Moins adaptée aux relations non linéaires (réseaux).",
        "compatible_operations": ["ordonner"],
        "compatible_pyramid_levels": [
            "faits_observables",
            "lois_relations",
            "schemes_operatoires",
            "principes_generateurs",
        ],
    },
    {
        "key": "missing_fragment",
        "label_fr": "Fragment manquant",
        "label_en": "Missing fragment",
        "description_fr": (
            "Restaurer une structure incomplète en plaçant le ou les bons fragments "
            "dans les lacunes (phrase, chaîne, formule, processus…)."
        ),
        "description_en": (
            "Restore an incomplete structure by placing the right fragment(s) "
            "into the gaps (sentence, chain, formula, process…)."
        ),
        "advantages_fr": (
            "Mesure directement l'opération compléter : analyser le contexte, "
            "déduire l'élément manquant, vérifier la cohérence globale."
        ),
        "limitations_fr": (
            "Moins adaptée à la reconstruction spatiale pure (puzzle) "
            "ou à l'assemblage libre (construction)."
        ),
        "compatible_operations": ["completer"],
        "compatible_pyramid_levels": [
            "faits_observables",
            "lois_relations",
            "schemes_operatoires",
            "principes_generateurs",
        ],
    },
    {
        "key": "puzzle",
        "label_fr": "Puzzle",
        "label_en": "Puzzle",
        "description_fr": "Recomposer un tout à partir de fragments.",
        "description_en": "Reassemble a whole from fragments.",
        "advantages_fr": "Synthèse visuelle, gestion de parties.",
        "limitations_fr": (
            "Recomposition spatiale d'un tout ; n'évalue pas le placement "
            "ciblé dans une structure déjà posée (fragment manquant)."
        ),
        "compatible_operations": ["completer", "construire", "ordonner", "transformer"],
        "compatible_pyramid_levels": ["schemes_operatoires", "structures_abstraites"],
    },
    {
        "key": "sorting",
        "label_fr": "Classement",
        "label_en": "Sorting",
        "description_fr": "Ordonner une liste selon un critère (déplacement rapide ↑↓).",
        "description_en": "Order a list by a criterion (quick ↑↓ moves).",
        "advantages_fr": "Évalue critères explicites rapidement.",
        "limitations_fr": (
            "Une seule dimension ; n'offre pas la manipulation spatiale "
            "d'une frise à reconstituer."
        ),
        "compatible_operations": ["ordonner", "comparer", "classer"],
        "compatible_pyramid_levels": ["lois_relations", "schemes_operatoires", "principes_generateurs"],
    },
    {
        "key": "construction",
        "label_fr": "Construction",
        "label_en": "Construction",
        "description_fr": "Assembler un modèle ou schéma.",
        "description_en": "Assemble a model or diagram.",
        "advantages_fr": "Créativité contrainte, synthèse.",
        "limitations_fr": (
            "Assemble des pièces ; n'évalue pas la conversion de forme "
            "avec conservation d'invariant (atelier des transformations)."
        ),
        "compatible_operations": ["construire", "transformer", "completer"],
        "compatible_pyramid_levels": ["schemes_operatoires", "structures_abstraites"],
    },
    {
        "key": "transform_atelier",
        "label_fr": "Atelier des transformations",
        "label_en": "Transformation workshop",
        "description_fr": (
            "Appliquer une ou plusieurs opérations pour passer d'une forme source "
            "à une forme cible tout en préservant un invariant (sens, valeur, relation…)."
        ),
        "description_en": (
            "Apply one or more operations to go from a source form "
            "to a target form while preserving an invariant (meaning, value, relation…)."
        ),
        "advantages_fr": (
            "Mesure directement l'opération transformer : distinguer forme et fond, "
            "choisir l'opération pertinente, vérifier l'intégrité du résultat."
        ),
        "limitations_fr": (
            "Moins adaptée à l'exploration libre d'un modèle dynamique (simulation) "
            "ou à l'assemblage de zéro (construction)."
        ),
        "compatible_operations": ["transformer"],
        "compatible_pyramid_levels": [
            "lois_relations",
            "schemes_operatoires",
            "principes_generateurs",
        ],
    },
    {
        "key": "investigation",
        "label_fr": "Enquête",
        "label_en": "Investigation",
        "description_fr": "Explorer des indices pour résoudre une énigme.",
        "description_en": "Explore clues to solve a mystery.",
        "advantages_fr": "Motivation narrative, diagnostic.",
        "limitations_fr": "Coûteux en contenu.",
        "compatible_operations": ["diagnostiquer", "expliquer", "evaluer"],
        "compatible_pyramid_levels": ["schemes_operatoires", "metacadres_theoriques"],
    },
    {
        "key": "simulation",
        "label_fr": "Simulation",
        "label_en": "Simulation",
        "description_fr": "Manipuler un modèle dynamique.",
        "description_en": "Manipulate a dynamic model.",
        "advantages_fr": "Transfer, prédiction.",
        "limitations_fr": (
            "Nécessite moteur de simulation ; n'évalue pas la conversion "
            "explicite de représentation avec invariant (atelier)."
        ),
        "compatible_operations": ["simuler", "optimiser", "transformer"],
        "compatible_pyramid_levels": ["lois_relations", "principes_generateurs", "metacadres_theoriques"],
    },
    {
        "key": "strategy",
        "label_fr": "Stratégie",
        "label_en": "Strategy",
        "description_fr": "Planifier une séquence d'actions.",
        "description_en": "Plan a sequence of actions.",
        "advantages_fr": "Planification, trade-offs.",
        "limitations_fr": "Temps de conception élevé.",
        "compatible_operations": ["optimiser", "choisir_cadre", "evaluer"],
        "compatible_pyramid_levels": ["principes_generateurs", "metacadres_theoriques"],
    },
    {
        "key": "sandbox",
        "label_fr": "Bac à sable",
        "label_en": "Sandbox",
        "description_fr": "Explorer librement avec feedback.",
        "description_en": "Explore freely with feedback.",
        "advantages_fr": "Découverte guidée, transfer.",
        "limitations_fr": "Évaluation plus difficile.",
        "compatible_operations": ["simuler", "construire", "transformer"],
        "compatible_pyramid_levels": ["schemes_operatoires", "structures_abstraites"],
    },
    {
        "key": "timed",
        "label_fr": "Chronomètre",
        "label_en": "Timed",
        "description_fr": "Contrainte temporelle sur une mécanique de base.",
        "description_en": "Time constraint on a base mechanic.",
        "advantages_fr": "Automatisation, fluidité.",
        "limitations_fr": "Stress, moins de réflexion profonde.",
        "compatible_operations": ["identifier", "comparer", "classer", "completer"],
        "compatible_pyramid_levels": ["faits_observables", "lois_relations", "schemes_operatoires"],
    },
    {
        "key": "resource_management",
        "label_fr": "Gestion de ressources",
        "label_en": "Resource management",
        "description_fr": "Allouer des ressources limitées.",
        "description_en": "Allocate limited resources.",
        "advantages_fr": "Optimisation, priorités.",
        "limitations_fr": "Courbe d'apprentissage.",
        "compatible_operations": ["optimiser", "evaluer", "choisir_cadre"],
        "compatible_pyramid_levels": ["principes_generateurs", "metacadres_theoriques"],
    },
]

COMPATIBILITY_MATRIX = [
    ("identifier", "drag_drop", 3), ("identifier", "matching", 2), ("identifier", "memory", 3),
    ("identifier", "timed", 2),
    ("comparer", "comparator", 3), ("comparer", "matching", 2), ("comparer", "sorting", 2), ("comparer", "drag_drop", 1),
    ("classer", "sorting_lab", 3), ("classer", "drag_drop", 2), ("classer", "sorting", 2), ("classer", "matching", 1),
    ("associer", "knowledge_bridges", 3), ("associer", "matching", 2), ("associer", "drag_drop", 2), ("associer", "construction", 1),
    ("ordonner", "sequence_frieze", 3), ("ordonner", "sorting", 2), ("ordonner", "drag_drop", 2), ("ordonner", "puzzle", 1),
    ("completer", "missing_fragment", 3), ("completer", "puzzle", 2), ("completer", "drag_drop", 2), ("completer", "construction", 1),
    ("transformer", "transform_atelier", 3), ("transformer", "simulation", 2), ("transformer", "construction", 2), ("transformer", "sandbox", 1),
    ("construire", "construction", 3), ("construire", "puzzle", 2), ("construire", "sandbox", 2),
    ("diagnostiquer", "investigation", 3), ("diagnostiquer", "simulation", 2),
    ("simuler", "simulation", 3), ("simuler", "sandbox", 2),
    ("optimiser", "resource_management", 3), ("optimiser", "strategy", 2), ("optimiser", "simulation", 2),
    ("expliquer", "investigation", 2), ("expliquer", "construction", 1),
    ("evaluer", "investigation", 2), ("evaluer", "strategy", 2),
    ("choisir_cadre", "strategy", 3), ("choisir_cadre", "resource_management", 2),
]

PYRAMID_GUIDANCE = {
    "faits_observables": {
        "operations": ["identifier", "comparer", "classer", "completer"],
        "mechanics": ["sorting_lab", "comparator", "memory", "missing_fragment", "matching"],
        "challenge_types": ["laboratoire de tri", "comparaison structurée", "fragment manquant", "association"],
        "indicators": ["classification_accuracy", "criterion_relevance", "accuracy", "error_rate"],
    },
    "lois_relations": {
        "operations": ["associer", "ordonner", "comparer", "expliquer", "simuler"],
        "mechanics": ["knowledge_bridges", "sequence_frieze", "comparator", "matching", "sorting"],
        "challenge_types": ["ponts du savoir", "frise à reconstituer", "comparaison structurée", "ordonnancement"],
        "indicators": ["relation_accuracy", "sequence_accuracy", "criterion_relevance", "justification_quality"],
    },
    "schemes_operatoires": {
        "operations": ["completer", "transformer", "construire", "diagnostiquer"],
        "mechanics": ["missing_fragment", "transform_atelier", "puzzle", "construction", "investigation"],
        "challenge_types": ["fragment manquant", "atelier des transformations", "procédure", "assemblage"],
        "indicators": ["gap_accuracy", "invariant_integrity", "step_correctness", "repair_success"],
    },
    "principes_generateurs": {
        "operations": ["transformer", "optimiser", "evaluer", "expliquer"],
        "mechanics": ["transform_atelier", "strategy", "simulation", "resource_management"],
        "challenge_types": ["atelier des transformations", "choix de principe", "optimisation"],
        "indicators": ["invariant_integrity", "transfer_score", "argument_quality", "constraint_satisfaction"],
    },
    "structures_abstraites": {
        "operations": ["construire", "choisir_cadre", "evaluer"],
        "mechanics": ["construction", "strategy", "sandbox"],
        "challenge_types": ["modélisation", "comparaison de cadres"],
        "indicators": ["model_coherence", "frame_fit", "abstraction_level"],
    },
    "metacadres_theoriques": {
        "operations": ["choisir_cadre", "evaluer", "expliquer"],
        "mechanics": ["investigation", "strategy", "resource_management"],
        "challenge_types": ["critique épistémologique", "choix de paradigme"],
        "indicators": ["meta_justification", "critique_depth", "epistemic_awareness"],
    },
}

ACHIEVEMENTS = [
    {
        "key": "first_challenge",
        "title_fr": "Premier défi",
        "title_en": "First challenge",
        "description_fr": "Compléter un premier défi cognitif.",
        "description_en": "Complete your first cognitive challenge.",
        "criteria": {"attempts_completed": 1},
        "xp_reward": 50,
    },
    {
        "key": "master_classifier",
        "title_fr": "Maître classificateur",
        "title_en": "Master classifier",
        "description_fr": "Atteindre 80% de maîtrise sur l'opération classer.",
        "description_en": "Reach 80% mastery on classify operation.",
        "criteria": {"operation": "classer", "mastery_min": 0.8},
        "xp_reward": 200,
    },
    {
        "key": "pyramid_explorer",
        "title_fr": "Explorateur de pyramide",
        "title_en": "Pyramid explorer",
        "description_fr": "Réussir un défi à chacun des six niveaux de savoir.",
        "description_en": "Succeed at one challenge per pyramid level.",
        "criteria": {"distinct_pyramid_levels": 6},
        "xp_reward": 500,
    },
]
