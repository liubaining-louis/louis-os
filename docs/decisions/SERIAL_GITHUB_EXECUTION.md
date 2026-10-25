# Une seule exécution GitHub — 25 octobre 2026

## Demande et défaut reproduit

Le propriétaire demande d'éviter les exécutions simultanées dans GitHub.
Au main `49fd71d4065b5501f09c67a5c777ae53d60bfba6`, les verrous étaient
facultatifs et répartis entre workflows ; la matrice CI exécutait Python 3.11
et 3.12 en parallèle. Un test de couverture du contrat unique échoue sur les
148 workflows avant migration.

## Contrat unique

Chaque job doté de `runs-on` acquiert exactement le même groupe :

```yaml
concurrency:
  group: louis-os-single-execution
  cancel-in-progress: false
  queue: max
```

Le groupe n'inclut ni branche, ni nom de workflow, ni version Python : un job
CI de PR, un cycle marché, une soumission et un ancien job manuel ne peuvent
donc pas occuper simultanément deux runners dans ce dépôt. La matrice CI a
aussi `max-parallel: 1`. Les anciens verrous de niveau workflow sont retirés.
Les 148 workflows sont couverts, pas seulement les trois workflows planifiés.

Un job qui appelle un workflow réutilisable local ne prend pas le verrou :
son enfant le prend lorsqu'il exécute son propre job. Cela évite qu'un parent
attende son enfant en conservant le verrou requis par cet enfant. Un appel
réutilisable externe non maîtrisé est rejeté par le contrôle de gouvernance.

Les jobs successifs d'un même workflow ne sont pas une transaction atomique :
un autre workflow peut utiliser le verrou entre deux étapes/jobs. Les
réservations, preuves, revalidations et reçus restent donc indispensables.

## Mise en place sans relancer les anciennes actions

Modifier certains anciens fichiers YAML déclenche leurs opérations cloud,
leurs soumissions ou diagnostics. Pour une publication strictement limitée à
la politique des workflows, le message de commit contient le marqueur
`[workflow-policy-only]`. Sur l'événement `push`, les jobs hors CI sont alors
sautés avant allocation du runner. Les conditions déjà présentes sont
conservées et combinées avec cette garde.

Ce marqueur n'est PAS une instruction GitHub de suppression de CI. La CI
`ci.yml` n'a pas cette exception et doit réussir au SHA exact avant fusion,
puis sur le commit intégré. Les vérifications `pull_request` continuent
normalement. Les futurs commits ordinaires, schedules et lancements manuels
gardent leurs déclencheurs d'origine. Ne pas utiliser le marqueur pour une
modification fonctionnelle devant effectivement exécuter un workflow métier.

## Vérification et limites

- `scripts/validate_workflow_governance.py` exige ce contrat pour chaque job.
- Tests : mauvais groupe, annulation, queue absente, matrice parallèle,
  appel parent verrouillé, réutilisation externe et garde de publication absente.
- Comparaison YAML locale avec le main initial : mêmes événements, permissions,
  variables, jobs, commandes et étapes ; seuls les verrous, les conditions de
  publication et `max-parallel` changent. Certaines fins de fichier sont normalisées.
- Les calendriers restent trois workflows et sept déclenchements théoriques/jour.
- GitHub peut afficher plusieurs workflows en cours/en attente : la garantie
  porte sur UN job de runner actif, pas sur l'unicité des lignes de l'interface.
- `queue: max` accepte jusqu'à 100 jobs/runs en attente ; au-delà, GitHub annule
  les arrivées supplémentaires. L'ordre strict des soumissions n'est pas garanti.
- Un job long, bloqué sur une dépendance ou en attente d'approbation peut retarder
  les suivants. Diagnostiquer avant toute annulation ; réconcilier les effets
  externes incertains. Le verrou ne garantit pas l'exécution exactement une fois.
- Les anciennes exécutions utilisant un ancien YAML ne sont pas rétroactivement
  sérialisées. Vérifier qu'elles sont terminées au moment de l'intégration.
- Le verrou GitHub ne couvre ni une VM, ni un opérateur externe, ni un autre
  dépôt. Il ne réactive pas GCP et n'autorise aucun nouveau coût ou transfert.

Références officielles vérifiées le 25/10/2026 :
https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/

Retour arrière : PR ciblée, testée, conservant les gardes de publication tant
que les déclencheurs historiques n'ont pas été neutralisés par une décision
revue. Ne pas faire un revert aveugle : retirer aussi ces gardes pourrait
relancer les anciens jobs sur push, même avec le marqueur. Aucun reçu supprimé.
