# C13 — secret serveur réservé au CP, bootstrap temporaire des workers

**Identifiant documentaire :** RUNBOOK-C13-K3S-IDENTITY
**Version :** 0.1
**Statut :** Implémentation préparée ; preflight et validation terrain requis ; rotation serveur non exécutée
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

## 4. Rotation du secret serveur exposé — C13 reste ouvert avant cette phase

La migration worker ne révoque pas le secret serveur exposé. Avant rotation, inspecter les indicateurs serveur du preflight et confirmer le datastore réel, les sources de token (config/env/fichier/arguments), les éventuels autres serveurs et la sauvegarde protégée hors du CP. Un chemin local root-only seul n'est pas une sauvegarde hors machine. Les sauvegardes antérieures nécessitent l'ancien token ; décider de leur rétention et de l'archivage protégé correspondant.

La rotation doit utiliser le mécanisme k3s token rotate, pas une simple réécriture du fichier token. Elle met à jour le secret serveur et le chiffrement du bootstrap dans le datastore ; pas de garantie de coexistence générale ancien/nouveau token serveur. L'API doit être disponible pour cette opération. Avec le CP unique, prévoir une interruption lors du redémarrage serveur.

La procédure exacte de sauvegarde et de rotation sera adaptée aux sorties réelles. Elle ne doit fournir aucun token en argument ni afficher de secret ; les copies persistées de l'ancien token et les paramètres statiques éventuels doivent être traités pour ne pas réintroduire l'ancien secret au redémarrage. Le nouveau secret doit être sauvegardé hors CP, les sauvegardes annotées avec leur génération de token, puis l'ancien secret vérifié comme non valable pour de nouveaux enrôlements. Le worker migré ne reçoit jamais le nouveau secret serveur.

Après rotation : retour du CP, vérification des services, contrôle preflight, redémarrage worker pour vérifier son indépendance du secret serveur, recette C11 et nouvelles preuves. C13 n'est clos qu'après migration worker, révocation bootstrap, test après révocation, idempotence, rotation du secret serveur exposé et sauvegarde protégée vérifiées.

## Sources officielles

- https://docs.k3s.io/cli/token
- https://docs.k3s.io/cli/agent
- https://docs.k3s.io/architecture
- https://docs.k3s.io/datastore/backup-restore
- https://github.com/k3s-io/k3s/releases/tag/v1.26.2%2Bk3s1
- https://github.com/k3s-io/k3s/blob/master/pkg/agent/config/config.go (implémentation consultée ; le master n'est pas une preuve de la version installée)
