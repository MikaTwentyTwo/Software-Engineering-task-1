# API и эксплуатация

Все бизнес-endpoints требуют Authorization: Bearer <token>, кроме login. Префикс gateway указан ниже. Swagger UI доступен по {prefix}/docs.

| Сервис | Префикс | Endpoint | Доступ |
|---|---|---|---|
| Users | /api/users | POST /login; GET /me | login публичный, me authenticated |
| Rooms | /api/rooms | POST /resources; GET /resources | запись admin, чтение authenticated |
| Equipment | /api/equipment | POST /resources; GET /resources | запись admin, чтение authenticated |
| Bookings | /api/bookings | GET /resources; POST /bookings; GET /bookings; DELETE /bookings/{id} | authenticated; список только свой, admin видит все |
| Notifications | /api/notifications | GET /notifications | свой inbox |
| Audit | /api/audit | GET /events; GET /archive | admin |

Каждый сервис имеет /health (жив процесс) и /ready (доступно storage). /ready не утверждает отсутствие consumer lag или здоровье Kafka. Gateway /health проверяет только Nginx. При production следует добавить end-to-end probes и метрики outbox age/lag.

Пример броневого тела:
```json
{"resource_id":"rooms-<uuid>","start":"2026-11-10T10:00:00+03:00","end":"2026-11-10T11:00:00+03:00"}
```

Нужен заголовок Idempotency-Key: уникальный ключ логической операции. Время UTC и другие offsets нормализуются перед сравнением повторов. Повтор возвращает ту же запись; если она отменена — тот же ID со статусом cancelled, новая бронь требует новый ключ.

## Диагностика

```bash
docker compose ps
docker compose logs --tail=100 bookings-a bookings-b
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group bookings-v1
docker compose exec postgres psql -U postgres -d bookings -c "SELECT count(*) FROM outbox WHERE NOT sent;"
```

Логи consumer содержат partition/offset при ошибках. Не удаляйте блокирующее сообщение без анализа; исправьте consumer или выполните контролируемый re-drive. Replay после истечения Kafka retention не восстанавливает полный каталог: для старых данных необходим snapshot/export и последующее чтение offsets. В MVP первоначальные события сохраняются только 7 суток, поэтому удалять projections/inbox спустя этот срок без snapshot нельзя.

## Архив

Отдельные MongoDB с томами mongo-hot-data и mongo-cold-data. Worker каждые 60 секунд переносит максимум 500 старых записей. Для теста в окружении audit выставить ARCHIVE_AFTER_DAYS=0 и дождаться цикла; не использовать на рабочих данных. Порядок: cold upsert → hot delete. Для последующих replay старое событие может снова попасть в hot и потом снова безопасно архивироваться.

## Backup и production

Суточный pg_dump каждой DB и mongodump обоих MongoDB с хранением вне Docker-host; Kafka и cache не заменяют backup. Проверять восстановление на изолированном стенде. Production: отдельные migrations, TLS, OIDC, Kafka 3 brokers, PostgreSQL HA, Mongo replica sets и auth, external secrets, observability, durable DLQ, load/security tests. Nginx имеет статические upstream IP, после пересоздания backend-контейнеров перезапустите gateway; HA routing требует динамического service discovery.
