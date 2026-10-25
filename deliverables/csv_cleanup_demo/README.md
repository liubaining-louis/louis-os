# Démonstration vérifiable : nettoyage CSV de contacts

Données entièrement synthétiques. Ce dossier est une preuve technique locale,
pas une mission client, une soumission ou un revenu. L'outil a été implémenté
avec le pilote ; ce n'est pas une preuve que Louis sait générer seul du code.

## Avant / après

`input.csv` contient six lignes : en-têtes réordonnés avec espaces/casse,
doublon simple, email incorrect, nom manquant et doublon contradictoire.
`cleaned.csv` conserve deux contacts. `report.json` explique les quatre lignes
non retenues et contient le SHA-256 de l'entrée intacte.

Les numéros du rapport sont les rangs des enregistrements CSV, en-tête inclus,
pas les numéros de ligne physique lorsqu'une cellule contient un saut de ligne.
Les doublons sont comptés séparément des rejets. Le premier contact valide pour
un email gagne ; un conflit n'est jamais fusionné ou résolu implicitement.

## Reproduire depuis la racine du dépôt

```bash
csv_trial=$(mktemp -d)
python atlas/csv_delivery.py deliverables/csv_cleanup_demo/input.csv "$csv_trial/cleaned.csv" --report "$csv_trial/report.json"
diff deliverables/csv_cleanup_demo/cleaned.csv "$csv_trial/cleaned.csv"
diff deliverables/csv_cleanup_demo/report.json "$csv_trial/report.json"
```

Le script `atlas/csv_delivery.py` est autonome et utilise seulement la
bibliothèque standard Python. Le générateur de démos Louis émet ce même fichier
sous le nom `process_csv.py`, sans copie parallèle de sa logique.

## Périmètre accepté

- CSV séparé par virgules, UTF-8 avec ou sans BOM ; LF et CRLF acceptés.
- Exactement trois colonnes `name`, `email`, `company`, quel que soit leur ordre.
  Seuls la casse et les espaces des en-têtes sont normalisés. Aucun renommage
  arbitraire de colonnes ou enrichissement de données manquantes.
- Espaces internes réduits et emails passés en minuscules ; validation email
  syntaxique simple, pas RFC exhaustive, existence de boîte ou consentement.
- Ligne incomplète, email invalide et cellule commençant par `=`, `+`, `-` ou
  `@` : rejet avec motif. Cette précaution tableur peut aussi rejeter du texte
  légitime ; aucun contenu n'est réinterprété en formule.
- En-têtes absents/dupliqués/inattendus, mauvais nombre de cellules, guillemets
  mal formés ou encodage non UTF-8 : échec explicite avant tout livrable.
- 10 000 000 octets et 100 000 enregistrements au maximum. Aucune mise à
  l'échelle volumineuse ou garantie universelle de nettoyage de données.
- Aucun fichier existant n'est remplacé, y compris via lien symbolique ou
  physique. Les sorties et le rapport doivent avoir des chemins distincts.
  Une erreur d'écriture système peut laisser une paire incomplète : inspecter
  avant de réessayer dans un autre répertoire, ne pas annoncer la réussite.

Tests : `python -m unittest tests.test_csv_delivery tests.test_csv_delivery_benchmark`.
Les douze cas d'acceptation sont séparés du code de nettoyage. Les 32 variantes
sont reproductibles avec une graine fixe, pas un jeu aveugle indépendant.
