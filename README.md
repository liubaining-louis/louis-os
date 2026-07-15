# ATLAS v2 — MVP exécutable

Ce dépôt transforme ATLAS en une boucle expérimentale concrète.

## Ce que le MVP fait

- exécute deux variantes d'agent sur des cas métier versionnés ;
- évalue les réponses avec des règles déterministes ;
- compare la baseline et la variante ;
- enregistre chaque run dans un Evidence Graph local (`results/evidence.jsonl`) ;
- génère un rapport HTML lisible (`results/report.html`) ;
- interdit la promotion d'une variante si elle régresse sur les garde-fous.

## Workflows inclus

1. **Calcul de coût import** : cohérence des Incoterms, unités, conversion tonne/kg, coût rendu et marge.
2. **Qualification fournisseur** : vérification de preuves, documents manquants, risque et refus de conclure sans données suffisantes.

## Démarrage

```bash
python -m atlas.cli run-all
python -m atlas.cli report
python -m unittest discover -s tests -v
```

Aucune dépendance externe n'est nécessaire (Python 3.10+).

## Structure

- `atlas/agents.py` : baseline et variante gouvernée.
- `atlas/evaluators.py` : évaluateurs déterministes.
- `atlas/runner.py` : boucle expérimentale.
- `atlas/evidence.py` : stockage des preuves.
- `benchmarks/` : cas métier JSON.
- `results/` : sorties produites.

## Règle de promotion

Une variante est promue uniquement si :

- son score moyen est supérieur à la baseline ;
- aucun garde-fou critique ne régresse ;
- au moins 80 % des cas sont réussis.
