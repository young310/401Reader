"""
Support Ticket System Data Models
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app import db


class SupportTicket(db.Model):
    """
    Main support ticket model
    """
    __tablename__ = 'support_ticket'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_number = Column(String(50), unique=True, nullable=False, index=True)
    subject = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50))  # system_error, feature_request, data_issue, other
    priority = Column(String(20))  # low, medium, high, urgent
    status = Column(String(20), default='new')  # new, in_progress, resolved, closed

    # User relations
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    assigned_to = Column(Integer, ForeignKey('users.id'))
    project_pm = Column(Integer, ForeignKey('users.id'))
    
    # Company and Office relations
    company_id = Column(Integer)
    office_id = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime)
    closed_at = Column(DateTime)

    # Cached user info (to avoid JOINs)
    user_email = Column(String(255))
    user_name = Column(String(255))

    # Relationships
    comments = relationship('TicketComment', backref='ticket', cascade='all, delete-orphan', lazy='dynamic')
    attachments = relationship('TicketAttachment', backref='ticket', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<SupportTicket {self.ticket_number}: {self.subject}>'

    def serialize(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'ticket_number': self.ticket_number,
            'subject': self.subject,
            'description': self.description,
            'category': self.category,
            'priority': self.priority,
            'status': self.status,
            'created_by': self.created_by,
            'assigned_to': self.assigned_to,
            'project_pm': self.project_pm,
            'company_id': self.company_id,
            'office_id': self.office_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'user_email': self.user_email,
            'user_name': self.user_name,
            'comments_count': self.comments.count(),
            'attachments_count': self.attachments.count()
        }

    @staticmethod
    def generate_ticket_number():
        """Generate unique ticket number in format TKT-YYYY-NNNN with retry logic"""
        from datetime import datetime
        from sqlalchemy import func
        import time
        
        year = datetime.utcnow().year
        
        # Simple approach: get max sequence number without locking
        # The uniqueness will be enforced by the database constraint
        # and handled by retry logic in the route
        try:
            # Get the maximum sequence number for this year
            result = db.session.query(
                func.max(
                    func.cast(
                        func.substring(SupportTicket.ticket_number, 10, 4),
                        Integer
                    )
                )
            ).filter(
                SupportTicket.ticket_number.like(f'TKT-{year}-%')
            ).scalar()
            
            new_seq = (result or 0) + 1
            
        except Exception as e:
            # Fallback to counting approach
            last_ticket = db.session.query(SupportTicket).filter(
                SupportTicket.ticket_number.like(f'TKT-{year}-%')
            ).order_by(SupportTicket.id.desc()).first()
            
            if last_ticket:
                try:
                    last_seq = int(last_ticket.ticket_number.split('-')[-1])
                    new_seq = last_seq + 1
                except (ValueError, IndexError):
                    new_seq = 1
            else:
                new_seq = 1
        
        return f'TKT-{year}-{new_seq:04d}'


class TicketComment(db.Model):
    """
    Comments/replies on support tickets
    """
    __tablename__ = 'ticket_comment'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey('support_ticket.id'), nullable=False, index=True)
    content = Column(Text, nullable=False)

    # Author info
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    author_email = Column(String(255))
    author_name = Column(String(255))

    # Internal notes are not visible to ticket creator
    is_internal = Column(Boolean, default=False)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    attachments = relationship('TicketAttachment', backref='comment', cascade='all, delete-orphan', lazy='dynamic')

    def __repr__(self):
        return f'<TicketComment {self.id} on Ticket {self.ticket_id}>'

    def serialize(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'content': self.content,
            'author_id': self.author_id,
            'author_email': self.author_email,
            'author_name': self.author_name,
            'is_internal': self.is_internal,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class TicketAttachment(db.Model):
    """
    File attachments for support tickets
    """
    __tablename__ = 'ticket_attachment'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey('support_ticket.id'), nullable=False, index=True)
    comment_id = Column(Integer, ForeignKey('ticket_comment.id'), nullable=True, index=True)  # Link to comment if uploaded with reply

    # File info
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)  # in bytes
    file_type = Column(String(100))  # MIME type

    # Upload info
    uploaded_by = Column(Integer, ForeignKey('users.id'), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<TicketAttachment {self.file_name} for Ticket {self.ticket_id}>'

    def serialize(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'ticket_id': self.ticket_id,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'uploaded_by': self.uploaded_by,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None
        }

    @property
    def file_size_human(self):
        """Return human-readable file size"""
        if not self.file_size:
            return "0 B"

        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class SupportEmailConfig(db.Model):
    """
    Support email configuration by domain
    Allows multiple support email addresses based on domain name
    """
    __tablename__ = 'support_email_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    support_emails = Column(Text, nullable=False)  # Comma-separated email addresses
    roles = Column(Text)  # Comma-separated roles (admin,reporter,manager,accountant)
    description = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey('users.id'))

    def __repr__(self):
        return f'<SupportEmailConfig {self.domain}: {self.support_emails}>'

    def serialize(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'domain': self.domain,
            'support_emails': self.support_emails,
            'support_emails_list': self.get_email_list(),
            'roles': self.roles,
            'roles_list': self.get_roles_list(),
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def get_email_list(self):
        """Return list of email addresses"""
        if not self.support_emails:
            return []
        return [email.strip() for email in self.support_emails.split(',') if email.strip()]

    def get_roles_list(self):
        """Return list of roles"""
        if not self.roles:
            return []
        return [role.strip() for role in self.roles.split(',') if role.strip()]

    @staticmethod
    def get_support_emails_for_domain(domain, company_id=None, office_id=None):
        """
        Get support email addresses for a specific domain

        Args:
            domain: Domain name (e.g., 'yageo.com', 'localhost')
            company_id: Company ID to get role-based emails
            office_id: Office ID to get role-based emails

        Returns:
            list: List of support email addresses
        """
        config = SupportEmailConfig.query.filter_by(domain=domain, is_active=True).first()
        
        # Get base support emails
        support_emails = []
        if config:
            support_emails = config.get_email_list()
        else:
            # Return default if no config found
            default_config = SupportEmailConfig.query.filter_by(domain='default', is_active=True).first()
            if default_config:
                support_emails = default_config.get_email_list()
            else:
                # Fallback to hardcoded default
                support_emails = ['extract.ami@gmail.com']

        # Get role-based emails if config has roles and we have company/office info
        role_emails = []
        if config and config.roles and company_id and office_id:
            role_emails = SupportEmailConfig.get_role_based_emails(
                config.get_roles_list(), company_id, office_id
            )

        # Combine and deduplicate emails
        all_emails = list(set(support_emails + role_emails))
        return all_emails if all_emails else ['extract.ami@gmail.com']

    @staticmethod
    def get_role_based_emails(roles, company_id, office_id):
        """
        Get email addresses of users with specific roles in the same company/office
        Note: Simplified for standalone 401Reader - returns empty list as User model
        does not have company_id/office_id fields

        Args:
            roles: List of roles to search for
            company_id: Company ID
            office_id: Office ID

        Returns:
            list: List of email addresses
        """
        # 401Reader User model doesn't have company_id/office_id fields
        # Return empty list - role-based email not supported in standalone version
        return []

    @staticmethod
    def get_current_domain():
        """
        Get current request domain
        """
        from flask import request
        if request:
            # Extract domain from host
            host = request.host.split(':')[0]  # Remove port
            return host
        return 'default'

    @staticmethod
    def get_display_domain():
        """
        Get domain for display purposes based on current request
        Returns full URL for specific subdomains, or 'localhost' for localhost
        """
        from flask import request
        if request:
            host = request.host.split(':')[0]  # Remove port
            
            # Check if it's localhost
            if host.startswith('localhost') or host == '127.0.0.1':
                return 'localhost'
            
            # For Azure websites or other specific domains, return full URL
            if 'azurewebsites.net' in host:
                protocol = 'https' if request.is_secure else 'http'
                return f"{protocol}://{host}"
            
            # For other domains, return the host
            return host
        return 'default'
