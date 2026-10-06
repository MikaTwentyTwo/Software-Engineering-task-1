# Приёмка платформы CampusReserve

Дата проверок: 2026-10-06.

## Выполнение требований

| Пункт | Реализация | Подтверждение |
|---|---|---|
| 1.1 Kubernetes + Cilium | Основной Minikube-кластер campus, Cilium и Hubble | Узел Ready; проверены разрешённые и запрещённые сетевые соединения |
| 1.2 Автоскейлинг worker-нод | Отдельный кластер Cluster API с Docker provider и Cluster Autoscaler | Автоматический цикл 1 → 2 → 1 worker; новые узлы Ready; удаление с drain |
| 2.1 Terraform | Namespaces, Service Accounts, базовые Secrets | Terraform apply выполнен |
| 2.2 ArgoCD | App of Apps, автоматическая синхронизация из Git | Все 19 приложений Synced / Healthy после восстановления стенда |
| 2.3 Ansible + Strimzi | Role strimzi, Kafka с постоянным хранилищем | Playbook завершился без ошибок; Kafka Ready |
| 3.1 Service Mesh | Istio, retry-политики, DestinationRule с outlier detection и лимитами соединений | При искусственном отказе зафиксированы retries и исключение endpoint |
| 3.2 Отказоустойчивый вход | Istio Gateway за парой HAProxy + Keepalived | VIP переходит на резервный балансировщик и возвращается после восстановления |
| 3.3 Rate Limiting | Envoy Rate Limit Service и отдельный Valkey | Проверены HTTP 429 и общий лимит для двух Gateway |
| 4 Observability | Prometheus, Grafana, Loki, Alloy, Tempo, Alertmanager | Проверены метрики, логи, трейсы и активные алерты; выбор стека описан отдельно |
| 5.1 Локальный runner | GitHub Actions Self-Hosted Runner на Windows | Pipeline Platform Build успешно выполнен |
| 5.2 CI/CD | Kaniko → локальный Registry → обновление Helm values → ArgoCD | Образ собран и опубликован; шесть сервисов обновлены; бизнес-тест PASS |
| 5.3 Helm | Чарты шести микросервисов | Helm lint прошёл; настроены подключения к Kafka, Valkey, PostgreSQL и MongoDB |
| 6.1 Locust | Запросы через Gateway с созданием и отменой бронирований | Baseline: 172 запроса, 0 ошибок; Kafka consumer lag после теста — 0 |
| 6.2 Искусственный отказ | Отказ одной реплики bookings во время Locust-теста | Зафиксированы outlier ejections и retries; результаты включают ошибки записи |
| 6.3 Grafana | Панели сервисов, Kafka и Rate Limiter | Проверены Kafka latency, consumer lag и счётчики разрешённых/отклонённых запросов |

## Результаты тестирования

### Бизнес-сценарии

После восстановления основного стенда scripts/demo.py завершился:

PASS: auth, roles, projections, idempotency, conflict, notification,
audit, cancellation, concurrency, ownership.

Тест выполнен через http://127.0.0.1:18080:
HAProxy → Istio Gateway → микросервисы.

### Нагрузка

Baseline Locust:

- 172 запроса.
- 0 ошибок.
- Средняя задержка около 35,2 мс.
- p95 около 54 мс.
- Скорость около 1,45 запроса/с.

Тест искусственного отказа:

- Продолжительность около 93 секунд.
- 171 запрос.
- 4 ошибки HTTP 503: две при создании и две при отмене.
- Доля ошибок около 2,34%.
- На обслуживающем Gateway: 2 outlier ejections,
  2 retries и 2 успешных retries.

Результаты не означают отсутствие ошибок при отказе.
Повторы операций записи ограничены для предотвращения
небезопасного повторного выполнения.

### Rate Limiting

В отдельном burst-тесте:

- Всего 200 запросов.
- HTTP 200: 20.
- HTTP 429: 180.
- Метрики Rate Limit Service подтвердили 200 total hits,
  20 within limit и 180 over limit.

### HAProxy + Keepalived

- VIP: 192.168.49.250.
- При остановке lb1 запросы переключились на lb2.
- В первом тесте: один таймаут, затем девять HTTP 200.
- После восстановления lb1 VIP вернулся на него.
- Повторный запуск исправлен хранением /run в tmpfs.
- Полный бизнес-тест прошёл через резервный lb2.

### Worker autoscaling

- Рабочий кластер: Kubernetes 1.36.4, Cilium 1.20.1.
- Cluster API / Docker provider: 1.14.2.
- Cluster Autoscaler: 1.36.1.
- Минимум 1, максимум 2 worker-ноды.
- Два тестовых Pod требовали разных узлов через podAntiAffinity.
- Второй Pod Pending вызвал автоматическое добавление worker.
- После удаления Deployment группа уменьшилась до одного worker.
- В логах подтверждено событие ScaleDown: removed with drain.

## Границы реализации

1. Автоскейлинг выполнен в отдельном локальном тестовом кластере.
   Основной Minikube-кластер campus не масштабируется автоматически.
2. Тест автоскейлинга использует ограничения размещения Pod,
   а не увеличение CPU-нагрузки бизнес-приложения.
3. Strimzi управляет Kafka через KafkaNodePool и StrimziPodSet.
   Это отличается от буквального требования StatefulSet.
4. Проверено outlier detection и retry. Срабатывание лимитов
   соединений/очереди circuit breaker отдельно не подтверждено.
5. Все компоненты размещены на одном компьютере.
   Компьютер и TCP relay access остаются точками отказа.
6. Kafka consumer lag показывает отставание потребителей в сообщениях.
   RequestQueueTimeMs показывает время ожидания запроса,
   а не количество элементов очереди.
7. Латентность Kafka на дашборде представлена средними значениями;
   она не является p95/p99.
8. Алерты проверены в Prometheus и Alertmanager.
   Отправка внешних уведомлений не проверена.
9. AI-monitoring — опциональный пункт, не реализован.
10. Для отдельного тестового кластера kubeconfig использует
    административные учётные данные и хранится вне Git.

## Материалы

- platform/docs/observability-decision.md — выбор observability.
- platform/docs/validation.md — дополнительные проверки.
- platform/ha/README.md — балансировщики и failover.
- platform/autoscaling/README.md — автоскейлинг.
- platform/tests/load/ — сценарий и описание нагрузочных тестов.
- .github/workflows/checks.yml — проверки приложения.
- .github/workflows/platform-build.yml — локальный CI/CD.