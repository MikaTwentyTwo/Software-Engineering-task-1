import asyncio
import contextlib
import hmac
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from psycopg.errors import ExclusionViolation, UniqueViolation
from psycopg.types.json import Jsonb
from redis import Redis

from app import runtime as rt
from app.domain import interval, validate_resource
from app.security import issue, verify

cache = Redis.from_url(os.environ.get('REDIS_URL', 'redis://valkey:6379'), decode_responses=True,
                       socket_connect_timeout=1, socket_timeout=1)


@asynccontextmanager
async def lifespan(app):
    tasks = []
    if rt.SERVICE != 'audit':
        rt.initialize()
        if rt.SERVICE == 'users':
            with rt.db() as c:
                for uid, role in [('student', 'student'), ('admin', 'admin')]:
                    if c.execute('INSERT INTO users(id,role) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING id', (uid, role)).fetchone():
                        rt.emit(c, 'user.created', uid, {'role': role})
        tasks.append(asyncio.create_task(rt.publisher()))
    if rt.SERVICE in ('bookings', 'notifications', 'audit'):
        tasks.append(asyncio.create_task(rt.consumer()))
    if rt.SERVICE == 'audit':
        from app.archive import archive, hot, cold
        hot.create_index('received_at')
        cold.create_index('received_at')
        tasks.append(asyncio.create_task(archive()))
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title='Campus ' + rt.SERVICE, lifespan=lifespan, root_path='/api/' + rt.SERVICE)


def actor(authorization: str = Header(default='')):
    try:
        if not authorization.startswith('Bearer '):
            raise ValueError('Bearer required')
        return verify(authorization[7:])
    except ValueError:
        raise HTTPException(401, 'Valid Bearer token required')


def admin(user=Depends(actor)):
    if user['role'] != 'admin':
        raise HTTPException(403, 'Admin required')
    return user


@app.get('/health')
def health():
    return {'service': rt.SERVICE, 'status': 'alive'}


@app.get('/ready')
def ready():
    try:
        if rt.SERVICE == 'audit':
            from app.archive import hot, cold
            hot.database.client.admin.command('ping')
            cold.database.client.admin.command('ping')
        else:
            with rt.db() as c:
                c.execute('SELECT 1')
        return {'status': 'ready', 'scope': 'storage'}
    except Exception:
        raise HTTPException(503, 'Storage unavailable')


class Login(BaseModel):
    username: str
    password: str


class Resource(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    capacity: int | None = None
    description: str = Field(default='', max_length=2000)


class Booking(BaseModel):
    resource_id: str = Field(min_length=1, max_length=100)
    start: str
    end: str


if rt.SERVICE == 'users':
    @app.post('/login')
    def login(body: Login):
        expected = os.environ.get('ADMIN_PASSWORD' if body.username == 'admin' else 'STUDENT_PASSWORD', '')
        if body.username not in ('admin', 'student') or not expected or not hmac.compare_digest(body.password, expected):
            raise HTTPException(401, 'Invalid credentials')
        with rt.db() as c:
            user = c.execute('SELECT * FROM users WHERE id=%s AND active', (body.username,)).fetchone()
        if not user:
            raise HTTPException(401, 'Inactive account')
        return {'access_token': issue(user['id'], user['role']), 'token_type': 'bearer', 'expires_in': 3600}

    @app.get('/me')
    def me(user=Depends(actor)):
        return user

if rt.SERVICE in ('rooms', 'equipment'):
    @app.post('/resources', status_code=201)
    def create_resource(body: Resource, user=Depends(admin)):
        data = body.model_dump()
        try:
            validate_resource(rt.SERVICE, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        rid = rt.SERVICE + '-' + str(uuid.uuid4())
        data['kind'] = rt.SERVICE
        with rt.db() as c:
            c.execute('INSERT INTO resources(id,kind,data) VALUES (%s,%s,%s)', (rid, rt.SERVICE, Jsonb(data)))
            rt.emit(c, 'resource.created', rid, data)
        try:
            cache.delete(rt.SERVICE + ':resources')
        except Exception:
            pass
        return {'id': rid, **data}

    @app.get('/resources')
    def list_resources(user=Depends(actor)):
        import json
        key = rt.SERVICE + ':resources'
        try:
            value = cache.get(key)
            if value:
                return json.loads(value)
        except Exception:
            pass
        with rt.db() as c:
            rows = c.execute('SELECT * FROM resources WHERE active ORDER BY id').fetchall()
        try:
            cache.setex(key, 30, json.dumps(rows))
        except Exception:
            pass
        return rows

if rt.SERVICE == 'bookings':
    @app.get('/resources')
    def projected_resources(user=Depends(actor)):
        with rt.db() as c:
            return c.execute('SELECT * FROM resources WHERE active ORDER BY id').fetchall()

    @app.post('/bookings', status_code=201)
    def book(body: Booking, user=Depends(actor), idempotency_key: str = Header(min_length=1, max_length=100)):
        try:
            start, end = interval(body.start, body.end)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        payload = {'resource_id': body.resource_id, 'start': start.isoformat(), 'end': end.isoformat()}
        try:
            with rt.db() as c:
                # Serialize retries for the same user/key before evaluating the overlap constraint.
                c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (user['sub'] + ':' + idempotency_key,))
                old = c.execute('SELECT * FROM bookings WHERE user_id=%s AND request_key=%s', (user['sub'], idempotency_key)).fetchone()
                if old:
                    if old['request_body'] != payload:
                        raise HTTPException(409, 'Idempotency key used for different request')
                    return old
                if start <= datetime.now(timezone.utc):
                    raise HTTPException(422, 'Booking must start in future')
                if not c.execute('SELECT id FROM users WHERE id=%s AND active', (user['sub'],)).fetchone():
                    raise HTTPException(409, 'User projection not ready; retry shortly')
                if not c.execute('SELECT id FROM resources WHERE id=%s AND active FOR UPDATE', (body.resource_id,)).fetchone():
                    raise HTTPException(409, 'Resource unknown or projection not ready')
                bid = str(uuid.uuid4())
                row = c.execute("INSERT INTO bookings VALUES (%s,%s,%s,%s,%s,'confirmed',%s,%s) RETURNING *",
                                (bid, user['sub'], body.resource_id, start, end, idempotency_key, Jsonb(payload))).fetchone()
                rt.emit(c, 'booking.confirmed', bid, {**payload, 'user_id': user['sub']})
                return row
        except ExclusionViolation:
            raise HTTPException(409, 'Resource already booked for this interval')
        except UniqueViolation:
            raise HTTPException(409, 'Concurrent idempotency conflict; retry')

    @app.get('/bookings')
    def bookings(user=Depends(actor)):
        with rt.db() as c:
            if user['role'] == 'admin':
                return c.execute('SELECT * FROM bookings ORDER BY starts_at').fetchall()
            return c.execute('SELECT * FROM bookings WHERE user_id=%s ORDER BY starts_at', (user['sub'],)).fetchall()

    @app.delete('/bookings/{booking_id}')
    def cancel(booking_id: uuid.UUID, user=Depends(actor)):
        with rt.db() as c:
            row = c.execute('SELECT * FROM bookings WHERE id=%s FOR UPDATE', (booking_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Booking not found')
            if user['role'] != 'admin' and row['user_id'] != user['sub']:
                raise HTTPException(403, 'Booking owner required')
            if row['status'] == 'confirmed':
                c.execute("UPDATE bookings SET status='cancelled' WHERE id=%s", (booking_id,))
                rt.emit(c, 'booking.cancelled', str(booking_id), {'user_id': row['user_id'], 'resource_id': row['resource_id']})
            return {'id': str(booking_id), 'status': 'cancelled'}

if rt.SERVICE == 'notifications':
    @app.get('/notifications')
    def notifications(user=Depends(actor)):
        with rt.db() as c:
            return c.execute('SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 100', (user['sub'],)).fetchall()

if rt.SERVICE == 'audit':
    @app.get('/events')
    def events(user=Depends(admin)):
        from app.archive import hot
        return list(hot.find({}, {'_id': 0}).sort('received_at', -1).limit(100))

    @app.get('/archive')
    def archived(user=Depends(admin)):
        from app.archive import cold
        return list(cold.find({}, {'_id': 0}).sort('received_at', -1).limit(100))

# Optional failure simulation for local platform acceptance tests.
if rt.SERVICE == "bookings" and os.environ.get("ENABLE_FAULT_TESTS") == "1":
    @app.middleware("http")
    async def acceptance_fault(request, call_next):
        import time
        from pathlib import Path
        from starlette.responses import JSONResponse

        if request.url.path not in ("/health", "/ready"):
            try:
                deadline = float(Path("/tmp/campus-fault-until").read_text())
            except (OSError, ValueError):
                deadline = 0
            if time.time() < deadline:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Acceptance test: temporary service failure"}
                )
        return await call_next(request)
