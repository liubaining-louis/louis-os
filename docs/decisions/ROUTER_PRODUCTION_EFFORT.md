# Routeur aligné sur la politique de production

Date : 25 octobre 2026

## Défaut reproduit

La politique centrale limitait une mission autonome à trois heures dans
`config/production_policy.json`, mais le routeur Internet avait encore deux
seuils locaux à huit heures : une valeur déclarative dans sa configuration et
une valeur codée dans sa logique. Une mission de quatre à huit heures pouvait
donc être affichée comme `execute_now` ou `prepare_then_gate`, avant d'être
bloquée plus tard par la politique de production.

Ce désaccord produisait une supervision trompeuse et pouvait faire préparer un
livrable qui n'était pas exécutable sous la politique courante.

## Décision

Le cycle du routeur charge désormais `max_autonomous_effort_hours` depuis la
politique centrale et le passe explicitement à la fonction de routage. Aucun
seuil de repli numérique n'est conservé dans le routeur. La configuration du
routeur référence la source centrale au lieu d'en recopier la valeur.

Le chemin `capability_build` reste séparé : il décrit une capacité à développer,
pas une autorisation d'exécuter une mission externe. Les autres critères de
sélection, les permissions, les déclencheurs et la politique centrale ne sont
pas modifiés.

## Vérification

- Une mission complète de trois heures reste `execute_now`.
- Une mission complète de 2,5 heures avec une action humaine reste
  `prepare_then_gate`.
- Une mission autrement admissible de quatre heures ne peut plus devenir une
  mission exécutable ni gated.
- Le test du cycle prouve que la limite vient du fichier de politique central.
- Les tests de politique, de passation et de sérialisation GitHub restent verts.

Le portefeuille routé du 25 octobre 2026 à 07:42 UTC ne contenait aucun candidat
actuellement exécutable entre trois et huit heures dans ses vingt premières
lignes. La correction ferme donc une incohérence de contrôle ; elle ne constitue
ni une nouvelle mission, ni une soumission, ni un revenu.

## Retour arrière

Revenir ensemble sur le chargement explicite et les tests. Ne pas réintroduire
un seuil local supérieur à la politique centrale. Toute hausse de la limite
doit être une décision explicite sur la politique de production, hors de ce lot.
