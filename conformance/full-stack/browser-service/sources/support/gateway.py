from handler import create_report

def dispatch(path, actor, requested, db):
    if path != "/gateway/reports":
        return {"status": 404}
    reply = create_report(actor, requested, db)
    if reply["status"] == 201:
        return {"status": 201, "data": reply["body"]}
    return reply
