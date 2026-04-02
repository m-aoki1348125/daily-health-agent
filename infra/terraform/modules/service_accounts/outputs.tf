output "job_service_account_email" {
  value = google_service_account.job.email
}

output "scheduler_service_account_email" {
  value = google_service_account.scheduler.email
}
