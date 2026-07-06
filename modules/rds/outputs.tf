output "rds_endpoint" {
  description = "Endpoint complet avec port (host:port)."
  value       = aws_db_instance.rds_db_instance.endpoint
}

output "rds_address" {
  description = "Nom DNS de l'instance (host sans port)."
  value       = aws_db_instance.rds_db_instance.address
}

output "rds_port" {
  description = "Port de la base (ex: 5432 pour Postgres)."
  value       = aws_db_instance.rds_db_instance.port
}

output "rds_db_name" {
  description = "Nom de la base initiale créée."
  value       = aws_db_instance.rds_db_instance.db_name
}

output "rds_username" {
  description = "Nom de l'utilisateur admin (master). À ne pas utiliser côté app."
  value       = aws_db_instance.rds_db_instance.username
}
