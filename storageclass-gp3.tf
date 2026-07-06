resource "kubernetes_storage_class_v1" "gp3" {
  metadata {
    name = "gp3"
    annotations = {
      # rendre gp3 la StorageClass par défaut du cluster
      "storageclass.kubernetes.io/is-default-class" = "true"
    }
  }

  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true

  parameters = {
    type      = "gp3"
    fsType    = "ext4"
    encrypted = "true"
    # (optionnel) iops / throughput si tu veux fixer des perf:
    # iops       = "3000"
    # throughput = "125"
  }

  # s’assure que le driver est installé avant de créer la SC
  depends_on = [
    module.ebs_csi
  ]
}
