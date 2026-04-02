variable "name_prefix" { type = string }
variable "region" { type = string }
variable "job_name" { type = string }
variable "image" { type = string }
variable "service_account_email" { type = string }
variable "args" { type = list(string) }
variable "plain_env" { type = map(string) }
variable "secret_env" {
  type = map(object({
    secret  = string
    version = string
  }))
}
variable "cpu" { type = string }
variable "memory" { type = string }
variable "timeout_seconds" { type = number }
