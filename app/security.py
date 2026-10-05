import base64
import hashlib
import hmac
import json
import os
import time


def issue(user_id, role, key=None, now=None):
    payload = {'sub': user_id, 'role': role, 'exp': int(time.time() if now is None else now) + 3600}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=')
    signature = hmac.new((key or os.environ['TOKEN_SECRET']).encode(), raw, hashlib.sha256).hexdigest()
    return raw.decode() + '.' + signature


def verify(token, key=None, now=None):
    try:
        raw, sig = token.split('.')
        expected = hmac.new((key or os.environ['TOKEN_SECRET']).encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError('Invalid token')
        data = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        if data['exp'] <= (time.time() if now is None else now) or data['role'] not in ('student', 'admin'):
            raise ValueError('Expired or invalid token')
        return data
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Invalid token') from exc
