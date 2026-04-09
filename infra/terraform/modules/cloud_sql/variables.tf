variable "name_prefix" { type = string }
variable "region" { type = string }
variable "db_tier" { type = string }
variable "db_disk_type" {
  type    = string
  default = "PD_SSD"
}
variable "db_backup_enabled" {
  type    = bool
  default = true
}
variable "private_network" { type = string }
variable "database_name" { type = string }
variable "database_user" { type = string }
variable "database_password" { type = string }
