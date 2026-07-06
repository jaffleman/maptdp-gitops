
variable "region" {
  description = "Région AWS"
  type        = string
  default     = "eu-west-3"
}

variable "vpc_cidr" {
  description = "CIDR du VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Nombre d'AZ à utiliser (eu-west-3 = 3 max)"
  type        = number
  default     = 2
}

variable "nat_per_az" {
  description = "true = 1 NAT Gateway par AZ, false = 1 seule NAT Gateway"
  type        = bool
  default     = true
}

variable "single_nat_az_index" {
  description = "Index (0-based) de l'AZ hébergeant la NAT unique si nat_per_az=false"
  type        = number
  default     = 0
}

variable "project" {
  description = "Nom du projet pour les tags"
  type        = string
}

variable "environment" {
  description = "Environnement (dev|staging|prod)"
  type        = string
}

variable "eks_cluster_name" {
  description = "Nom du cluster EKS (pour tag cluster facultatif). Laisser vide pour ignorer."
  type        = string
  default     = ""
}

variable "public_subnet_cidrs" {
  description = "Optionnel: liste des CIDR des subnets publics (longueur = az_count). Si null, calcul automatique."
  type        = list(string)
  default     = null
}

variable "private_subnet_cidrs" {
  description = "Optionnel: liste des CIDR des subnets privés (longueur = az_count). Si null, calcul automatique."
  type        = list(string)
  default     = null
}

variable "private_rds_subnet_cidrs" {
  description = "Optionnel: liste des CIDR des subnets privés pour RDS (longueur = az_count). Si null, calcul automatique."
  type        = list(string)
  default     = null
}

variable "tags" {
  description = "Tags additionnels"
  type        = map(string)
  default     = { "team-tag" : "fos-DevOps", "resource-module" : "network" }
}
