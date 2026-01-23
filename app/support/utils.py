"""
Support Ticket System Utility Functions
"""
import os
import platform
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import current_app
from app import db


# Allowed file extensions for attachments
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def get_upload_folder():
    """
    根據不同作業系統取得適當的上傳資料夾路徑。

    此函數會依據作業系統類型決定上傳資料夾的位置：
    - 在 macOS 上，使用當前工作目錄下的 "uploads" 資料夾
    - 在 Linux 上，使用環境變數 UPLOAD_FOLDER 或預設的 '/home/uploads/'
    - 在 Windows 上，使用當前工作目錄下的 "uploads" 資料夾

    回傳:
        str: 標準化後的上傳資料夾路徑
    """
    # 預設使用環境變數中的 UPLOAD_FOLDER 或預設值 '/home/uploads/'
    upload_folder = os.getenv('UPLOAD_FOLDER', '/home/uploads/')

    # 根據作業系統類型設定適當的路徑
    if os.name == 'posix':  # Unix-like 系統 (Linux/macOS)
        if platform.system() == 'Darwin':  # 專門處理 macOS
            upload_folder = os.path.join(os.getcwd(), "uploads")
        # Linux 系統保留原始設定值

    elif os.name == 'nt':  # Windows 系統
        upload_folder = os.path.join(os.getcwd(), "uploads")

    # 確保上傳資料夾存在，若不存在則自動建立
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)

    # 回傳標準化的路徑格式
    return os.path.normpath(upload_folder)


def allowed_file(filename):
    """
    Check if file extension is allowed
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_size(file):
    """
    Get file size in bytes
    """
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    return size


def save_attachment(file, ticket_id):
    """
    Save uploaded file and return file info

    Args:
        file: FileStorage object from request.files
        ticket_id: ID of the ticket

    Returns:
        dict with file_name, file_path, file_size, file_type
        or None if save failed
    """
    if not file or not allowed_file(file.filename):
        return None

    # Check file size
    file_size = get_file_size(file)
    if file_size > MAX_FILE_SIZE:
        return None

    # Generate safe filename
    filename = secure_filename(file.filename)
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{filename}"

    # Create directory structure using OS-aware upload folder
    upload_folder = get_upload_folder()
    ticket_folder = os.path.join(upload_folder, 'support_tickets', str(ticket_id))
    os.makedirs(ticket_folder, exist_ok=True)

    # Save file
    file_path = os.path.join(ticket_folder, filename)
    file.save(file_path)

    return {
        'file_name': file.filename,  # Original filename
        'file_path': file_path,
        'file_size': file_size,
        'file_type': file.content_type
    }


def format_status_badge(status):
    """
    Return Bootstrap badge class for ticket status
    """
    status_map = {
        'new': 'badge-primary',
        'in_progress': 'badge-warning',
        'resolved': 'badge-success',
        'closed': 'badge-secondary'
    }
    return status_map.get(status, 'badge-info')


def format_priority_badge(priority):
    """
    Return Bootstrap badge class for ticket priority
    """
    priority_map = {
        'low': 'badge-info',
        'medium': 'badge-warning',
        'high': 'badge-danger',
        'urgent': 'badge-dark'
    }
    return priority_map.get(priority, 'badge-secondary')


def format_category_display(category):
    """
    Return human-readable category name
    """
    category_map = {
        'system_error': '系統錯誤',
        'feature_request': '功能請求',
        'data_issue': '資料問題',
        'other': '其他'
    }
    return category_map.get(category, category)


def format_status_display(status):
    """
    Return human-readable status name
    """
    status_map = {
        'new': '新建',
        'in_progress': '處理中',
        'resolved': '已解決',
        'closed': '已關閉'
    }
    return status_map.get(status, status)


def format_priority_display(priority):
    """
    Return human-readable priority name
    """
    priority_map = {
        'low': '低',
        'medium': '中',
        'high': '高',
        'urgent': '緊急'
    }
    return priority_map.get(priority, priority)


def can_user_access_ticket(user, ticket):
    """
    Check if user has permission to access a ticket

    Args:
        user: User object
        ticket: SupportTicket object

    Returns:
        bool
    """
    # Admin, manager, and accountant can access tickets from their company/office
    if user.user_role and any(role in user.user_role for role in ['admin', 'manager', 'accountant']):
        # Check if ticket belongs to same company and office
        if hasattr(user, 'company_id') and user.company_id and ticket.company_id:
            if user.company_id != ticket.company_id:
                return False
        if hasattr(user, 'office_id') and user.office_id and ticket.office_id:
            if user.office_id != ticket.office_id:
                return False
        return True

    # Users can only access their own tickets
    return ticket.created_by == user.id


def can_user_modify_ticket(user, ticket):
    """
    Check if user has permission to modify a ticket (change status, assign, etc.)

    Args:
        user: User object
        ticket: SupportTicket object

    Returns:
        bool
    """
    # Only admin, manager, and accountant can modify tickets
    if user.user_role and any(role in user.user_role for role in ['admin', 'manager', 'accountant']):
        return True

    return False


def get_ticket_url(ticket_id):
    """
    Generate full URL for ticket detail page

    Args:
        ticket_id: ID of the ticket

    Returns:
        str: Full URL
    """
    from flask import request, url_for
    return request.host_url.rstrip('/') + url_for('support.ticket_detail', ticket_id=ticket_id)


def build_ticket_search_query(query, filters):
    """
    Build SQLAlchemy query with filters

    Args:
        query: Base SQLAlchemy query
        filters: dict with filter parameters

    Returns:
        Modified query
    """
    from app.support.models import SupportTicket

    # Filter by status
    if filters.get('status'):
        query = query.filter(SupportTicket.status == filters['status'])

    # Filter by priority
    if filters.get('priority'):
        query = query.filter(SupportTicket.priority == filters['priority'])

    # Filter by category
    if filters.get('category'):
        query = query.filter(SupportTicket.category == filters['category'])

    # Filter by creator
    if filters.get('created_by'):
        query = query.filter(SupportTicket.created_by == filters['created_by'])

    # Filter by assigned user
    if filters.get('assigned_to'):
        query = query.filter(SupportTicket.assigned_to == filters['assigned_to'])

    # Filter by company
    if filters.get('company_id'):
        query = query.filter(SupportTicket.company_id == filters['company_id'])

    # Filter by office
    if filters.get('office_id'):
        query = query.filter(SupportTicket.office_id == filters['office_id'])

    # Search in subject and description
    if filters.get('search'):
        search_term = f"%{filters['search']}%"
        query = query.filter(
            db.or_(
                SupportTicket.subject.ilike(search_term),
                SupportTicket.description.ilike(search_term),
                SupportTicket.ticket_number.ilike(search_term)
            )
        )

    return query
