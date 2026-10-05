# Проверки платформы

## Kubernetes и сеть
- Minikube, профиль campus: узел Ready.
- Cilium: агент работает.
- Hubble: наблюдение сетевых потоков работает.
- NetworkPolicy: client имеет доступ к web, outsider заблокирован.

## Terraform
- Созданы namespace campus, argocd, monitoring.
- Созданы Service Accounts для шести микросервисов.
- Создан Secret campus-credentials с четырьмя настройками.
- Повторный terraform plan: No changes.

## ArgoCD
- Все компоненты готовы.
- Настроен App of Apps: campus-root → campus-network-test.
- Синхронизация из ветки main работает.
- Приложения Synced / Healthy.
- SelfHeal возвращает число реплик web к конфигурации из Git.

## Ansible и Kafka
- Ansible Core 2.21.5, kubernetes.core 6.6.0.
- Strimzi 1.2.0, Kafka 4.3.1.
- Первый запуск: ok=6, changed=2, failed=0.
- Повторный запуск: ok=6, changed=0, failed=0.
- Kafka Ready=True; PVC 5Gi имеет статус Bound.
- Сообщение campus-kafka-test-001 записано и прочитано.
- После удаления и автоматического пересоздания пода
  campus-kafka-dual-role-0 прежнее сообщение прочитано повторно.

## Ограничения
- Kafka работает на одном узле: отказоустойчивость брокеров не проверена.
- Проверена сохранность на PVC, восстановление из резервной копии не проверено.
- Strimzi управляет Kafka через StrimziPodSet, а не StatefulSet.
  Это отличие от буквальной формулировки задания.
- Kubernetes 1.37 выходит за опубликованный диапазон тестирования
  Strimzi 1.2.0 (1.30–1.36); перечисленные проверки на стенде прошли.
- Автомасштабирование воркер-нод пока не реализовано.
