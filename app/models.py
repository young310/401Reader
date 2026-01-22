# models.py
# 獨立的資料庫模型定義

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Boolean
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """使用者模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    user_role = Column(String(50), default="reporter", nullable=False)  # admin, accountant, reporter
    locale = Column(String(10), default="zh_TW")
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        """設定密碼（加密）"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """驗證密碼"""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'user_role': self.user_role,
            'locale': self.locale,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TaxOcrCaseUser(db.Model):
    """稅務案件使用者關聯表 - 支援多使用者協作"""
    __tablename__ = "tax_ocr_case_users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("tax_ocr_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # 權限角色
    role = Column(String(20), default="reporter", nullable=False)  # accountant, reporter, manager

    # 時間戳記
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 關聯
    case = db.relationship("TaxOcrCase", back_populates="case_users")
    user = db.relationship("User", backref="case_memberships")

    # 唯一約束
    __table_args__ = (
        db.UniqueConstraint('case_id', 'user_id', name='uq_case_user'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'case_id': self.case_id,
            'user_id': self.user_id,
            'user_name': self.user.username if self.user else None,
            'user_email': self.user.email if self.user else None,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TaxOcrCase(db.Model):
    """稅務案件表 - 記錄每個公司的年度查帳案件"""
    __tablename__ = "tax_ocr_cases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    client_name = Column(String(255), nullable=False)
    client_code = Column(String(50), nullable=True)
    tax_id = Column(String(20), nullable=False)
    year = Column(Integer, nullable=False)
    status = Column(String(50), default="active", nullable=False)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 關聯
    owner = db.relationship("User", foreign_keys=[owner_id], backref="owned_cases")
    case_users = db.relationship("TaxOcrCaseUser", back_populates="case", cascade="all, delete-orphan")
    jobs = db.relationship("TaxOcrJob", back_populates="case", cascade="all, delete-orphan")
    versions = db.relationship("TaxOcrVersion", back_populates="case", cascade="all, delete-orphan")

    def to_dict(self, include_users=False):
        result = {
            'id': self.id,
            'client_name': self.client_name,
            'client_code': self.client_code,
            'tax_id': self.tax_id,
            'year': self.year,
            'status': self.status,
            'owner_id': self.owner_id,
            'owner_name': self.owner.username if self.owner else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_users:
            result['users'] = [cu.to_dict() for cu in self.case_users]

        return result

    def has_user_access(self, user_id, required_role=None):
        """檢查使用者是否有權限存取此案件"""
        # 檢查是否為擁有者
        if self.owner_id == user_id:
            return True

        # 檢查是否在權限表中
        for cu in self.case_users:
            if cu.user_id == user_id:
                if required_role is None:
                    return True
                # 權限檢查
                role_priority = {'manager': 1, 'reporter': 2, 'accountant': 3}
                return role_priority.get(cu.role, 0) >= role_priority.get(required_role, 0)

        return False

    def can_user_edit(self, user_id):
        """檢查使用者是否可以編輯（上傳、修改資料）"""
        if self.owner_id == user_id:
            return True

        for cu in self.case_users:
            if cu.user_id == user_id and cu.role in ['accountant', 'reporter']:
                return True

        return False

    def can_user_delete(self, user_id):
        """檢查使用者是否可以刪除案件"""
        if self.owner_id == user_id:
            return True

        for cu in self.case_users:
            if cu.user_id == user_id and cu.role == 'accountant':
                return True

        return False


class TaxOcrJob(db.Model):
    """稅務任務表 - 記錄單一檔案的處理狀態"""
    __tablename__ = "tax_ocr_jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("tax_ocr_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # 檔案資訊
    original_filename = Column(String(255), nullable=False)
    temp_filepath = Column(String(500), nullable=False)

    # 文件類型
    document_type = Column(String(50), nullable=False, index=True)
    classified_type = Column(String(50), nullable=True, index=True)

    # 任務狀態
    status = Column(String(50), default="PENDING", nullable=False, index=True)

    # 辨識結果
    detected_stream = Column(String(20), nullable=True)
    detected_company_name = Column(String(255), nullable=True)

    # LLM 處理結果
    result_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    # 時間戳記
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 關聯
    case = db.relationship("TaxOcrCase", back_populates="jobs")
    uploader = db.relationship("User", backref="uploaded_jobs")
    edit_logs = db.relationship("TaxOcrLog", back_populates="job", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'case_id': self.case_id,
            'uploaded_by': self.uploaded_by,
            'original_filename': self.original_filename,
            'temp_filepath': self.temp_filepath,
            'document_type': self.document_type,
            'classified_type': self.classified_type,
            'status': self.status,
            'detected_stream': self.detected_stream,
            'detected_company_name': self.detected_company_name,
            'result_json': self.result_json,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TaxOcrVersion(db.Model):
    """稅務版本表 - 記錄AI辨識校對後建立的版本"""
    __tablename__ = "tax_ocr_versions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("tax_ocr_cases.id", ondelete="CASCADE"), nullable=False, index=True)

    table_type = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    record_count = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    exported_by = Column(String(50), default="K12A", nullable=False)

    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    creator_name = Column(String(100), nullable=True)

    company_name = Column(String(200), nullable=True)
    fiscal_year = Column(Integer, nullable=True)
    tax_id = Column(String(20), nullable=True)

    job_ids = Column(JSON, nullable=False)
    table_data = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 關聯
    case = db.relationship("TaxOcrCase", back_populates="versions")
    creator = db.relationship("User", backref="created_versions")

    def to_dict(self):
        return {
            'id': self.id,
            'case_id': self.case_id,
            'table_type': self.table_type,
            'file_name': self.file_name,
            'record_count': self.record_count,
            'notes': self.notes,
            'exported_by': self.exported_by,
            'creator_id': self.creator_id,
            'creator_name': self.creator_name,
            'company_name': self.company_name,
            'fiscal_year': self.fiscal_year,
            'tax_id': self.tax_id,
            'job_ids': self.job_ids,
            'table_data': self.table_data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class TaxOcrLog(db.Model):
    """稅務編輯軌跡表"""
    __tablename__ = "tax_ocr_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("tax_ocr_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    case_id = Column(Integer, ForeignKey("tax_ocr_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    action_type = Column(String(50), nullable=False)
    data_snapshot = Column(JSON, nullable=False)
    change_summary = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # 關聯
    job = db.relationship("TaxOcrJob", back_populates="edit_logs")
    case = db.relationship("TaxOcrCase", backref="case_edit_logs")
    user = db.relationship("User", backref="tax_ocr_logs")

    def to_dict(self):
        return {
            'id': self.id,
            'job_id': self.job_id,
            'case_id': self.case_id,
            'user_id': self.user_id,
            'user_name': self.user.username if self.user else None,
            'action_type': self.action_type,
            'change_summary': self.change_summary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def to_dict_with_data(self):
        result = self.to_dict()
        result['data_snapshot'] = self.data_snapshot
        return result
