resource "google_service_account" "job" {
  account_id   = "${var.name_prefix}-job"
  display_name = "${var.name_prefix} job service account"
}

resource "google_service_account" "scheduler" {
  account_id   = "${var.name_prefix}-scheduler"
  display_name = "${var.name_prefix} scheduler service account"
}

resource "google_project_iam_member" "job_roles" {
  for_each = toset(var.job_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.job.email}"
}

resource "google_project_iam_member" "scheduler_roles" {
  for_each = toset(var.scheduler_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}
