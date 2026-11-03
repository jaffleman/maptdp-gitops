# Sauvegarde locale des images MAPTDP

Exécuter sur le MSI avec Bash, GNU coreutils, Python 3 et Docker Engine local sur /var/run/docker.sock. Cible linux/amd64. Données applicatives internes : choisir un répertoire privé hors synchronisation cloud, avec assez d’espace pour les couches et les TAR. Ne transmettre ni clé, ni Docker config, ni Secret Kubernetes.

1. À partir du relevé des pods, sélectionner un imageID complet docker.io/...@sha256:... et conserver à part la correspondance entre tag de déploiement, digest et namespace. Une même image peut servir à plusieurs tags. Un ancien ReplicaSet à zéro n’est pas une preuve d’exécution.
2. Depuis la racine du dépôt :

```bash
umask 077
OUT="$HOME/images-maptdp"
REF='docker.io/jaffleman971/maptdp-backend@sha256:c9a5c69fe62a45bba11169a2e8a9b9126298af5ed048d23f129e6b8dc54ebf80'
ops/images/backup-image.sh "$REF" "$OUT"
ops/images/load-image.sh "$OUT/${REF##*:}"
```

Le premier script utilise un client vierge et exige un digest de Docker Hub. Il enregistre un TAR sans tag, la source, l’ID Docker local et leurs SHA-256 dans un sous-dossier par digest. Un export existant est conservé. Pour vérifier une archive existante, utiliser le second script. Pour un nouvel essai indépendant, employer un autre répertoire. En cas de refus anonyme, consigner le refus et arrêter pour cette image. Ne pas remplacer un digest indisponible par le tag courant.

Le rechargement cible le démon Docker local et vérifie l’ID obtenu. Le choix d’un futur nom ou tag relève de la procédure de reprise. Avant toute affectation, comparer la destination et l’objet existant pour éviter d’écraser une autre référence. Le daemon containerd de k3s a son propre magasin : une image chargée sur MSI n’est pas installée dans le cluster. Aucun déploiement ni push dans ces scripts.

Les sauvegardes restent transitoires. Un test pod, une publication ou un stockage distant demandent la session dédiée et l’accord de Sébastien.