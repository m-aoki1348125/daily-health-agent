resource "google_sql_database_instance" "postgres" {
  name             = "${var.name_prefix}-postgres"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier = var.db_tier
    disk_type = var.db_disk_type
    backup_configuration {
      enabled = var.db_backup_enabled
    }
    ip_configuration {
      ipv4_enabled = true
    }
  }

  deletion_protection = false
}

resource "google_sql_database" "app" {
  name     = var.database_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  name     = var.database_user
  instance = google_sql_database_instance.postgres.name
  password = var.database_password
}
