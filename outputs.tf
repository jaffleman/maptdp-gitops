# ------------------------------
# VPC / Réseau
# ------------------------------
output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_ids" {
  value = module.network.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.network.private_workers_subnet_ids
}

output "nat_gateway_ids" {
  value = module.network.nat_gateway_ids
}

output "availability_zones" {
  value = module.network.availability_zones
}

# ------------------------------
# EKS - Outputs basés sur le module
# ------------------------------
output "eks_cluster_name" {
  value = module.eks.cluster_name
}

# Si ton module expose ces sorties (noms usuels pour terraform-aws-eks)
output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  value = module.eks.cluster_certificate_authority_data
}

output "cluster_arn" {
  value = module.eks.cluster_arn
}

# ------------------------------
# KUBECONFIG rendu statiquement (exec IAM, sans secret)
# ------------------------------
output "kubeconfig_rendered" {
  value = yamlencode({
    apiVersion = "v1"
    clusters = [{
      cluster = {
        server                     = module.eks.cluster_endpoint
        certificate-authority-data = module.eks.cluster_certificate_authority_data
      }
      name = module.eks.cluster_name
    }]
    contexts = [{
      context = {
        cluster = module.eks.cluster_name
        user    = module.eks.cluster_name
      }
      name = module.eks.cluster_name
    }]
    "current-context" = module.eks.cluster_name
    kind              = "Config"
    preferences       = {}
    users = [{
      name = module.eks.cluster_name
      user = {
        exec = {
          apiVersion = "client.authentication.k8s.io/v1beta1"
          command    = "aws"
          args       = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
        }
      }
    }]
  })
  sensitive = true
}
# ------------------------------
# RDS — Re-projection des outputs du module "rds"
# ------------------------------
output "rds_endpoint" {
  description = "Endpoint complet avec port (host:port)."
  value       = module.rds.rds_endpoint
}

output "rds_address" {
  description = "Nom DNS de l'instance (host sans port)."
  value       = module.rds.rds_address
}

output "rds_port" {
  description = "Port de la base."
  value       = module.rds.rds_port
}

output "rds_db_name" {
  description = "Nom de la base initiale."
  value       = module.rds.rds_db_name
  sensitive   = true
}

output "rds_username" {
  description = "Nom de l'utilisateur admin (master)."
  value       = module.rds.rds_username
  sensitive   = true
}

output "debug_vault" {
  value     = data.vault_kv_secret_v2.rds.data
  sensitive = true # Obligatoire pour les secrets
}
