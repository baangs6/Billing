from datetime import timedelta
import pytest
from werkzeug.security import check_password_hash
from saas import digest, now
from test_app import mongo_backend, workspace

def test_recovery_unconfigured_and_links(workspace,monkeypatch):
    client,post,backend=workspace
    monkeypatch.delenv('SMTP_HOST',raising=False)
    anonymous=client.application.test_client()
    assert b'Forgot password?' in anonymous.get('/login').data
    assert b'not configured' in anonymous.get('/forgot-password').data
    assert anonymous.get('/reset-password/invalid').status_code==400
    with anonymous.session_transaction() as state: csrf=state['csrf']
    assert anonymous.post('/forgot-password',data=dict(csrf=csrf,email='owner@example.com')).status_code==503

def test_reset_atomic_replay_expiry_and_sessions(workspace):
    client,post,backend=workspace
    user=backend.database.users.find_one({'email':'owner@example.com'})
    token='test-random-reset-token'
    backend.database.password_resets.insert_one(dict(_id=digest(token),kind='company',user_id=user['id'],business_id=user['business_id'],version=user.get('session_version',0),expires_at=now()+timedelta(minutes=30)))
    anon=client.application.test_client()
    assert anon.get('/reset-password/'+token).status_code==200
    with anon.session_transaction() as state: csrf=state['csrf']
    fields=dict(csrf=csrf,password='new correct horse password',confirmation='new correct horse password')
    assert anon.post('/reset-password/'+token,data=fields).status_code==302
    changed=backend.database.users.find_one({'id':user['id']})
    assert check_password_hash(changed['password_hash'],fields['password'])
    assert changed['session_version']==user.get('session_version',0)+1
    assert anon.post('/reset-password/'+token,data=fields).status_code==400
    assert client.get('/billing').status_code==302
    backend.database.password_resets.insert_one(dict(_id=digest('expired'),kind='company',user_id=user['id'],expires_at=now()-timedelta(minutes=1)))
    assert anon.get('/reset-password/expired').status_code==400

def test_email_reset_generic_response_and_host(workspace,monkeypatch):
    import smtplib
    sent=[]
    class SMTP:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def starttls(self,**kwargs): pass
        def send_message(self,message): sent.append(message)
    monkeypatch.setattr(smtplib,'SMTP',SMTP)
    monkeypatch.setenv('SMTP_HOST','smtp.example.com');monkeypatch.setenv('SMTP_FROM','ledger@example.com');monkeypatch.setenv('PUBLIC_BASE_URL','https://ledger.example.com')
    monkeypatch.delenv('SMTP_USERNAME',raising=False)
    client=workspace[0].application.test_client(); client.get('/forgot-password')
    with client.session_transaction() as state: csrf=state['csrf']
    for email in ('owner@example.com','unknown@example.com'):
        assert client.post('/forgot-password',data=dict(csrf=csrf,email=email)).status_code==302
    assert len(sent)==1
    assert 'https://ledger.example.com/reset-password/' in sent[0].get_content()
    assert 'untrusted.example' not in sent[0].get_content()

from test_saas import owner

def test_owner_password_reset_preserves_mfa(owner):
    admin,post,backend,secret,password=owner
    user=backend.database.admin_users.find_one({'email':'admin@example.com'})
    token='owner-test-reset'
    backend.database.password_resets.insert_one(dict(_id=digest(token),kind='owner',user_id=user['id'],version=user['session_version'],expires_at=now()+timedelta(minutes=30)))
    assert admin.get('/reset-password/'+token).status_code==200
    response=post('/reset-password/'+token,dict(password='new owner secure password',confirmation='new owner secure password'))
    assert response.status_code==302
    changed=backend.database.admin_users.find_one({'id':user['id']})
    assert changed['totp_secret']==user['totp_secret']
    assert changed['recovery_hashes']==user['recovery_hashes']
    assert backend.database.admin_sessions.count_documents({})==0
    assert check_password_hash(changed['password_hash'],'new owner secure password')
