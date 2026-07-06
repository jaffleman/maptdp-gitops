locals {
  db_ports = {
    postgres = 5432
    mysql    = 3306
    mariadb  = 3306
  }
  db_port = try(local.db_ports[var.db_engine], 5432)

  # Fusion et déduplication des SG autorisés
  all_sg_sources = [var.app_sg_ids]
}

resource "aws_db_subnet_group" "rds_subnet_group" {
  subnet_ids = var.network.private_rds_subnet_ids

  tags = {
    Name        = "${var.project_name}-${var.environment}-db-subnet-group"
    Project     = var.project_name
    Environment = var.environment
    Team        = var.team_tag
  }
}

resource "aws_security_group" "rds_sg" {
  name        = "${var.project_name}-${var.environment}-rds-sg"
  description = "Security group for RDS instance"
  vpc_id      = var.network.vpc_id

  revoke_rules_on_delete = true

  tags = {
    Name        = "${var.project_name}-${var.environment}-rds-sg"
    Project     = var.project_name
    Environment = var.environment
    Team        = var.team_tag
  }
}


resource "aws_security_group_rule" "rds_from_apps" {
  count = length(var.app_sg_ids)

  type                     = "ingress"
  from_port                = local.db_port
  to_port                  = local.db_port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds_sg.id
  source_security_group_id = var.app_sg_ids[count.index]
}


resource "aws_security_group_rule" "rds_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.rds_sg.id
}



resource "aws_db_instance" "rds_db_instance" {
  vpc_security_group_ids    = [aws_security_group.rds_sg.id]
  db_subnet_group_name      = aws_db_subnet_group.rds_subnet_group.name
  skip_final_snapshot       = true
  final_snapshot_identifier = "${var.project_name}-${var.environment}-final"
  instance_class            = var.db_instance_class
  engine                    = var.db_engine
  engine_version            = var.db_engine_version
  db_name                   = var.db_name
  username                  = var.db_username
  password                  = var.db_password
  allocated_storage         = var.allocated_storage
  storage_type              = "gp3"
  max_allocated_storage     = var.allocated_storage * 2
  multi_az                  = true
  publicly_accessible       = false
}
