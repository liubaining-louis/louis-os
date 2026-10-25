# Premier lot de montée en niveau : contexte mémoire mesuré

Date : 25 octobre 2026. Base : `676e0e3886933db493dabfc614bcf53415f0feea`.

## Défaut et périmètre

Une requête `normalize csv columns` retournait un souvenir `hotel reservation
Edinburgh` avec une confiance de 1. Le score de pertinence nul recevait un bonus
de confiance de 0,05, égal au seuil d'admission. Le repli lexical pouvait aussi
faire passer une sous-chaîne (`api` dans `apiculture`) ou tous les souvenirs
lorsque la requête n'avait aucun terme exploitable.

Le benchmark existant ne contenait que trois recherches positives et abaissait
le seuil à zéro. Il mesurait le rang du bon résultat, pas les souvenirs inutiles
qui entraient avec lui dans le contexte.

Ce lot corrige uniquement la sélection du contexte mémoire existant. Il ne
construit pas un nouveau moteur d'agents et n'ajoute aucun fournisseur, appel
réseau, credential, modèle, wallet ou dépendance. Les anciennes PR #2 et #23
portent sur la fondation/abstraction du stockage mémoire ; ce lot ne reprend
pas leur migration ni leur fournisseur d'embeddings et conserve les interfaces
actuelles.

## Décision

- Exiger un terme exact commun avant d'admettre une similarité par hachage.
  Une collision de vecteurs n'est pas une preuve de pertinence.
- Appliquer le seuil à la similarité avant le bonus de confiance. La confiance
  aide à classer les souvenirs admissibles, pas à les rendre pertinents.
- Partager la tokenisation entre les chemins sémantique local et lexical.
  S'abstenir pour une requête vide ou sans terme exploitable, y compris dans le
  repli hybride.
- Conserver les deux affirmations pertinentes quand elles sont actives mais
  contradictoires. Ni une confiance supérieure ni une date récente ne prouvent
  automatiquement laquelle est vraie. La source centrale reste à vérifier.

## Banc d'essai et résultat

`benchmarks/semantic_memory/mission_context_v2.json` contient douze scénarios
figés de contexte : CSV, petite API, comparaison sourcée, absence d'information,
requête vide, termes inutilisables, mauvais domaine, casse du domaine,
affirmations contradictoires, sous-chaîne trompeuse et souvenir superseded.
Ce corpus n'active aucune recherche commerciale ni activité charbon.

Mesure sur le même corpus et les mêmes seuils, avant/après le correctif :

| Mesure | Avant | Après |
|---|---:|---:|
| Cas avec ensemble exact de souvenirs attendu | 3/12 | 12/12 |
| Souvenirs indésirables retournés, cumulés par cas | 19 | 0 |
| Abstentions correctes | 0/5 | 5/5 |
| Bon résultat en tête des cas positifs | 7/7 | 7/7 |

Le benchmark v1 conserve ses seuils et réussit avec le seuil de production,
sans abaissement spécial. Les nouveaux contrôles refusent un résultat dont le
premier souvenir est bon mais le reste contaminé, ou qui masque une des deux
affirmations attendues.

Les douze cas sont également rejoués depuis un stockage local temporaire dans
les trois modes sémantique, hybride et lexical (36 combinaisons). Des tests de
mission passent par `run_mission`, la récupération, le contexte du spécialiste
et le reçu local `memories_used`, avec des réponses de modèle simulées. Ils
vérifient le câblage, pas la vérité du texte généré ni l'aptitude à livrer une
mission réelle. Les tests normaux de l'orchestrateur restent inchangés.

Cent tests locaux ciblant mémoire, orchestrateur, expérience, routeur,
passation, politique et verrou GitHub réussissent. La compilation, le contrôle
de diff et la gouvernance des workflows réussissent également. La suite CI
complète au SHA exact reste obligatoire avant toute intégration.

## Limites et prochaine étape

Ce sont des exemples de développement connus, pas un jeu indépendant ni une
preuve de généralisation. Le mécanisme reste lexical/haché, non un véritable
modèle sémantique multilingue. L'exigence de mots communs peut manquer des
paraphrases. Les mots génériques peuvent encore faire remonter des souvenirs
faiblement utiles. La fenêtre des cent derniers souvenirs n'est pas agrandie.
Les contradictions restent visibles mais ne sont pas résolues automatiquement.

Le chemin testé est celui des missions conversationnelles, pas le générateur
universel du runtime marché. Aucun taux de livraison réelle, coût modèle ou
revenu supplémentaire n'est mesuré. Les politiques, verrous GitHub et
fréquences restent identiques. Coût Actions marginal/total inconnu.

Prochain lot : un petit jeu indépendant de missions CSV/API/recherche avec
fichiers d'entrée, livrables attendus et critères déterministes. Mesurer d'abord
la réussite sans intervention et les erreurs avant livraison ; n'utiliser un
modèle réel qu'avec l'accès et le budget déjà autorisés. Ne pas déduire cette
réussite des réponses simulées de ce lot.

Retour arrière : rétablir les deux fonctions de récupération ensemble, en
conservant le benchmark comme témoin explicite du défaut. Aucune migration ni
suppression de données mémoire n'est nécessaire.
