variable "project_id" {
  type = string
}

variable "name_prefix" {
  type = string
}

variable "job_roles" {
  type = list(string)
}

variable "scheduler_roles" {
  type = list(string)
}
