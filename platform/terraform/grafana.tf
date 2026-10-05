resource "random_password" "grafana_admin" {
  length  = 40
  special = false
}

resource "kubernetes_secret_v1" "grafana_admin" {
  metadata {
    name      = "grafana-admin"
    namespace = kubernetes_namespace_v1.platform["monitoring"].metadata[0].name
  }

  type = "Opaque"

  data = {
    username = "admin"
    password = random_password.grafana_admin.result
  }
}
