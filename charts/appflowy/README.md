# AppFlowy — préproduction K3s

L'application Argo CD `appflowy-preprod` est déclarée dans
`apps/dev-staging/infra/apps/appflowy-preprod.yaml`. Elle suit la branche
`bootstrap-infra`, rend `charts/appflowy` avec `values-preprod.yaml` et utilise
uniquement le namespace `appflowy-preprod`.

## Accès

- URL : `https://appflowy-preprod.jaffleman.tech`
- Administration : `https://appflowy-preprod.jaffleman.tech/console`
- Compte initial : `admin@appflowy.local` (adresse technique locale, SMTP désactivé).
- Mot de passe initial : clé `admin-password` du Secret `appflowy-credentials`.
- Inscriptions publiques désactivées. Aucun identifiant par défaut ni secret en Git.

Pour lire le mot de passe depuis une session administrateur du cluster :

```sh
kubectl -n appflowy-preprod get secret appflowy-credentials \
  -o jsonpath='{.data.admin-password}' | base64 --decode
```

Les secrets sont créés une seule fois par le Job `appflowy-credentials-bootstrap-v1`
dans le cluster, avec génération cryptographique. Les resynchronisations ne les
régénèrent pas. Le Job ne peut ni modifier ni supprimer un Secret. Conserver ce
Secret avec les sauvegardes des données ; ne pas le supprimer pour relancer Argo CD.
Une migration vers Vault/VSO pourra réutiliser son nom et ses clés, sans changer
les références des applications. Aucun secret Vault ni rôle MapTDP n'est utilisé.

## Composants et stockage

Services officiels AppFlowy Cloud 0.21.4, Worker 0.21.4, Search 0.21.4,
Web 0.20.12, Admin 0.20.2 et GoTrue. Images référencées par digest immuable.
L'IA intégrée et les fournisseurs payants sont désactivés ; la recherche par
mots-clés est activée, sans indexation sémantique payante.

PostgreSQL/pgvector, Redis avec AOF et MinIO utilisent des StatefulSets natifs,
sans images Bitnami privées. Volumes dédiés : PostgreSQL 20 Gi, Redis 2 Gi,
MinIO 20 Gi et index Search 5 Gi. La classe de stockage par défaut du cluster
est utilisée ; `infrastructure.storageClass` et
`appflowy-search.persistence.storageClass` permettent une sélection explicite.
Les PVC des StatefulSets sont retenus à la suppression ; le PVC Search est
protégé contre le prune et la suppression Argo CD.

La persistance des volumes ne constitue pas une sauvegarde. Aucune sauvegarde
hors cluster ni restauration n'est encore qualifiée. L'outil de restauration
AppFlowy intégré reste désactivé : sa documentation exclut la restauration sous
réconciliation Argo CD active. Avant des données réelles, définir et tester une
sauvegarde de PostgreSQL, MinIO, Redis, Search et du Secret de cette instance.

## Routage et prérequis existants

Traefik termine TLS et transmet au gateway Nginx interne. Le gateway conserve
les routes `/api`, `/ws`, `/console`, retire `/gotrue` et `/minio-api`, et rétablit
le Host interne MinIO pour la signature S3. Il ne dépend pas des annotations
NGINX-Ingress ni des CRD Middleware Traefik. Les consoles MinIO et SCIM ne sont
pas exposées. Les NetworkPolicies isolent l'instance et permettent les entrées
gateway depuis `kube-system` (K3s) et `traefik`.

Conditions à vérifier côté installation :

1. Le parent Argo CD suit `apps/dev-staging/infra/apps` sur `bootstrap-infra`.
2. Le DNS `appflowy-preprod.jaffleman.tech` pointe vers l'entrée Traefik.
3. L'IngressClass `traefik`, le ClusterIssuer `letsencrypt` et une StorageClass
   par défaut fonctionnent ; les sorties HTTPS et DNS sont disponibles.
4. L'émission du certificat HTTP-01 est routée par cert-manager/Traefik.

Vérifications après synchronisation :

```sh
kubectl -n argocd get application appflowy-preprod
kubectl -n appflowy-preprod get jobs,pods,pvc,ingress,certificate
curl --fail https://appflowy-preprod.jaffleman.tech/api/health
curl --fail https://appflowy-preprod.jaffleman.tech/gotrue/health
```

Ensuite : connexion web, création/modification/suppression d'une page de test,
pièce jointe avec téléchargement, puis redémarrage des pods et contrôle de la
persistance. La connexion MCP ChatGPT et ses tests CRUD constituent une étape
suivante ; aucun connecteur opérationnel n'est déclaré dans ce commit.
Aucune migration Notion n'est lancée.

## Provenance et adaptations

Chart et templates applicatifs issus du dépôt officiel
[AppFlowy-SelfHost-Commercial](https://github.com/AppFlowy-IO/AppFlowy-SelfHost-Commercial/tree/e39869a2bae964e951832e577407e35a548b48c8/helm/appflowy-cloud),
commit `e39869a2bae964e951832e577407e35a548b48c8`, consulté le 14 novembre 2026.
Distribution commerciale auto-hébergée, offre Free acceptée : un utilisateur,
trois invités éditeurs. Les conditions officielles AppFlowy s'appliquent.

Adaptations locales : dépendances PostgreSQL/Redis/MinIO remplacées par des
StatefulSets natifs ; secrets générés hors rendu Helm et réutilisés ; gateway
Traefik ; protection PVC Search ; ServiceAccount applicatif sans token API.
Les versions et digests applicatifs proviennent du chart officiel ; les digests
GoTrue et d'infrastructure ont été résolus depuis le registre le 14 novembre 2026.

## Vérifications locales

```sh
helm lint charts/appflowy -f charts/appflowy/values-preprod.yaml
helm template appflowy-preprod charts/appflowy -n appflowy-preprod \
  -f charts/appflowy/values-preprod.yaml > /tmp/appflowy.yaml
kubeconform -strict -summary /tmp/appflowy.yaml
python -m unittest discover -s charts/appflowy/tests -v
```

Ces contrôles statiques et tests du bootstrap ne prouvent pas la santé réelle du
cluster. Ne qualifier le déploiement opérationnel qu'après les contrôles Argo CD,
TLS, authentification, pièces jointes et persistance ci-dessus.
