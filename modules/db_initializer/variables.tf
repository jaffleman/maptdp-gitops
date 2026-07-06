variable "project_name" {
  type        = string
  description = "Nom du projet pour préfixer les ressources"
}

variable "rds_instance_id" {
  type        = string
  description = "ID de l'instance RDS PostgreSQL"
}

variable "rds_address" {
  type        = string
  description = "Endpoint (address) de l'instance RDS"
}

variable "rds_db_name" {
  type        = string
  description = "Nom de la base de données"
}

variable "rds_username" {
  type        = string
  description = "Nom de l'utilisateur Master"
}

variable "rds_password" {
  type        = string
  description = "Mot de passe Master"
  sensitive   = true
}

variable "bucket_id" {
  type        = string
  description = "ID du bucket S3 contenant le fichier SQL"
}

variable "bucket_arn" {
  type        = string
  description = "ARN du bucket S3 pour les politiques IAM"
}

variable "sql_file_key" {
  type        = string
  description = "Nom (clé) du fichier SQL dans le bucket S3"
}

variable "sql_file_etag" {
  type        = string
  description = "L'Etag du fichier S3 pour détecter les changements"
}

variable "vpc_id" {
  type        = string
  description = "ID du VPC où se trouve le RDS"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Liste des sous-réseaux privés pour CodeBuild"
}

variable "codebuild_security_group_ids" {
  type        = list(string)
  description = "Security Group à attribuer à CodeBuild"
}
