"""Shared owner identities with tenant-scoped memberships and independent subscriptions."""
import secrets
from flask import abort,flash,g,redirect,render_template,request,session,url_for
from werkzeug.security import generate_password_hash
from mongo_store import TENANT_COLLECTIONS
from saas import seed_roles,Platform,stamp
from factory_reset import confirm_reset,preserve_shared_identities
from fiscal_period import close_date


def install_business_accounts(app,db,settings,audit,today,defaults):
    def principal():
        user=g.access['user']
        root=db().backend.database.users.find_one({'id':user.get('identity_id',user['id']),'active':True},session=db().mongo_session)
        if not root or root.get('identity_id'): abort(403)
        return root

    def memberships(root):
        database=db().backend.database;ms=db().mongo_session;result=[]
        for user in database.users.find({'active':True,'$or':[{'id':root['id']},{'identity_id':root['id']}]},session=ms):
            role=database.roles.find_one({'id':user.get('role_id'),'business_id':user['business_id']},session=ms)
            company=database.businesses.find_one({'id':user['business_id']},session=ms)
            if role and company: result.append((user,company))
        return result

    def administrator():
        role=db().one('roles',{'id':g.access['user'].get('role_id')})
        if not role or not role.get('protected') or role['name']!='COMPANY_ADMIN': abort(403)

    @app.route('/businesses',methods=['GET','POST'])
    def businesses_page():
        root=principal();backend=db().backend;database=backend.database;ms=db().mongo_session
        if request.method=='POST':
            if request.form.get('action')=='switch':
                target=next((user for user,company in memberships(root) if str(company['id'])==request.form.get('business')),None)
                if not target: abort(403)
                audit('switch_business','company',target['business_id'])
                session.clear();session.update(user=target['id'],business=target['business_id'],version=target.get('session_version',0),identity_id=root['id'],identity_version=root.get('session_version',0),csrf=secrets.token_hex(32));session.permanent=True
                return redirect(url_for('dashboard'))
            if request.form.get('action')!='create': raise ValueError('Choose a business action.')
            administrator()
            token=request.form.get('submission','')
            if len(token)!=64: raise ValueError('Refresh before creating a business.')
            if database.businesses.find_one({'identity_root':root['id'],'creation_submission':token},session=ms):
                return redirect(url_for('businesses_page'))
            name=request.form.get('name','').strip();state=request.form.get('state','').strip()
            if not name or len(name)>150 or not state: raise ValueError('Enter the new business name and state.')
            policy=database.platform_settings.find_one({'_id':'policy','registration_open':True},session=ms)
            plan=database.plans.find_one({'id':int(request.form.get('plan_id') or 0),'active':True},session=ms)
            if not policy or not plan: raise ValueError('New business registration is closed or the selected plan is unavailable.')
            store=backend.scope();store.mongo_session=ms;store.write_allowed=True
            bid,uid=store.register_business(name,'linked-'+secrets.token_hex(16)+'@internal.invalid',generate_password_hash(secrets.token_urlsafe(32)),defaults|dict(name=name,state=state,email=root['email']))
            fresh=backend.scope(bid);fresh.mongo_session=ms;fresh.write_allowed=True;roles=seed_roles(fresh)
            fresh.update('businesses',{},dict(status='PENDING',identity_root=root['id'],creation_submission=token,owner_name=root.get('name',''),contact_email=root['email'],phone='',state=state,requested_plan_id=plan['id']))
            fresh.update('users',{'id':uid},dict(identity_id=root['id'],name=root.get('name','Owner'),active=True,role_id=roles['COMPANY_ADMIN']['id'],session_version=0))
            audit('create_linked_business','company',bid)
            flash('New business created. It needs its own subscription and software-owner approval.')
            return redirect(url_for('businesses_page'))
        rows=[dict(id=company['id'],name=company['name'],status=company.get('status','PENDING')) for user,company in memberships(root)]
        role=db().one('roles',{'id':g.access['user'].get('role_id')})
        return render_template('businesses.html',title='Your businesses',rows=rows,plans=list(database.plans.find({'active':True},{'_id':0},session=ms)),can_create=bool(role and role.get('protected')),selected_state=settings()['state'],submission=secrets.token_hex(32))

    @app.post('/business/close-year')
    def close_financial_year():
        administrator();root=principal();values=settings();previous=values.get('closed_through','')
        if request.form.get('expected_closed_through','')!=previous: raise ValueError('The closed period changed. Refresh Settings.')
        end=close_date(request.form.get('end',''),today(),previous)
        if request.form.get('confirmation')!='CLOSE FINANCIAL YEAR': raise ValueError('Type CLOSE FINANCIAL YEAR exactly to lock the period.')
        confirm_reset(db().backend,root,request.form,'CLOSE FINANCIAL YEAR','company')
        values['closed_through']=end
        db().update('business_settings',{},dict(data=values));audit('close_financial_year','company',session['business'],'Locked through '+end+'; balances and stock continue from existing records.')
        flash('Financial entries through '+end+' are locked. Balances and stock continue without copying or deleting records.')
        return redirect(url_for('settings_page'))

    @app.post('/business/delete')
    def delete_business():
        administrator();root=principal();backend=db().backend;database=backend.database;ms=db().mongo_session;bid=session['business']
        confirm_reset(backend,root,request.form,'DELETE BUSINESS','company')
        database.platform_meta.update_one({'_id':'write_lock'},{'$inc':{'version':1}},session=ms)
        user_ids=[row['id'] for row in database.users.find({'business_id':bid},{'id':1},session=ms)]
        preserve_shared_identities(database,ms,bid)
        for name in TENANT_COLLECTIONS: database[name].delete_many({'business_id':bid},session=ms)
        database.businesses.delete_one({'id':bid},session=ms)
        database.password_resets.delete_many({'kind':'company','$or':[{'business_id':bid},{'user_id':{'$in':user_ids}}]},session=ms)
        Platform(backend).insert('admin_audit',dict(action='company_self_delete',business_id=bid,actor_id=session['user'],reason='Password and typed confirmation verified; selected company permanently deleted.'),ms)
        session.clear();flash('Business permanently deleted. If other businesses remain, your shared login still accesses them.')
        return redirect(url_for('login'))

    return {'businesses_page':(None,None),'close_financial_year':('settings.manage','settings.manage'),'delete_business':('settings.manage','settings.manage')}
