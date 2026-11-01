# C13 — secret serveur réservé au CP, bootstrap temporaire des workers

**Identifiant documentaire :** RUNBOOK-C13-K3S-IDENTITY
**Version :** 1.0
**Statut :** Validé — C13 clos le 01/11/2026 (PREUVE-017 et PREUVE-018)
**Classification :** Interne
**Propriétaire :** Sébastien MATHURIN
**Date :** 01/11/2026
**Références :** audit C13 ; PREUVE-016 ; documentation officielle k3s token, agent, architecture, backup-restore ; notes de version v1.26.2+k3s1.

## Modèle retenu et limites

Le token serveur reste sur le CP et doit disposer d'une sauvegarde protégée hors du CP, associée au datastore sauvegardé. Le worker reçoit seulement un bootstrap secure (préfixe K10 et empreinte CA), généré par le CP pour le run Ansible, TTL par défaut 20 minutes. Un bootstrap n'est pas un token à usage unique et n'est pas intrinsèquement lié à un seul nom de nœud ; sa fenêtre d'usage est réduite par la révocation explicite après Ready.

L'agent conserve ses certificats et /etc/rancher/node/password. Le fichier root-only /etc/rancher/k3s/worker-bootstrap-token reste présent après révocation pour satisfaire le chargement du token-file et conserver l'information de CA ; son secret d'enrôlement est révoqué. Ne pas supprimer l'identité locale ou le Node pour tester l'expiration. Les notes de version k3s documentent le maintien de l'identité par certificats après suppression/expiration du bootstrap, sauf suppression de l'objet Node. Le rôle teste effectivement un redémarrage après révocation et exige un nouveau Lease, pas seulement un Ready potentiellement ancien.

Un certificat expiré, une identité locale perdue, un Node supprimé ou un CP reconstruit peut imposer un nouveau bootstrap. Le rôle le génère automatiquement si le certificat/fichier est absent ou expiré, ou à la demande par k3s_refresh_bootstrap_token=true. Il ne supprime jamais automatiquement un Node existant ni son node-password. Un nom réutilisé après perte du mot de passe nécessite une procédure explicite distincte pour traiter le conflit d'identité.

## 1. Preflight en lecture seule — première commande

Depuis MSI, à la racine du dépôt, sans k3s_token ni ansible_host en extra-vars :

```bash
git pull --ff-only origin refactor/ansible-phase1-phase2
python3 -m unittest discover -s ops -p 'test_*.py'
ansible-playbook -i inventory/hosts.yml playbooks/k3s_tokens_preflight.yml --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/k3s_worker_identity.yml --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/k3s_worker.yml --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/k3s_tokens_preflight.yml
```

Le preflight cible CP et worker, requiert sudo, ne crée aucun bootstrap, n'affiche aucune valeur de token, empreinte, clé ni contenu brut de configuration. Il rapporte des booléens, une classification et la version. Les layouts personnalisés, surcharges systemd, fichiers env alternatifs ou configuration non gérée doivent être étudiés avant migration. Le script refuse de classifier une configuration env non prise en charge au lieu de l'évaluer comme du shell.

## 2. Migration du worker existant — après analyse du preflight

La recette C11 fournit l'état de référence. La migration redémarre l'agent deux fois (application, puis preuve après révocation) ; les pods peuvent subir une perturbation. Prévoir la fenêtre et contrôler les workloads après le run. Le CP n'est pas redémarré par cette migration.

```bash
ansible-playbook -i inventory/hosts.yml playbooks/recette.yml -l vps-ovh1
ansible-playbook -i inventory/hosts.yml playbooks/k3s_worker_identity.yml -l vps-ovh2
ansible-playbook -i inventory/hosts.yml playbooks/k3s_tokens_preflight.yml
ansible-playbook -i inventory/hosts.yml playbooks/recette.yml -l vps-ovh1
```

Ordre interne : vérifier le layout ; créer le bootstrap sur CP sous no_log ; copier uniquement ce bootstrap sur worker en 0600 ; configurer token-file et retirer K3S_TOKEN du fichier env standard sans sauvegarde en clair ; redémarrer ; vérifier Ready et Lease renouvelé ; révoquer le bootstrap par ID ; redémarrer à nouveau et vérifier un nouveau Lease. En cas d'échec, bloc always tente la révocation et le TTL borne la validité même si Ansible est interrompu. La valeur temporaire n'est pas mise en cache et est effacée de la variable finale ; le contrôleur admin voit néanmoins nécessairement le bootstrap en mémoire pendant le transport Ansible, jamais le secret serveur.

Attendus après migration : env_has_literal_token=false, managed_token_file_selected=true, worker_credential_kind=bootstrap, service actif et certificats présents/valides. La classification bootstrap ne prouve pas sa révocation ; celle-ci est prouvée par la réussite de token delete puis du redémarrage. Réexécuter le playbook de migration doit ne créer aucun token, ne redémarrer aucun service et converger sans changement si rien n'a dérivé.

Récupération après un échec d'enrôlement : ne pas revenir à l'ancien rôle distribuant le secret serveur. Après diagnostic du layout/Node/Lease, une nouvelle tentative peut demander un bootstrap neuf via le paramètre non secret -e k3s_refresh_bootstrap_token=true. Ne jamais coller les fichiers env, les journaux bruts ou des valeurs de tokens dans le chat.

## 3. Futurs workers et PRA

Sur un worker neuf, exécuter phase 1 puis playbooks/k3s_worker.yml sans aucun secret k3s. Le rôle installe la version k3s observée sur le CP, sans upgrade d'un worker déjà installé ; les prérequis de phase 2 restent dans le playbook existant. Les adresses viennent de l'inventaire. Le rôle n'a besoin d'aucun AppRole Vault pour l'enrôlement : le contrôleur admin utilise sa délégation SSH au CP.

Le secret serveur est régénéré sur un cluster neuf selon le bootstrap actuel ; le PRA from scratch GitOps + dumps PG ne requiert pas le token d'un ancien cluster. Restaurer un datastore k3s existant est un autre scénario : il impose le token associé à cette sauvegarde.

## 4. Rotation du secret serveur — procédure pour le layout SQLite standard

La migration worker ne révoque pas le secret serveur exposé. Avant rotation, inspecter les indicateurs serveur du preflight et confirmer le datastore réel, les sources de token (config/env/fichier/arguments), les éventuels autres serveurs et la sauvegarde protégée hors du CP. Un chemin local root-only seul n'est pas une sauvegarde hors machine. Les sauvegardes antérieures nécessitent l'ancien token ; décider de leur rétention et de l'archivage protégé correspondant.

La rotation doit utiliser le mécanisme k3s token rotate, pas une simple réécriture du fichier token. Elle met à jour le secret serveur et le chiffrement du bootstrap dans le datastore ; pas de garantie de coexistence générale ancien/nouveau token serveur. L'API doit être disponible pour cette opération. Avec le CP unique, prévoir une interruption lors du redémarrage serveur.

La procédure versionnée est ops/c13_rotate_server.py. Elle cible un CP unique au layout standard SQLite, sans token fixé dans la configuration ou l'environnement ; elle refuse les autres layouts. SSH conserve le contrôle strict de la clé hôte. Les secrets passent uniquement en mémoire/stdin sur les canaux SSH/Vault, jamais en arguments ou stdout. L'accès Vault local est saisi avec ops/c13_vault_session.py et conservé en tmpfs 0600 pour une fenêtre d'utilisation locale de 20 minutes maximum ; cela ne modifie pas le TTL réel du token Vault.

```bash
python3 ops/c13_vault_session.py
# Conserver la même valeur non secrète pour toutes les phases et reprises.
export C13_ROTATION_ID=$(date -u +%Y%m%dT%H%M%SZ)
python3 ops/c13_rotate_server.py --host 100.74.111.47 --rotation-id "$C13_ROTATION_ID" --phase prepare
python3 ops/c13_rotate_server.py --host 100.74.111.47 --rotation-id "$C13_ROTATION_ID" --phase rotate
python3 ops/c13_rotate_server.py --host 100.74.111.47 --rotation-id "$C13_ROTATION_ID" --phase verify
ansible-playbook -i inventory/hosts.yml playbooks/k3s_worker_certificate_check.yml -l vps-ovh2
ansible-playbook -i inventory/hosts.yml playbooks/recette.yml -l vps-ovh1
```

Adapter le paramètre --host à l'adresse tailnet réelle du CP avant une future utilisation. prepare archive et relit le token avant dans Vault (KV v2 CAS=0), puis crée une copie SQLite en ligne et vérifie PRAGMA quick_check. rotate enregistre une intention root-only, exécute la rotation native une seule fois, archive et relit le nouveau token puis redémarre k3s. Un marqueur dans /var/backups/k3s/c13-<rotation-id>/rotation.json permet la reprise avec le même identifiant sans répéter la rotation si le token a déjà changé. Ne pas changer rotation-id pour reprendre une opération interrompue.

Les archives sont dans k3s/infra/maptdp/server-tokens/<UID-kube-system>/<rotation-id>/before et after. Conserver before pour restaurer les sauvegardes antérieures correspondantes, malgré la révocation de son accès courant. La copie SQLite reste locale au CP en répertoire 0700 et fichier 0600 : elle sert au retour arrière local, pas à couvrir la perte du CP. Une sauvegarde hors machine de ce datastore reste un chantier distinct ; le PRA GitOps + dumps applicatifs déjà testé reste inchangé.

verify compare le token courant à l'archive after et effectue un contrôle positif/négatif sur /v1-k3s/encrypt/status, avec validation TLS : nouveau=200, ancien=401 ou 403. Ne pas utiliser /server-bootstrap pour exiger un 200 sur SQLite : cet endpoint exige etcd et renvoie 400 même après authentification valide. Le contrôle ne lit ni n'affiche les corps des réponses. Après validation, supprimer la copie locale tmpfs de l'accès Vault ; ne pas révoquer le token Vault administratif d'origine à la place du token k3s.

Après rotation : retour du CP, vérification des services, contrôle preflight, redémarrage worker pour vérifier son indépendance du secret serveur, recette C11 et nouvelles preuves. C13 n'est clos qu'après migration worker, révocation bootstrap, test après révocation, idempotence, rotation du secret serveur exposé et sauvegarde protégée vérifiées.

## 5. Validation du 01/11/2026

Volet worker : migration, révocation et redémarrage après révocation validés ; idempotence changed=0 (PREUVE-017). Rotation serveur 20261101T103530Z : archives before/after relues dans Vault, copie SQLite cohérente de 44 679 168 octets, rotation native et restart CP réussis, contrôle nouveau=200 / ancien=401. Worker redémarré après rotation sans nouveau bootstrap, Ready et nouveau Lease validés ; recette C11 verte (PREUVE-018). Tests Python : 28 réussis sous Ubuntu. Aucun secret affiché, aucun push staging.

## Sources officielles

- https://docs.k3s.io/cli/token
- https://docs.k3s.io/cli/agent
- https://docs.k3s.io/architecture
- https://docs.k3s.io/datastore/backup-restore
- https://github.com/k3s-io/k3s/releases/tag/v1.26.2%2Bk3s1
- https://github.com/k3s-io/k3s/blob/master/pkg/agent/config/config.go (implémentation consultée ; le master n'est pas une preuve de la version installée)

