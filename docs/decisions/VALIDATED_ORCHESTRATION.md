# Une seule boucle d'acceptation — 25 octobre 2026

## Décision

Simplifier le chemin conversationnel de `atlas.missions.run_mission` :
plan déterministe, spécialiste, contrôle structurel, critique explicite,
révision si nécessaire. Retourner exactement le texte accepté, sans nouvelle
synthèse ni réparation supplémentaire hors budget.

Le refus critique persistant était reproductible sur le main de départ
`f7c79a6b0c28af11e1769f7c420193b7541e1823` : après une révision et un second
`VERDICT: REVISE`, une synthèse pouvait encore produire `completed`.

## Contrat

- Seule une première ligne exacte `VERDICT: PASS` (casse indifférente) accepte
  une réponse. Réponse critique vide ou mal formée : aucun succès implicite.
- Les contrôles structurels sont exécutés avant de demander une critique.
- Toute révision conserve objectif, contexte et avertissement sur les mémoires.
- Réparations structurelles et révisions critiques partagent le même budget :
  une par défaut, deux au maximum, aucune si la configuration vaut zéro.
- La réponse finale n'est jamais réécrite après son acceptation.
- `completed`, `failed_validation` et `approval_required` restent les états
  publics ; les champs de résultat restent compatibles. Les étapes de trace
  `synthesis` et `contract_repair` disparaissent.
- L'auteur et le modèle enregistrés sont ceux du texte retourné, pas du critique.
- Une action à haut risque reste arrêtée avant tout appel de modèle.

## Effet mesurable et limites

Une réponse acceptée sans révision nécessite deux appels logiques au modèle au
lieu de trois. Avec une révision : quatre au lieu de cinq pour ce scénario.
La borne maximale est six appels logiques, hors tentatives internes des
fournisseurs. Aucun changement de modèle, de cadence, de permission ou de coût
autorisé. Il ne s'agit pas d'une mesure de tokens, de latence réelle ou d'euros.

Les tests utilisent des réponses simulées et vérifient les états, les budgets,
la conservation du contexte et l'identité du texte accepté. Ils ne démontrent
ni une amélioration de qualité sur tâches inconnues, ni un résultat client,
ni une soumission ou un paiement. Le runtime marché sans VM n'utilise pas cette
chaîne comme générateur universel : ne pas lui attribuer ces gains.

## Suite de la simplification

1. Unifier la limite d'effort du routeur et la politique centrale, sans
   assouplir celle-ci ; reproduire et tester avant une PR séparée.
2. Corriger la récupération de mémoire non pertinente et distinguer confiance
   déclarée, succès interne et résultat externe réellement vérifié.
3. Cartographier les points d'entrée actifs, leurs dépendances et les voies
   historiques. Retirer les vrais doublons par lots réversibles ; ne pas
   supprimer un adaptateur, un reçu ou un workflow sur son seul nom.
4. Comparer une chaîne simple et Louis sur les mêmes tâches et budgets ;
   instrumenter temps humain et coûts par livrable accepté avant extension.

Chaque lot doit avoir un effet précis, des tests, une PR et une CI au SHA exact.
La politique de production, les reçus historiques, l'exclusion du charbon,
l'interdiction de transactions et la non-réactivation de GCP restent inchangés.

## Retour arrière

Révoquer le commit de cette PR par une PR de revert avec CI. Aucune migration
de données, modification de credentials ou changement de dépendance n'est requis.
