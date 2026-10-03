"""Temporary real Atlas-backed owner UI, isolated from the live database."""
import sys
import base64
import secrets
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_app import mongo_backend,workspace
from saas import Platform,digest
from admin_app import create_admin_app
from werkzeug.security import generate_password_hash
from waitress import create_server

generator=mongo_backend.__wrapped__(); backend=next(generator); server=None
try:
    workspace.__wrapped__(backend)
    app=create_admin_app(backend); platform=Platform(backend)
    def create(ms,store):
        platform.insert('admin_users',dict(name='Platform Owner',email='qa-admin@example.com',password_hash=generate_password_hash('temporary QA owner password'),totp_secret=app.extensions['cipher'].encrypt(base64.b32encode(secrets.token_bytes(20))).decode(),last_totp_counter=0,recovery_hashes=[digest('0123456789abcdef')],active=True,session_version=0),ms)
    platform.transaction(create)
    server=create_server(app,host='127.0.0.1',port=5002)
    threading.Thread(target=server.run,daemon=True).start()
    print('Isolated admin QA ready at http://127.0.0.1:5002/login',flush=True)
    input('Press Enter to close and delete the isolated QA database.\n')
finally:
    if server:
        server.close()
        server.task_dispatcher.shutdown()
    try: next(generator)
    except StopIteration: pass
    print('QA database cleaned.',flush=True)
