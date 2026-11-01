# C14 — postconditions de la bascule SSH

**Identifiant documentaire :** RUNBOOK-C14-SSH-POSTCONDITIONS
**Version :** 1.0
**Statut :** Validé / clos — C14, posture actuelle et contrôles outillés
**Classification :** Interne
**Propriétaire :** Sébastien MATHURIN
**Date :** 01/11/2026
**Références :** audit C14 ; playbooks/prepare_vps.yml ; playbooks/ssh_postconditions.yml ; rôle ssh_postconditions.

## Utilisation sans mutation des VPS

```bash
python3 -m unittest discover -s ops -p 'test_*.py'
ansible-playbook -i inventory/hosts.yml playbooks/ssh_postconditions.yml --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/prepare_vps.yml --syntax-check
ansible-playbook -i inventory/hosts.yml playbooks/ssh_postconditions.yml
```

Le playbook dédié lit les états, contrôle une connexion SSH neuve et sonde les endpoints. Il ne réécrit aucune configuration, ne redémarre aucun service et ne touche pas UFW. Il abandonne une éventuelle connexion Ansible persistante, force le port final via une variable de play, puis utilise pour le contrôle d'authentification une connexion OpenSSH distincte sans ControlMaster/ControlPath, BatchMode, par clé uniquement et avec StrictHostKeyChecking=yes. La clé privée par défaut est celle utilisée par le dépôt (~/.ssh/ansible_ed25519) ; ssh_postconditions_identity_file permet d'en indiquer un autre chemin. Aucun contenu de clé n'est lu ou affiché par le script.

## Critères requis

| Contrôle | Résultat exigé |
|---|---|
| Configuration | sshd -t valide ; sshd -T ne déclare que ssh_port, différent de 22, y compris les ports des ListenAddress |
| Écoutes | Aucune écoute TCP 22, y compris loopback/IPv6 ; écoute du port final présente |
| Persistance systemd | ssh.service actif et enabled ; ssh.socket inactive et disabled/masked |
| Pare-feu | UFW actif et politique entrante deny ; deny explicite 22 IPv4 et IPv6 si IPV6=yes ; aucun allow/limit explicite 22 résiduel |
| Authentification | Connexion neuve depuis MSI sur le port final et la cible d'inventaire, clé uniquement, utilisateur attendu |
| Probes 22 | Aucun endpoint sondé ne doit accepter une connexion TCP 22 ; cible d'inventaire et IP publiques déduites des interfaces globales |

Les probes distinguent refused, timeout, unreachable et error. Un timeout indique un filtrage/une absence de réponse, pas à lui seul l'absence de listener. Une absence de route (notamment IPv6 depuis WSL) est signalée comme non concluante dans warnings ; elle n'est jamais présentée comme une preuve réseau de fermeture. L'absence locale d'écoute sur toutes les interfaces, la configuration et UFW sont alors les preuves indépendantes du port 22 fermé côté VPS. Le test réseau part du contrôleur MSI, pas d'une sonde Internet indépendante.

Le contrôle ne prétend pas auditer toutes les règles UFW/OVH ni tous les paramètres Match/authentification SSH. Il vérifie le contrat de bascule et une authentification par clé effective.

## Intégration à la phase 1

prepare_vps.yml importe le playbook de postconditions dans un nouveau play à la fin, après les attentes locales de retour du port final. Le mécanisme atomique fermeture du filet/reboot reste intact : aucune tâche distante n'est ajoutée à l'ancienne session bootstrap. Le nouveau play force ansible_port=ssh_port, abandonne la connexion persistante et reconnecte sur le port final, même si bootstrap_ssh=22 a servi en phase 1.

Ne pas fournir ansible_port=22 en extra-vars : sa priorité neutraliserait le port final du nouveau play. La phase 1 peut utiliser bootstrap_ssh=22, avec variables secrètes via fichier protégé hors Git. Après phase 1, actualiser l'adresse tailnet dans l'inventaire avant la phase 2, sans extra-var globale ansible_host.

Ne jamais exécuter le rôle security seul pour vérifier C14 : son reset UFW effacerait les règles cluster. Les runs partiels par tags peuvent sauter les postconditions ; utiliser le playbook dédié pour une recette ciblée. Le playbook de préparation complet peut modifier SSH/UFW et redémarrer la machine ; ce n'est pas une commande de recette en production.

## Validation à consigner

Tests Python positifs/négatifs (écoute 22, allow résiduel, port supplémentaire, socket actif, absence de route et faux succès par connexion persistante). Syntax-checks des deux playbooks, deux passages du checker en lecture seule avec changed=0, recette C11. La future intégration après un nouveau reboot/rebuild reste à vérifier lors du prochain test PRA ; aucun reboot de production n'est requis pour lire les postconditions actuelles.

## Résultats du 01/11/2026 — PREUVE-019

39 tests Python OK sous Ubuntu (dont 11 C14), deux syntax-checks OK. Premier passage corrigé : ok=7 changed=0 unreachable=0 failed=0 sur chaque VPS. Deuxième passage avec -e bootstrap_ssh=22 : même résultat, prouvant la connexion sur le port final malgré la variable de bootstrap. Aucune modification de configuration SSH/UFW et aucun reboot/restart de VPS.

Sur les deux hôtes : ports effectifs et ListenAddress uniquement 63210 ; aucune écoute 22 ; ssh.service active/enabled ; ssh.socket inactive/disabled ; UFW actif, deny entrant et deny 22 IPv4/IPv6, aucun allow/limit explicite 22 ; nouvelle connexion par clé avec host key strictement vérifiée réussie. Probes 22 : refused sur tailnet, timeout sur IPv4 publique, unreachable sur IPv6 publique depuis MSI (limite réseau explicitement signalée). Fermeture IPv6 côté VPS confirmée indépendamment par écoutes/configuration/UFW, pas par une sonde externe IPv6.

Imprévu initial : le parseur n'acceptait pas les commentaires des règles deny du CP, pourtant présentes ; normalisation des commentaires et test représentatif ajoutés au commit 2b19f8d0. Aucun changement de pare-feu nécessaire. Recette C11 après vérification : six contrôles verts, ok=3 changed=0 failed=0. L'exécution du nouveau play automatiquement après un prochain rebuild/reboot de phase 1 restera une validation du prochain PRA, pas une opération effectuée aujourd'hui.

