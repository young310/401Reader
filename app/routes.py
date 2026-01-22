# app/routes.py
# 路由定義

import os
import re
import time
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, send_file, current_app, redirect, url_for, flash
from flask_login import login_required, current_user, login_user, logout_user
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from sqlalchemy import desc

from app.models import db, User, TaxOcrCase, TaxOcrJob, TaxOcrVersion, TaxOcrCaseUser, TaxOcrLog


# ==================== Blueprints ====================

main_bp = Blueprint('main', __name__)
auth_bp = Blueprint('auth', __name__)
api_bp = Blueprint('api', __name__)


# ==================== 輔助函數 ====================

def get_template_context(**kwargs):
    """取得模板的通用上下文變數"""
    jwtToken = ''
    if current_user.is_authenticated:
        try:
            jwtToken = create_access_token(identity=current_user.username)
        except Exception as e:
            print(f"Warning: Could not create JWT token: {e}")

    context = {
        'userName': current_user.username if current_user.is_authenticated else '',
        'userEmail': current_user.email if current_user.is_authenticated else '',
        'userRole': getattr(current_user, 'user_role', '') if current_user.is_authenticated else '',
        'userLocale': getattr(current_user, 'locale', 'zh_TW') if current_user.is_authenticated else 'zh_TW',
        'jwtToken': jwtToken,
        'viewOnly': False,
    }
    context.update(kwargs)
    return context


def sanitize_filename(filename: str) -> str:
    """清理檔案名稱"""
    name_parts = filename.rsplit('.', 1)
    if len(name_parts) == 2:
        name, ext = name_parts
    else:
        name = filename
        ext = ''

    name = name.replace('/', '_').replace('\\', '_')
    name = re.sub(r'[\x00-\x1f\x7f-\x9f]', '_', name)
    name = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', name)
    name = re.sub(r'_{2,}', '_', name)
    name = name.strip('_')

    max_length = 200
    if ext:
        max_name_length = max_length - len(ext) - 1
        if len(name) > max_name_length:
            name = name[:max_name_length].rstrip('_')
        return f"{name}.{ext}"
    else:
        if len(name) > max_length:
            name = name[:max_length].rstrip('_')
        return name


# ==================== 主頁面路由 ====================

@main_bp.route('/')
def index():
    """首頁"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """案件總覽頁面"""
    return render_template('dashboard.html', **get_template_context())


@main_bp.route('/upload')
@login_required
def upload():
    """憑證上傳頁面"""
    case_id = request.args.get('case_id', type=int)

    if case_id:
        case = TaxOcrCase.query.get(case_id)
        if not case:
            flash('案件不存在，請重新選擇', 'error')
            return redirect(url_for('main.dashboard'))

        if not case.has_user_access(current_user.id):
            flash('您沒有權限存取此案件', 'error')
            return redirect(url_for('main.dashboard'))

    return render_template('upload.html', **get_template_context())


@main_bp.route('/database')
@login_required
def database():
    """資料庫頁面"""
    case_id = request.args.get('case_id', type=int)

    if case_id:
        case = TaxOcrCase.query.get(case_id)
        if not case:
            flash('案件不存在，請重新選擇', 'error')
            return redirect(url_for('main.dashboard'))

        if not case.has_user_access(current_user.id):
            flash('您沒有權限存取此案件', 'error')
            return redirect(url_for('main.dashboard'))

    return render_template('database.html', **get_template_context())


@main_bp.route('/history')
@login_required
def history():
    """紀錄與下載頁面"""
    case_id = request.args.get('case_id', type=int)

    if case_id:
        case = TaxOcrCase.query.get(case_id)
        if not case:
            flash('案件不存在，請重新選擇', 'error')
            return redirect(url_for('main.dashboard'))

        if not case.has_user_access(current_user.id):
            flash('您沒有權限存取此案件', 'error')
            return redirect(url_for('main.dashboard'))

    return render_template('history.html', **get_template_context())


@main_bp.route('/verification')
@login_required
def verification():
    """AI驗證頁面"""
    case_id = request.args.get('case_id', type=int)
    job_ids_param = request.args.get('jobIds')

    if not case_id and job_ids_param:
        try:
            job_ids = [int(jid.strip()) for jid in job_ids_param.split(',') if jid.strip()]
            if job_ids:
                first_job = TaxOcrJob.query.get(job_ids[0])
                if first_job:
                    case_id = first_job.case_id
        except (ValueError, AttributeError):
            flash('無效的參數格式', 'error')
            return redirect(url_for('main.dashboard'))

    if case_id:
        case = TaxOcrCase.query.get(case_id)
        if not case:
            flash('案件不存在，請重新選擇', 'error')
            return redirect(url_for('main.dashboard'))

        if not case.has_user_access(current_user.id):
            flash('您沒有權限存取此案件', 'error')
            return redirect(url_for('main.dashboard'))

    return render_template('verification.html', **get_template_context())


@main_bp.route('/permissions')
@login_required
def permissions():
    """權限管理頁面"""
    user_role = getattr(current_user, 'user_role', '')
    if not user_role or ('admin' not in user_role and 'accountant' not in user_role):
        flash('您沒有權限存取此頁面', 'error')
        return redirect(url_for('main.dashboard'))

    return render_template('permissions.html', **get_template_context())


# ==================== 認證路由 ====================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """登入"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))

        flash('使用者名稱或密碼錯誤', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """登出"""
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """註冊"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('使用者名稱已存在', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email 已被使用', 'error')
            return render_template('register.html')

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('註冊成功，請登入', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')


# ==================== API 路由 ====================

@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康檢查"""
    return jsonify({
        "status": "ok",
        "service": "Tax AI OCR API",
        "version": "1.0.0"
    }), 200


# --- Case Management ---

@api_bp.route('/cases', methods=['GET'])
@login_required
def list_cases():
    """列出案件"""
    try:
        skip = request.args.get('skip', 0, type=int)
        limit = request.args.get('limit', 100, type=int)

        query = TaxOcrCase.query
        user_role = getattr(current_user, 'user_role', '')

        if user_role and 'admin' in user_role.lower():
            pass  # admin 可看所有案件
        else:
            accessible_case_ids = db.session.query(TaxOcrCaseUser.case_id).filter(
                TaxOcrCaseUser.user_id == current_user.id
            ).subquery()
            query = query.filter(
                db.or_(
                    TaxOcrCase.owner_id == current_user.id,
                    TaxOcrCase.id.in_(accessible_case_ids)
                )
            )

        cases = query.order_by(desc(TaxOcrCase.created_at)).offset(skip).limit(limit).all()
        return jsonify([case.to_dict() for case in cases]), 200

    except Exception as e:
        current_app.logger.error(f"列出案件失敗: {str(e)}")
        return jsonify({"error": "列出案件失敗", "detail": str(e)}), 500


@api_bp.route('/cases/<int:case_id>', methods=['GET'])
@login_required
def get_case(case_id):
    """取得單一案件"""
    try:
        case = TaxOcrCase.query.get(case_id)
        if not case:
            return jsonify({"error": "案件不存在"}), 404

        if not case.has_user_access(current_user.id):
            return jsonify({"error": "無權限存取此案件"}), 403

        return jsonify(case.to_dict()), 200

    except Exception as e:
        return jsonify({"error": "取得案件失敗", "detail": str(e)}), 500


@api_bp.route('/cases', methods=['POST'])
@login_required
def create_case():
    """建立案件"""
    try:
        user_role = getattr(current_user, 'user_role', '')
        if not user_role or ('admin' not in user_role.lower() and 'accountant' not in user_role.lower()):
            return jsonify({"error": "您沒有權限建立案件"}), 403

        data = request.get_json()
        required_fields = ['client_name', 'tax_id', 'year']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"缺少必填欄位: {field}"}), 400

        existing = TaxOcrCase.query.filter_by(tax_id=data['tax_id'], year=data['year']).first()
        if existing:
            return jsonify({"error": "案件已存在"}), 400

        case = TaxOcrCase(
            client_name=data['client_name'],
            client_code=data.get('client_code'),
            tax_id=data['tax_id'],
            year=data['year'],
            status='active',
            owner_id=current_user.id
        )
        db.session.add(case)
        db.session.flush()

        # 建立案件資料夾
        case_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'tax_ai_ocr', f'case_{case.id}')
        os.makedirs(case_dir, exist_ok=True)

        # 加入權限表
        case_user = TaxOcrCaseUser(case_id=case.id, user_id=current_user.id, role='accountant')
        db.session.add(case_user)
        db.session.commit()

        return jsonify(case.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "建立案件失敗", "detail": str(e)}), 500


@api_bp.route('/cases/<int:case_id>', methods=['DELETE'])
@login_required
def delete_case(case_id):
    """刪除案件"""
    try:
        import shutil

        case = TaxOcrCase.query.get(case_id)
        if not case:
            return jsonify({"error": "案件不存在"}), 404

        if not case.can_user_delete(current_user.id):
            return jsonify({"error": "無權限刪除此案件"}), 403

        jobs_count = TaxOcrJob.query.filter_by(case_id=case_id).count()
        versions_count = TaxOcrVersion.query.filter_by(case_id=case_id).count()
        client_name = case.client_name

        # 刪除檔案目錄
        case_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'tax_ai_ocr', f'case_{case_id}')
        if os.path.exists(case_dir):
            shutil.rmtree(case_dir)

        db.session.delete(case)
        db.session.commit()

        return jsonify({
            "ok": True,
            "message": f"已刪除案件「{client_name}」",
            "deleted_jobs": jobs_count,
            "deleted_versions": versions_count
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "刪除案件失敗", "detail": str(e)}), 500


# --- Job Management ---

@api_bp.route('/cases/<int:case_id>/jobs', methods=['GET'])
@login_required
def list_case_jobs(case_id):
    """列出案件的工作"""
    try:
        case = TaxOcrCase.query.get(case_id)
        if not case:
            return jsonify({"error": "案件不存在"}), 404

        jobs = TaxOcrJob.query.filter_by(case_id=case_id).order_by(desc(TaxOcrJob.created_at)).all()
        return jsonify([job.to_dict() for job in jobs]), 200

    except Exception as e:
        return jsonify({"error": "列出工作失敗", "detail": str(e)}), 500


@api_bp.route('/jobs', methods=['GET'])
@login_required
def list_jobs():
    """列出工作"""
    try:
        ids_str = request.args.get('ids')

        if ids_str:
            job_ids = [int(id.strip()) for id in ids_str.split(',') if id.strip()]
            jobs = TaxOcrJob.query.filter(TaxOcrJob.id.in_(job_ids)).all()
            jobs_dict = {job.id: job for job in jobs}
            jobs = [jobs_dict[job_id] for job_id in job_ids if job_id in jobs_dict]
        else:
            skip = request.args.get('skip', 0, type=int)
            limit = request.args.get('limit', 100, type=int)
            jobs = TaxOcrJob.query.order_by(desc(TaxOcrJob.created_at)).offset(skip).limit(limit).all()

        return jsonify([job.to_dict() for job in jobs]), 200

    except Exception as e:
        return jsonify({"error": "列出工作失敗", "detail": str(e)}), 500


@api_bp.route('/jobs/<int:job_id>', methods=['GET'])
@login_required
def get_job(job_id):
    """取得單一工作"""
    try:
        job = TaxOcrJob.query.get(job_id)
        if not job:
            return jsonify({"error": "工作不存在"}), 404

        return jsonify(job.to_dict()), 200

    except Exception as e:
        return jsonify({"error": "取得工作失敗", "detail": str(e)}), 500


@api_bp.route('/jobs/<int:job_id>', methods=['DELETE'])
@login_required
def delete_job(job_id):
    """刪除工作"""
    try:
        job = TaxOcrJob.query.get(job_id)
        if not job:
            return jsonify({"error": "工作不存在"}), 404

        filename = job.original_filename
        db.session.delete(job)
        db.session.commit()

        return jsonify({"ok": True, "message": f"工作已刪除：{filename}"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "刪除工作失敗", "detail": str(e)}), 500


@api_bp.route('/jobs/<int:job_id>/result', methods=['PATCH'])
@login_required
def update_job_result(job_id):
    """更新工作結果"""
    try:
        job = TaxOcrJob.query.get(job_id)
        if not job:
            return jsonify({"error": "工作不存在"}), 404

        data = request.get_json()

        if 'ocr_result' in data:
            job.result_json = data['ocr_result']
        if 'status' in data:
            job.status = data['status']

        # 記錄編輯軌跡
        if 'ocr_result' in data:
            log_entry = TaxOcrLog(
                job_id=job_id,
                case_id=job.case_id,
                user_id=current_user.id,
                action_type='edit',
                data_snapshot=data['ocr_result'],
                change_summary=f"使用者編輯了檔案 {job.original_filename}"
            )
            db.session.add(log_entry)

        db.session.commit()
        return jsonify({"ok": True, "message": "結果已更新", "job_id": job_id}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "更新失敗", "detail": str(e)}), 500


# --- File Upload ---

@api_bp.route('/upload_files', methods=['POST'])
@login_required
def upload_files():
    """上傳檔案"""
    try:
        case_id = request.form.get('case_id', type=int)
        document_type = request.form.get('document_type')
        files = request.files.getlist('files')

        if not case_id:
            return jsonify({"error": "缺少 case_id 參數"}), 400
        if not document_type:
            return jsonify({"error": "缺少 document_type 參數"}), 400
        if not files:
            return jsonify({"error": "未上傳任何檔案"}), 400

        case = TaxOcrCase.query.get(case_id)
        if not case:
            return jsonify({"error": f"案件 {case_id} 不存在"}), 404

        if not case.can_user_edit(current_user.id):
            return jsonify({"error": "無權限上傳檔案"}), 403

        valid_types = ['401', '403', 'withholding-slip', 'withholding-statement', 'dividend-slip']
        if document_type not in valid_types:
            return jsonify({"error": f"document_type 必須為：{', '.join(valid_types)}"}), 400

        timestamp = int(time.time())
        upload_base = current_app.config['TAX_OCR_UPLOAD_BASE']
        relative_dir = os.path.join('tax_ai_ocr', f'case_{case_id}', f'upload_{timestamp}')
        upload_dir = os.path.join(upload_base, relative_dir)
        os.makedirs(upload_dir, exist_ok=True)

        created_jobs = []

        for file in files:
            try:
                original_filename = file.filename
                sanitized_filename = sanitize_filename(original_filename)

                full_file_path = os.path.join(upload_dir, sanitized_filename)
                relative_file_path = os.path.join(relative_dir, sanitized_filename)

                file.save(full_file_path)

                job = TaxOcrJob(
                    case_id=case_id,
                    uploaded_by=current_user.id,
                    original_filename=sanitized_filename,
                    temp_filepath=relative_file_path,
                    document_type=document_type,
                    status='PENDING'
                )
                db.session.add(job)
                created_jobs.append(job)

            except Exception as e:
                current_app.logger.error(f"檔案 {file.filename} 處理失敗：{e}")
                continue

        db.session.commit()
        job_ids = [job.id for job in created_jobs]

        return jsonify({
            "case_id": case_id,
            "total_files": len(created_jobs),
            "job_ids": job_ids,
            "message": f"已上傳 {len(created_jobs)} 個檔案，開始處理"
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "上傳失敗", "detail": str(e)}), 500


# Alias for frontend compatibility
@api_bp.route('/upload_batch', methods=['POST'])
@login_required
def upload_batch():
    """上傳檔案（upload_files 的別名，保持前端相容性）"""
    return upload_files()


# --- Version Management ---

@api_bp.route('/versions', methods=['GET'])
@login_required
def list_all_versions():
    """列出所有版本"""
    try:
        query = TaxOcrVersion.query
        user_role = getattr(current_user, 'user_role', '')

        if not (user_role and 'admin' in user_role.lower()):
            accessible_case_ids = db.session.query(TaxOcrCaseUser.case_id).filter(
                TaxOcrCaseUser.user_id == current_user.id
            ).subquery()
            query = query.join(TaxOcrCase).filter(
                db.or_(
                    TaxOcrCase.owner_id == current_user.id,
                    TaxOcrCase.id.in_(accessible_case_ids)
                )
            )

        versions = query.order_by(TaxOcrVersion.created_at.desc()).all()
        return jsonify([version.to_dict() for version in versions]), 200

    except Exception as e:
        return jsonify({'error': '載入版本記錄失敗'}), 500


@api_bp.route('/versions/<int:case_id>', methods=['GET'])
@login_required
def list_versions(case_id):
    """列出案件的版本"""
    try:
        case = TaxOcrCase.query.get(case_id)
        if not case:
            return jsonify({"error": "案件不存在"}), 404

        query = TaxOcrVersion.query.filter_by(case_id=case_id)
        job_id = request.args.get('job_id', type=int)
        if job_id:
            query = query.filter_by(job_id=job_id)

        versions = query.order_by(desc(TaxOcrVersion.created_at)).all()
        return jsonify([version.to_dict() for version in versions]), 200

    except Exception as e:
        return jsonify({"error": "列出版本失敗", "detail": str(e)}), 500


@api_bp.route('/versions', methods=['POST'])
@login_required
def create_version():
    """建立版本"""
    try:
        data = request.get_json()

        required_fields = ['case_id', 'file_name', 'table_type', 'job_ids', 'data', 'notes', 'record_count']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"缺少必填欄位: {field}"}), 400

        case = TaxOcrCase.query.get(data['case_id'])
        if not case:
            return jsonify({"error": f"案件不存在: {data['case_id']}"}), 404

        fiscal_year = case.year - 1911 if case.year else None

        version = TaxOcrVersion(
            case_id=data['case_id'],
            table_type=data['table_type'],
            file_name=data['file_name'],
            record_count=data['record_count'],
            notes=data['notes'],
            exported_by=data.get('exported_by', 'K12A'),
            creator_id=current_user.id,
            creator_name=current_user.username,
            company_name=case.client_name,
            fiscal_year=fiscal_year,
            tax_id=case.tax_id,
            job_ids=data['job_ids'],
            table_data=data['data']
        )

        db.session.add(version)
        db.session.commit()

        return jsonify(version.to_dict()), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "建立版本失敗", "detail": str(e)}), 500


@api_bp.route('/versions/<int:version_id>', methods=['DELETE'])
@login_required
def delete_version(version_id):
    """刪除版本"""
    try:
        version = TaxOcrVersion.query.get(version_id)
        if not version:
            return jsonify({"error": "版本不存在"}), 404

        db.session.delete(version)
        db.session.commit()

        return jsonify({"ok": True, "message": "版本已刪除"}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "刪除版本失敗", "detail": str(e)}), 500


@api_bp.route('/versions/<int:version_id>/download', methods=['GET'])
@login_required
def download_version(version_id):
    """下載版本 Excel"""
    try:
        version = TaxOcrVersion.query.get(version_id)
        if not version:
            return jsonify({"error": "版本不存在"}), 404

        from app.services.excel_export_service import create_excel_from_version
        excel_file = create_excel_from_version(version)

        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=version.file_name
        )

    except Exception as e:
        return jsonify({"error": "下載失敗", "detail": str(e)}), 500
