import asyncio
import os
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

hot = MongoClient(os.environ.get('MONGO_HOT', 'mongodb://mongo-hot:27017'), serverSelectionTimeoutMS=3000).audit.events
cold = MongoClient(os.environ.get('MONGO_COLD', 'mongodb://mongo-cold:27017'), serverSelectionTimeoutMS=3000).archive.events


def record(event):
    hot.update_one({'_id': event['id']}, {'$setOnInsert': {**event, 'received_at': datetime.now(timezone.utc)}}, upsert=True)


async def archive():
    while True:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=int(os.environ.get('ARCHIVE_AFTER_DAYS', '30')))
            for event in hot.find({'received_at': {'$lt': cutoff}}).limit(500):
                cold.replace_one({'_id': event['_id']}, event, upsert=True)
                hot.delete_one({'_id': event['_id']})
        except Exception:
            import logging
            logging.exception('Archive retry')
        await asyncio.sleep(60)
