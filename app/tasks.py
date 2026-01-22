# app/tasks.py
# Celery 任務定義

import os
import json
from datetime import datetime, timedelta

from celery_app import celery_app
from app.models import db, TaxOcrCase, TaxOcrJob
from app.utils.pdf_utils import get_pdf_page_count, is_supported_file, convert_pdf_page_to_png, convert_image_to_png
from app.services.ocr_service import run_ocr_on_page
from app.services.llm_service import (
    run_llm_extraction,
    extract_company_name_from_result,
    detect_stream_from_result
)


# Prompt 類型映射
PROMPT_TYPE_MAPPING = {
    '401': 'GROUP_A_401',
    '403': 'GROUP_A_403',
    'withholding-slip': 'GROUP_B_CERTIFICATE_PAYMENT',
    'withholding-statement': 'GROUP_B_SUMMARY_PAYMENT',
    'dividend-slip': 'GROUP_B_DIVIDEND_PAYMENT',
}


def cleanup_temp_files(file_paths: list[str]):
    """清理臨時檔案"""
    if not file_paths:
        return

    cleaned_count = 0
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                cleaned_count += 1
        except Exception as e:
            print(f"清理臨時檔案失敗：{file_path} - {e}")

    if cleaned_count > 0:
        print(f"共清理了 {cleaned_count} 個臨時 PNG 檔案")


def determine_detected_stream(document_type: str, llm_result, company_name_provided: str) -> str:
    """判斷收支方向"""
    if document_type in ['401', '403']:
        return None

    streams = []

    if isinstance(llm_result, dict):
        if "頁面資料" in llm_result:
            pages = llm_result.get("頁面資料", [])
            for page_data in pages:
                if isinstance(page_data, dict) and page_data.get("stream"):
                    streams.append(page_data.get("stream"))
        else:
            if llm_result.get("stream"):
                streams.append(llm_result.get("stream"))

    if not streams:
        detected_stream = None
    elif len(set(streams)) == 1:
        detected_stream = streams[0]
    else:
        from collections import Counter
        stream_counts = Counter(streams)
        detected_stream = stream_counts.most_common(1)[0][0]

    return detected_stream


@celery_app.task(name="process_job", bind=True)
def process_job(self, job_id: int, company_name_provided: str = "") -> dict:
    """處理單一 Job 的 OCR + LLM 流程"""
    from flask import current_app
    import time

    start_time = time.time()

    # 需要在 Flask app context 中執行
    from app import create_app
    app = create_app()

    with app.app_context():
        try:
            job = TaxOcrJob.query.get(job_id)
            if not job:
                raise ValueError(f"Job {job_id} 不存在")

            if job.status == "COMPLETED":
                return {"status": "already_completed", "job_id": job_id}

            if job.status == "PROCESSING":
                if job.updated_at and datetime.utcnow() - job.updated_at > timedelta(minutes=30):
                    job.status = "PENDING"
                    db.session.commit()
                else:
                    return {"status": "already_processing", "job_id": job_id}

            # 更新狀態為 PROCESSING
            job.status = "PROCESSING"
            db.session.commit()

            # 組合完整檔案路徑
            upload_base = os.environ.get('TAX_OCR_UPLOAD_BASE', os.path.join(app.root_path, 'uploads'))

            if os.path.isabs(job.temp_filepath):
                full_file_path = job.temp_filepath
            else:
                full_file_path = os.path.join(upload_base, job.temp_filepath)

            if not os.path.exists(full_file_path):
                raise FileNotFoundError(f"檔案不存在：{full_file_path}")

            print(f"開始處理 Job {job_id}: {job.original_filename}")

            # 檢查檔案是否支援
            is_supported, file_type = is_supported_file(full_file_path)
            if not is_supported:
                raise ValueError(f"不支援的檔案格式：{job.original_filename}")

            # 取得總頁數
            if file_type == "pdf":
                total_pages = get_pdf_page_count(full_file_path)
            else:
                total_pages = 1

            # 根據 document_type 選擇 Prompt 類型
            prompt_type = PROMPT_TYPE_MAPPING.get(job.document_type)
            if not prompt_type:
                raise ValueError(f"未知的 document_type: {job.document_type}")

            # 逐頁處理 OCR + LLM
            all_pages_results = []
            temp_png_files = []

            for page_no in range(total_pages):
                print(f"處理第 {page_no + 1}/{total_pages} 頁")

                # OCR
                ocr_text, png_path = run_ocr_on_page(full_file_path, page_no, job.document_type)
                temp_png_files.append(png_path)

                # LLM
                page_result = run_llm_extraction(
                    ocr_text,
                    prompt_type,
                    company_name_provided,
                    image_path=png_path
                )

                if isinstance(page_result, dict):
                    page_result["頁碼"] = page_no + 1
                    page_result["總頁數"] = total_pages

                all_pages_results.append(page_result)

            # 聚合結果
            if total_pages == 1:
                final_result = all_pages_results[0]
            else:
                final_result = {"頁面資料": all_pages_results}

            # 判斷 detected_stream
            detected_stream = determine_detected_stream(
                job.document_type,
                final_result,
                company_name_provided
            )

            # 提取公司名稱
            detected_company_name = extract_company_name_from_result(final_result, job.document_type)

            # 更新 Job
            job.status = "COMPLETED"
            job.result_json = final_result
            job.detected_stream = detected_stream
            job.detected_company_name = detected_company_name
            job.error_message = None
            db.session.commit()

            # 清理臨時檔案
            cleanup_temp_files(temp_png_files)

            total_time = time.time() - start_time
            print(f"Job {job_id} 處理完成，耗時 {total_time:.2f} 秒")

            return {"status": "success", "job_id": job_id}

        except Exception as e:
            job = TaxOcrJob.query.get(job_id)
            if job:
                job.status = "FAILED"
                job.error_message = str(e)
                db.session.commit()

            print(f"Job {job_id} 處理失敗：{str(e)}")
            return {"status": "failed", "job_id": job_id, "error": str(e)}


@celery_app.task(name="dispatch_jobs")
def dispatch_jobs_task():
    """中央調度器：定期掃描並分配 Job"""
    from app import create_app
    app = create_app()

    MAX_JOBS_PER_USER = 8

    with app.app_context():
        try:
            from sqlalchemy import distinct

            pending_users = db.session.query(distinct(TaxOcrJob.uploaded_by)).filter(
                TaxOcrJob.status == "PENDING",
                TaxOcrJob.uploaded_by.isnot(None)
            ).all()

            pending_user_ids = [user_id for (user_id,) in pending_users]

            if not pending_user_ids:
                return {"dispatched": 0, "message": "No pending jobs"}

            dispatched_count = 0

            for user_id in pending_user_ids:
                processing_count = TaxOcrJob.query.filter(
                    TaxOcrJob.uploaded_by == user_id,
                    TaxOcrJob.status == "PROCESSING"
                ).count()

                available_slots = MAX_JOBS_PER_USER - processing_count

                if available_slots <= 0:
                    continue

                next_jobs = TaxOcrJob.query.filter(
                    TaxOcrJob.uploaded_by == user_id,
                    TaxOcrJob.status == "PENDING"
                ).order_by(TaxOcrJob.created_at, TaxOcrJob.id).limit(available_slots).all()

                if not next_jobs:
                    continue

                for job in next_jobs:
                    case = TaxOcrCase.query.get(job.case_id)
                    company_name = case.client_name if case else ""

                    process_job.delay(job.id, company_name)
                    dispatched_count += 1

            return {
                "dispatched": dispatched_count,
                "total_users": len(pending_user_ids),
                "message": f"Dispatched {dispatched_count} jobs"
            }

        except Exception as e:
            print(f"調度器執行失敗：{e}")
            return {"error": str(e)}


@celery_app.task(name="cleanup_old_failed_files", bind=True, max_retries=3)
def cleanup_old_failed_files(self):
    """每日清理 30 天前的失敗檔案"""
    from app import create_app
    app = create_app()

    with app.app_context():
        try:
            cutoff_date = datetime.now() - timedelta(days=30)

            failed_jobs = TaxOcrJob.query.filter(
                TaxOcrJob.status == "FAILED",
                TaxOcrJob.created_at < cutoff_date
            ).all()

            deleted_count = 0
            upload_base = os.environ.get('TAX_OCR_UPLOAD_BASE', os.path.join(app.root_path, 'uploads'))

            for job in failed_jobs:
                try:
                    if not job.temp_filepath:
                        continue

                    if os.path.isabs(job.temp_filepath):
                        file_path = job.temp_filepath
                    else:
                        file_path = os.path.join(upload_base, job.temp_filepath)

                    if os.path.exists(file_path):
                        os.remove(file_path)
                        deleted_count += 1

                except Exception as e:
                    print(f"清理過期檔案失敗 - Job {job.id}: {e}")
                    continue

            print(f"定期清理完成 - 刪除 {deleted_count} 個過期失敗檔案")
            return {"success": True, "deleted_count": deleted_count}

        except Exception as exc:
            print(f"定期清理失敗：{exc}")

            if self.request.retries < self.max_retries:
                raise self.retry(countdown=60, exc=exc)
            else:
                return {"success": False, "error": str(exc)}
