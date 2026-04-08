from app.workers.celery_app import celery_app


def _task_result(task_name: str, payload: dict | None = None) -> dict:
    return {
        "task": task_name,
        "status": "queued_stub",
        "payload": payload or {},
    }


@celery_app.task(name="process_incoming_message")
def process_incoming_message(payload: dict) -> dict:
    return _task_result("process_incoming_message", payload)


@celery_app.task(name="transcribe_audio")
def transcribe_audio(payload: dict) -> dict:
    return _task_result("transcribe_audio", payload)


@celery_app.task(name="generate_reply")
def generate_reply(payload: dict) -> dict:
    return _task_result("generate_reply", payload)


@celery_app.task(name="publish_instagram")
def publish_instagram(payload: dict) -> dict:
    return _task_result("publish_instagram", payload)


@celery_app.task(name="publish_tiktok")
def publish_tiktok(payload: dict) -> dict:
    return _task_result("publish_tiktok", payload)


@celery_app.task(name="publish_youtube")
def publish_youtube(payload: dict) -> dict:
    return _task_result("publish_youtube", payload)


@celery_app.task(name="sync_youtube_comments")
def sync_youtube_comments(payload: dict) -> dict:
    return _task_result("sync_youtube_comments", payload)


@celery_app.task(name="recalc_metrics")
def recalc_metrics(payload: dict) -> dict:
    return _task_result("recalc_metrics", payload)
