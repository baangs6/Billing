"""Explicit password confirmation for permanent data resets."""
import time
from werkzeug.security import check_password_hash


def confirm_reset(backend, user, fields, phrase, kind):
    if fields.get('confirmation','') != phrase:
        raise ValueError('Type '+phrase+' exactly to confirm permanent deletion.')
    key='factory-reset:'+kind+':'+str(user['id'])
    attempt=backend.login_attempt(key)
    if attempt and attempt['count']>=5 and time.time()-attempt['started']<900:
        raise ValueError('Too many password attempts. Try again in 15 minutes.')
    if not check_password_hash(user['password_hash'],fields.get('password','')):
        backend.failed_login(key)
        raise ValueError('Current password is incorrect. Nothing was deleted.')
    backend.reset_login_attempt(key)
