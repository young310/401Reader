"""
Support Ticket System Routes and API Endpoints
"""
import os
import traceback
from datetime import datetime
from flask import (
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    send_file,
    current_app
)
from flask_login import login_required, current_user
from sqlalchemy import or_, and_, desc
from werkzeug.utils import secure_filename

from app import db
from app.support import support_blueprint
from app.support.models import SupportTicket, TicketComment, TicketAttachment, SupportEmailConfig
from app.support.utils import (
    save_attachment,
    can_user_access_ticket,
    can_user_modify_ticket,
    get_ticket_url,
    format_status_badge,
    format_priority_badge
)

def get_template_context():
    """Get common template context variables"""
    user_company = getattr(current_user, 'company_name', '') if hasattr(current_user, 'company_name') else ''
    user_office = getattr(current_user, 'office_name', '') if hasattr(current_user, 'office_name') else ''
    jwt_token = request.cookies.get('access_token_cookie', '')
    
    return {
        'userCompany': user_company,
        'userOffice': user_office,
        'jwtToken': jwt_token,
        'userLocale': 'zh-TW',
        'userEmail': current_user.email,
        'userName': getattr(current_user, 'username', current_user.email),
        'userRole': current_user.user_role,
        'viewOnly': '',
        'JWT_ACCESS_TOKEN_EXPIRES': current_app.config.get('JWT_ACCESS_TOKEN_EXPIRES', 3600)
    }


@support_blueprint.route('/')
@login_required
def index():
    """
    Main support page - redirects to ticket list
    """
    return redirect(url_for('support.ticket_list'))


@support_blueprint.route('/tickets')
@login_required
def ticket_list():
    """
    Display list of tickets (user's own tickets or all tickets for admin)
    """
    # Check if user is admin (admin, manager, or accountant - not just reporter)
    is_admin = current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])

    # Build query based on user role
    if is_admin:
        # Admin can see tickets from their company and office
        tickets = SupportTicket.query
        if hasattr(current_user, 'company_id') and current_user.company_id:
            tickets = tickets.filter_by(company_id=current_user.company_id)
        if hasattr(current_user, 'office_id') and current_user.office_id:
            tickets = tickets.filter_by(office_id=current_user.office_id)
    else:
        # Regular users can only see their own tickets
        tickets = SupportTicket.query.filter_by(created_by=current_user.id)

    # Apply filters from query parameters
    status_filter = request.args.get('status')
    priority_filter = request.args.get('priority')
    category_filter = request.args.get('category')

    if status_filter:
        tickets = tickets.filter_by(status=status_filter)
    if priority_filter:
        tickets = tickets.filter_by(priority=priority_filter)
    if category_filter:
        tickets = tickets.filter_by(category=category_filter)

    # Order by most recent first
    tickets = tickets.order_by(desc(SupportTicket.created_at)).all()

    context = get_template_context()
    context.update({
        'tickets': tickets,
        'is_admin': is_admin
    })
    
    return render_template('support/ticket_list.html', **context)


@support_blueprint.route('/admin/tickets')
@login_required
def admin_tickets():
    """
    Admin view of all tickets with advanced filtering
    """
    # Check if user is admin (admin, manager, or accountant - not just reporter)
    if not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
        flash('您沒有權限訪問此頁面', 'error')
        return redirect(url_for('support.ticket_list'))

    # Get tickets filtered by company and office
    tickets_query = SupportTicket.query
    if hasattr(current_user, 'company_id') and current_user.company_id:
        tickets_query = tickets_query.filter_by(company_id=current_user.company_id)
    if hasattr(current_user, 'office_id') and current_user.office_id:
        tickets_query = tickets_query.filter_by(office_id=current_user.office_id)
    
    tickets = tickets_query.order_by(desc(SupportTicket.created_at)).all()

    # Get statistics
    total_tickets = len(tickets)
    new_tickets = len([t for t in tickets if t.status == 'new'])
    in_progress_tickets = len([t for t in tickets if t.status == 'in_progress'])
    resolved_tickets = len([t for t in tickets if t.status == 'resolved'])

    stats = {
        'total': total_tickets,
        'new': new_tickets,
        'in_progress': in_progress_tickets,
        'resolved': resolved_tickets
    }

    context = get_template_context()
    context.update({
        'tickets': tickets,
        'stats': stats
    })
    
    return render_template('support/admin_tickets.html', **context)


@support_blueprint.route('/ticket/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    """
    Display ticket details with comments and attachments
    """
    ticket = SupportTicket.query.get_or_404(ticket_id)

    # Check access permission
    if not can_user_access_ticket(current_user, ticket):
        flash('您沒有權限查看此工單', 'error')
        return redirect(url_for('support.ticket_list'))

    # Get comments and attachments
    comments = ticket.comments.order_by(TicketComment.created_at).all()
    attachments = ticket.attachments.filter(TicketAttachment.comment_id.is_(None)).order_by(TicketAttachment.uploaded_at).all()  # Only original ticket attachments

    # Check if user can modify ticket
    can_modify = can_user_modify_ticket(current_user, ticket)

    # Get list of users for assignment (admin, manager, accountant)
    from app.models import User
    support_users = []
    if can_modify:
        support_users = User.query.filter(
            or_(
                User.user_role.like('%admin%'),
                User.user_role.like('%manager%'),
                User.user_role.like('%accountant%')
            )
        ).all()

    context = get_template_context()
    context.update({
        'ticket': ticket,
        'comments': comments,
        'attachments': attachments,
        'can_modify': can_modify,
        'support_users': support_users
    })
    
    return render_template('support/ticket_detail.html', **context)


@support_blueprint.route('/api/ticket/create', methods=['POST'])
@login_required
def create_ticket():
    """
    API endpoint to create a new support ticket
    """
    from sqlalchemy.exc import IntegrityError
    import time
    
    # Get form data once (outside retry loop)
    subject = request.form.get('subject', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', 'other')
    priority = request.form.get('priority', 'medium')

    # Validate required fields
    if not subject or not description:
        return jsonify({
            'success': False,
            'message': '主旨和問題描述為必填欄位'
        }), 400
    
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Ensure clean session state before each attempt
            db.session.rollback()
            
            # Generate ticket number
            ticket_number = SupportTicket.generate_ticket_number()

            # Create ticket
            ticket = SupportTicket(
                ticket_number=ticket_number,
                subject=subject,
                description=description,
                category=category,
                priority=priority,
                status='new',
                created_by=current_user.id,
                user_email=current_user.email,
                user_name=getattr(current_user, 'username', current_user.email),
                company_id=getattr(current_user, 'company_id', None),
                office_id=getattr(current_user, 'office_id', None)
            )

            db.session.add(ticket)
            db.session.flush()  # Get ticket ID

            # Handle file uploads
            uploaded_files = []
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                for file in files:
                    if file and file.filename:
                        file_info = save_attachment(file, ticket.id)
                        if file_info:
                            attachment = TicketAttachment(
                                ticket_id=ticket.id,
                                file_name=file_info['file_name'],
                                file_path=file_info['file_path'],
                                file_size=file_info['file_size'],
                                file_type=file_info['file_type'],
                                uploaded_by=current_user.id
                            )
                            db.session.add(attachment)
                            uploaded_files.append(file_info['file_name'])

            db.session.commit()

            # Send email notification
            try:
                from app.support.email_utils import send_ticket_created_email
                send_ticket_created_email(ticket)
            except Exception as e:
                current_app.logger.error(f"Failed to send ticket creation email: {str(e)}")
                # Don't fail the request if email fails

            return jsonify({
                'success': True,
                'message': '工單建立成功',
                'ticket_id': ticket.id,
                'ticket_number': ticket.ticket_number,
                'uploaded_files': uploaded_files
            })

        except IntegrityError as e:
            db.session.rollback()
            # Check if it's a duplicate ticket_number error
            if 'duplicate key' in str(e).lower() and 'ticket_number' in str(e).lower():
                if attempt < max_retries - 1:
                    current_app.logger.warning(f"Duplicate ticket number on attempt {attempt + 1}, retrying...")
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                else:
                    current_app.logger.error(f"Failed to create ticket after {max_retries} attempts: {str(e)}")
                    return jsonify({
                        'success': False,
                        'message': '建立工單時發生錯誤，請稍後再試'
                    }), 500
            else:
                # Other integrity errors
                current_app.logger.error(f"Integrity error creating ticket: {str(e)}\n{traceback.format_exc()}")
                return jsonify({
                    'success': False,
                    'message': f'建立工單時發生錯誤: {str(e)}'
                }), 500

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating ticket: {str(e)}\n{traceback.format_exc()}")
            return jsonify({
                'success': False,
                'message': f'建立工單時發生錯誤: {str(e)}'
            }), 500
    
    # Should never reach here
    return jsonify({
        'success': False,
        'message': '建立工單時發生未知錯誤'
    }), 500


@support_blueprint.route('/api/ticket/<int:ticket_id>/comment', methods=['POST'])
@login_required
def add_comment(ticket_id):
    """
    API endpoint to add a comment to a ticket with optional file attachments
    """
    try:
        ticket = SupportTicket.query.get_or_404(ticket_id)

        # Check access permission
        if not can_user_access_ticket(current_user, ticket):
            return jsonify({
                'success': False,
                'message': '您沒有權限操作此工單'
            }), 403

        # Get comment data
        content = request.form.get('content', '').strip()
        is_internal = request.form.get('is_internal') == 'true'

        # Check if we have content or files
        has_files = 'attachments' in request.files and any(f.filename for f in request.files.getlist('attachments'))
        
        if not content and not has_files:
            return jsonify({
                'success': False,
                'message': '請輸入回覆內容或選擇附件'
            }), 400

        # Only admin/manager/accountant can create internal comments
        if is_internal and not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
            is_internal = False

        # Create comment (content can be empty if there are files)
        comment = TicketComment(
            ticket_id=ticket_id,
            content=content if content else '[附件]',
            author_id=current_user.id,
            author_email=current_user.email,
            author_name=getattr(current_user, 'username', current_user.email),
            is_internal=is_internal
        )

        db.session.add(comment)
        db.session.flush()  # Get comment ID for file uploads

        # Handle file uploads
        uploaded_files = []
        if has_files:
            files = request.files.getlist('attachments')
            for file in files:
                if file and file.filename:
                    file_info = save_attachment(file, ticket_id)
                    if file_info:
                        attachment = TicketAttachment(
                            ticket_id=ticket_id,
                            comment_id=comment.id,  # Link attachment to this comment
                            file_name=file_info['file_name'],
                            file_path=file_info['file_path'],
                            file_size=file_info['file_size'],
                            file_type=file_info['file_type'],
                            uploaded_by=current_user.id
                        )
                        db.session.add(attachment)
                        uploaded_files.append(file_info['file_name'])

        # Update ticket updated_at
        ticket.updated_at = datetime.utcnow()

        db.session.commit()

        # Send email notification
        try:
            from app.support.email_utils import send_ticket_reply_email
            send_ticket_reply_email(ticket, comment)
        except Exception as e:
            current_app.logger.error(f"Failed to send reply email: {str(e)}")

        response_data = {
            'success': True,
            'message': '回覆已送出',
            'comment': comment.serialize()
        }
        
        if uploaded_files:
            response_data['uploaded_files'] = uploaded_files
            response_data['message'] += f'，已上傳 {len(uploaded_files)} 個附件'

        return jsonify(response_data)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding comment: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'新增回覆時發生錯誤: {str(e)}'
        }), 500


@support_blueprint.route('/api/ticket/<int:ticket_id>/update', methods=['POST'])
@login_required
def update_ticket(ticket_id):
    """
    API endpoint to update ticket status, priority, assignment, etc.
    """
    try:
        ticket = SupportTicket.query.get_or_404(ticket_id)

        # Check modify permission (admin, manager, or accountant)
        if not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
            return jsonify({
                'success': False,
                'message': '您沒有權限修改此工單'
            }), 403

        # Get update data
        data = request.get_json() or request.form.to_dict()
        old_status = ticket.status
        old_assigned_to = ticket.assigned_to
        old_project_pm = ticket.project_pm

        # Update fields
        if 'status' in data:
            ticket.status = data['status']
            if data['status'] == 'resolved':
                ticket.resolved_at = datetime.utcnow()
            elif data['status'] == 'closed':
                ticket.closed_at = datetime.utcnow()

        if 'priority' in data:
            ticket.priority = data['priority']

        if 'assigned_to' in data:
            ticket.assigned_to = int(data['assigned_to']) if data['assigned_to'] else None

        if 'project_pm' in data:
            ticket.project_pm = int(data['project_pm']) if data['project_pm'] else None

        if 'category' in data:
            ticket.category = data['category']

        ticket.updated_at = datetime.utcnow()

        db.session.commit()

        # Send email notification if status changed
        if old_status != ticket.status:
            try:
                from app.support.email_utils import send_ticket_status_change_email
                send_ticket_status_change_email(ticket, old_status, ticket.status)
            except Exception as e:
                current_app.logger.error(f"Failed to send status change email: {str(e)}")

        # Send email notification if assignment changed
        if old_assigned_to != ticket.assigned_to and ticket.assigned_to:
            try:
                from app.models import User
                from app.support.email_utils import send_ticket_assignment_email
                assigned_user = User.query.get(ticket.assigned_to)
                if assigned_user:
                    send_ticket_assignment_email(ticket, assigned_user)
            except Exception as e:
                current_app.logger.error(f"Failed to send assignment email: {str(e)}")

        # Send email notification if project_pm changed
        if old_project_pm != ticket.project_pm and ticket.project_pm:
            try:
                from app.models import User
                from app.support.email_utils import send_ticket_project_pm_assignment_email
                project_pm_user = User.query.get(ticket.project_pm)
                if project_pm_user:
                    send_ticket_project_pm_assignment_email(ticket, project_pm_user)
            except Exception as e:
                current_app.logger.error(f"Failed to send project PM assignment email: {str(e)}")

        return jsonify({
            'success': True,
            'message': '工單更新成功',
            'ticket': ticket.serialize()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating ticket: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'更新工單時發生錯誤: {str(e)}'
        }), 500


@support_blueprint.route('/api/ticket/<int:ticket_id>/attachment', methods=['POST'])
@login_required
def upload_attachment(ticket_id):
    """
    API endpoint to upload attachment to existing ticket
    """
    try:
        ticket = SupportTicket.query.get_or_404(ticket_id)

        # Check access permission
        if not can_user_access_ticket(current_user, ticket):
            return jsonify({
                'success': False,
                'message': '您沒有權限操作此工單'
            }), 403

        # Handle file upload
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': '沒有檔案上傳'
            }), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({
                'success': False,
                'message': '沒有選擇檔案'
            }), 400

        # Save file
        file_info = save_attachment(file, ticket_id)
        if not file_info:
            return jsonify({
                'success': False,
                'message': '檔案上傳失敗（檔案類型不允許或檔案太大）'
            }), 400

        # Create attachment record
        attachment = TicketAttachment(
            ticket_id=ticket_id,
            file_name=file_info['file_name'],
            file_path=file_info['file_path'],
            file_size=file_info['file_size'],
            file_type=file_info['file_type'],
            uploaded_by=current_user.id
        )

        db.session.add(attachment)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '附件上傳成功',
            'attachment': attachment.serialize()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading attachment: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'上傳附件時發生錯誤: {str(e)}'
        }), 500


@support_blueprint.route('/api/ticket/<int:ticket_id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete_ticket(ticket_id):
    """
    API endpoint to delete a ticket (admin only)
    """
    try:
        ticket = SupportTicket.query.get_or_404(ticket_id)

        # Only admin/manager/accountant can delete tickets
        if not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
            return jsonify({
                'success': False,
                'message': '您沒有權限刪除工單'
            }), 403

        # Delete ticket (cascade will delete comments and attachments)
        db.session.delete(ticket)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '工單已刪除'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting ticket: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'刪除工單時發生錯誤: {str(e)}'
        }), 500


@support_blueprint.route('/api/tickets/count')
@login_required
def get_ticket_count():
    """
    API endpoint to get unread/new ticket count for current user
    """
    try:
        # Count new tickets for current user
        count = SupportTicket.query.filter_by(
            created_by=current_user.id,
            status='new'
        ).count()

        return jsonify({
            'success': True,
            'count': count
        })

    except Exception as e:
        current_app.logger.error(f"Error getting ticket count: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@support_blueprint.route('/attachment/<int:attachment_id>/view')
@login_required
def view_attachment(attachment_id):
    """
    View attachment file in browser
    """
    try:
        attachment = TicketAttachment.query.get_or_404(attachment_id)
        ticket = SupportTicket.query.get(attachment.ticket_id)

        # Check access permission
        if not can_user_access_ticket(current_user, ticket):
            flash('您沒有權限查看此附件', 'error')
            return redirect(url_for('support.ticket_list'))

        # Check if file exists
        if not os.path.exists(attachment.file_path):
            flash('檔案不存在', 'error')
            return redirect(url_for('support.ticket_detail', ticket_id=ticket.id))

        return send_file(
            attachment.file_path,
            as_attachment=False,  # Display in browser instead of download
            download_name=attachment.file_name
        )

    except Exception as e:
        current_app.logger.error(f"Error viewing attachment: {str(e)}")
        flash('查看附件時發生錯誤', 'error')
        return redirect(url_for('support.ticket_list'))


@support_blueprint.route('/attachment/<int:attachment_id>/download')
@login_required
def download_attachment(attachment_id):
    """
    Download attachment file
    """
    try:
        attachment = TicketAttachment.query.get_or_404(attachment_id)
        ticket = SupportTicket.query.get(attachment.ticket_id)

        # Check access permission
        if not can_user_access_ticket(current_user, ticket):
            flash('您沒有權限下載此附件', 'error')
            return redirect(url_for('support.ticket_list'))

        # Check if file exists
        if not os.path.exists(attachment.file_path):
            flash('檔案不存在', 'error')
            return redirect(url_for('support.ticket_detail', ticket_id=ticket.id))

        return send_file(
            attachment.file_path,
            as_attachment=True,
            download_name=attachment.file_name
        )

    except Exception as e:
        current_app.logger.error(f"Error downloading attachment: {str(e)}")
        flash('下載附件時發生錯誤', 'error')
        return redirect(url_for('support.ticket_list'))


# ============================================================================
# Support Email Configuration Management
# ============================================================================

@support_blueprint.route('/admin/email-config')
@login_required
def email_config():
    """
    Admin page for managing support email configurations
    """
    # Check if user is admin (admin, manager, or accountant)
    if not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
        flash('您沒有權限訪問此頁面', 'error')
        return redirect(url_for('support.ticket_list'))

    # Get current domain for filtering and display
    current_domain = SupportEmailConfig.get_current_domain()
    display_domain = SupportEmailConfig.get_display_domain()
    
    # Filter configurations based on domain
    if current_domain == 'localhost' or request.host.startswith('localhost'):
        # Show all configurations for localhost
        configs = SupportEmailConfig.query.order_by(SupportEmailConfig.domain).all()
    else:
        # Show only configurations for current domain and default
        configs = SupportEmailConfig.query.filter(
            or_(
                SupportEmailConfig.domain == current_domain,
                SupportEmailConfig.domain == 'default'
            )
        ).order_by(SupportEmailConfig.domain).all()

    context = get_template_context()
    context.update({
        'configs': configs,
        'current_domain': current_domain,
        'display_domain': display_domain,
        'is_localhost': current_domain == 'localhost' or request.host.startswith('localhost')
    })
    
    return render_template('support/email_config.html', **context)


@support_blueprint.route('/api/email-config/list', methods=['GET'])
@login_required
def get_email_configs():
    """
    API endpoint to get all email configurations
    """
    try:
        # Check admin permission (admin, manager, or accountant)
        if not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
            return jsonify({
                'success': False,
                'message': '權限不足'
            }), 403

        # Get current domain and filter configurations
        current_domain = SupportEmailConfig.get_current_domain()
        
        if current_domain == 'localhost' or request.host.startswith('localhost'):
            # Show all configurations for localhost
            configs = SupportEmailConfig.query.order_by(SupportEmailConfig.domain).all()
        else:
            # Show only configurations for current domain and default
            configs = SupportEmailConfig.query.filter(
                or_(
                    SupportEmailConfig.domain == current_domain,
                    SupportEmailConfig.domain == 'default'
                )
            ).order_by(SupportEmailConfig.domain).all()

        return jsonify({
            'success': True,
            'configs': [config.serialize() for config in configs]
        })

    except Exception as e:
        current_app.logger.error(f"Error getting email configs: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@support_blueprint.route('/api/email-config/create', methods=['POST'])
@login_required
def create_email_config():
    """
    API endpoint to create new email configuration
    """
    try:
        # Check admin permission (admin, manager, or accountant)
        if not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
            return jsonify({
                'success': False,
                'message': '您沒有權限建立郵件配置'
            }), 403

        # Get form data
        data = request.get_json() or request.form.to_dict()
        domain = data.get('domain', '').strip()
        support_emails = data.get('support_emails', '').strip()
        roles = data.get('roles', '').strip()
        description = data.get('description', '').strip()
        is_active = data.get('is_active', 'true') in [True, 'true', '1', 'yes']

        # Validate
        if not domain or not support_emails:
            return jsonify({
                'success': False,
                'message': '網域名稱和支援郵箱為必填欄位'
            }), 400

        # Check domain restriction (non-localhost environments)
        current_domain = SupportEmailConfig.get_current_domain()
        display_domain = SupportEmailConfig.get_display_domain()
        if not (current_domain == 'localhost' or request.host.startswith('localhost')):
            if domain != current_domain and domain != 'default':
                return jsonify({
                    'success': False,
                    'message': f'只能為當前網域 ({display_domain}) 或預設配置建立郵件配置'
                }), 400

        # Check if domain already exists
        existing = SupportEmailConfig.query.filter_by(domain=domain).first()
        if existing:
            return jsonify({
                'success': False,
                'message': f'網域 {domain} 的配置已存在'
            }), 400

        # Validate email format
        emails = [e.strip() for e in support_emails.split(',')]
        import re
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        for email in emails:
            if not email_pattern.match(email):
                return jsonify({
                    'success': False,
                    'message': f'無效的郵箱格式: {email}'
                }), 400

        # Validate roles if provided
        if roles:
            valid_roles = ['admin', 'reporter', 'manager', 'accountant']
            role_list = [r.strip() for r in roles.split(',') if r.strip()]
            for role in role_list:
                if role not in valid_roles:
                    return jsonify({
                        'success': False,
                        'message': f'無效的角色: {role}。有效角色為: {", ".join(valid_roles)}'
                    }), 400

        # Create config
        config = SupportEmailConfig(
            domain=domain,
            support_emails=support_emails,
            roles=roles,
            description=description,
            is_active=is_active,
            created_by=current_user.id
        )

        db.session.add(config)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '郵件配置建立成功',
            'config': config.serialize()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating email config: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'建立配置時發生錯誤: {str(e)}'
        }), 500


@support_blueprint.route('/api/email-config/<int:config_id>/update', methods=['POST', 'PUT'])
@login_required
def update_email_config(config_id):
    """
    API endpoint to update email configuration
    """
    try:
        # Check admin permission (admin, manager, or accountant)
        if not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
            return jsonify({
                'success': False,
                'message': '您沒有權限修改郵件配置'
            }), 403

        config = SupportEmailConfig.query.get_or_404(config_id)

        # Get form data
        data = request.get_json() or request.form.to_dict()

        if 'support_emails' in data:
            support_emails = data['support_emails'].strip()
            if not support_emails:
                return jsonify({
                    'success': False,
                    'message': '支援郵箱不能為空'
                }), 400

            # Validate email format
            emails = [e.strip() for e in support_emails.split(',')]
            import re
            email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
            for email in emails:
                if not email_pattern.match(email):
                    return jsonify({
                        'success': False,
                        'message': f'無效的郵箱格式: {email}'
                    }), 400

            config.support_emails = support_emails

        if 'roles' in data:
            roles = data['roles'].strip()
            if roles:
                # Validate roles
                valid_roles = ['admin', 'reporter', 'manager', 'accountant']
                role_list = [r.strip() for r in roles.split(',') if r.strip()]
                for role in role_list:
                    if role not in valid_roles:
                        return jsonify({
                            'success': False,
                            'message': f'無效的角色: {role}。有效角色為: {", ".join(valid_roles)}'
                        }), 400
            config.roles = roles

        if 'description' in data:
            config.description = data['description'].strip()

        if 'is_active' in data:
            config.is_active = data['is_active'] in [True, 'true', '1', 'yes']

        config.updated_at = datetime.utcnow()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '郵件配置更新成功',
            'config': config.serialize()
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating email config: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'更新配置時發生錯誤: {str(e)}'
        }), 500


@support_blueprint.route('/api/email-config/<int:config_id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete_email_config(config_id):
    """
    API endpoint to delete email configuration
    """
    try:
        # Check admin permission (admin, manager, or accountant)
        if not (current_user.user_role and any(role in current_user.user_role for role in ['admin', 'manager', 'accountant'])):
            return jsonify({
                'success': False,
                'message': '您沒有權限刪除郵件配置'
            }), 403

        config = SupportEmailConfig.query.get_or_404(config_id)

        # Prevent deleting default config
        if config.domain == 'default':
            return jsonify({
                'success': False,
                'message': '無法刪除預設配置'
            }), 400

        # Check domain restriction (non-localhost environments)
        current_domain = SupportEmailConfig.get_current_domain()
        display_domain = SupportEmailConfig.get_display_domain()
        if not (current_domain == 'localhost' or request.host.startswith('localhost')):
            if config.domain != current_domain:
                return jsonify({
                    'success': False,
                    'message': f'只能刪除當前網域 ({display_domain}) 的配置'
                }), 400

        db.session.delete(config)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '郵件配置已刪除'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting email config: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'刪除配置時發生錯誤: {str(e)}'
        }), 500
