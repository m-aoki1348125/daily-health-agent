variable "project_id" { type = string }
variable "region" { type = string }
variable "environment" { type = string }
variable "db_tier" { type = string }
variable "artifact_registry_repository" { type = string }
variable "cloud_run_image" { type = string }
variable "timezone" { type = string }
variable "daily_schedule" { type = string }
variable "weekly_schedule" { type = string }
variable "monthly_schedule" { type = string }
variable "line_user_id" { type = string }
variable "llm_provider" { type = string }
variable "llm_model_name" { type = string }
variable "private_network" { type = string }
variable "db_password" { type = string }
variable "line_webhook_path" {
  type    = string
  default = "/line/webhook"
}
