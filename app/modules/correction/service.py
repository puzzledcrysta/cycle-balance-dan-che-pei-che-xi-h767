import json
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from app.errors import DataError
from app.store import connection
from app.modules.contract.schema import mapping
from app.modules.intake.reader import decode
from app.modules.intake.service import intake
from app.modules.review.decisions import timeline
from app.modules.runs.repository import fetch, lookup
from app.modules.runs.service import run


def validate(payload):
    report = intake(payload)
    try:
        mapping(report['header'])
    except DataError as error:
        raise DataError('CONTRACT', f'更正记录表头与来源契约不符：{error}') from error


def merge_source(base_payload, correction_payload):
    base_text, _ = decode(base_payload)
    correction_text, _ = decode(correction_payload)
    separator = '' if base_text.endswith('\n') else '\n'
    return (base_text + separator + correction_text).encode()


def affected_keys(before, after):
    prior = {row['key']: row['amount'] for row in before}
    current = {row['key']: row['amount'] for row in after}
    changes = []
    for key in sorted(prior.keys() | current.keys()):
        old, new = prior.get(key), current.get(key)
        if old is not None and new is not None and Decimal(old) == Decimal(new):
            continue
        change = 'ADDED' if old is None else 'REMOVED' if new is None else 'CHANGED'
        changes.append({'key': key, 'before': old, 'after': new, 'change': change})
    return changes


def dispatch_advice(base_run_id, corrected_run_id, changes):
    if not changes:
        return {'use_run_id': base_run_id, 'code': 'KEEP_BASE',
                'reason': '更正未改变任何已采信调车区结论，下午派车沿用原批次与原签核'}
    return {'use_run_id': corrected_run_id, 'code': 'USE_CORRECTION',
            'reason': f'原签核依据的盘点数据已在 {len(changes)} 个调车区被更正，下午派车采用更正批次，'
                      '无需等待全部重审；未受影响调车区两批结论一致，原签核证据保留在原批次，不随新版本覆盖'}


def record(row):
    item = dict(row)
    for field in ('affected', 'basis', 'dispatch'):
        item[field] = json.loads(item[field])
    return item


def store(base_run_id, corrected_run_id, changes, basis, advice):
    correction_id = sha256(f'correction:{base_run_id}:{corrected_run_id}'.encode()).hexdigest()
    created = datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM corrections WHERE base_run_id=?',
                             (base_run_id,)).fetchone()[0]
        cursor = db.execute('INSERT OR IGNORE INTO corrections VALUES (?,?,?,?,?,?,?,?)',
                            (correction_id, base_run_id, corrected_run_id, version,
                             json.dumps(changes, ensure_ascii=False), json.dumps(basis, ensure_ascii=False),
                             json.dumps(advice, ensure_ascii=False), created))
        row = record(db.execute('SELECT * FROM corrections WHERE id=?', (correction_id,)).fetchone())
    row['replayed'] = cursor.rowcount == 0
    return row


def register(base_run_id, correction_payload, book_payload=None):
    base = fetch(base_run_id)
    validate(correction_payload)
    merged = merge_source(base['source'], correction_payload)
    corrected = run(merged, base['book'] if book_payload is None else book_payload)
    base_result = json.loads(base['result'])
    changes = affected_keys(base_result['accepted'], corrected['accepted'])
    basis = {'run_id': base_run_id, 'manifest': base_result['manifest'], 'reviews': timeline(base_run_id)}
    advice = dispatch_advice(base_run_id, corrected['manifest']['run_id'], changes)
    return store(base_run_id, corrected['manifest']['run_id'], changes, basis, advice)


def lineage(run_id):
    with connection() as db:
        lookup(db, run_id)
        as_base = db.execute('SELECT * FROM corrections WHERE base_run_id=? ORDER BY version', (run_id,))
        as_result = db.execute('SELECT * FROM corrections WHERE run_id=? ORDER BY version', (run_id,))
        return {'as_base': [record(row) for row in as_base],
                'as_result': [record(row) for row in as_result]}
