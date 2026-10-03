"""Single-use password recovery for company and owner identities."""
import os
import re
import secrets
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import urlparse
from flask import request, session, render_template, flash, redirect, url_for
from werkzeug.security import generate_password_hash
from saas import now, digest


def install_recovery(app, backend, owner=False):
    backend.database.password_resets.create_index('expires_at',expireAfterSeconds=0)
    backend.database.password_resets.create_index([('kind',1),('user_id',1)])
    collection=backend.database.admin_users if owner else backend.database.users
    kind='owner' if owner else 'company'
    base_name='ADMIN_PUBLIC_BASE_URL' if owner else 'PUBLIC_BASE_URL'
    def configured():
        base=os.environ.get(base_name,'').rstrip('/')
        parsed=urlparse(base)
        return bool(os.environ.get('SMTP_HOST') and os.environ.get('SMTP_FROM') and parsed.scheme=='https' and parsed.netloc and not parsed.username and not parsed.query and not parsed.fragment)
    def page(reset=False,valid=True):
        return render_template('recovery.html',title='Reset password' if reset else 'Forgot password',reset=reset,valid=valid,owner_recovery=owner,delivery_ready=configured())
    @app.route('/forgot-password',methods=['GET','POST'])
    def forgot_password():
        if request.method=='POST':
            if not configured():
                flash('Password recovery email is not configured yet. Please contact the service owner.','error')
                return page(),503
            email=request.form.get('email','').strip().lower()
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
                flash('Enter a valid email address.','error'); return page(),400
            key='recovery:'+kind+':'+(request.remote_addr or '')
            attempt=backend.login_attempt(key)
            if attempt and attempt['count']>=5 and __import__('time').time()-attempt['started']<900:
                flash('Too many requests. Please wait 15 minutes.','error'); return page(),429
            backend.failed_login(key)
            user=collection.find_one({'email':email,'active':True})
            if user:
                token=secrets.token_urlsafe(32); token_hash=digest(token)
                backend.database.password_resets.insert_one({'_id':token_hash,'kind':kind,'user_id':user['id'],'business_id':user.get('business_id'),'version':user.get('session_version',0),'expires_at':now()+timedelta(minutes=30)})
                message=EmailMessage(); message['Subject']='Reset your Ledger password'; message['From']=os.environ['SMTP_FROM']; message['To']=email
                link=os.environ[base_name].rstrip('/')+'/reset-password/'+token
                message.set_content('A password reset was requested for your Ledger account.\n\n'+link+'\n\nThis link expires in 30 minutes and can be used once. If you did not request it, ignore this email. Your password has not changed. Owner accounts still require an authenticator or recovery code after resetting the password.')
                try:
                    with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.environ.get('SMTP_PORT','587')),timeout=15) as smtp:
                        smtp.starttls(context=ssl.create_default_context())
                        if os.environ.get('SMTP_USERNAME'): smtp.login(os.environ['SMTP_USERNAME'],os.environ.get('SMTP_PASSWORD',''))
                        smtp.send_message(message)
                except Exception:
                    backend.database.password_resets.delete_one({'_id':token_hash})
                    app.logger.error('Password recovery email delivery failed; check SMTP configuration.')
            flash('If an active account matches this email, a reset link will be sent. Check your inbox and spam folder.','success')
            return redirect(url_for('forgot_password'))
        return page()
    @app.route('/reset-password/<token>',methods=['GET','POST'])
    def reset_password(token):
        record=backend.database.password_resets.find_one({'_id':digest(token),'kind':kind,'expires_at':{'$gt':now()}})
        if not record: return page(True,False),400
        if request.method=='POST':
            password=request.form.get('password','')
            if len(password)<(14 if owner else 12) or password!=request.form.get('confirmation',''):
                flash('Passwords must match and contain at least '+str(14 if owner else 12)+' characters.','error'); return page(True),400
            password_hash=generate_password_hash(password)
            def change(ms):
                row=backend.database.password_resets.find_one({'_id':digest(token),'kind':kind,'expires_at':{'$gt':now()}},session=ms)
                if not row: return False
                query={'id':row['user_id'],'active':True}
                if not owner: query['business_id']=row['business_id']
                user=collection.find_one(query,session=ms)
                if not user or user.get('session_version',0)!=row['version']: return False
                collection.update_one(query,{'$set':{'password_hash':password_hash},'$inc':{'session_version':1}},session=ms)
                backend.database.password_resets.delete_many({'kind':kind,'user_id':row['user_id']},session=ms)
                if owner: backend.database.admin_sessions.delete_many({'admin_id':row['user_id']},session=ms)
                return True
            with backend.client.start_session() as ms:
                changed=ms.with_transaction(change)
            if not changed: return page(True,False),400
            session.clear(); flash('Password updated. Sign in with your new password.','success')
            return redirect(url_for('login'))
        return page(True)
