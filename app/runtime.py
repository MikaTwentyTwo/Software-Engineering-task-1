"""Infrastructure shared by six separately deployed services; no service-to-service HTTP."""
import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

log = logging.getLogger('campus')
TOPIC = 'campus.events.v1'
SERVICE = os.environ.get('SERVICE', 'bookings')


def db():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row)


def initialize():
    with db() as c:
        c.execute("SELECT pg_advisory_xact_lock(9473201)")
        c.execute(Path(__file__).with_name('schema.sql').read_text())


def emit(c, kind, aggregate, data):
    event = {'id': str(uuid.uuid4()), 'version': 1, 'type': kind,
             'aggregate_id': aggregate, 'source': SERVICE, 'data': data}
    c.execute('INSERT INTO outbox(id,event) VALUES (%s,%s)', (event['id'], Jsonb(event)))


async def publisher():
    while True:
        producer = AIOKafkaProducer(bootstrap_servers=os.environ['KAFKA_BOOTSTRAP'],
                                   enable_idempotence=True)
        try:
            await producer.start()
            while True:
                # Lock held until broker acknowledgement; concurrent replicas cannot publish the same row simultaneously.
                with db() as c:
                    rows = c.execute('SELECT * FROM outbox WHERE NOT sent ORDER BY created_at LIMIT 50 FOR UPDATE SKIP LOCKED').fetchall()
                    for row in rows:
                        e = row['event']
                        await producer.send_and_wait(TOPIC, json.dumps(e).encode(), key=e['aggregate_id'].encode())
                        c.execute('UPDATE outbox SET sent=TRUE WHERE id=%s', (row['id'],))
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Outbox retry')
            await asyncio.sleep(2)
        finally:
            await producer.stop()


def apply_event(c, e):
    inserted = c.execute('INSERT INTO inbox(id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING id', (e['id'],)).fetchone()
    if not inserted:
        return
    d = e['data']
    if SERVICE == 'bookings' and e['type'] == 'resource.created':
        c.execute('INSERT INTO resources(id,kind,data) VALUES (%s,%s,%s) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                  (e['aggregate_id'], d['kind'], Jsonb(d)))
    if SERVICE == 'bookings' and e['type'] == 'user.created':
        c.execute('INSERT INTO users(id,role) VALUES (%s,%s) ON CONFLICT DO NOTHING', (e['aggregate_id'], d['role']))
    if SERVICE == 'notifications' and e['type'] in ('booking.confirmed', 'booking.cancelled'):
        c.execute('INSERT INTO notifications(id,user_id,event) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                  (e['id'], d['user_id'], Jsonb(e)))


async def consumer():
    while True:
        client = AIOKafkaConsumer(TOPIC, bootstrap_servers=os.environ['KAFKA_BOOTSTRAP'],
                                  group_id=SERVICE + '-v1', enable_auto_commit=False,
                                  auto_offset_reset='earliest', max_poll_interval_ms=300000)
        try:
            await client.start()
            async for msg in client:
                # Retry this exact record before advancing; poison records block the partition and are visible in logs.
                while True:
                    try:
                        e = json.loads(msg.value)
                        if e['version'] != 1:
                            raise ValueError('Unsupported event version')
                        if SERVICE == 'audit':
                            from app.archive import record
                            record(e)
                        else:
                            with db() as c:
                                apply_event(c, e)
                        await client.commit()
                        break
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        log.exception('Consumer retry partition=%s offset=%s', msg.partition, msg.offset)
                        await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception('Consumer reconnect')
            await asyncio.sleep(2)
        finally:
            await client.stop()
