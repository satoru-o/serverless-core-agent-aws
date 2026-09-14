terraform {
  required_version = "~> 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  backend "s3" {
    bucket       = "sca-aws-tfstate"
    key          = "agent/terraform.tfstate"
    region       = "ap-northeast-1"
    use_lockfile = true
    encrypt      = true
    profile      = "sca-aws"
  }
}

provider "aws" {
  region  = "ap-northeast-1"
  profile = "sca-aws"

  default_tags {
    tags = {
      Project   = "serverless-core-agent-aws"
      ManagedBy = "terraform"
      Phase     = "agent"
    }
  }
}

data "aws_caller_identity" "current" {}

# core/ のtfstateを参照し、Ticket APIのREST API ID・execution_arnを取得する
# (002-agent-safe-operation research.md §10)
data "terraform_remote_state" "core" {
  backend = "s3"

  config = {
    bucket  = "sca-aws-tfstate"
    key     = "core/terraform.tfstate"
    region  = "ap-northeast-1"
    profile = "sca-aws"
  }
}
