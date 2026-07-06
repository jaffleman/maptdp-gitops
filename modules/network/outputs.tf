output "vpc_id" {
  value       = aws_vpc.this.id
  description = "ID du VPC"
}

output "igw_id" {
  value       = aws_internet_gateway.this.id
  description = "ID de l'Internet Gateway"
}

output "public_subnet_ids" {
  value       = [for k, s in aws_subnet.public : s.id]
  description = "Liste des IDs des subnets publics"
}

output "private_workers_subnet_ids" {
  value       = [for k, s in aws_subnet.private_workers : s.id]
  description = "Liste des IDs des subnets privés pour les workers"
}

output "private_rds_subnet_ids" {
  value       = [for k, s in aws_subnet.private_rds : s.id]
  description = "Liste des IDs des subnets privés pour RDS"
}

output "availability_zones" {
  value       = [for az in local.azs : az]
  description = "AZs utilisées"
}

output "public_route_table_id" {
  value       = aws_route_table.public.id
  description = "ID de la route table publique"
}

output "private_workers_route_table_ids" {
  value       = [for k, rt in aws_route_table.private_per_az : rt.id]
  description = "IDs des route tables privées"
}

output "nat_gateway_ids" {
  value       = [for k, nat in aws_nat_gateway.per_az : nat.id]
  description = "IDs des NAT Gateways"
}
