# C4 и взаимодействия

Диаграммы написаны в Mermaid и отображаются на GitHub. C4 здесь представлен через явно обозначенные границы и типы элементов. L3 раскрывает сервис бронирования; остальные контейнеры показаны на L2.

## L1 — System Context

```mermaid
flowchart TB
  student["Person: студент / преподаватель"]
  admin["Person: администратор"]
  campus["System: CampusReserve"]
  student -->|"Поиск, бронь, отмена, inbox"| campus
  admin -->|"Добавление ресурсов, аудит"| campus
```

Внешних интеграций в MVP нет. В перспективе — вузовский IdP и поставщик email, сейчас их роль не имитируется внешними вызовами.

## L2 — Containers

```mermaid
flowchart TB
  client["Client: браузер / CLI"]
  subgraph System["CampusReserve"]
    gw["Nginx: Router + Load Balancer + Rate Limiter"]
    users["Users: FastAPI"]
    rooms["Rooms: FastAPI"]
    equip["Equipment: FastAPI"]
    booking["Bookings: FastAPI, 2 replicas"]
    notif["Notifications: FastAPI"]
    audit["Audit: FastAPI + archiver"]
    bus["Kafka: campus.events.v1, 6 partitions"]
    pg["PostgreSQL: 5 service-owned databases"]
    cache["Valkey: resource cache"]
    hot["MongoDB: hot audit"]
    cold["MongoDB: archive, separate volume"]
    gw --> users
    gw --> rooms
    gw --> equip
    gw --> booking
    gw --> notif
    gw --> audit
    users -->|"user.created"| bus
    rooms -->|"resource.created"| bus
    equip -->|"resource.created"| bus
    booking -->|"booking events"| bus
    bus -->|"users/resources projection"| booking
    bus --> notif
    bus --> audit
    users --> pg
    rooms --> pg
    equip --> pg
    booking --> pg
    notif --> pg
    rooms --> cache
    equip --> cache
    audit --> hot
    audit --> cold
  end
  client -->|HTTP| gw
```

Каждый сервис развёртывается отдельным контейнером со своим SERVICE и отдельной учётной записью БД. Общая библиотека не делает их одним процессом: межсервисных Python-вызовов нет. Один PostgreSQL-инстанс экономит ресурсы стенда; базы и роли отдельные. Стандартный bootstrap создаёт одинаковые таблицы в каждой DB, но бизнес-сервис использует только принадлежащие ему таблицы. В production следует разделить миграции и запретить CONNECT к чужим DB, а не полагаться только на владение таблицами.

## L3 — Bookings components

```mermaid
flowchart TB
  api["API handlers: book / cancel / list"]
  auth["Token verifier: HMAC + role + owner"]
  domain["Domain validation: UTC intervals, 8h limit"]
  repository["Repository: transaction + advisory lock + exclusion constraint"]
  publisher["Outbox publisher: locks + Kafka ack"]
  consumer["Projection consumer: inbox deduplication"]
  db["Bookings DB: bookings, resources, users, outbox, inbox"]
  kafka["Kafka event log"]
  api --> auth
  api --> domain
  api --> repository
  repository --> db
  publisher --> db
  publisher --> kafka
  kafka --> consumer
  consumer --> db
```

Соответствие коду: API/repository — app/main.py, validation — app/domain.py, token verifier — app/security.py, consumer/publisher — app/runtime.py, constraint — app/schema.sql. Компоненты repository/API пока находятся в одном модуле: это границы ответственности, а не отдельные сервисы.

## Sequence — подтверждение и конфликт бронирования

```mermaid
sequenceDiagram
  actor U as Пользователь
  participant G as Nginx
  participant B as Bookings
  participant D as Bookings DB
  participant K as Kafka
  participant N as Notifications
  participant A as Audit
  U->>G: POST booking + token + Idempotency-Key
  G->>B: Rate limit + балансировка
  B->>B: Проверка токена и интервала
  B->>D: BEGIN; lock(user,key); lookup key
  alt Ключ уже существует с тем же телом
    D-->>B: Прежняя бронь
    B-->>U: 201, тот же ID
  else Новый запрос
    B->>D: INSERT booking + outbox
    alt Интервал занят
      D-->>B: ExclusionViolation; ROLLBACK
      B-->>U: 409
    else Интервал свободен
      B->>D: COMMIT
      B-->>U: 201 confirmed
      loop Фоновый outbox relay
        B->>D: SELECT unsent FOR UPDATE SKIP LOCKED
        B->>K: Publish booking.confirmed, key=booking_id
        K-->>B: Ack
        B->>D: Mark sent; COMMIT
      end
      K->>N: Event, group notifications-v1
      N->>N: Transaction: inbox + notification
      N->>K: Commit offset
      K->>A: Event, group audit-v1
      A->>A: Mongo upsert by event_id
      A->>K: Commit offset
    end
  end
```

Kafka ack и отметка sent не атомарны между собой: сбой после ack даёт повторную публикацию. Inbox/upsert устраняют повторный эффект; гарантия транспорта at-least-once. Отмена использует row lock и одну транзакцию status + outbox. Нет saga: бронирование единственного ресурса полностью принадлежит одной DB. Для составной брони аудитория+оборудование потребовался бы отдельный протокол согласования.
