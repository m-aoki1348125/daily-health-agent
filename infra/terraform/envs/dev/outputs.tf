output "artifact_registry_repository" {
  value = google_artifact_registry_repository.repo.name
}

output "cloud_sql_connection_name" {
  value = module.cloud_sql.instance_connection_name
}

output "daily_job_name" {
  value = module.daily_job.name
}

output "line_webhook_url" {
  value = google_cloud_run_v2_service.line_webhook.uri
}
