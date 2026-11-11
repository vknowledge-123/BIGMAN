"""Bounded HTTP ingress. Broker feeds and execution workers do not pass here."""
import asyncio
from collections import OrderedDict
import hashlib
import json
import logging
import threading
import time

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool
from . import access

from .access import transport


class RequestLimits:
    """Bounded token buckets; use proxy/WAF controls for distributed floods."""
    def __init__(self):
        self.lock = threading.Lock()
        self.buckets = OrderedDict()
        self.last_notice = {}

    def notice(self, status):
        now=time.monotonic()
        with self.lock:
            if now-self.last_notice.get(status, float('-inf'))<60:
                return
            self.last_notice[status]=now
        # Bounded messages, never request bodies, URLs, cookies or credentials.
        logging.getLogger('scanner.security').warning('HTTP protection rejected a request: status=%s', status)

    def take(self, key, rate, burst):
        now = time.monotonic()
        key = hashlib.sha256(key.encode()).digest()
        with self.lock:
            while self.buckets and next(iter(self.buckets.values()))[1] < now-120:
                self.buckets.popitem(last=False)
            if key not in self.buckets and len(self.buckets) >= 4096:
                return False
            tokens, last = self.buckets.pop(key, (burst, now))
            tokens = min(burst, tokens + max(0, now-last)*rate)
            allowed = tokens >= 1
            self.buckets[key] = (tokens-1 if allowed else tokens, now)
            return allowed


limits = RequestLimits()


def authorize_upload(request):
    # Reject large anonymous bodies before buffering/parsing an upload.
    access.require_admin(request, access.require_user(request))



class SecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.readers = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            await send({'type':'websocket.close','code':1008})
            return
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)
        request = Request(scope)

        async def secured_send(message):
            if message['type']=='http.response.start':
                headers = [(k,v) for k,v in message.get('headers',[]) if k.lower() not in
                           (b'cache-control',b'permissions-policy',b'x-content-type-options',b'x-frame-options',b'referrer-policy',b'content-security-policy',b'strict-transport-security')]
                headers += [(b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff'),
                            (b'x-frame-options',b'DENY'),(b'referrer-policy',b'same-origin'),
                            (b'permissions-policy',b'camera=(), microphone=(), geolocation=(), payment=()'),
                            (b'content-security-policy',b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]
                if scope.get('scheme')=='https':
                    headers.append((b'strict-transport-security',b'max-age=31536000'))
                message = {**message,'headers':headers}
            await send(message)

        async def reject(status, message):
            limits.notice(status)
            headers={'Retry-After':'60'} if status in (429,503) else None
            await JSONResponse({'detail':message},status_code=status,headers=headers)(scope,receive,secured_send)

        # Check authority on every route, including static files and API discovery.
        try:
            if len(request.headers.getlist('host')) != 1:
                return await reject(400,'Invalid host header.')
            transport(request)
        except HTTPException as exc:
            return await reject(exc.status_code,exc.detail)
        except (ValueError,UnicodeError):
            return await reject(400,'Invalid request authority.')
        if len(scope.get('query_string',b''))>4096 or len(scope.get('raw_path',b''))>2048:
            return await reject(414,'Request URL is too long.')
        if sum(len(k)+len(v) for k,v in scope.get('headers',[]))>16384:
            return await reject(431,'Request headers are too large.')
        if request.method not in ('GET','HEAD','POST','OPTIONS'):
            return await reject(405,'Method not allowed.')
        ip = (scope.get('client') or ('unknown',0))[0]
        if not limits.take('global',300,600) or not limits.take('ip:'+ip,10,120):
            return await reject(429,'Too many requests. Please wait before retrying.')
        if request.method=='POST' and request.url.path.startswith('/api/auth/'):
            if not limits.take('auth:'+ip,1,12):
                return await reject(429,'Too many sign-in requests. Please try again later.')
        # No request decompression or multipart parsing is needed by this app.
        if request.headers.get('content-encoding','identity').lower()!='identity':
            return await reject(415,'Compressed request bodies are not supported.')
        declared=request.headers.getlist('content-length')
        if len(declared)>1 or (declared and request.headers.get('transfer-encoding')):
            return await reject(400,'Ambiguous request framing.')
        try:
            length=int(declared[0]) if declared else 0
            if length<0: raise ValueError()
        except ValueError:
            return await reject(400,'Invalid content length.')
        cap = 16*1024 if request.url.path.startswith('/api/auth/') else 256*1024
        if request.url.path in ('/api/preopen/preview','/api/preopen/apply'):
            try:
                await run_in_threadpool(authorize_upload,request)
            except HTTPException as exc:
                return await reject(exc.status_code,exc.detail)
            cap=13*1024*1024  # Existing 2 MiB CSV, including JSON \uXXXX expansion.
        if length>cap:
            return await reject(413,'Request body is too large.')
        if request.method in ('GET','HEAD','OPTIONS'):
            if length or request.headers.get('transfer-encoding'):
                return await reject(400,'This method does not accept a request body.')
            return await self.app(scope,receive,secured_send)
        if length and request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':
            return await reject(415,'Use an application/json request body.')
        if self.readers>=16:
            return await reject(503,'Server is busy. Please retry shortly.')
        self.readers+=1
        body=bytearray()
        try:
            async def read():
                while True:
                    message=await receive()
                    if message['type']=='http.disconnect':
                        return False
                    body.extend(message.get('body',b''))
                    if len(body)>cap:
                        return 'large'
                    if not message.get('more_body',False):
                        return True
            outcome=await asyncio.wait_for(read(),timeout=10)
        except asyncio.TimeoutError:
            return await reject(408,'Request body timed out.')
        finally:
            self.readers-=1
        if outcome is False:
            return
        if outcome=='large':
            return await reject(413,'Request body is too large.')
        if declared and len(body)!=length:
            return await reject(400,'Content length does not match request body.')
        if body:
            if request.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':
                return await reject(415,'Use an application/json request body.')
            try:
                value=json.loads(body)
                stack=[(value,0)]
                while stack:
                    item,depth=stack.pop()
                    if depth>32: raise ValueError()
                    if isinstance(item,dict): stack.extend((v,depth+1) for v in item.values())
                    elif isinstance(item,list): stack.extend((v,depth+1) for v in item)
            except (ValueError,RecursionError,UnicodeError):
                return await reject(400,'Invalid or excessively nested JSON.')
        replayed=False
        async def replay():
            nonlocal replayed
            if not replayed:
                replayed=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,replay,secured_send)
