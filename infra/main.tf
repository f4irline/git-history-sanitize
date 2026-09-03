# Illustrative Terraform configuration only.
terraform {
  required_version = ">= 1.5.0"
}

variable "environment" {
  description = "A label for the example environment."
  type        = string
  default     = "demo"
}

output "environment" {
  value = var.environment
}
