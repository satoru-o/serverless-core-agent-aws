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
    key          = "core/terraform.tfstate"
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
      Phase     = "core"
    }
  }
}