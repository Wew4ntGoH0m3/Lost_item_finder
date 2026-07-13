from .extensions import celery
from .services.matching import analyze_found_post, analyze_lost_post


@celery.task(
    name="lostlink.analyze_lost_post",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def analyze_lost_post_task(lost_post_id: int):
    return analyze_lost_post(lost_post_id)


@celery.task(
    name="lostlink.analyze_found_post",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def analyze_found_post_task(found_post_id: int):
    return analyze_found_post(found_post_id)
