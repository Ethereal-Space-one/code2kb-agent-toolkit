import os
from pathlib import Path

DEFAULT_LIMIT = 10

def create_report(actor, requested, db):
    limit = int(os.environ.get("REPORT_LIMIT", DEFAULT_LIMIT))
    if not actor.can_export:
        return {"status": 403, "error": "forbidden"}
    if requested > limit:
        return {"status": 422, "error": "limit"}
    statement = Path(__file__).with_name("create.sql").read_text()
    db.execute(statement, (requested,))
    return {"status": 201, "body": {"report": "created"}}
