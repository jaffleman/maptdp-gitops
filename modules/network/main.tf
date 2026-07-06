data "aws_availability_zones" "this" {
  state = "available"
}

locals {
  # Liste des AZ à utiliser (tronquée à az_count)
  azs = slice(data.aws_availability_zones.this.names, 0, var.az_count)

  # Conserver /16 -> /24 (newbits = 8) et familles disjointes
  # Public:  10.0.0.0/24, 10.0.1.0/24, 10.0.2.0/24
  # Workers: 10.0.20.0/24, 10.0.21.0/24, 10.0.22.0/24
  # RDS:     10.0.30.0/24, 10.0.31.0/24, 10.0.32.0/24

  computed_public_cidrs          = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, 0 + i)]
  computed_private_workers_cidrs = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, 20 + i)]
  computed_private_rds_cidrs     = [for i in range(var.az_count) : cidrsubnet(var.vpc_cidr, 8, 30 + i)]

  public_cidrs          = var.public_subnet_cidrs != null ? var.public_subnet_cidrs : local.computed_public_cidrs
  private_workers_cidrs = var.private_subnet_cidrs != null ? var.private_subnet_cidrs : local.computed_private_workers_cidrs
  private_rds_cidrs     = var.private_rds_subnet_cidrs != null ? var.private_rds_subnet_cidrs : local.computed_private_rds_cidrs

  # Mapping index → { az, cidr_public, cidr_private }
  az_map = {
    for i, az in local.azs :
    i => {
      az                   = az
      cidr_public          = local.public_cidrs[i]
      cidr_private_workers = local.private_workers_cidrs[i]
      cidr_private_rds     = local.private_rds_cidrs[i]

    }
  }

  base_tags = merge({
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "Terraform"
    Module      = "network"
  }, var.tags)
}

# VPC
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.base_tags, {
    Name = "${var.project}-${var.environment}-vpc"
  })
}

# IGW
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags = merge(local.base_tags, {
    Name = "${var.project}-${var.environment}-igw"
  })
}

# Subnets publics
resource "aws_subnet" "public" {
  for_each                = local.az_map
  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr_public
  availability_zone       = each.value.az
  map_public_ip_on_launch = true

  tags = merge(local.base_tags, {
    Name                                            = "${var.project}-${var.environment}-public-${each.value.az}"
    "kubernetes.io/role/elb"                        = "1" # Requis pour ALB public
    "kubernetes.io/cluster/${var.eks_cluster_name}" = var.eks_cluster_name == "" ? null : "shared"
  })
}

# Subnets privés
resource "aws_subnet" "private_workers" {
  for_each                = local.az_map
  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr_private_workers
  availability_zone       = each.value.az
  map_public_ip_on_launch = false

  tags = merge(local.base_tags, {
    Name                                            = "${var.project}-${var.environment}-private-${each.value.az}"
    "kubernetes.io/role/internal-elb"               = "1" # Requis pour ALB interne (optionnel)
    "kubernetes.io/cluster/${var.eks_cluster_name}" = var.eks_cluster_name == "" ? null : "shared"
  })
}

resource "aws_subnet" "private_rds" {
  for_each                = local.az_map
  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr_private_rds
  availability_zone       = each.value.az
  map_public_ip_on_launch = false

  tags = merge(local.base_tags, {
    Name = "${var.project}-${var.environment}-private-${each.value.az}"
  })
}

# Table de routage publique + route vers IGW
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags = merge(local.base_tags, {
    Name = "${var.project}-${var.environment}-rt-public"
  })
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

# Associations des subnets publics à la RT publique
resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

#############################
# NAT Gateway(s) + EIP(s)
#############################

# NAT par AZ (HA) : EIP & NAT pour chaque subnet public
resource "aws_eip" "nat_eip_per_az" {
  for_each = aws_subnet.public
  domain   = "vpc"

  tags = merge(local.base_tags, {
    Name = "${var.project}-${var.environment}-eip-nat-${each.key}"
  })
}

resource "aws_nat_gateway" "per_az" {
  for_each      = aws_subnet.public
  allocation_id = aws_eip.nat_eip_per_az[each.key].id
  subnet_id     = each.value.id

  tags = merge(local.base_tags, {
    Name = "${var.project}-${var.environment}-nat-${each.key}"
  })

  depends_on = [aws_internet_gateway.this]
}

#############################
# Routage privé
#############################


resource "aws_route_table" "private_per_az" {
  for_each = aws_subnet.private_workers
  vpc_id   = aws_vpc.this.id

  tags = merge(local.base_tags, {
    Name = "${var.project}-${var.environment}-rt-private-${each.key}"
  })
}

resource "aws_route" "private_per_az_default" {
  for_each               = aws_route_table.private_per_az
  route_table_id         = each.value.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.per_az[each.key].id
}

resource "aws_route_table_association" "private_per_az_assoc" {
  for_each       = aws_subnet.private_workers
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private_per_az[each.key].id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.this.id              # Votre ID de VPC
  service_name = "com.amazonaws.eu-west-3.s3" # Adaptez la région si besoin (ici eu-west-3)
  route_table_ids = concat(
    [aws_route_table.public.id],
    [for k, rt in aws_route_table.private_per_az : rt.id] # Associe l'endpoint à vos tables de routage privées
  )

  tags = {
    Name = "${var.project}-${var.environment}-s3-endpoint"
  }
}
