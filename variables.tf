############################################
# NETWORK VARIABLES
############################################
variable "region" {
  description = "Région AWS"
  type        = string
  default     = "eu-west-3"
}
# variable "vpc_cidr" {
#   description = "CIDR du VPC"
#   type        = string
#   default     = "10.0.0.0/16"
# }

############################################
# PROJECT VARIABLES
############################################
variable "project_name" {
  description = "Nom du projet pour les tags"
  type        = string
  default     = "mapttdp-project"
}
variable "environment" {
  description = "Environnement (dev|staging|prod)"
  type        = string
  default     = "prod"
}
# variable "team_tag" {
#   description = "Tag de l'équipe propriétaire des ressources"
#   type        = string
#   default     = "jaff-devops"
# }

############################################
# RDS VARIABLES
############################################
variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}
variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}
variable "db_engine" {
  description = "Database engine (postgres, mysql)"
  type        = string
  default     = "postgres"
}
variable "db_engine_version" {
  description = "Database engine version"
  type        = string
  default     = "13"
}

###########################################
# OVERWRIDE RDS VARIABLES FOR DB CREATION
###########################################
variable "db_name" {
  description = "Database name"
  type        = string
  default     = "maptdpbdd"
}
variable "db_username" {
  description = "Database username"
  type        = string
  default     = "wpadmin"
}
variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
  default     = "password"
}

############################################
# ISSUER — activation conditionnelle
############################################
variable "enable_issuer" {
  description = "Active la création du ClusterIssuer (séparé des add-ons)"
  type        = bool
  default     = false
}

variable "vault_role_id" {
  type      = string
  sensitive = true
}

variable "vault_secret_id" {
  type      = string
  sensitive = true
}

variable "s3_bucket_name" {
  type        = string
  description = "Nom du bucket S3 contenant les assets de la base de données"
  default     = "maptdp-database-489575506572-eu-west-3-an"
}
