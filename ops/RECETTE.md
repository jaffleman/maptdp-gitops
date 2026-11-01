# C11 — recette de plateforme en lecture seule

Depuis le contrôleur Ansible, à la racine du dépôt :

```bash
ansible-playbook -i inventory/hosts.yml playbooks/recette.yml -l vps-ovh1 --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/recette.yml -l vps-ovh1
```

Prérequis : phase 2 terminée, accès SSH utilisateur au CP, python3 et kubectl sur le CP, kubeconfig utilisateur fonctionnel. Aucun AppRole, token k3s, rôle runtime, pip ou module Python externe requis. Le playbook n'installe rien et ne modifie aucun objet cluster. Il lance le script Python via command/argv sur le CP, sans fichier distant. Les GET HTTPS partent aussi du CP, avec validation TLS et sans suivi des redirections.

Le rapport collecte six contrôles, continue après une défaillance de contrôle et renvoie un code non nul si l'un échoue. Les erreurs kubectl brutes ne sont pas reproduites. Les WARN bénins de lecture de config k3s n'invalident pas un kubectl qui réussit. Tous les appels réseau et kubectl ont un délai borné. Une indisponibilité de l'API peut néanmoins cumuler ces délais sur plusieurs contrôles.

| Contrôle | Critères |
|---|---|
| Nœuds | vps-cp et vps-worker présents ; tous les nœuds Ready, non cordonnés et versions kubelet alignées |
| ArgoCD | Au moins 23 applications ; toutes Synced/Healthy ; aucune opération Running/Terminating/Failed/Error |
| VSO | Pod(s) dont le nom contient vault-secrets-operator Running/Ready ; au moins 12 VaultStaticSecrets ; conditions SecretSynced (ou Synced), Healthy, Ready vraies ; génération courante quand exposée |
| Cron dump | CronJob postgres-backup-cronjob présent, non suspendu ; succès d'un Job possédé par son UID datant d'au plus 30 h ; dernier Job non Failed et non bloqué depuis plus d'une heure |
| Application | Deployments frontend/backend avec au moins 2 réplicas souhaités ; StatefulSet maptdp-db présent ; tous les Deployments/StatefulSets staging prêts et actualisés |
| HTTPS | Frontend https://maptdp.jaffleman.tech/ et API https://api.jaffleman.tech/healthz répondent 200 avec certificat vérifié |

Les URLs proviennent des values-staging et du chemin de probe backend lus dans la branche staging. L'objet vivant doit être inspecté si le test révèle une divergence. Les paramètres recette_* peuvent être surchargés via un fichier extra-vars non secret : namespace, nœuds attendus, seuils, fenêtre de sauvegarde, timeout et liste recette_https_checks (objets url/status). Une liste HTTPS vide échoue explicitement. Les seuils 23/12 sont des minima pour permettre les ajouts, pas une preuve d'identité de chaque ressource attendue.

Limites : états déclarés VSO (pas de lecture des Secrets ni preuve de renouvellement effectif), historique Jobs conservé (pas de lecture du bucket S3), disponibilité des workloads et endpoints HTTPS (pas de requête métier, ni lecture/écriture DB). Une suppression de l'historique des Jobs peut faire échouer le contrôle de sauvegarde même si le dump existe dans S3 ; investiguer, ne pas contourner silencieusement. Un Synced=False VSO doit être diagnostiqué au regard du comportement connu VSO 1.4.0, sans supprimer de Secret pour faire passer la recette.

Validation hors cluster : `python3 -m unittest discover -s ops -p test_recette.py`. Validation terrain : à réaliser par l'utilisateur, avec changed=0 attendu ; une recette entièrement verte ne remplace pas le test PRA ni la recette métier.
