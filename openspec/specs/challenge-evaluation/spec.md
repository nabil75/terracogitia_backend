# Challenge Evaluation Specification

## Purpose
Cadre universel d'évaluation par **défis cognitifs ludiques** (gamification) remplaçant
l'ancien dispositif question/réponse noté par IA. Ce domaine définit :

1. Une **taxonomie des opérations cognitives** universelles
2. Un **modèle générique du défi cognitif** (unité fondamentale d'évaluation)
3. Un **catalogue de mécaniques de jeu** réutilisables
4. Une **architecture de génération** d'exercices
5. Un **modèle de données** (entités, relations)
6. Des règles de **progression et adaptativité**
7. Un système de **gamification** orienté maîtrise
8. L'**alignement avec la pyramide des six niveaux de savoir**

Fichiers : `routers/challenges.py`, `challenge_framework/catalog_seed.py`,
`challenge_framework/models.py`, tables créées dans `database.py`.

Référence pyramide : spec `pyramid-knowledge-model`.

---

## 1. Taxonomie des opérations cognitives

Le système SHALL reconnaître quatorze opérations cognitives fondamentales, extensibles,
chacune mappée à une famille (`perception`, `organisation`, `transformation`,
`construction`, `diagnostic`, `simulation`, `optimisation`, `discours`, `meta`).

| Clé | Définition | Évalue principalement | Niveaux pyramide privilégiés |
|-----|------------|----------------------|------------------------------|
| `identifier` | Repérer et nommer un élément pertinent dans un ensemble | Reconnaissance, discrimination | faits_observables, lois_relations |
| `comparer` | Mettre en regard des éléments selon un ou plusieurs critères | Similarité/différence, critères | faits_observables, lois_relations |
| `classer` | Regrouper selon une règle ou une catégorie | Catégorisation, critères de classement | faits_observables, lois_relations, schemes_operatoires |
| `associer` | Relier deux ou plusieurs éléments par une relation pertinente | Liaison conceptuelle, mapping | lois_relations, schemes_operatoires |
| `ordonner` | Placer des éléments dans une séquence ou une hiérarchie | Ordre causal, logique, chronologique | lois_relations, schemes_operatoires, principes_generateurs |
| `completer` | Remplir une lacune dans une structure partielle | Règle implicite, pattern | faits_observables → schemes_operatoires |
| `transformer` | Appliquer une opération qui modifie la forme tout en préservant l'invariant | Invariance, opération réversible | schemes_operatoires, principes_generateurs |
| `construire` | Assembler des éléments pour produire un artefact cohérent | Synthèse, cohérence structurelle | schemes_operatoires → structures_abstraites |
| `diagnostiquer` | Identifier la cause ou l'erreur dans un système dysfonctionnel | Analyse d'erreur, causalité | schemes_operatoires, principes_generateurs |
| `simuler` | Explorer un comportement dans un modèle ou un scénario | Prédiction, conséquences | lois_relations → metacadres_theoriques |
| `optimiser` | Choisir la meilleure option selon des contraintes et critères | Trade-offs, contraintes | principes_generateurs, structures_abstraites |
| `expliquer` | Produire une justification structurée d'un phénomène | Compréhension profonde, causalité | lois_relations → metacadres_theoriques |
| `evaluer` | Porter un jugement argumenté sur la validité ou la qualité | Critique, critères explicites | principes_generateurs → metacadres_theoriques |
| `choisir_cadre` | Sélectionner le modèle ou le cadre théorique le plus pertinent | Métacognition, épistémologie | structures_abstraites, metacadres_theoriques |

#### Scenario: Catalogue des opérations exposé
- WHEN un client appelle `GET /challenges/catalog/cognitive-operations`
- THEN la liste complète des opérations avec définitions, familles et niveaux compatibles est renvoyée

---

## 2. Modèle universel du défi cognitif

Le système SHALL représenter un **défi cognitif** (`cognitive_challenge`) comme unité
fondamentale d'évaluation, distincte de l'**exercice** (instance jouable) et de la
**tentative** (interaction apprenant).

### Attributs essentiels du défi cognitif

| Attribut | Description |
|----------|-------------|
| `pyramid_level` | Niveau de savoir visé (clé canonique pyramide) |
| `cognitive_operation` | Opération cognitive évaluée |
| `game_mechanic` | Mécanique ludique retenue |
| `knowledge_object_type` | Type d'objet (`question`, `subtheme`, `concept`, …) |
| `knowledge_object_id` | Identifiant générique (`id_objet`) |
| `difficulty` | 1–5 (facilité croissante de la tâche, pas du contenu seul) |
| `success_criteria` | Critères mesurables de réussite (JSON) |
| `evaluated_competencies` | Compétences visées avec poids |
| `prerequisites` | Prérequis conceptuels ou défis préalables |
| `typical_errors` | Erreurs attendues pour le diagnostic adaptatif |
| `performance_indicators` | KPI (précision, temps, tentatives, transfert) |
| `generation_rules` | Règles pour instancier un exercice |
| `content_payload` | Données spécifiques au défi (items, graphe, scénario) |

### Relations

```
KnowledgeObject ──< CognitiveChallenge >── GameMechanic
                        │
                        ├──< ChallengeExercise (instance)
                        │         │
                        │         └──< ChallengeAttempt
                        │                   │
                        │                   └── ChallengeEvaluation
                        │
CognitiveOperation ─────┘
PyramidLevel ───────────┘
```

#### Scenario: Création d'un défi cognitif
- GIVEN un objet de connaissance et une combinaison opération + mécanique + niveau valide
- WHEN un client envoie `POST /challenges`
- THEN un enregistrement `cognitive_challenge` est créé avec statut `draft` ou `published`

---

## 3. Catalogue des mécaniques de jeu

Le système SHALL maintenir un catalogue de mécaniques ludiques réutilisables :

| Clé | Description | Opérations compatibles (extrait) | Niveaux privilégiés |
|-----|-------------|----------------------------------|---------------------|
| `drag_drop` | Placer des éléments dans des zones cibles | identifier, classer, associer, ordonner | faits → schemes |
| `sorting_lab` | Laboratoire de tri : répartir dans des catégories (règle visible ou à découvrir) | classer | faits → structures |
| `knowledge_bridges` | Ponts du savoir : relier sources et cibles selon une relation | associer | faits → principes |
| `sequence_frieze` | Frise à reconstituer : ordonner des cartes dans une séquence | ordonner | faits → principes |
| `missing_fragment` | Fragment manquant : compléter des lacunes dans une structure | completer | faits → principes |
| `transform_atelier` | Atelier des transformations : convertir une forme en préservant un invariant | transformer | lois → principes |
| `matching` | Relier paires ou groupes correspondants | associer, comparer, classer | faits → principes |
| `comparator` | Comparaison structurée critère par critère (relation, justification, matrice, synthèse) | comparer | faits → principes |
| `memory` | Retrouver des paires identiques ou associées | identifier, comparer, associer | faits_observables |
| `puzzle` | Recomposer un tout à partir de fragments | completer, construire, ordonner | schemes → structures |
| `sorting` | Ordonner une liste selon un critère | ordonner, comparer, classer | lois → principes |
| `construction` | Assembler un modèle ou un schéma | construire, transformer, completer | schemes → structures |
| `investigation` | Explorer indices pour résoudre une énigme | diagnostiquer, expliquer, evaluer | schemes → metacadres |
| `simulation` | Manipuler un modèle dynamique | simuler, predire, optimiser | lois → metacadres |
| `strategy` | Planifier une séquence d'actions | optimiser, choisir_cadre, evaluer | principes → metacadres |
| `sandbox` | Explorer librement avec feedback | simuler, construire, transformer | schemes → structures |
| `timed` | Contrainte temporelle sur toute mécanique | identifier, comparer, appliquer | faits → schemes |
| `resource_management` | Allouer des ressources limitées | optimiser, choisir, evaluer | principes → metacadres |

#### Scenario: Matrice opérations × mécaniques
- WHEN un client appelle `GET /challenges/catalog/compatibility-matrix`
- THEN une matrice `{ operation, mechanic, score }` est renvoyée (0 = incompatible, 3 = optimal)

---

## 4. Architecture de génération

Le système SHALL exposer `POST /challenges/generate` produisant un **exercice** à partir de :

- `knowledge_object_type`, `knowledge_object_id` (`id_objet`)
- `pyramid_level`, `cognitive_operation`, `game_mechanic`
- `difficulty` (optionnel, défaut 2)
- `variant` (optionnel : seed, personnalisation)
- `use_ai` (optionnel : `true`=Mistral, `false`=règles, `null`=auto selon `MISTRAL_API_KEY`)
- `lang` (optionnel : `fr`|`en` pour le prompt IA)

### Règles de génération (v1)

1. Valider la compatibilité opération × mécanique × niveau (matrice)
2. Charger l'objet de connaissance (question enrichie + parcours + proposition Discover courante)
3. Si IA activée : appeler `mistral/question_mistral.py` avec constitution pyramide et schéma mécanique
4. Sinon (ou échec IA) : appliquer un **template de mécanique** rule-based
5. Ajuster la difficulté : nombre d'items, distracteurs, contrainte temps, feedback partiel
6. Persister `challenge_exercise` ; marquer `content.generated_by` (`mistral` | `rule_based`)

### Niveaux de difficulté

| Niveau | Effet typique |
|--------|---------------|
| 1 | Peu d'items, indices visibles, feedback immédiat |
| 2 | Items standards, distracteurs faibles |
| 3 | Distracteurs plausibles, pas d'indice |
| 4 | Contrainte temps ou ressources |
| 5 | Transfer : contexte nouveau, double contrainte |

#### Scenario: Génération réussie
- GIVEN une combinaison compatible
- WHEN `POST /challenges/generate` est appelé
- THEN un `challenge_exercise` est créé avec `content` JSON jouable et `success_criteria` copiés/adaptés

#### Scenario: Combinaison incompatible
- GIVEN une combinaison absente de la matrice ou score 0
- WHEN la génération est demandée
- THEN la réponse est `400` avec détail de l'incompatibilité

---

## 5. Modèle de données

### Entités distinguées

| Entité | Rôle |
|--------|------|
| **Objet de connaissance** | Contenu évalué (question, concept, parcours…) — référence externe via `type` + `id_objet` |
| **Défi cognitif** | Définition réutilisable (template pédagogique + règles) |
| **Exercice** | Instance jouable générée pour un apprenant / session |
| **Mécanique de jeu** | Entrée catalogue (comportement UI / règles interaction) |
| **Tentative** | Une session d'interaction apprenant sur un exercice |
| **Évaluation** | Résultat structuré d'une tentative (critères, scores, feedback) |
| **Compétence / maîtrise** | Agrégat longitudinal par apprenant × objet × opération × niveau |

### Tables (implémentées)

- `cognitive_operation_catalog`
- `game_mechanic_catalog`
- `operation_mechanic_compatibility`
- `cognitive_challenge`
- `challenge_exercise`
- `challenge_attempt`
- `challenge_evaluation`
- `learner_mastery`
- `learner_gamification`
- `achievement_definition`
- `learner_achievement`

#### Scenario: Soumission d'une tentative
- GIVEN un exercice en cours
- WHEN `POST /challenges/attempts` est appelé avec actions et durée
- THEN une `challenge_attempt` et une `challenge_evaluation` sont créées, la maîtrise et l'XP sont mises à jour

---

## 6. Progression et adaptativité

Le système SHALL :

- Calculer une **maîtrise** (0–1) par `(user, knowledge_object, pyramid_level, operation)` avec decay et confidence
- Détecter les **lacunes** via `typical_errors` et échecs répétés sur mêmes critères
- Adapter la **difficulté** : +1 après 2 succès consécutifs, −1 après 2 échecs sur même opération
- Éviter la mémorisation : variantes de surface, transfer (`variant=new_context`), espacement (SM-2 simplifié)
- Construire des **parcours** : prioriser défis sur opérations faibles × niveau pyramide cible du parcours

#### Scenario: Mise à jour de maîtrise
- GIVEN une tentative réussie avec score ≥ seuil
- WHEN l'évaluation est enregistrée
- THEN `learner_mastery.mastery_score` augmente selon `mastery_delta` et `performance_indicators`

---

## 7. Gamification

Le système SHALL implémenter une gamification **orientée compétence** :

- **XP** : proportionnelle au score × difficulté × nouveauté de l'opération
- **Niveaux apprenant** : paliers XP (courbe sqrt)
- **Succès / badges** : critères sur maîtrise, streak, diversité d'opérations
- **Quêtes** : séquences de défis (ex. « maîtriser classer au niveau lois_relations »)
- **Récompenses** : déblocage de variantes sandbox, défis spéciaux
- **Maîtrise progressive** : étoiles par critère (1–3), pas seulement win/lose

Anti-patterns interdits : XP sans lien critère, badges purement volumétriques sans compétence.

#### Scenario: Profil gamification
- WHEN `GET /challenges/gamification/profile` est appelé pour l'utilisateur courant
- THEN XP, niveau, streak et badges récents sont renvoyés

---

## 8. Pyramide des savoirs × évaluation

| Niveau | Opérations prioritaires | Mécaniques adaptées | Défis privilégiés | Indicateurs |
|--------|-------------------------|---------------------|-------------------|-------------|
| Faits observables | identifier, comparer, classer, completer | memory, drag_drop, matching, timed | Reconnaissance, tri de faits | Précision, temps |
| Lois et relations | associer, ordonner, comparer, expliquer | matching, sorting, simulation | Relier cause-effet, ordonner | Liens corrects, justification courte |
| Schèmes opératoires | completer, transformer, construire, diagnostiquer | puzzle, construction, investigation | Procédures, détection d'erreur | Étapes correctes, correction |
| Principes générateurs | transformer, optimiser, evaluer, expliquer | strategy, simulation, sandbox | Choisir principe applicable | Transfer, justification |
| Structures abstraites | construire, choisir_cadre, evaluer | construction, strategy, sandbox | Modéliser, comparer cadres | Cohérence modèle |
| Métacadres théoriques | choisir_cadre, evaluer, expliquer | investigation, strategy, resource_management | Critique de cadres, épistémologie | Argumentation, meta-justification |

#### Scenario: Guidance par niveau pyramide
- WHEN `GET /challenges/catalog/pyramid-guidance/{level}` est appelé
- THEN opérations, mécaniques et indicateurs recommandés pour ce niveau sont renvoyés

---

## 9. API (implémentée v1)

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/challenges/catalog/cognitive-operations` | Taxonomie |
| GET | `/challenges/catalog/game-mechanics` | Mécaniques |
| GET | `/challenges/catalog/compatibility-matrix` | Matrice |
| GET | `/challenges/catalog/pyramid-guidance/{level}` | Recommandations par niveau |
| GET | `/challenges` | Liste défis (filtres optionnels) |
| POST | `/challenges` | Créer un défi cognitif |
| GET | `/challenges/{id}` | Détail défi |
| POST | `/challenges/generate` | Générer un exercice |
| GET | `/challenges/exercises/{id}` | Détail exercice |
| POST | `/challenges/attempts` | Soumettre une tentative |
| GET | `/challenges/mastery` | Maîtrise de l'utilisateur courant |
| POST | `/challenges/exercises/{id}/save` | Sauvegarder un exercice comme défi réutilisable |
| GET | `/challenges/exercises/by-question/{id}/saved` | Défis sauvegardés pour une question |
| GET | `/challenges/evaluation-reservoir` | Historique d'évaluations (filtres optionnels) |
| GET | `/challenges/gamification/profile` | Profil XP / niveau |
