terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.26"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  name_prefix = "daily-health-${var.environment}"
  secret_names = [
    "fitbit-client-id",
    "fitbit-client-secret",
    "fitbit-refresh-token",
    "openai-api-key",
    "claude-api-key",
    "line-channel-access-token",
    "line-channel-secret",
    "db-password",
    "drive-root-folder-id",
    "drive-oauth-client-id",
    "drive-oauth-client-secret",
    "drive-oauth-refresh-token",
  ]
  plain_env = {
    APP_ENV            = var.environment
    TIMEZONE           = var.timezone
    FITBIT_CLIENT_MODE = "api"
    GOOGLE_DRIVE_MODE  = "api"
    LINE_CLIENT_MODE   = "api"
    LINE_USER_ID       = var.line_user_id
    LLM_PROVIDER       = var.llm_provider
    LLM_MODEL_NAME     = var.llm_model_name
    DATABASE_URL       = "postgresql+psycopg://health_agent:${var.db_password}@/health_agent?host=/cloudsql/${module.cloud_sql.instance_connection_name}"
  }
  secret_env = {
    FITBIT_CLIENT_ID          = { secret = "fitbit-client-id", version = "latest" }
    FITBIT_CLIENT_SECRET      = { secret = "fitbit-client-secret", version = "latest" }
    FITBIT_REFRESH_TOKEN      = { secret = "fitbit-refresh-token", version = "latest" }
    OPENAI_API_KEY            = { secret = "openai-api-key", version = "latest" }
    CLAUDE_API_KEY            = { secret = "claude-api-key", version = "latest" }
    LINE_CHANNEL_ACCESS_TOKEN = { secret = "line-channel-access-token", version = "latest" }
    LINE_CHANNEL_SECRET       = { secret = "line-channel-secret", version = "latest" }
    DRIVE_ROOT_FOLDER_ID      = { secret = "drive-root-folder-id", version = "latest" }
    DRIVE_OAUTH_CLIENT_ID     = { secret = "drive-oauth-client-id", version = "latest" }
    DRIVE_OAUTH_CLIENT_SECRET = { secret = "drive-oauth-client-secret", version = "latest" }
    DRIVE_OAUTH_REFRESH_TOKEN = { secret = "drive-oauth-refresh-token", version = "latest" }
  }
  webhook_plain_env = {
    APP_ENV            = var.environment
    TIMEZONE           = var.timezone
    GOOGLE_DRIVE_MODE  = "api"
    LINE_CLIENT_MODE   = "api"
    LINE_USER_ID       = var.line_user_id
    LLM_PROVIDER       = var.llm_provider
    LLM_MODEL_NAME     = var.llm_model_name
    LINE_WEBHOOK_PATH  = var.line_webhook_path
    DATABASE_URL       = "postgresql+psycopg://health_agent:${var.db_password}@/health_agent?host=/cloudsql/${module.cloud_sql.instance_connection_name}"
  }
  webhook_secret_env = {
    OPENAI_API_KEY            = { secret = "openai-api-key", version = "latest" }
    CLAUDE_API_KEY            = { secret = "claude-api-key", version = "latest" }
    LINE_CHANNEL_ACCESS_TOKEN = { secret = "line-channel-access-token", version = "latest" }
    LINE_CHANNEL_SECRET       = { secret = "line-channel-secret", version = "latest" }
    DRIVE_ROOT_FOLDER_ID      = { secret = "drive-root-folder-id", version = "latest" }
    DRIVE_OAUTH_CLIENT_ID     = { secret = "drive-oauth-client-id", version = "latest" }
    DRIVE_OAUTH_CLIENT_SECRET = { secret = "drive-oauth-client-secret", version = "latest" }
    DRIVE_OAUTH_REFRESH_TOKEN = { secret = "drive-oauth-refresh-token", version = "latest" }
  }
  webhook_env_list = [for key, value in local.webhook_plain_env : {
    name  = key
    value = value
  }]
  webhook_secret_env_list = [for key, value in local.webhook_secret_env : {
    name = key
    value_source = {
      secret_key_ref = {
        secret  = value.secret
        version = value.version
      }
    }
  }]
}

resource "google_project_service" "services" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "drive.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "iam.googleapis.com",
    "compute.googleapis.com",
  ])
  project = var.project_id
  service = each.value
}

resource "google_artifact_registry_repository" "repo" {
  repository_id = var.artifact_registry_repository
  location      = var.region
  format        = "DOCKER"
}

module "service_accounts" {
  source      = "../../modules/service_accounts"
  project_id  = var.project_id
  name_prefix = local.name_prefix
  job_roles = [
    "roles/logging.logWriter",
    "roles/secretmanager.secretAccessor",
    "roles/secretmanager.secretVersionAdder",
    "roles/cloudsql.client",
  ]
  scheduler_roles = [
    "roles/run.invoker",
  ]
}

module "secrets" {
  source       = "../../modules/secrets"
  secret_names = local.secret_names
}

module "cloud_sql" {
  source            = "../../modules/cloud_sql"
  name_prefix       = local.name_prefix
  region            = var.region
  db_tier           = var.db_tier
  private_network   = var.private_network
  database_name     = "health_agent"
  database_user     = "health_agent"
  database_password = var.db_password
}

module "daily_job" {
  source                = "../../modules/cloud_run_job"
  name_prefix           = local.name_prefix
  region                = var.region
  job_name              = "daily"
  image                 = var.cloud_run_image
  service_account_email = module.service_accounts.job_service_account_email
  args                  = ["-m", "app.batch.run_daily_job"]
  plain_env             = local.plain_env
  secret_env            = local.secret_env
  cloud_sql_instances   = [module.cloud_sql.instance_connection_name]
  cpu                   = "1"
  memory                = "512Mi"
  timeout_seconds       = 900
  max_retries           = 0
}

module "weekly_job" {
  source                = "../../modules/cloud_run_job"
  name_prefix           = local.name_prefix
  region                = var.region
  job_name              = "weekly"
  image                 = var.cloud_run_image
  service_account_email = module.service_accounts.job_service_account_email
  args                  = ["-m", "app.batch.run_weekly_job"]
  plain_env             = local.plain_env
  secret_env            = local.secret_env
  cloud_sql_instances   = [module.cloud_sql.instance_connection_name]
  cpu                   = "1"
  memory                = "512Mi"
  timeout_seconds       = 900
  max_retries           = 0
}

module "monthly_job" {
  source                = "../../modules/cloud_run_job"
  name_prefix           = local.name_prefix
  region                = var.region
  job_name              = "monthly"
  image                 = var.cloud_run_image
  service_account_email = module.service_accounts.job_service_account_email
  args                  = ["-m", "app.batch.run_monthly_job"]
  plain_env             = local.plain_env
  secret_env            = local.secret_env
  cloud_sql_instances   = [module.cloud_sql.instance_connection_name]
  cpu                   = "1"
  memory                = "512Mi"
  timeout_seconds       = 900
  max_retries           = 0
}

resource "google_cloud_run_v2_service" "line_webhook" {
  name     = "${local.name_prefix}-line-webhook"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = module.service_accounts.job_service_account_email
    timeout         = "300s"

    containers {
      image   = var.cloud_run_image
      command = ["python"]
      args = [
        "-m",
        "uvicorn",
        "app.web.line_webhook:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
      ]

      dynamic "env" {
        for_each = concat(local.webhook_env_list, local.webhook_secret_env_list)
        content {
          name = env.value.name

          dynamic "value_source" {
            for_each = try([env.value.value_source], [])
            content {
              secret_key_ref {
                secret  = value_source.value.secret_key_ref.secret
                version = value_source.value.secret_key_ref.version
              }
            }
          }

          value = try(env.value.value, null)
        }
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [module.cloud_sql.instance_connection_name]
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "line_webhook_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.line_webhook.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

data "google_project" "current" {
  project_id = var.project_id
}

module "daily_scheduler" {
  source                          = "../../modules/scheduler"
  name_prefix                     = local.name_prefix
  job_name                        = "daily"
  region                          = var.region
  schedule                        = var.daily_schedule
  timezone                        = var.timezone
  project_number                  = data.google_project.current.number
  cloud_run_job_name              = module.daily_job.name
  scheduler_service_account_email = module.service_accounts.scheduler_service_account_email
}

module "weekly_scheduler" {
  source                          = "../../modules/scheduler"
  name_prefix                     = local.name_prefix
  job_name                        = "weekly"
  region                          = var.region
  schedule                        = var.weekly_schedule
  timezone                        = var.timezone
  project_number                  = data.google_project.current.number
  cloud_run_job_name              = module.weekly_job.name
  scheduler_service_account_email = module.service_accounts.scheduler_service_account_email
}

module "monthly_scheduler" {
  source                          = "../../modules/scheduler"
  name_prefix                     = local.name_prefix
  job_name                        = "monthly"
  region                          = var.region
  schedule                        = var.monthly_schedule
  timezone                        = var.timezone
  project_number                  = data.google_project.current.number
  cloud_run_job_name              = module.monthly_job.name
  scheduler_service_account_email = module.service_accounts.scheduler_service_account_email
}
