# Выбор стека Observability

## Контекст

Учебная платформа работает на одном узле Minikube.
Компьютер: 15,8 ГБ RAM; лимит WSL установлен в 10 ГБ.
Нужны метрики, логи, трассы, дашборды и алертинг.
Команда состоит из двух человек.

## Рассмотренные варианты

| Стек | Возможности | Решение для проекта |
|---|---|---|
| Prometheus + Loki + Tempo + Grafana + Alertmanager | Раздельные компоненты для метрик, логов и трасс, общий интерфейс Grafana | Выбран: можно внедрять и проверять компоненты поэтапно |
| VictoriaMetrics + VictoriaLogs + Jaeger + Grafana | Альтернативные хранилища метрик и логов, отдельный backend трасс | Подходит для дальнейшего сравнения; миграция сейчас добавит работу без подтверждённой необходимости |
| Elasticsearch + Logstash + Kibana с отдельными средствами метрик и трасс | Поиск и обработка логов | Не выбран: для текущего задания предпочли единый интерфейс Grafana и уже настроенные источники |
| SigNoz + OpenTelemetry Collector + ClickHouse | Общая платформа для метрик, логов и трасс | Не выбран: потребовал бы внедрения нового хранилища и переноса существующих дашбордов и алертов |

Сравнение качественное. Альтернативы не разворачивались;
сравнительные замеры RAM, скорости и стоимости не проводились.

## Реализованная схема

Метрики:
Istio, Kafka JMX, Kafka Exporter, Rate Limit Service,
kube-state-metrics и node-exporter → Prometheus → Grafana.

Логи:
Kubernetes Pod Logs → Grafana Alloy → Loki → Grafana.
Alloy собирает логи namespace campus и istio-system.

Трассы:
Istio Envoy → OTLP/gRPC → Tempo → Grafana.
Для учебной проверки включена выборка 100% HTTP-запросов.

Алерты:
Правила Prometheus → Alertmanager.
Проверены CampusWatchdog и CampusRateLimitExceeded.
Получение алертов в Alertmanager подтверждено.
Внешняя доставка в почту или мессенджер не настроена.

## Хранение и ресурсы

- Prometheus: retention 1 день, ограничение хранения 1 ГБ,
  PVC 3 ГиБ.
- Loki: retention 24 часа, PVC 3 ГиБ.
- Tempo: retention 24 часа, PVC 3 ГиБ.
- Grafana: PVC 1 ГиБ.
- Alertmanager: PVC 1 ГиБ.
- Loki и Tempo работают в режиме одного экземпляра.
- Ресурсы компонентов ограничены Kubernetes requests/limits.

Retention — настройка хранения, а не доказательство
проверенной очистки данных по возрасту.

## Подтверждённые проверки

- Prometheus успешно опрашивает Istio-прокси.
- Доступны метрики длительности запросов Kafka
  и времени ожидания в очереди запросов брокера.
- Доступен consumer lag Kafka.
- Rate Limit Service экспортирует счётчики разрешённых
  и отклонённых запросов.
- Grafana отображает соответствующие панели.
- Логи приложений доступны через источник Loki.
- HTTP-трассы с несколькими spans доступны через Tempo.
- Выполнены базовый тест Locust и тест отказа bookings.
- Подробная статистика: ../tests/load/RESULTS.md.

## Ограничения

- Один узел и локальные PVC не обеспечивают HA.
- Consumer lag показывает отставание потребителей,
  а не общий размер Kafka на диске.
- Среднее время запроса Kafka не является p95/p99.
- Длительный Fetch может включать ожидание новых сообщений.
- Трассы отражают HTTP-обмен через Istio.
  Trace context в событиях Kafka не реализован и не проверен.
- Связь логов с трассами по trace_id отдельно не настроена.
- Нагрузочный тест не определяет предел производительности.
- AI-monitoring не развёрнут: это опциональная часть задания.

## Дальнейшее развитие

- Подобрать sampling трасс под фактическую нагрузку.
- Настроить внешнюю доставку алертов.
- Добавить trace context в Kafka-события.
- Проверить резервное копирование и восстановление.
- Для нескольких узлов пересмотреть хранение и репликацию.

## Источники

- Loki storage:
  https://grafana.com/docs/loki/latest/configure/storage/
- Tempo architecture:
  https://grafana.com/docs/tempo/latest/introduction/architecture/
- VictoriaLogs:
  https://docs.victoriametrics.com/victorialogs/
- SigNoz architecture:
  https://signoz.io/docs/architecture/
- Istio OpenTelemetry:
  https://istio.io/latest/docs/tasks/observability/distributed-tracing/opentelemetry/