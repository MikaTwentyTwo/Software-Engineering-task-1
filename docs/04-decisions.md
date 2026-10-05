# Архитектурные решения (ADR)

## ADR-001: микросервисы и EDA

Статус: принято для учебного проекта. Users владеет ролями; Rooms — аудиториями; Equipment — отдельными экземплярами; Bookings — расписанием броней; Notifications — inbox; Audit — историей. Bookings держит локальные проекции пользователей и ресурсов, получая их через Kafka. Синхронных бизнес-вызовов между сервисами нет. Изоляция упрощает независимые уведомления и аудит, но создаёт eventual consistency: сразу после создания ресурс может ещё отсутствовать в booking-проекции.

Прототип не реализует изменение/удаление ресурса или отзыв токена, поэтому события обновления и согласование maintenance не заявляются реализованными. Добавление этих операций потребует versioned-проекций и правил для существующих броней.

## ADR-002: Kafka против RabbitMQ и NATS

| Критерий | Kafka | RabbitMQ | NATS + JetStream |
|---|---|---|---|
| Основная модель | Партиционированный журнал | Exchanges + очереди; также Streams | Subjects; JetStream добавляет persistence |
| Независимые подписчики | Consumer groups и свои offsets | Отдельная очередь на подписчика; Streams с replay | Durable consumers, filters, replay |
| Повторное чтение истории | Естественно в пределах retention | Обычная ack-очередь не сохраняет обработанное; Streams сохраняют | Поддерживается JetStream |
| Порядок | Внутри partition | Зависит от consumers, redelivery, priorities | Зависит от stream/consumer и режима обработки |
| Надёжность | Ack, replication; внешняя DB требует dedup | Publisher confirms, consumer ack, quorum queues | JetStream ack и redelivery; Core NATS отдельно at-most-once |
| Удобство задач и маршрутизации | Требует прикладной логики | Сильная сторона exchanges и очередей | Subjects и request/reply удобны |
| Цена эксплуатации для малого MVP | Относительно высокая | Обычно проще для очередей задач | Компактный старт, но надёжный JetStream тоже требует управления |

**Почему выбрана Kafka:** она прямо требуется заданием; журнал событий позволяет отдельно строить уведомления, аудит и проекции, а затем подключать аналитику и повторно читать историю. Один topic в MVP сохраняет порядок событий одного aggregate при key=aggregate_id; 6 партиций дают параллелизм. Kafka не заменяет PostgreSQL-транзакции и не гарантирует exactly-once для внешних DB.

**Что объективно лучше для данного малого сервиса:** при отсутствии учебного требования и при небольшом потоке броней, без постоянной аналитики и replay, я бы выбрал RabbitMQ с quorum queues: задача преимущественно про доставку уведомлений и интеграционных событий. Если нужен компактный стек, request/reply и replay, NATS JetStream — разумная альтернатива. Универсального победителя нет: конкретное преимущество проверяется нагрузкой и компетенциями команды. При расширении до аналитики использования ресурсов Kafka становится более оправданной.

Первичные источники:
- Kafka design: https://kafka.apache.org/41/design/design/
- RabbitMQ reliability: https://www.rabbitmq.com/docs/reliability
- RabbitMQ Streams: https://www.rabbitmq.com/docs/stream
- NATS JetStream: https://docs.nats.io/learn/jetstream/
- NATS consumers: https://docs.nats.io/nats-concepts/jetstream/consumers

## ADR-003: доставка событий

Envelope: id (UUID), version=1, type, aggregate_id, source, data. События: user.created, resource.created, booking.confirmed, booking.cancelled. Key — ID пользователя/ресурса/брони соответственно. Topic campus.events.v1: 6 partitions, retention 7 суток, RF=1 на стенде; production RF=3, min.insync.replicas=2, acks=all.

Outbox сохраняется с бизнес-записью. Relay держит row lock до подтверждения Kafka и использует SKIP LOCKED для реплик. В случае сбоя повторяет отправку. Consumer отключает auto-commit и фиксирует offset только после DB commit либо Mongo upsert. Для PostgreSQL inbox и эффект находятся в одной транзакции. Mongo audit upsert имеет уникальный _id. Группы bookings-v1, notifications-v1, audit-v1 независимы.

Невалидное событие блокирует partition и ретраится с логированием; автоматический DLQ в MVP отсутствует. Это осознанное ограничение: ошибка не должна молча терять сообщение. Production требует DLQ с исходным payload, ошибкой и координатами partition/offset, ограниченных retries и оператора re-drive. Синхронные DB-вызовы внутри worker допустимы только при малом потоке; при росте — async driver/отдельный relay и метрики lag.

## ADR-004: данные и кэш

PostgreSQL выбран для транзакций и exclusion constraint по resource_id и tstzrange [start,end). На одну строку брони приходится один физический ресурс; одинаковые интервалы разных ресурсов допустимы. MongoDB хранит гибкие события аудита. Через 30 дней archiver делает идемпотентный upsert в отдельную MongoDB и лишь затем удаляет горячую запись; сбой между операциями может временно оставить обе копии, но не теряет архивную.

Холодный архив логически отдельный, имеет отдельный том. Чтобы он был экономически холодным, промышленный сервер должен использовать дешёвые диски/storage tier и редкий доступ; локальный Compose этого не моделирует. Kafka retention не равен сроку хранения аудита. Архив автоматически не очищается.

Valkey: cache-aside списков rooms/equipment, TTL 30 секунд, best-effort invalidation при создании. При отказе — PostgreSQL fallback. Гонка list/create может вернуть устаревший список до TTL; это допустимо для каталога. Решение о занятом интервале никогда не принимается по кэшу.

## ADR-005: routing и безопасность

Nginx объединяет три обязанности: маршрутизация по /api/{service}, round-robin для двух booking-реплик и rate limiting 10 RPS/IP с burst=20. Для локального стенда единый limiter достаточен; при нескольких gateways понадобится согласованный внешний limiter или контролируемая инфраструктура. Нельзя доверять клиентскому X-Forwarded-For без доверенных proxy.

HMAC bearer token живёт час; student/admin имеют разные права. Два пароля задаются в .env, в репозиторий не входят. Это демонстрационная аутентификация, production использует OIDC/SSO, ротацию ключей, TLS и персональные учётные записи. Mongo и Kafka не публикуют порты на host; Docker network является границей локального стенда, а не заменой аутентификации production.
