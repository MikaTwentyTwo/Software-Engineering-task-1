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

## Helm и приложение в Kubernetes
- PostgreSQL, Valkey, MongoDB hot/cold развёрнуты через Helm и ArgoCD.
- PostgreSQL создал пять баз микросервисов.
- Рабочий KafkaTopic campus.events.v1: 6 разделов, Ready=True.
- Созданы шесть отдельных Helm-чартов микросервисов.
- Все микросервисы готовы; bookings имеет две реплики.

## Istio и Gateway
- Istio 1.31.1 установлен через ArgoCD.
- Шесть микросервисов работают с sidecar-прокси.
- Gateway имеет две готовые реплики.
- Маршруты /api/<service>/ настроены для всех сервисов.
- Все приложения ArgoCD: Synced / Healthy.
- Через Gateway успешно пройден scripts/demo.py:
  auth, roles, projections, idempotency, conflict,
  notification, audit, cancellation, concurrency, ownership.

## Пока не проверено
- Circuit Breaker, Outlier Detection и retry-политики.
- Rate Limiting в Kubernetes.
- Отказоустойчивая внешняя точка входа с Keepalived.
- Observability и нагрузочное тестирование.
- Автоматическая сборка и доставка образов.

## Проверка Outlier Detection и retry
- В одном экземпляре bookings включён временный ответ 503.
- Отправлено 100 GET-запросов из users через sidecar Istio.
- Все 100 запросов завершились с HTTP 200.
- Счётчик ejections_enforced_total вырос с 0 до 1.
- upstream_rq_retry: 4; upstream_rq_retry_success: 4.
- Тестовый отказ отключён.
- После периода исключения ejections_active вернулся к 0.
- API bookings/ready доступен.
- Отдельная диагностическая команда прямого запроса не прошла
  из-за ошибки кавычек; её результат не используется как доказательство.
- Проверка переполнения connection pool и тест с Locust ещё не выполнены.

## Проверка Outlier Detection и retry
- В одном экземпляре bookings включён временный ответ 503.
- Отправлено 100 GET-запросов из users через sidecar Istio.
- Все 100 запросов завершились с HTTP 200.
- Счётчик ejections_enforced_total вырос с 0 до 1.
- upstream_rq_retry: 4; upstream_rq_retry_success: 4.
- Тестовый отказ отключён.
- После периода исключения ejections_active вернулся к 0.
- API bookings/ready доступен.
- Отдельная диагностическая команда прямого запроса не прошла
  из-за ошибки кавычек; её результат не используется как доказательство.
- Проверка переполнения connection pool и тест с Locust ещё не выполнены.

## Rate Limiting
- Развёрнут Envoy Rate Limit Service с отдельным Valkey.
- Gateway настроен на общий лимит 20 запросов в секунду.
- Проверка через localhost:8080: 200 запросов, 20 параллельных потоков.
- Результат: HTTP 200 — 40; HTTP 429 — 160.
- Использование общего счётчика двумя репликами Gateway
  пока не проверено отдельным тестом.

## Общий лимит двух реплик Gateway
- Выполнены прямые обращения к двум разным подам Gateway.
- 100 запросов, 20 параллельных потоков, длительность 0.388 секунды.
- Первая реплика: 200 — 10, 429 — 40.
- Вторая реплика: 200 — 10, 429 — 40.
- Суммарно: 200 — 20, 429 — 80.
- Подтверждён общий лимит 20 запросов в секунду через Valkey.
