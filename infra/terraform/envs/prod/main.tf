module "prod" {
  source = "../dev"

  project_id                   = var.project_id
  region                       = var.region
  environment                  = var.environment
  db_tier                      = var.db_tier
  artifact_registry_repository = var.artifact_registry_repository
  cloud_run_image              = var.cloud_run_image
  timezone                     = var.timezone
  daily_schedule               = var.daily_schedule
  weekly_schedule              = var.weekly_schedule
  monthly_schedule             = var.monthly_schedule
  line_user_id                 = var.line_user_id
  llm_provider                 = var.llm_provider
  llm_model_name               = var.llm_model_name
  private_network              = var.private_network
  db_password                  = var.db_password
}
