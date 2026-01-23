"""
Support Ticket System Module
"""
from flask import Blueprint

support_blueprint = Blueprint(
    'support',
    __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/support'
)

from app.support import routes
