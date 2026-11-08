"""Durable, resumable state for catalogue ingestion."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {'discovered', 'pending', 'imported', 'failed', 'skipped'}

class IngestionState:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {'version': 1, 'titles': {}}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(loaded, dict) and isinstance(loaded.get('titles'), dict):
                    self.data = loaded
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)

    def ensure(self, title_id, title=''):
        title_id = str(title_id)
        record = self.data['titles'].setdefault(title_id, {'status': 'discovered', 'attempts': 0, 'errors': []})
        record.setdefault('status', 'discovered')
        record.setdefault('attempts', 0)
        record.setdefault('errors', [])
        if title and title != record.get('title'):
            record['title'] = title
        return record

    def pending(self, limit=None):
        now = time.time()
        items = []
        for title_id, record in self.data['titles'].items():
            status = record.get('status')
            if status == 'pending':
                priority = 0 if record.get('priority') == 'high' else 1
                items.append((priority, int(title_id), title_id, record))
            elif status == 'failed':
                next_retry = record.get('next_retry_at', 0)
                if next_retry and now < next_retry:
                    continue
                items.append((2, int(title_id), title_id, record))
        items.sort(key=lambda item: (item[0], item[1]))
        if limit is not None:
            items = items[:limit]
        return [title_id for _, _, title_id, _ in items]

    def mark_imported(self, title_id):
        record = self.ensure(title_id)
        record.update({'status': 'imported', 'imported_at': datetime.now(timezone.utc).isoformat(), 'next_retry_at': 0})

    def mark_failed(self, title_id, error, base_delay=30):
        record = self.ensure(title_id)
        record['status'] = 'failed'
        record['attempts'] = int(record.get('attempts', 0)) + 1
        record['last_error'] = str(error)[:500]
        record['last_failed_at'] = datetime.now(timezone.utc).isoformat()
        delay = min(base_delay * (2 ** min(record['attempts'] - 1, 6)), 3600)
        record['next_retry_at'] = time.time() + delay
        record['errors'].append({'at': record['last_failed_at'], 'error': str(error)[:500]})
        record['errors'] = record['errors'][-10:]

    def mark_skipped(self, title_id, reason):
        record = self.ensure(title_id)
        record.update({'status': 'skipped', 'skip_reason': str(reason)[:200], 'next_retry_at': 0})

    def coverage(self):
        counts = {status: 0 for status in STATUSES}
        for record in self.data['titles'].values():
            counts[record.get('status', 'discovered')] += 1
        discovered = sum(counts.values())
        return {'generated_at': datetime.now(timezone.utc).isoformat(), 'discovered': discovered,
                'imported': counts['imported'], 'pending': counts['pending'], 'failed': counts['failed'],
                'skipped': counts['skipped'], 'coverage_percent': round(counts['imported'] / discovered * 100, 2) if discovered else 0}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', default='data/ingestion-state.json')
    args = parser.parse_args()
    print(json.dumps(IngestionState(args.state).coverage(), ensure_ascii=False, indent=2))
