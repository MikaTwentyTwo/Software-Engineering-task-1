# CampusReserve — бронирование аудиторий и оборудования

Учебный проект по программной инженерии: 6 независимо развёртываемых микросервисов, EDA/Kafka, PostgreSQL, MongoDB, Valkey и Nginx. Предметная область — университет. Основной сценарий реализован: администратор добавляет ресурс, студент бронирует его, получает уведомление и отменяет бронь. Два параллельных запроса не могут занять один ресурс на пересекающееся время.

## Соответствие заданию

| Требование | Где смотреть |
|---|---|
| ТЗ, ключевые разделы ГОСТ 19 и 34 | [docs/01-specification.md](docs/01-specification.md) |
| User Stories, Use Cases, NFR | [docs/02-requirements.md](docs/02-requirements.md) |
| C4 L1–L3 и Sequence | [docs/03-architecture.md](docs/03-architecture.md) |
| 3+ сервисов, распределение по команде | 6 сервисов; [docs/05-team.md](docs/05-team.md) |
| Kafka, EDA, сравнение RabbitMQ/NATS | [docs/04-decisions.md](docs/04-decisions.md) |
| RDBMS + NoSQL + холодный архив | отдельные PostgreSQL DB; две MongoDB для горячего аудита и архива |
| Redis-like кэш | Valkey, cache-aside, TTL 30 секунд |
| Маршрутизатор, балансировщик, limiter | Nginx, две реплики bookings, 10 запросов/с на IP |

## Запуск

Требуются Docker Engine с Compose v2, Python 3.12 для демонстрации и тестов. Локально рекомендуется 8 GB RAM. Образы и зависимости закреплены версиями; для production необходимы обновления и проверка уязвимостей.

```bash
cp .env.example .env
# Замените четыре значения в .env. Для POSTGRES_PASSWORD используйте URL-safe символы.
docker compose up --build -d
python scripts/demo.py
```

Демонстрация читает пароли из `.env`, ждёт доступности API, создаёт аудиторию и оборудование, проверяет проекции, бронь, повтор с тем же ключом, конкурентный конфликт, уведомление, аудит, отмену и освобождение интервала. Endpoint: http://localhost:8080.

Swagger: `/api/users/docs`, `/api/rooms/docs`, `/api/equipment/docs`, `/api/bookings/docs`, `/api/notifications/docs`, `/api/audit/docs`. Префикс прокси настроен через `root_path` приложения; API описан в [docs/06-operations.md](docs/06-operations.md).

```bash
python -m unittest discover -s tests -v
docker compose logs -f bookings-a notifications audit
docker compose down
# down сохраняет данные; down -v удаляет их.
```

## Границы прототипа

Учётные записи `student` и `admin` создаются автоматически; пароли задаются пользователем. Есть роли, подписанные токены с часовой экспирацией и проверка владельца брони. Отдельная бронь относится к одному экземпляру оборудования либо одной аудитории. Совместная атомарная бронь нескольких ресурсов, регистрация пользователей, изменение ресурсов, расписание занятий, почта/SMS, напоминания, frontend и интеграция с вузовским SSO — следующий этап. Уведомления сейчас доступны через API как inbox.

Compose — локальный стенд: один Kafka-брокер, один PostgreSQL, MongoDB без репликации, HTTP только на loopback. Целевые показатели доступности из NFR не гарантируются этим стендом. Холодное хранилище — отдельная MongoDB с отдельным томом: логическое архивирование через 30 дней; физически более дешёвый storage tier настраивается при промышленном развёртывании.

Проверки и статус выполнения: [docs/07-validation.md](docs/07-validation.md).
