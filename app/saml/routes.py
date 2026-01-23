# app/saml/routes.py
# SAML SSO 路由

from flask import Blueprint, redirect, request, session, url_for, current_app, make_response, jsonify
from flask_login import login_user
from urllib.parse import urlparse
import json
import os

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from app.models import db, User

saml_bp = Blueprint('saml', __name__, url_prefix='/saml')


def init_saml_auth(req):
    """初始化 SAML Auth 物件"""
    saml_path = os.path.join(current_app.root_path, 'saml')

    # 讀取設定檔
    settings_file = os.path.join(saml_path, 'settings.json')
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            settings = json.load(f)

        # 動態更新 SP 的 URL（根據當前 host）
        host = req.get('http_host', 'localhost:5002')
        scheme = 'https' if req.get('https') == 'on' else 'http'
        base_url = f"{scheme}://{host}"

        settings['sp']['entityId'] = f"{base_url}/saml/metadata"
        settings['sp']['assertionConsumerService']['url'] = f"{base_url}/saml/acs/"
        settings['sp']['singleLogoutService']['url'] = f"{base_url}/saml/sls/"

        auth = OneLogin_Saml2_Auth(req, settings)
        return auth

    # 預設使用 custom_base_path
    auth = OneLogin_Saml2_Auth(req, custom_base_path=saml_path)
    return auth


def prepare_flask_request(request):
    """準備 Flask request 給 SAML library"""
    url_data = urlparse(request.url)
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
    return {
        'https': 'on' if scheme == 'https' else 'off',
        'http_host': request.host,
        'server_port': url_data.port,
        'script_name': request.path,
        'get_data': request.args.copy(),
        'post_data': request.form.copy(),
        'query_string': request.query_string
    }


@saml_bp.route('/')
def sso():
    """SAML SSO 入口點"""
    print('SAML SSO initiated')
    req = prepare_flask_request(request)
    auth = init_saml_auth(req)

    # 取得 return URL
    return_to = request.args.get('return_to', '')
    if return_to and '/saml/' not in return_to:
        print(f'SSO with return_to: {return_to}')
        return redirect(auth.login(return_to=return_to))
    else:
        print('SSO without return_to')
        return redirect(auth.login())


@saml_bp.route('/acs/', methods=['POST'])
def acs():
    """SAML Assertion Consumer Service - 處理 IdP 回應"""
    print('SAML ACS initiated')
    req = prepare_flask_request(request)
    auth = init_saml_auth(req)

    auth.process_response()
    errors = auth.get_errors()

    if len(errors) > 0:
        print('SAML ACS errors:', errors)
        print('SAML Last Error Reason:', auth.get_last_error_reason())
        error_msg = f"SSO 錯誤: {', '.join(errors)}"
        if auth.get_last_error_reason():
            error_msg += f" | 原因: {auth.get_last_error_reason()}"
        return error_msg, 400

    if not auth.is_authenticated():
        return 'SSO 驗證失敗', 401

    # 取得用戶資訊
    attributes = auth.get_attributes()
    email = attributes.get('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name', [None])[0]
    display_name = attributes.get('http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname', [None])[0]

    if not email:
        print("Error: No email found in SAML attributes.")
        return 'SSO 錯誤: 無法取得 Email', 400

    print(f'SAML User Email: {email}')

    # 儲存 SAML session 資訊
    session['samlUserdata'] = attributes
    session['samlNameId'] = auth.get_nameid()
    session['samlSessionIndex'] = auth.get_session_index()
    session['display_name'] = display_name if display_name else email.split('@')[0]

    # 查找或建立用戶
    user = User.query.filter_by(email=email, is_active=True).first()

    if not user:
        # 建立新用戶
        username = email.split('@')[0]
        # 確保 username 唯一
        base_username = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1

        user = User(
            email=email,
            username=username,
            user_role='reporter',
            locale='zh_TW',
            is_active=True
        )
        # 設置一個隨機密碼（SSO 用戶不需要密碼登入）
        import secrets
        user.set_password(secrets.token_urlsafe(32))

        db.session.add(user)
        db.session.commit()
        print(f"Created new SSO user: {email}")

    # 設置 session 過期時間
    from datetime import datetime, timedelta
    session.permanent = True
    expires_at = datetime.utcnow() + timedelta(hours=8)
    session['expires_at'] = expires_at.timestamp()

    # 登入用戶
    login_user(user, remember=True)

    # 處理 RelayState 重導向
    relay_state = request.form.get('RelayState', '')
    self_url = OneLogin_Saml2_Utils.get_self_url(req)

    if relay_state and self_url != relay_state:
        parsed_relay = urlparse(relay_state)
        if '/saml/' not in parsed_relay.path:
            print(f'Redirecting to RelayState: {relay_state}')
            return redirect(auth.redirect_to(relay_state))

    # 預設重導向到 dashboard
    print('Redirecting to dashboard')
    return redirect('/dashboard')


@saml_bp.route('/metadata')
def metadata():
    """SAML SP Metadata"""
    print('SAML Metadata endpoint called')
    req = prepare_flask_request(request)
    auth = init_saml_auth(req)
    settings = auth.get_settings()
    metadata = settings.get_sp_metadata()
    errors = settings.validate_metadata(metadata)

    if len(errors) == 0:
        resp = make_response(metadata, 200)
        resp.headers['Content-Type'] = 'text/xml'
    else:
        print('SAML Metadata errors:', errors)
        resp = make_response(', '.join(errors), 500)
    return resp


@saml_bp.route('/debug')
def debug():
    """SAML Debug 端點"""
    req = prepare_flask_request(request)
    auth = init_saml_auth(req)
    settings = auth.get_settings()

    debug_info = {
        'sp_entity_id': settings.get_sp_data().get('entityId'),
        'sp_acs_url': settings.get_sp_data().get('assertionConsumerService', {}).get('url'),
        'idp_entity_id': settings.get_idp_data().get('entityId'),
        'idp_sso_url': settings.get_idp_data().get('singleSignOnService', {}).get('url'),
        'current_host': request.host,
        'current_scheme': request.scheme,
        'current_url': request.url
    }

    return f"<pre>{json.dumps(debug_info, indent=2)}</pre>"
