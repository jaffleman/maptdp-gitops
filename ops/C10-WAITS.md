# C10 — Attentes de disponibilité bornées

Les attentes APT, k3s, VSO et ArgoCD utilisent le rôle `readiness_wait` et le programme standard Python `ops/readiness_wait.py`.

- APT : tester les quatre verrous POSIX existants sans supprimer de fichier ni interrompre de processus. Une absence de fichier n'est pas un verrou occupé. La vérification ne remplace pas le verrouillage des tâches APT suivantes.
- k3s : exiger `Node Ready=True` puis une réponse `ok` de `/readyz`, avec le kubeconfig serveur puis celui de l'utilisateur via le tailnet.
- Deployments VSO et serveur ArgoCD : génération observée à jour, nombre désiré strictement positif et réplicas totaux, actualisés, prêts et disponibles égaux au nombre désiré.
- Applications racines ArgoCD : `Synced/Healthy`, sans opération en cours ou échouée. Les états absents ou partiels restent en attente.

Chaque attente possède une échéance monotone globale. Chaque sous-processus kubectl et sa requête API sont bornés par le budget restant. Le diagnostic affiche uniquement des états sélectionnés, jamais les réponses brutes ou les Secrets. Les délais par défaut dans l'inventaire sont de 300 secondes pour APT, les nœuds et les Deployments, et 600 secondes pour chaque application ArgoCD. Ces budgets ne bornent pas la durée totale des installations ni du playbook.

## Validation sans installation

Depuis la racine du dépôt, inspecter d'abord les tâches sélectionnées :

```bash
python3 -m unittest discover -s ops -p 'test_*.py'
ansible-playbook -i inventory/hosts.yml playbooks/k3s_platform.yml --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/k3s_worker.yml --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/prepare_vps.yml --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/k3s_platform.yml -l vps-ovh1 --tags apt_wait,k3s_ready,k3s_tailnet_ready,vso_ready,argocd_ready --list-tasks
ansible-playbook -i inventory/hosts.yml playbooks/k3s_platform.yml -l vps-ovh1 --tags apt_wait,k3s_ready,k3s_tailnet_ready,vso_ready,argocd_ready
ansible-playbook -i inventory/hosts.yml playbooks/recette.yml -l vps-ovh1
```

Un test négatif peut cibler un nœud inexistant sans modifier le cluster : la commande suivante doit échouer avec `échéance globale dépassée` après environ deux secondes d'attente (hors transport Ansible).

```bash
ansible-playbook -i inventory/hosts.yml playbooks/k3s_platform.yml -l vps-ovh1 --tags k3s_ready -e readiness_name=maptdp-c10-inexistant -e readiness_timeout=2 -e readiness_poll_interval=0.2
```

Les tests Python simulent les états incomplets, les générations anciennes et les échéances. Sur Linux, ils vérifient aussi un verrou POSIX réellement détenu dans un fichier temporaire, puis sa libération sans suppression ni modification du contenu. Ne jamais bloquer les verrous APT de production pour un test.

Le bootstrap complet et une reconstruction PRA restent à valider lors d'un exercice dédié. Les contrôles ciblés ne rejouent ni Helm, ni les applications de manifests, ni les redémarrages.

## Recette du 01/11/2026 — C10 validé

Code validé : `21f086a40e4760009f1b35df27d8bdda3369ac28` sur `refactor/ansible-phase1-phase2`, aucun push staging. Sous Ubuntu : 49 tests réussis, dont verrou POSIX interprocessus ; syntax-check des trois playbooks réussi ; sélection des tâches inspectée avant exécution.

- Phase 2 CP, huit attentes : `ok=25 changed=0 failed=0`. CP Ready et API prête avec les deux kubeconfigs ; VSO et ArgoCD à 1/1 réplicas, générations observées 1 et 3 ; trois racines Synced/Healthy, opérations Succeeded.
- Phase 1, tag APT uniquement : chaque VPS `ok=4 changed=0 failed=0` ; phase 2 worker, tag APT : `ok=4 changed=0 failed=0`.
- Test négatif sur nœud inexistant : six tentatives, `elapsed_seconds=2.003`, `ok=false`, `échéance globale dépassée` ; échec Ansible attendu, aucune modification.
- Recette C11 finale : six contrôles OK, `ok=3 changed=0 failed=0` ; 2 nœuds Ready, 23 applications Synced/Healthy, 12 VSS conformes, Cron dump réussi depuis 10,4 h, workloads et HTTPS conformes. S3 et parcours métier non vérifiés.

Référence documentaire : PREUVE-020-C10-ATTENTES V1.0. Aucun paquet installé, manifeste appliqué ou service redémarré pendant cette recette ciblée.

