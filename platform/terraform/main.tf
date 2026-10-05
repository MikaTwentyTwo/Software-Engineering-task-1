terraform {
  required_version = ">= 1.16.0, < 2.0.0"

  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.36.0, < 4.0.0"
    }
  }
}

provider "kubernetes" {
  config_path    = pathexpand("~/.kube/config")
  config_context = "campus"
}

locals {
  namespaces = toset([
    "campus",
    "argocd",
    "monitoring"
  ])

  services = toset([
    "users",
    "rooms",
    "equipment",
    "bookings",
    "notifications",
    "audit"
  ])
}

resource "kubernetes_namespace_v1" "platform" {
  for_each = local.namespaces

  metadata {
    name = each.value
    labels = {
      "app.kubernetes.io/part-of" = "campusreserve"
    }
  }
}

resource "kubernetes_service_account_v1" "services" {
  for_each = local.services

  metadata {
    name      = each.value
    namespace = kubernetes_namespace_v1.platform["campus"].metadata[0].name
  }

  automount_service_account_token = false
}
resource "random_password" "credentials" {
  for_each = toset([
    "POSTGRES_PASSWORD",
    "TOKEN_SECRET",
    "ADMIN_PASSWORD",
    "STUDENT_PASSWORD"
  ])

  length  = 40
  special = false
}

resource "kubernetes_secret_v1" "credentials" {
  metadata {
    name      = "campus-credentials"
    namespace = kubernetes_namespace_v1.platform["campus"].metadata[0].name
  }

  type = "Opaque"

  data = {
    for name, password in random_password.credentials :
    name => password.result
  }
}