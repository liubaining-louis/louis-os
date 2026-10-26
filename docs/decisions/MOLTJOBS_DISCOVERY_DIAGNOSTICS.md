# Diagnostic MoltJobs sans assouplissement d'admission

26 octobre 2026.

## Défaut et preuve

La lecture publique bornée du 25 octobre a observé dix offres OPEN à
deadlineAt=null. Le parseur les refusait, puis collect() publiait empty.
Un mélange de lignes valides et invalides était publié ok. Cela masquait une
lecture incomplète derrière une apparente absence de missions ou bonne santé.

Trois régressions échouent avant correction : dix délais absents, mélange
valide/invalide, enregistrements et champs invalides. Aucun nouveau scan public
identique, credential ou payload intégral n'est nécessaire à leur reproduction.

## Changement borné

- Zéro ligne admissible avec données invalides : failed, et non empty.
- Lignes admissibles avec données invalides : partial, et non ok.
- Compteur invalid conservé ; sous-compteurs invalid_record,
  invalid_deadline et invalid_job_fields, sans texte fourni par l'annonceur.
- Une vraie liste vide ou un filtrage métier normal conserve empty.

Les lignes admissibles sont strictement identiques. Les délais, montants,
preuves de paiement et gates compte/conditions ne sont pas assouplis. Le
collecteur existant persiste déjà les états et motifs ; aucun nouvel exécuteur,
workflow, retry, coût ou autorisation n'est ajouté. Les états sous results/
restent historiques jusqu'au prochain cycle existant, sans réétiquetage rétroactif.

## Effet, limites et retour arrière

Effet testé : dix offres à délai absent restent exclues mais leur cause devient
visible ; aucune offre supplémentaire n'est qualifiée. Les erreurs réseau et
schéma global restent failed. Les admissions et filtres métier sont rejoués en
régression. Ceci n'est ni une livraison client, ni une acceptation, ni un paiement
ou une économie mesurée. Cela ne crée pas d'accès MoltJobs ni de pivot rentable.

Retour arrière : retirer ensemble les sous-compteurs, la sélection de statut et
leurs tests. Ne jamais accepter un délai inconnu pour rétablir un état vert.
