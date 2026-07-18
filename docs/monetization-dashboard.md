# Tableau de bord de monétisation en temps réel

## Démarrage local

```bash
python -m atlas.monetization_dashboard --port 8080
```

Puis ouvrir `http://localhost:8080`.

## Déploiement Cloud Run

Le serveur utilise uniquement la bibliothèque standard Python, écoute sur la variable `PORT` et expose :

- `/` : interface de supervision ;
- `/api/status` : état JSON courant ;
- `/healthz` : sonde de santé.

Commande de démarrage recommandée :

```bash
python -m atlas.monetization_dashboard
```

## Sources de données

Le tableau de bord n'invente jamais de résultats. Il lit uniquement :

- `results/monetization.json` pour les agrégats économiques ;
- `results/monetization_experiments.jsonl` pour les expériences ;
- `results/evidence.jsonl` pour le journal de preuves.

Lorsque ces fichiers sont absents, tous les indicateurs restent à zéro et l'interface affiche qu'aucune action n'est encore prouvée.

### Exemple `results/monetization.json`

```json
{
  "revenue_received": 0,
  "weighted_pipeline": 0,
  "hours_invested": 0,
  "outreach_sent": 0,
  "qualified_replies": 0,
  "conversions": 0
}
```

### Exemple d'expérience JSONL

```json
{"timestamp":"2026-07-19T00:00:00Z","title":"Mission de recherche","domain":"freelancing","stage":"application","probability":0.25,"expected_hourly_revenue":20,"next_action":"Envoyer la proposition","blocker":"Aucun","decision":"continue","proof":"https://..."}
```

L'interface interroge `/api/status` toutes les dix secondes. Pour obtenir une vraie mise à jour continue, les cycles ATLAS doivent écrire leurs résultats vérifiés dans ces fichiers après chaque action.