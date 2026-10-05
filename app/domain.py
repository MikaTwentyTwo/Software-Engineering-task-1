from datetime import datetime, timezone


def interval(start: str, end: str):
    a, b = (datetime.fromisoformat(x.replace('Z', '+00:00')) for x in (start, end))
    if a.tzinfo is None or b.tzinfo is None:
        raise ValueError('Timezone required')
    if a >= b or (b - a).total_seconds() > 8 * 3600:
        raise ValueError('Interval must be positive and at most 8 hours')
    return a.astimezone(timezone.utc), b.astimezone(timezone.utc)


def overlaps(a, b, c, d):
    return a < d and c < b


def validate_resource(kind, body):
    if kind not in ('rooms', 'equipment') or not isinstance(body.get('name'), str) or not body['name'].strip():
        raise ValueError('Resource name required')
    if len(body['name']) > 200:
        raise ValueError('Name too long')
    if kind == 'rooms' and (type(body.get('capacity')) is not int or body['capacity'] < 1):
        raise ValueError('Positive capacity required')
    return body
