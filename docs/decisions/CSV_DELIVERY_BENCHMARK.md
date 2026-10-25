# Banc de livraison CSV : outil réel et critères d'acceptation séparés

Date : 25 octobre 2026. Main initial :
`99c827284ebf77a2c8bf7fe8018562f83fb61070`.

## Défauts reproduits

Le générateur contenait déjà une petite démo CSV avec un seul exemple attendu.
Il affirmait `input_not_overwritten` après un test en mémoire, sans appeler le
traitement de fichier. Une sortie liée physiquement à l'entrée passait la seule
comparaison de chemins résolus et modifiait réellement l'original. Ce défaut a
été reproduit dans un répertoire temporaire, pas sur des données utilisateur.

Les lignes invalides et les doublons étaient ignorés sans rapport, les en-têtes
réordonnés/espacés n'étaient pas normalisés et un simple `@` suffisait à passer
le contrôle email. Le nouveau contrat exige un rapport : le score initial du
nouveau benchmark n'est donc pas une comparaison équitable de deux outils
supportant déjà la même interface. Ne pas présenter « 0 à 12 » comme un progrès
de généralisation.

## Une seule implémentation

`atlas/csv_delivery.py` est la source canonique, autonome et standard-library.
`csv_automation_demo_files()` l'émet sous le nom `process_csv.py`, à la place
de l'ancien grand bloc de code embarqué. Aucun autre générateur, routeur ou
modèle n'est ajouté. La validation existante de la démo vérifie désormais de
vrais fichiers et le hash de l'entrée, et émet un contrôle de rapport.

Le contrat est volontairement étroit : trois colonnes de contacts, CSV virgule
UTF-8/BOM, 10 MB et 100 000 lignes. Les sorties préexistantes sont refusées.
Les rejets et les doublons, dont les conflits, sont décrits par enregistrement.
Premier email valide conservé ; aucune donnée manquante n'est inventée.
Le README du livrable documente toutes les limites et la reprise après erreur
d'écriture système. Pas de nettoyage universel, vérification de boîte email,
soumission ou autorisation commerciale implicite.

## Preuves inspectables

- Douze cas CSV/JSON écrits séparément du nettoyeur dans
  `benchmarks/csv_delivery/cases.json` : sept succès et cinq refus de schéma ou
  parsing. Exécution du script autonome dans un répertoire temporaire neuf,
  comparaison octet à octet du CSV, du rapport JSON attendu et de l'entrée.
- Trente-deux variantes générées à graine fixe : ordre/casse des en-têtes,
  LF/CRLF, BOM, tailles et ordre des contacts, doublons et valeurs manquantes.
  L'oracle vient des contacts synthétiques avant perturbation, pas du nettoyeur.
- Chemins identiques, liens symboliques/physiques, sorties ou rapport existants,
  déterminisme, limites taille/lignes et encodage : tests de protection.
- Un programme qui annonce simplement la réussite, ou modifie l'entrée puis
  annonce un refus, est rejeté par le banc. `python -I` isole les imports mais
  n'est pas un sandbox : seul le code de confiance du dépôt est exécuté.
- Dossier montrable `deliverables/csv_cleanup_demo/` : entrée synthétique de six
  lignes, CSV de deux contacts et rapport expliquant deux doublons et deux
  rejets. Test de reproduction exacte des deux fichiers livrés et de leur hash.

Le corpus est connu pendant le développement, pas un test aveugle indépendant.
Ces résultats mesurent un outil déterministe écrit avec le pilote, pas Louis
générant seul du code à partir d'une demande client. Le temps local du banc est
mesuré séparément par cas ; ce n'est pas le temps commercial d'une mission.
Aucun appel modèle ou réseau n'est nécessaire au banc.

## Coûts, état opérationnel et suite

Politiques et verrous GitHub inchangés ; pas de hausse de fréquence, accès VM,
wallet, credentials ni facturation GCP. Aucun nouveau coût API. Coût Actions
marginal/total inconnu. Zéro mission externe qualifiée, soumission, acceptation
ou paiement nouveau. Le dossier synthétique n'est pas compté comme client livré.

Les anciens fichiers et reçus datés sous `results/software_micro_mission_demos/`
ne sont pas réécrits : ils restent des snapshots de leur ancien code. Le prochain
cycle autorisé régénérera la démo avec la source canonique. Aucun cycle externe
n'est déclenché pour cette publication. Le marqueur `[workflow-policy-only]`
doit être conservé au commit d'intégration pour éviter les anciens jobs push.

Prochaine étape : choisir une vraie mission compatible avec ce contrat et un
accès déjà autorisé, ou évaluer un besoin utilisateur concret sans élargir les
permissions. Ne pas réécrire des scripts génériques ni multiplier les démos sans
nouveau critère d'acceptation. Retour arrière possible sur cette branche, sans
migration ou suppression de données utilisateur ; garder les tests du défaut.
