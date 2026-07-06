variable "project_name" {
  description = "Nom du projet pour les tags"
  type        = string
  default     = "wordpress-eks"
}
variable "environment" {
  description = "Environnement pour les tags"
  type        = string
}
variable "team_tag" {
  description = "Tag de l'équipe propriétaire des ressources"
  type        = string
  default     = "ofs-devops"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
}

variable "db_engine" {
  description = "Database engine (e.g., postgres, mysql)"
  type        = string
}

variable "db_engine_version" {
  description = "Database engine version"
  type        = string
}

variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_username" {
  description = "Master username"
  type        = string
}

variable "db_password" {
  description = "Master password"
  type        = string
  sensitive   = true
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
}

variable "app_sg_ids" {
  description = "Security Groups des applications autorisées à accéder à RDS"
  type        = list(string)
  default     = []
}


# Objet réseau (puisqu'on lui passe vpc_id + subnets)
variable "network" {
  description = "Infos réseau pour RDS (VPC + subnets privés RDS)"
  type = object({
    vpc_id                 = string
    private_rds_subnet_ids = list(string)
  })
}
