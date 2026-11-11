"""Authentication endpoints and server-side role/CSRF enforcement."""
import base64
from io import BytesIO
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
import qrcode
import qrcode.image.svg

from .accounts import Accounts, AccountError, DisplaySettings

accounts = Accounts(Path(__file__).resolve().parent.parent / 'data/auth.sqlite3')
router = APIRouter()
COOKIE = 'scanner_session'


def transport(request):
    configured = os.environ.get('SCANNER_PUBLIC_ORIGIN', '').rstrip('/')
    origin = str(request.base_url).rstrip('/')
    if configured:
        parsed = urlsplit(configured)
        if parsed.scheme != 'https' or parsed.path not in ('','/') or origin != configured:
            raise HTTPException(400, 'Public access requires the configured HTTPS origin.')
    elif request.url.hostname not in ('127.0.0.1','localhost','::1'):
        raise HTTPException(400, 'Configure SCANNER_PUBLIC_ORIGIN with your HTTPS URL before remote access.')
    supplied = request.headers.get('origin')
    if supplied and supplied != origin:
        raise HTTPException(403, 'Cross-origin request rejected.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Cross-site request rejected.')


def public_write(request: Request):
    transport(request)
    if request.headers.get('x-requested-with') != 'scanner' or not request.headers.get('content-type','').startswith('application/json'):
        raise HTTPException(403, 'Use the application form to submit this request.')


def optional_user(request: Request):
    transport(request)
    return accounts.identity(request.cookies.get(COOKIE))


def require_user(request: Request):
    user = optional_user(request)
    if not user:
        raise HTTPException(401, 'Sign in with your password and authenticator.')
    return user


def csrf(request, user):
    transport(request)
    if not secrets.compare_digest(request.headers.get('x-csrf-token','').encode(), user['csrf'].encode()):
        raise HTTPException(403, 'Security token expired. Refresh and try again.')


def require_admin(request: Request, user=Depends(require_user)):
    if user['role'] != 'admin' or user['status'] != 'active':
        raise HTTPException(403, 'Administrator access required.')
    if request.method not in ('GET','HEAD','OPTIONS'):
        csrf(request,user)
    return user


def require_member(user=Depends(require_user)):
    if user['status'] != 'active':
        raise HTTPException(403, 'Your account is awaiting administrator approval.')
    return user


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=1,max_length=128)


class Signup(Login):
    name: str = Field(min_length=1,max_length=80)


class Verify(BaseModel):
    model_config = ConfigDict(extra='forbid')
    challenge: str = Field(min_length=20,max_length=100)
    code: str = Field(min_length=6,max_length=6,pattern=r'^[0-9]{6}$')


def limit(request, action, email=None):
    # Trust only the ASGI client address. Configure the proxy allowlist, never
    # read arbitrary client-supplied X-Forwarded-For here.
    ip = request.client.host if request.client else 'unknown'
    accounts.throttle(action+':ip:'+ip, 8 if action=='signup' else 40)
    accounts.throttle(action+':global', 200 if action=='signup' else 600, seconds=900 if action=='signup' else 60)
    if email:
        accounts.throttle(action+':account:'+email.strip().lower(), 10)


def enrollment(result):
    if result.get('enrollment'):
        image = qrcode.make(result['uri'], image_factory=qrcode.image.svg.SvgPathImage, border=4)
        output = BytesIO()
        image.save(output)
        result['qr'] = 'data:image/svg+xml;base64,' + base64.b64encode(output.getvalue()).decode()
    return result


@router.post('/api/auth/signup', dependencies=[Depends(public_write)])
def signup(payload: Signup, request: Request):
    limit(request,'signup')
    uid = accounts.create(payload.email,payload.password,payload.name)
    return enrollment(accounts.challenge(uid))


@router.post('/api/auth/login', dependencies=[Depends(public_write)])
def login(payload: Login, request: Request):
    limit(request,'login',payload.email)
    return enrollment(accounts.password_login(payload.email,payload.password))


@router.post('/api/auth/verify', dependencies=[Depends(public_write)])
def verify(payload: Verify, request: Request, response: Response):
    limit(request,'verify')
    session,user = accounts.verify(payload.challenge,payload.code)
    response.set_cookie(COOKIE,session,max_age=43200,httponly=True,secure=request.url.scheme=='https',samesite='strict',path='/')
    return {'user':user,'redirect':'/'}


@router.get('/api/auth/me')
def me(user=Depends(require_user)):
    return user


@router.post('/api/auth/logout')
def logout(request: Request, response: Response, user=Depends(require_user)):
    csrf(request,user)
    accounts.logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE,path='/',httponly=True,samesite='strict',secure=request.url.scheme=='https')
    return {'ok':True}


@router.get('/api/admin/users')
def users(_=Depends(require_admin)):
    return {'users':accounts.users()}


class StatusIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: str = Field(pattern=r'^(active|suspended)$')


@router.post('/api/admin/users/{uid}')
def user_status(uid: str, payload: StatusIn, user=Depends(require_admin)):
    accounts.status(uid,payload.status,user['id'])
    return {'ok':True}


@router.get('/api/display-settings')
def display_get(_=Depends(require_admin)):
    return accounts.display()


@router.post('/api/display-settings')
def display_save(payload: DisplaySettings, _=Depends(require_admin)):
    return accounts.display(payload)
