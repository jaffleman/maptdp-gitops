
variable "region" {
  description = "Région AWS"
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Nom du projet"
  type        = string
}

variable "environment" {
  description = "Environnement (dev, staging, prod)"
  type        = string
}

variable "cluster_name" {
  description = "Nom du cluster EKS"
  type        = string
}

variable "kubernetes_version" {
  description = "Version Kubernetes pour EKS (ex: 1.29)"
  type        = string
  default     = "1.30"
}

variable "private_subnet_ids" {
  description = "Liste des subnets privés où placer les nodes EKS"
  type        = list(string)
}

variable "instance_types" {
  description = "Types d'instances du node group"
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  description = "Taille désirée du node group"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Taille minimale du node group"
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = "Taille maximale du node group"
  type        = number
  default     = 6
}

variable "disk_size" {
  description = "Taille disque (GiB) des nodes"
  type        = number
  default     = 50
}

variable "tags" {
  description = "Tags additionnels"
  type        = map(string)
  default     = { "team-tag" : "fos-DevOps", "resource-module" : "eks" }
}
# Flag pour rendre conditionnelles les datas/ressources post-création cluster
variable "enable_post_cluster" {
  description = "Active les ressources/data post-création du cluster (OIDC provider, IRSA CSI, addons CSI). Laisser à false pour le premier apply."
  type        = bool
  default     = true
}
