resource "aws_iam_role" "codebuild_rds_role" {
  name = "${var.project_name}-codebuild-rds-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "codebuild.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "codebuild_combined_policy" {
  name = "${var.project_name}-codebuild-combined-policy"
  role = aws_iam_role.codebuild_rds_role.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "VPCAccessAndNetwork"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeVpcs",
          "ec2:DescribeDhcpOptions",
          "ec2:CreateNetworkInterfacePermission"
        ]
        Resource = "*"
      },
      {
        Sid    = "S3BucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:ListBucket"
        ]
        Resource = [
          "${var.bucket_arn}",
          "${var.bucket_arn}/*"
        ]
      },
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}



resource "aws_codebuild_project" "db_init" {
  name         = "${var.project_name}-rds-initializer"
  service_role = aws_iam_role.codebuild_rds_role.arn

  artifacts { type = "NO_ARTIFACTS" }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = true
  }

  source {
    type = "NO_SOURCE"
    buildspec = jsonencode({
      version = "0.2"
      phases = {
        build = {
          commands = [
            "aws s3 cp s3://${var.bucket_id}/${var.sql_file_key} ./database.sql",

            # 1. On stocke le mot de passe dans une variable d'environnement CodeBuild
            "export PGPASSWORD='${var.rds_password}'",

            # 2. On demande à Docker d'injecter cette variable SANS l'écrire dans la commande psql
            "docker run --rm -v $(pwd):/workspace -e PGPASSWORD postgres:15-alpine psql -h '${var.rds_address}' -U '${var.rds_username}' -d '${var.rds_db_name}' -f /workspace/database.sql"
          ]
        }
      }
    })
  }

  vpc_config {
    vpc_id             = var.vpc_id
    subnets            = var.private_subnet_ids
    security_group_ids = var.codebuild_security_group_ids
  }
}

resource "terraform_data" "trigger_codebuild" {
  depends_on = [aws_codebuild_project.db_init]

  triggers_replace = {
    sql_file_version = var.sql_file_etag
    rds_id           = var.rds_instance_id
  }

  provisioner "local-exec" {
    command = "aws codebuild start-build --project-name ${aws_codebuild_project.db_init.name}"
  }
}
