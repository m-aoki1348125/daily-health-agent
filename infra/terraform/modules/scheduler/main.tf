resource "google_cloud_scheduler_job" "job" {
  name      = "${var.name_prefix}-${var.job_name}"
  region    = var.region
  schedule  = var.schedule
  time_zone = var.timezone

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_number}/jobs/${var.cloud_run_job_name}:run"

    oauth_token {
      service_account_email = var.scheduler_service_account_email
    }
  }
}
