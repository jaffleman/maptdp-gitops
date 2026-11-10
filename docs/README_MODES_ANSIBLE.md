# Modes d’usage Ansible MAPTDP

EXEC-20261110-001, 10 novembre 2026. Branche d’exploitation `ansible`, dépôt `jaffleman/maptdp-gitops`. Documentation de commandes pour une future exécution autorisée. Cette session n’exécute ni reconstruction complète, ni phase 1, ni relance à froid de phase 2.

## Préconditions communes

Lancer depuis Ubuntu sur le MSI, avec Ansible et les collections du projet installés, clé SSH privée disponible localement, hôtes et clés d’hôte vérifiés. Ne jamais afficher ou committer les identifiants Vault, Tailscale, S3, les tokens ou le contenu des fichiers privés. L’accès root temporaire de la session S3 ne constitue pas une autorisation de lancer les procédures ci-dessous.

Le wrapper Phoenix et le rôle historique `argocd_bootstrapv2` utilisent le chemin persistant `$HOME/maptdp-gitops`. Avant toute exécution, vérifier ce checkout, sa branche, son commit et ses fichiers. Un clone placé ailleurs n’isole pas ces dépendances. Ne pas écraser un checkout existant ou sale pour faire correspondre le chemin. Les dépendances volatiles sont proscrites, notamment kubeconfig temporaire réutilisé entre appels, répertoire de session supposé présent ou contexte implicite. Si une copie temporaire est indispensable, elle doit être créée, utilisée et supprimée dans un même appel. Le kubeconfig canonique du VPS reste `/etc/rancher/k3s/k3s.yaml`, sans modification de son contexte.

Pré-vol local, commandes en lecture seule

```bash
cd "$HOME/maptdp-gitops"
git status --short --branch
git log -1 --oneline
git branch --show-current
ansible-inventory -i inventory/hosts.yml --graph
ansible -i inventory/hosts.yml vps-ovh1 -m debug -a var=ansible_python_interpreter
```

`vps-ovh1` est l’alias du control-plane `vps-cp`, `vps-ovh2` celui du worker. Depuis D1, `vps-ovh1` porte `ansible_python_interpreter: /opt/ansible-venv/bin/python` dans `inventory/hosts.yml`. Le worker n’a pas reçu cette variable. Les IP effectives et le port doivent être constatés avant une opération, les exemples ne remplacent pas l’inventaire.

**Ne jamais exécuter le tag `security` seul.** Son UFW reset peut supprimer les règles Tailscale et provoquer la partition CP/worker observée le 20/10. Utiliser la séquence complète autorisée qui repose les règles, avec un plan de reprise d’accès et les garde-fous du mandat de reconstruction.

## 1 — Reconstruction complète sur VPS vierge

Le lancement exige un mandat de reconstruction et la sauvegarde des données concernées. Aucun de ces actes n’est autorisé par le seul document présent.

Phoenix ne lance pas `prepare_vps.yml`. La phase 1 se lance d’abord explicitement, puis la phase 2 du control-plane se lance via `phoenix-v2.sh --ansible-only`. Le mode Phoenix par défaut peut appeler `$HOME/lib/clean_vps.sh`, fichier hors dépôt. Ne pas utiliser le mode par défaut ni `--clean-only` pour une simple reconstruction Ansible ou une relance de serveur existant.

Pour un CP réellement vierge, `/opt/ansible-venv/bin/python` n’existe pas encore. La toute première phase 1 doit démarrer avec le Python système, puis crée le venv. L’override ci-dessous est limité à ce bootstrap initial. Le port 22 doit être le port effectivement ouvert sur le VPS neuf.

Préparer en privé, hors dépôt et mode 0600, le fichier persistant `$HOME/.config/maptdp/phase1-private.json` contenant les paramètres propres au VPS et la clé d’enrôlement Tailscale. Ne pas en afficher le contenu. Il doit inclure l’adresse publique `ansible_host` correcte pour cette phase. Vérifier aussi que `node_hostname` correspond au nœud visé.

```bash
cd "$HOME/maptdp-gitops"
test -f "$HOME/.config/maptdp/phase1-private.json"
test "$(stat -c '%a' "$HOME/.config/maptdp/phase1-private.json")" = 600
ansible-playbook -i inventory/hosts.yml playbooks/prepare_vps.yml \
  -l vps-ovh1 -e bootstrap_ssh=22 \
  -e ansible_python_interpreter=/usr/bin/python3 \
  -e @"$HOME/.config/maptdp/phase1-private.json"
```

La phase 1 peut durcir SSH/UFW, enrôler Tailscale et provoquer un reboot fire-and-forget pour la bascule SSH vers 63210. Vérifier son résultat et le retour d’accès avant de continuer. Mettre à jour l’adresse Tailscale dans l’inventaire si le ré-enrôlement l’a changée, selon le mandat applicable.

La phase 2 ne doit pas recevoir d’extra-var globale `ansible_host` ou d’interpréteur. Les extra-vars ont une précédence globale et peuvent détourner une tâche déléguée vers le mauvais hôte. Le fichier privé phase 1 ne doit pas être réutilisé en phase 2.

```bash
cd "$HOME/maptdp-gitops"
ANSIBLE_INVENTORY="$PWD/inventory/hosts.yml" bash ./phoenix-v2.sh --ansible-only
```

Le wrapper lance `playbooks/k3s_platform.yml`. Il demande les identifiants AppRole Vault nécessaires à cette chaîne. Les saisir en console privée, sans `--secret-id` ou `--role-id` en clair dans l’historique. Le SecretID est masqué par le wrapper, mais la saisie et l’affichage du RoleID ne sont pas intégralement masqués dans cette version. Son `phoenix.log` est sensible et doit être expurgé avant tout partage. Ne pas ajouter `--verbose` par défaut.

Le worker utilise sa phase 1 puis `playbooks/k3s_worker.yml`, pas `k3s_platform.yml`. Son enrôlement et son token exigent un périmètre d’exécution propre, non fourni par cette documentation.

## 2 — Relance ciblée sur un serveur en service

Exemple `argocd_bootstrapv2`, sans override d’interpréteur. Vérifier d’abord le venv distant et les manifestes persistants `root_app_dir` lus par le rôle. La sélection `bootstrap` évite les autres rôles de la phase 2, notamment Vault et le réseau.

```bash
cd "$HOME/maptdp-gitops"
ansible-playbook -i inventory/hosts.yml playbooks/k3s_platform.yml \
  -l vps-ovh1 --tags bootstrap --list-tasks
ansible-playbook -i inventory/hosts.yml playbooks/k3s_platform.yml \
  -l vps-ovh1 --tags bootstrap --ssh-common-args='-o ConnectTimeout=10'
```

Sous réserve d’un mandat autorisant la relance, conserver la sortie complète quel que soit le code retour, protéger les journaux et expurger avant partage. Comparer l’état des applications avant/après, ainsi que les éventuels `changed`, `failed` et `unreachable`.

Preuve D1 de cette session, commit d’inventaire `16a086a` et PREUVE-060, relance réelle sur vps-cp sans override d’interpréteur, `ok=8 changed=0 unreachable=0 failed=0`, 29/29 Applications Synced/Healthy avant et après. Le worker n’a pas été exécuté.

## 3 — Relance à froid de la phase 2 sur serveur existant

Ce mode reprend la phase 2 complète et ses rôles. Il n’est pas équivalent au seul bootstrap ArgoCD. Vérifier les accès, les dépendances persistantes, les changements attendus, les sauvegardes, les secrets nécessaires et le mandat d’exécution. Ne pas repasser la phase 1 ou le nettoyage Phoenix pour obtenir une simple relance de phase 2.

```bash
cd "$HOME/maptdp-gitops"
ansible-playbook -i inventory/hosts.yml playbooks/k3s_platform.yml --list-tasks
ANSIBLE_INVENTORY="$PWD/inventory/hosts.yml" bash ./phoenix-v2.sh --ansible-only
```

Les modules cherchent à converger vers l’état attendu. `changed` peut être non nul sans échec, une réinstallation, un rafraîchissement ou un fait recalculé ne se déduit pas du seul nombre. Qualifier les tâches changées et vérifier le service, plutôt que d’exiger systématiquement changed=0 pour une chaîne complète. L’exemple historique worker du 29/10, `ok=49 changed=14 failed=0` sans reboot, concerne la phase 1 selon les commentaires d’inventaire. Il ne prouve pas une relance à froid complète de la phase 2 du CP. Celle-ci est NON TESTÉE dans EXEC-20261110-001.

## Limite du contenu actuel et gouvernance

Le rôle `argocd_bootstrapv2` de la branche `ansible` observée pour D1 repose sur les racines root-appv2, dev et staging. La tâche de racine prod publiée pendant P5.2 se trouve sur `refactor/ansible-phase1-phase2` au commit `1ee06cf`. Cette session ne copie ni ne fusionne ces branches. La procédure décrit la chaîne présente, elle ne certifie pas une reconstruction complète et canonique de toute la production depuis `ansible`. Réconcilier ce périmètre avant un futur test réel de reconstruction.

Aucune automatisation CI/Ansible n’est mise en place par ce README. La CI reste hors périmètre tant qu’elle n’est pas arbitrée. Ne pas ajouter de workflow ou planifier une relance sur la seule base de cette documentation.
