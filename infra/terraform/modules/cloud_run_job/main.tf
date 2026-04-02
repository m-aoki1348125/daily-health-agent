locals {
  env_list = [for key, value in var.plain_env : {
    name  = key
    value = value
  }]
  secret_env_list = [for key, value in var.secret_env : {
    name = key
    value_source = {
      secret_key_ref = {
        secret  = value.secret
        version = value.version
      }
    }
  }]
}

resource "google_cloud_run_v2_job" "job" {
  name     = "${var.name_prefix}-${var.job_name}"
  location = var.region

  template {
    template {
      service_account = var.service_account_email
      timeout         = "${var.timeout_seconds}s"
      max_retries     = 1

      containers {
        image = var.image
        args  = var.args

        dynamic "env" {
          for_each = concat(local.env_list, local.secret_env_list)
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
            cpu    = var.cpu
            memory = var.memory
          }
        }
      }
    }
  }
}
