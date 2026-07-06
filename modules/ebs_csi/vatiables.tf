variable "project_name" {
  type        = string
  description = "Nom du projet (pour le nommage IAM)"
}

variable "environment" {
  type        = string
  description = "Environnement (ex: AWS-PROD)"
}

variable "cluster_name" {
  type        = string
  description = "Nom du cluster EKS"
}

variable "cluster_oidc_issuer" {
  type        = string
  description = "Issuer OIDC complet du cluster EKS (https://oidc.eks.<region>.amazonaws.com/id/xxx)"
}
