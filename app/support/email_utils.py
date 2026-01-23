"""
Support Ticket Email Notification Functions
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app, url_for
from datetime import datetime, timezone, timedelta


# Default support team email address (fallback)
DEFAULT_SUPPORT_EMAIL = 'ami.support@yageo.com'

# Taiwan timezone (UTC+8)
TAIWAN_TZ = timezone(timedelta(hours=8))


def format_taiwan_time(dt):
    """
    Convert datetime to Taiwan timezone and format as string
    
    Args:
        dt: datetime object (assumed to be UTC if no timezone info)
    
    Returns:
        str: Formatted time string in Taiwan timezone
    """
    if dt is None:
        return ''
    
    # If datetime is naive (no timezone), assume it's UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Taiwan timezone
    taiwan_time = dt.astimezone(TAIWAN_TZ)
    
    return taiwan_time.strftime('%Y-%m-%d %H:%M:%S')


def get_support_emails(company_id=None, office_id=None):
    """
    Get support email addresses for current domain

    Args:
        company_id: Company ID to get role-based emails
        office_id: Office ID to get role-based emails

    Returns:
        list: List of support email addresses
    """
    from app.support.models import SupportEmailConfig

    try:
        domain = SupportEmailConfig.get_current_domain()
        emails = SupportEmailConfig.get_support_emails_for_domain(domain, company_id, office_id)
        return emails if emails else [DEFAULT_SUPPORT_EMAIL]
    except Exception as e:
        current_app.logger.error(f"Error getting support emails: {str(e)}")
        return [DEFAULT_SUPPORT_EMAIL]


def send_email(to_emails, subject, html_body):
    """
    Send email using SMTP configuration from app config

    Args:
        to_emails: Recipient email address (string) or list of addresses
        subject: Email subject
        html_body: HTML email body
    """
    try:
        # Convert single email to list
        if isinstance(to_emails, str):
            to_emails = [to_emails]

        # Get email configuration from app config
        mail_username = current_app.config.get('MAIL_USERNAME')
        mail_password = current_app.config.get('MAIL_PASSWORD')
        mail_server = current_app.config.get('MAIL_SERVER', 'smtp.gmail.com')
        mail_port = current_app.config.get('MAIL_PORT', 587)

        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = mail_username
        msg['To'] = ', '.join(to_emails)  # Join multiple emails
        msg['Subject'] = subject

        # Attach HTML body
        html_part = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(html_part)

        # Send email
        with smtplib.SMTP(mail_server, mail_port) as server:
            server.starttls()
            server.login(mail_username, mail_password)
            server.send_message(msg)

        current_app.logger.info(f"Email sent successfully to {', '.join(to_emails)}: {subject}")
        return True

    except Exception as e:
        current_app.logger.error(f"Failed to send email to {to_emails}: {str(e)}")
        return False


def get_ticket_url(ticket):
    """
    Generate full URL for ticket detail page
    """
    from flask import request
    # Get base URL from request or use a default
    base_url = request.url_root if request else 'http://localhost:9000/'
    return f"{base_url.rstrip('/')}/support/ticket/{ticket.id}"


def send_ticket_created_email(ticket):
    """
    Send email notification when a new ticket is created

    Args:
        ticket: SupportTicket object
    """
    ticket_url = get_ticket_url(ticket)

    # Email to support team
    subject = f"[Support Ticket] {ticket.ticket_number} - {ticket.subject}"

    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #007bff; color: white; padding: 15px; border-radius: 5px; }}
            .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
            .info-row {{ margin: 10px 0; }}
            .label {{ font-weight: bold; color: #555; }}
            .value {{ color: #333; }}
            .button {{
                display: inline-block;
                padding: 10px 20px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 15px;
            }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
            .priority-high {{ color: #dc3545; font-weight: bold; }}
            .priority-medium {{ color: #ffc107; font-weight: bold; }}
            .priority-low {{ color: #28a745; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>新的支援工單</h2>
            </div>
            <div class="content">
                <p>親愛的支援團隊：</p>
                <p>使用者 <strong>{ticket.user_email}</strong> 提交了新的支援工單。</p>

                <div class="info-row">
                    <span class="label">工單編號：</span>
                    <span class="value">{ticket.ticket_number}</span>
                </div>

                <div class="info-row">
                    <span class="label">主旨：</span>
                    <span class="value">{ticket.subject}</span>
                </div>

                <div class="info-row">
                    <span class="label">類型：</span>
                    <span class="value">{get_category_display(ticket.category)}</span>
                </div>

                <div class="info-row">
                    <span class="label">優先級：</span>
                    <span class="value priority-{ticket.priority}">{get_priority_display(ticket.priority)}</span>
                </div>

                <div class="info-row">
                    <span class="label">建立時間：</span>
                    <span class="value">{format_taiwan_time(ticket.created_at)}</span>
                </div>

                <div class="info-row">
                    <span class="label">問題描述：</span>
                    <div class="value" style="margin-top: 5px; padding: 10px; background-color: white; border-radius: 3px;">
                        {ticket.description.replace(chr(10), '<br>')}
                    </div>
                </div>

                <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看工單詳情</a>
            </div>
            <div class="footer">
                <p>此郵件由 AMI 支援系統自動發送，請勿直接回覆此郵件。</p>
                <p>如需回覆工單，請登入系統進行操作。</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send to support team (multiple recipients)
    support_emails = get_support_emails(ticket.company_id, ticket.office_id)
    send_email(support_emails, subject, html_body)

    # Also send confirmation email to user
    user_subject = f"[工單已建立] {ticket.ticket_number} - {ticket.subject}"
    user_html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #28a745; color: white; padding: 15px; border-radius: 5px; }}
            .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
            .button {{
                display: inline-block;
                padding: 10px 20px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 15px;
            }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>工單建立成功</h2>
            </div>
            <div class="content">
                <p>親愛的 {ticket.user_email}：</p>
                <p>您的支援工單已成功建立。我們的支援團隊會盡快處理您的問題。</p>
                <p><strong>工單編號：</strong>{ticket.ticket_number}</p>
                <p><strong>主旨：</strong>{ticket.subject}</p>
                <p>您可以隨時登入系統查看工單處理進度。</p>
                <a href="{ticket_url}" class="button" style="background-color: #28a745 !important; color: white !important; text-decoration: none;">查看工單</a>
            </div>
            <div class="footer">
                <p>此郵件由 AMI 支援系統自動發送。</p>
            </div>
        </div>
    </body>
    </html>
    """

    send_email(ticket.user_email, user_subject, user_html_body)


def send_ticket_reply_email(ticket, comment):
    """
    Send email notification when someone replies to a ticket

    Args:
        ticket: SupportTicket object
        comment: TicketComment object
    """
    # Don't send email for internal comments
    if comment.is_internal:
        return

    ticket_url = get_ticket_url(ticket)

    # Determine recipient based on who commented
    # If support staff commented, notify the user
    # If user commented, notify support staff
    from app.base.models import User
    commenter = User.query.get(comment.author_id)
    is_support_staff = commenter and commenter.user_role and any(role in commenter.user_role for role in ['admin', 'manager', 'accountant'])

    if is_support_staff:
        # Send to ticket creator
        user_subject = f"[工單回覆] {ticket.ticket_number} - 您的問題已有新回覆"
        user_greeting = f"親愛的 {ticket.user_email}"
        
        user_html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #17a2b8; color: white; padding: 15px; border-radius: 5px; }}
                .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
                .reply-box {{
                    background-color: white;
                    padding: 15px;
                    margin: 15px 0;
                    border-left: 4px solid #17a2b8;
                    border-radius: 3px;
                }}
                .button {{
                    display: inline-block;
                    padding: 10px 20px;
                    background-color: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 15px;
                }}
                .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
                .meta {{ color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>工單有新回覆</h2>
                </div>
                <div class="content">
                    <p>{user_greeting}：</p>
                    <p>工單 <strong>{ticket.ticket_number}</strong> 有新的回覆。</p>
                    <p><strong>主旨：</strong>{ticket.subject}</p>

                    <div class="reply-box">
                        <div class="meta">
                            <strong>{comment.author_name}</strong> 於 {format_taiwan_time(comment.created_at)} 回覆：
                        </div>
                        <div style="margin-top: 10px;">
                            {comment.content.replace(chr(10), '<br>')}
                        </div>
                    </div>

                    <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看完整工單</a>
                </div>
                <div class="footer">
                    <p>此郵件由 AMI 支援系統自動發送。</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send to user
        send_email(ticket.user_email, user_subject, user_html_body)
        
        # Also send to support team
        support_subject = f"[工單回覆] {ticket.ticket_number} - 支援團隊已回覆"
        support_greeting = "親愛的支援團隊"
        
        support_html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #17a2b8; color: white; padding: 15px; border-radius: 5px; }}
                .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
                .info-row {{ margin: 10px 0; }}
                .label {{ font-weight: bold; color: #555; }}
                .value {{ color: #333; }}
                .reply-box {{
                    background-color: white;
                    padding: 15px;
                    margin: 15px 0;
                    border-left: 4px solid #17a2b8;
                    border-radius: 3px;
                }}
                .button {{
                    display: inline-block;
                    padding: 10px 20px;
                    background-color: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 15px;
                }}
                .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
                .meta {{ color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>工單有新回覆</h2>
                </div>
                <div class="content">
                    <p>{support_greeting}：</p>
                    <p>工單 <strong>{ticket.ticket_number}</strong> 有新的回覆。</p>
                    
                    <div class="info-row">
                        <span class="label">主旨：</span>
                        <span class="value">{ticket.subject}</span>
                    </div>

                    <div class="info-row">
                        <span class="label">建立者：</span>
                        <span class="value">{ticket.user_email}</span>
                    </div>

                    <div class="reply-box">
                        <div class="meta">
                            <strong>{comment.author_name}</strong> 於 {format_taiwan_time(comment.created_at)} 回覆：
                        </div>
                        <div style="margin-top: 10px;">
                            {comment.content.replace(chr(10), '<br>')}
                        </div>
                    </div>

                    <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看完整工單</a>
                </div>
                <div class="footer">
                    <p>此郵件由 AMI 支援系統自動發送。</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send to support team
        support_emails = get_support_emails(ticket.company_id, ticket.office_id)
        send_email(support_emails, support_subject, support_html_body)
        
    else:
        # Send to support team (multiple recipients)
        to_emails = get_support_emails(ticket.company_id, ticket.office_id)
        subject = f"[工單更新] {ticket.ticket_number} - 使用者已回覆"
        greeting = "親愛的支援團隊"

        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #17a2b8; color: white; padding: 15px; border-radius: 5px; }}
                .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
                .reply-box {{
                    background-color: white;
                    padding: 15px;
                    margin: 15px 0;
                    border-left: 4px solid #17a2b8;
                    border-radius: 3px;
                }}
                .button {{
                    display: inline-block;
                    padding: 10px 20px;
                    background-color: #007bff;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin-top: 15px;
                }}
                .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
                .meta {{ color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>工單有新回覆</h2>
                </div>
                <div class="content">
                    <p>{greeting}：</p>
                    <p>工單 <strong>{ticket.ticket_number}</strong> 有新的回覆。</p>
                    <p><strong>主旨：</strong>{ticket.subject}</p>

                    <div class="reply-box">
                        <div class="meta">
                            <strong>{comment.author_name}</strong> 於 {format_taiwan_time(comment.created_at)} 回覆：
                        </div>
                        <div style="margin-top: 10px;">
                            {comment.content.replace(chr(10), '<br>')}
                        </div>
                    </div>

                    <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看完整工單</a>
                </div>
                <div class="footer">
                    <p>此郵件由 AMI 支援系統自動發送。</p>
                </div>
            </div>
        </body>
        </html>
        """

        send_email(to_emails, subject, html_body)

    # Also send notification to project PM if assigned
    if hasattr(ticket, 'project_pm') and ticket.project_pm:
        from app.base.models import User
        project_pm_user = User.query.get(ticket.project_pm)
        
        if project_pm_user and project_pm_user.email:
            # Don't send duplicate email if the project PM is the one who commented
            if not (commenter and commenter.id == project_pm_user.id):
                pm_subject = f"[工單回覆] {ticket.ticket_number} - 提交給您的工單有新回覆"
                pm_greeting = f"親愛的 {project_pm_user.username or project_pm_user.email}"
                
                pm_html_body = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background-color: #6f42c1; color: white; padding: 15px; border-radius: 5px; }}
                        .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
                        .reply-box {{
                            background-color: white;
                            padding: 15px;
                            margin: 15px 0;
                            border-left: 4px solid #6f42c1;
                            border-radius: 3px;
                        }}
                        .button {{
                            display: inline-block;
                            padding: 10px 20px;
                            background-color: #6f42c1;
                            color: white;
                            text-decoration: none;
                            border-radius: 5px;
                            margin-top: 15px;
                        }}
                        .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
                        .meta {{ color: #666; font-size: 14px; }}
                        .info-row {{ margin: 10px 0; }}
                        .label {{ font-weight: bold; color: #555; }}
                        .value {{ color: #333; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h2>📋 提交工單有新回覆</h2>
                        </div>
                        <div class="content">
                            <p>{pm_greeting}：</p>
                            <p>提交給您的工單 <strong>{ticket.ticket_number}</strong> 有新的回覆。</p>
                            
                            <div class="info-row">
                                <span class="label">主旨：</span>
                                <span class="value">{ticket.subject}</span>
                            </div>

                            <div class="info-row">
                                <span class="label">建立者：</span>
                                <span class="value">{ticket.user_email}</span>
                            </div>

                            <div class="reply-box">
                                <div class="meta">
                                    <strong>{comment.author_name}</strong> 於 {format_taiwan_time(comment.created_at)} 回覆：
                                </div>
                                <div style="margin-top: 10px;">
                                    {comment.content.replace(chr(10), '<br>')}
                                </div>
                            </div>

                            <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看完整工單</a>
                        </div>
                        <div class="footer">
                            <p>此郵件由 AMI 支援系統自動發送。</p>
                            <p>如有任何問題，請聯繫系統管理員。</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                
                send_email(project_pm_user.email, pm_subject, pm_html_body)


def send_ticket_status_change_email(ticket, old_status, new_status):
    """
    Send email notification when ticket status changes

    Args:
        ticket: SupportTicket object
        old_status: Previous status
        new_status: New status
    """
    ticket_url = get_ticket_url(ticket)

    # Email to user
    user_subject = f"[工單狀態變更] {ticket.ticket_number} - {get_status_display(old_status)} → {get_status_display(new_status)}"

    # Additional message based on status
    additional_message = ""
    if new_status == 'resolved':
        additional_message = "<p style='color: #28a745; font-weight: bold;'>您的問題已經解決！如果還有其他疑問，請回覆此工單。</p>"
    elif new_status == 'closed':
        additional_message = "<p>此工單已關閉。如需要重新開啟，請聯繫支援團隊。</p>"
    elif new_status == 'in_progress':
        additional_message = "<p style='color: #ffc107; font-weight: bold;'>支援團隊正在處理您的問題，請耐心等候。</p>"

    user_html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #6f42c1; color: white; padding: 15px; border-radius: 5px; }}
            .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
            .status-change {{
                background-color: white;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
                text-align: center;
                font-size: 18px;
            }}
            .button {{
                display: inline-block;
                padding: 10px 20px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 15px;
            }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>工單狀態已變更</h2>
            </div>
            <div class="content">
                <p>親愛的 {ticket.user_email}：</p>
                <p>您的工單 <strong>{ticket.ticket_number}</strong> 狀態已變更。</p>
                <p><strong>主旨：</strong>{ticket.subject}</p>

                <div class="status-change">
                    <strong>{get_status_display(old_status)}</strong>
                    →
                    <strong>{get_status_display(new_status)}</strong>
                </div>

                {additional_message}

                <p><strong>變更時間：</strong>{format_taiwan_time(datetime.utcnow())}</p>

                <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看工單詳情</a>
            </div>
            <div class="footer">
                <p>此郵件由 AMI 支援系統自動發送。</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send email to user
    send_email(ticket.user_email, user_subject, user_html_body)

    # Also send notification to support team
    support_subject = f"[工單狀態變更] {ticket.ticket_number} - {get_status_display(old_status)} → {get_status_display(new_status)}"
    
    support_html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #6f42c1; color: white; padding: 15px; border-radius: 5px; }}
            .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
            .info-row {{ margin: 10px 0; }}
            .label {{ font-weight: bold; color: #555; }}
            .value {{ color: #333; }}
            .status-change {{
                background-color: white;
                padding: 15px;
                margin: 15px 0;
                border-radius: 5px;
                text-align: center;
                font-size: 18px;
            }}
            .button {{
                display: inline-block;
                padding: 10px 20px;
                background-color: #007bff;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 15px;
            }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>工單狀態已變更</h2>
            </div>
            <div class="content">
                <p>親愛的支援團隊：</p>
                <p>工單 <strong>{ticket.ticket_number}</strong> 的狀態已變更。</p>

                <div class="info-row">
                    <span class="label">工單編號：</span>
                    <span class="value">{ticket.ticket_number}</span>
                </div>

                <div class="info-row">
                    <span class="label">主旨：</span>
                    <span class="value">{ticket.subject}</span>
                </div>

                <div class="info-row">
                    <span class="label">建立者：</span>
                    <span class="value">{ticket.user_email}</span>
                </div>

                <div class="status-change">
                    <strong>{get_status_display(old_status)}</strong>
                    →
                    <strong>{get_status_display(new_status)}</strong>
                </div>

                <p><strong>變更時間：</strong>{format_taiwan_time(datetime.utcnow())}</p>

                <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看工單詳情</a>
            </div>
            <div class="footer">
                <p>此郵件由 AMI 支援系統自動發送。</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send email to support team
    support_emails = get_support_emails(ticket.company_id, ticket.office_id)
    send_email(support_emails, support_subject, support_html_body)


# Helper functions for display names
def get_category_display(category):
    """Return human-readable category name"""
    category_map = {
        'system_error': '系統錯誤',
        'feature_request': '功能請求',
        'data_issue': '資料問題',
        'other': '其他'
    }
    return category_map.get(category, category)


def get_status_display(status):
    """Return human-readable status name"""
    status_map = {
        'new': '新建',
        'in_progress': '處理中',
        'resolved': '已解決',
        'closed': '已關閉'
    }
    return status_map.get(status, status)


def get_priority_display(priority):
    """Return human-readable priority name"""
    priority_map = {
        'low': '低',
        'medium': '中',
        'high': '高',
        'urgent': '緊急'
    }
    return priority_map.get(priority, priority)


def send_ticket_assignment_email(ticket, assigned_user):
    """
    Send email notification when a ticket is assigned to someone

    Args:
        ticket: SupportTicket object
        assigned_user: User object who was assigned to the ticket
    """
    if not assigned_user or not assigned_user.email:
        return

    ticket_url = get_ticket_url(ticket)

    subject = f"[工單指派] {ticket.ticket_number} - 新工單已指派給您"

    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #ff9800; color: white; padding: 15px; border-radius: 5px; }}
            .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
            .info-row {{ margin: 10px 0; }}
            .label {{ font-weight: bold; color: #555; }}
            .value {{ color: #333; }}
            .button {{
                display: inline-block;
                padding: 10px 20px;
                background-color: #ff9800;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 15px;
            }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
            .priority-urgent {{ color: #000; font-weight: bold; }}
            .priority-high {{ color: #dc3545; font-weight: bold; }}
            .priority-medium {{ color: #ffc107; font-weight: bold; }}
            .priority-low {{ color: #28a745; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>📋 工單已指派給您</h2>
            </div>
            <div class="content">
                <p>親愛的 {assigned_user.username or assigned_user.email}：</p>
                <p>以下工單已被指派給您處理，請盡快查看並回應。</p>

                <div class="info-row">
                    <span class="label">工單編號：</span>
                    <span class="value">{ticket.ticket_number}</span>
                </div>

                <div class="info-row">
                    <span class="label">主旨：</span>
                    <span class="value">{ticket.subject}</span>
                </div>

                <div class="info-row">
                    <span class="label">類型：</span>
                    <span class="value">{get_category_display(ticket.category)}</span>
                </div>

                <div class="info-row">
                    <span class="label">優先級：</span>
                    <span class="value priority-{ticket.priority}">{get_priority_display(ticket.priority)}</span>
                </div>

                <div class="info-row">
                    <span class="label">狀態：</span>
                    <span class="value">{get_status_display(ticket.status)}</span>
                </div>

                <div class="info-row">
                    <span class="label">建立者：</span>
                    <span class="value">{ticket.user_email}</span>
                </div>

                <div class="info-row">
                    <span class="label">建立時間：</span>
                    <span class="value">{format_taiwan_time(ticket.created_at)}</span>
                </div>

                <div class="info-row">
                    <span class="label">問題描述：</span>
                    <div class="value" style="margin-top: 5px; padding: 10px; background-color: white; border-radius: 3px;">
                        {ticket.description.replace(chr(10), '<br>')}
                    </div>
                </div>

                <a href="{ticket_url}" class="button">查看並處理工單</a>
            </div>
            <div class="footer">
                <p>此郵件由 AMI 支援系統自動發送。</p>
                <p>如有任何問題，請聯繫系統管理員。</p>
            </div>
        </div>
    </body>
    </html>
    """

    send_email(assigned_user.email, subject, html_body)


def send_ticket_project_pm_assignment_email(ticket, project_pm_user):
    """
    Send email notification when a ticket is assigned to a project PM

    Args:
        ticket: SupportTicket object
        project_pm_user: User object who was assigned as project PM to the ticket
    """
    if not project_pm_user or not project_pm_user.email:
        return

    ticket_url = get_ticket_url(ticket)

    subject = f"[工單提交 Deloitte] {ticket.ticket_number} - 新工單已提交給您"

    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #6f42c1; color: white; padding: 15px; border-radius: 5px; }}
            .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
            .info-row {{ margin: 10px 0; }}
            .label {{ font-weight: bold; color: #555; }}
            .value {{ color: #333; }}
            .button {{
                display: inline-block;
                padding: 10px 20px;
                background-color: #6f42c1;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 15px;
            }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
            .priority-urgent {{ color: #000; font-weight: bold; }}
            .priority-high {{ color: #dc3545; font-weight: bold; }}
            .priority-medium {{ color: #ffc107; font-weight: bold; }}
            .priority-low {{ color: #28a745; font-weight: bold; }}
            .highlight {{ background-color: #e7e3ff; padding: 10px; border-radius: 5px; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>📋 工單已提交給您</h2>
            </div>
            <div class="content">
                <p>親愛的 {project_pm_user.username or project_pm_user.email}：</p>
                <p>以下工單已提交給您處理，請盡快查看並回應。</p>

                <div class="info-row">
                    <span class="label">工單編號：</span>
                    <span class="value">{ticket.ticket_number}</span>
                </div>

                <div class="info-row">
                    <span class="label">主旨：</span>
                    <span class="value">{ticket.subject}</span>
                </div>

                <div class="info-row">
                    <span class="label">類型：</span>
                    <span class="value">{get_category_display(ticket.category)}</span>
                </div>

                <div class="info-row">
                    <span class="label">優先級：</span>
                    <span class="value priority-{ticket.priority}">{get_priority_display(ticket.priority)}</span>
                </div>

                <div class="info-row">
                    <span class="label">狀態：</span>
                    <span class="value">{get_status_display(ticket.status)}</span>
                </div>

                <div class="info-row">
                    <span class="label">建立者：</span>
                    <span class="value">{ticket.user_email}</span>
                </div>

                <div class="info-row">
                    <span class="label">建立時間：</span>
                    <span class="value">{format_taiwan_time(ticket.created_at)}</span>
                </div>

                <div class="info-row">
                    <span class="label">問題描述：</span>
                    <div class="value" style="margin-top: 5px; padding: 10px; background-color: white; border-radius: 3px;">
                        {ticket.description.replace(chr(10), '<br>')}
                    </div>
                </div>

                <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看工單詳情</a>
            </div>
            <div class="footer">
                <p>此郵件由 AMI 支援系統自動發送。</p>
                <p>如有任何問題，請聯繫系統管理員。</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send email to project PM
    send_email(project_pm_user.email, subject, html_body)

    # Also send notification to support team
    support_subject = f"[工單提交 Deloitte] {ticket.ticket_number} - 工單已提交給 {project_pm_user.username or project_pm_user.email}"
    
    support_html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #6f42c1; color: white; padding: 15px; border-radius: 5px; }}
            .content {{ background-color: #f8f9fa; padding: 20px; margin-top: 20px; border-radius: 5px; }}
            .info-row {{ margin: 10px 0; }}
            .label {{ font-weight: bold; color: #555; }}
            .value {{ color: #333; }}
            .button {{
                display: inline-block;
                padding: 10px 20px;
                background-color: #6f42c1;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin-top: 15px;
            }}
            .footer {{ margin-top: 20px; font-size: 12px; color: #777; }}
            .priority-urgent {{ color: #000; font-weight: bold; }}
            .priority-high {{ color: #dc3545; font-weight: bold; }}
            .priority-medium {{ color: #ffc107; font-weight: bold; }}
            .priority-low {{ color: #28a745; font-weight: bold; }}
            .highlight {{ background-color: #e7e3ff; padding: 10px; border-radius: 5px; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>📋 工單已提交給 Deloitte</h2>
            </div>
            <div class="content">
                <p>親愛的支援團隊：</p>
                <p>工單 <strong>{ticket.ticket_number}</strong> 已提交給 Deloitte 專案負責窗口處理。</p>

                <div class="info-row">
                    <span class="label">工單編號：</span>
                    <span class="value">{ticket.ticket_number}</span>
                </div>

                <div class="info-row">
                    <span class="label">主旨：</span>
                    <span class="value">{ticket.subject}</span>
                </div>

                <div class="info-row">
                    <span class="label">類型：</span>
                    <span class="value">{get_category_display(ticket.category)}</span>
                </div>

                <div class="info-row">
                    <span class="label">優先級：</span>
                    <span class="value priority-{ticket.priority}">{get_priority_display(ticket.priority)}</span>
                </div>

                <div class="info-row">
                    <span class="label">狀態：</span>
                    <span class="value">{get_status_display(ticket.status)}</span>
                </div>

                <div class="info-row">
                    <span class="label">建立者：</span>
                    <span class="value">{ticket.user_email}</span>
                </div>

                <div class="info-row">
                    <span class="label">提交給：</span>
                    <span class="value">{project_pm_user.email}</span>
                </div>

                <div class="info-row">
                    <span class="label">建立時間：</span>
                    <span class="value">{format_taiwan_time(ticket.created_at)}</span>
                </div>

                <div class="info-row">
                    <span class="label">問題描述：</span>
                    <div class="value" style="margin-top: 5px; padding: 10px; background-color: white; border-radius: 3px;">
                        {ticket.description.replace(chr(10), '<br>')}
                    </div>
                </div>

                <a href="{ticket_url}" class="button" style="color: white !important; text-decoration: none;">查看工單詳情</a>
            </div>
            <div class="footer">
                <p>此郵件由 AMI 支援系統自動發送。</p>
                <p>如有任何問題，請聯繫系統管理員。</p>
            </div>
        </div>
    </body>
    </html>
    """

    # Send email to support team
    support_emails = get_support_emails(ticket.company_id, ticket.office_id)
    send_email(support_emails, support_subject, support_html_body)
