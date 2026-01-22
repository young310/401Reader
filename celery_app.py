# celery_app.py
# Celery 應用程式入口點

import os
from celery import Celery
from celery.schedules import crontab

# 從環境變數讀取 Celery 配置
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# 建立 Celery 應用
celery_app = Celery(
    "tax_ai_ocr_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['app.tasks']  # 直接指定任務模組
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=900,  # 15 分鐘超時
    task_soft_time_limit=840,  # 14 分鐘軟超時
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# 定期任務排程
celery_app.conf.beat_schedule = {
    'dispatch-jobs': {
        'task': 'dispatch_jobs',
        'schedule': 3.0,  # 每 3 秒
    },
    'cleanup-old-failed-files': {
        'task': 'cleanup_old_failed_files',
        'schedule': crontab(hour=2, minute=0),
    },
}


class FlaskTask(celery_app.Task):
    """自訂 Celery Task 類別，提供 Flask 應用程式上下文"""
    _flask_app = None

    @property
    def flask_app(self):
        if self._flask_app is None:
            from app import create_app
            self._flask_app = create_app()
        return self._flask_app

    def __call__(self, *args, **kwargs):
        with self.flask_app.app_context():
            return super().__call__(*args, **kwargs)


# 設定預設 Task 類別
celery_app.Task = FlaskTask


if __name__ == "__main__":
    celery_app.start()
