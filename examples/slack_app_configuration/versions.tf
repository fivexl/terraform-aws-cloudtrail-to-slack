terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.47.0"
    }
    external = {
      source  = "hashicorp/external"
      version = ">= 2.4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.9.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.3.0"
    }
  }
}
