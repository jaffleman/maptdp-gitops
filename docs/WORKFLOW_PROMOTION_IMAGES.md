# Promotion et réétiquetage des images MAPTDP

Documentation opératoire, EXEC-20261110-001, 10 novembre 2026. Aucun build, déclenchement CI ou promotion exécuté pour rédiger ce document.

## Principe et emplacement

Les branches `dev`, `staging` et `prod` du GitOps sont indépendantes par design. La promotion du code et des images se déroule dans `jaffleman/maptdp-backend` et `jaffleman/maptdp-frontend`. Une PR entre branches d’environnement du GitOps ne constitue pas une étape de promotion.

Ce document vit sur la branche `ansible`, avec les modes d’exploitation, car il décrit une procédure transversale sans modifier les repos applicatifs ni les environnements. Sources lues dans `.github/workflows/` de la branche prod des deux repos applicatifs, fichiers `backend-{dev,staging,prod}.yml` et `frontend-{dev,staging,prod}.yml`, captures de session du 10/11/2026. Vérifier les versions effectives de ces fichiers sur les branches concernées avant une future exécution. Les commandes ci-dessous sont des exemples pour une future opération autorisée, NON exécutés ici.

## Cycle réel à connaître

| Étape | Déclencheur décrit par les workflows lus | Artefact et sens du tag |
|---|---|---|
| Build dev | Push sur dev | Build et push Docker Hub de `dev-sha-<GITHUB_SHA sur 7 caractères>` et `dev-latest`. Création d’une PR applicative dev vers staging si absente. |
| Promotion staging | PR fermée et fusionnée vers staging, source dev exigée | Pull de `dev-latest`, réétiquetage et push en `staging-sha-<date Unix en secondes>` et `staging-latest`. Aucun rebuild dans ce job de réétiquetage. PR staging vers prod si absente. |
| Promotion prod | PR fermée et fusionnée vers prod, source staging exigée | Pull de `staging-latest`, réétiquetage et push en `sha-<SHA de tête de la PR sur 7 caractères>` et `latest`. Aucun rebuild dans ce job. |
| Déploiement | Commit sur la branche GitOps de l’environnement | Références explicites aux tags qualifiés dans les manifests ou values de l’environnement, puis réconciliation ArgoCD. Le push d’un tag ne prouve pas son déploiement. |

Le suffixe de `staging-sha-*` est donc actuellement un horodatage, malgré son nom. Le `sha-*` prod désigne la tête de PR utilisée pour le nommage, pas nécessairement le commit de build du binaire réétiqueté. Les tags latest sont mobiles. Aucun de ces noms ne suffit à établir l’identité du code et des octets.

Les workflows dev lus comportent gitleaks, tests, audit npm, hadolint, build-scan, Trivy, build/push. Dans ces versions, l’audit npm contient `|| true` et Trivy `exit-code: 0`. Un job vert ne prouve donc pas l’absence de vulnérabilités. Ce document ne modifie ni ces règles ni la CI.

## Qualification AVANT promotion

1. Relever le commit source exact, l’arbre Git, le run de build et les tags publiés pour le candidat. Relever également la branche et le SHA complets des PR applicatives. Une fusion verte ne prouve pas que le bon binaire sera réétiqueté depuis un latest mobile.
2. Relever le digest de l’image candidate et celui de l’image effectivement en service, pour la même plateforme. Distinguer digest d’index multi-architecture, digest de manifest de plateforme et imageID/config selon le runtime. Comparer des objets de même nature, conserver la chaîne de résolution.
3. Vérifier l’arbre de la source proposée par rapport à la source qualifiée. Par exemple, dans un clone applicatif contenant les deux objets Git

   ```bash
   git rev-parse "${SOURCE_SHA}^{tree}"
   git rev-parse "${CANDIDATE_SHA}^{tree}"
   git diff --stat "$SOURCE_SHA" "$CANDIDATE_SHA"
   ```

4. Vérifier les fonctionnalités du candidat. Pour le backend MAPTDP, qualifier notamment les routes POST `/tdp/search`, POST `/geolock/getAllAcces` et GET `/healthz`. Vérifier aussi les chemins appelés par le frontend et sa configuration d’URL API. Une inspection de routes dans une image ne vaut pas test fonctionnel du parcours.
5. Avant de valider une promotion applicative, vérifier que le latest utilisé par le workflow résout encore vers le digest qualifié. S’il a changé, arrêter et requalifier. Après réétiquetage, le digest du tag promu doit correspondre au digest retenu. Une différence impose un arrêt et un arbitrage, pas une validation par simple conformité du nom du tag.

Exemples de relevés en lecture seule, à exécuter uniquement avec l’accès et le contexte autorisés

```bash
docker buildx imagetools inspect "docker.io/jaffleman971/maptdp-backend:${TAG}"
docker buildx imagetools inspect "docker.io/jaffleman971/maptdp-frontend:${TAG}"
ssh -i ~/.ssh/ansible_ed25519 -p 63210 ubuntu@100.74.111.47 \
  'sudo -n kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml get pods -n maptdp-prod -o custom-columns=NAME:.metadata.name,IMAGE:.spec.containers[*].image,IMAGE_ID:.status.containerStatuses[*].imageID'
```

## Leçon de P5.2

PREUVE-042 a établi qu’un ancien tag prod backend ne présentait pas les routes requises alors que l’application en service les possédait. Les noms de tags et les fusions de branches ne remplaçaient pas l’identité du contenu. La qualification B0 suivante a rapproché sources, arbres, routes et digests avant modification du GitOps.

Exemples HISTORIQUES qualifiés pendant P5.2, à ne pas traiter comme un inventaire en temps réel

| Image | Tag prod qualifié | Source du contenu en service | Digest de manifest historique |
|---|---|---|---|
| backend | sha-bd0cc00 | dev-sha-b693814, également staging-sha-1784575443 | sha256:c9a5c69fe62a45bba11169a2e8a9b9126298af5ed048d23f129e6b8dc54ebf80 |
| frontend | sha-efd02ba | dev-sha-e4fef1f, également staging-sha-1785183276 | sha256:9bd7df72fbf407d263ce7d6ca37283d5c6f8914eeb01c862f886ff49d56c91ce |

Le suffixe prod et le suffixe du commit ayant construit le contenu peuvent différer, ce tableau en est un exemple. Relever des preuves fraîches à chaque future promotion.

## Passage dans chaque environnement

Après qualification et accord de promotion, laisser le workflow applicatif autorisé construire ou réétiqueter puis publier les tags. Consigner la correspondance image, tag, digest, plateforme, commit de build, tête de PR, arbre Git et branche source. Ne pas déclencher une CI pour simplement mettre à jour cette documentation.

Dans un clone propre de la branche GitOps cible, modifier uniquement les références d’images de cet environnement. Vérifier namespace, URL API, annotations ArgoCD et Image Updater, stratégie éventuelle de mise à jour, réplicas et absence de résidu d’un autre environnement. Relire le diff complet, committer et pousser sans force selon les protections applicables. Ne pas copier une branche GitOps d’environnement sur une autre.

Constater le SHA Git effectivement appliqué par ArgoCD, l’état Synced/Healthy, puis l’image et son identité réellement chargées par les pods. Qualifier le parcours de l’environnement, pas uniquement `/healthz`. Conserver une référence de retour arrière aux manifests et images précédemment qualifiés. Tout retour arrière opérationnel nécessite le périmètre d’exécution correspondant.

La mise en place ou la modification d’une automatisation CI/Ansible reste hors périmètre tant qu’elle n’est pas arbitrée séparément. Ce document n’ajoute aucun workflow ni automatisation.
