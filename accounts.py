"""Named account balances derived once from source records, plus balanced transfers."""
from collections import defaultdict
from datetime import date
import secrets
from flask import abort,flash,g,redirect,render_template,request,url_for


def account_key(store,value,fallback,day):
    if not value or value.startswith('legacy:'):
        key=value or 'legacy:'+fallback
        if key not in ('legacy:Cash','legacy:Bank','legacy:Other'): raise ValueError('Choose a valid account.')
        return key
    try: ident=int(value)
    except ValueError: raise ValueError('Choose a valid account.')
    account=store.one('bank_accounts',{'id':ident})
    if not account or account.get('archived') or account['date']>day: raise ValueError('Choose an active account opened on or before the transaction date.')
    return str(ident)


def ledger_rows(store,as_of=None):
    rows=[]
    for account in store.find('bank_accounts'):
        rows.append(dict(date=account['date'],account=str(account['id']),opening=True,amount=account['opening'],title='Opening balance',source='Account opening'))
    for entry in store.find('finance_entries',{'status':'ACTIVE'},projection={'receipt':0}):
        rows.append(dict(date=entry['date'],account=entry.get('ledger_account','legacy:'+entry['account']),opening=entry['kind']=='OPENING',amount=entry['amount']*(-1 if entry['kind']=='EXPENSE' else 1),title=entry['title'],source='Finance #'+str(entry['id'])))
    for pay in store.find('payments'):
        fallback='Cash' if pay['method']=='Cash' else 'Other' if pay['method']=='Other' else 'Bank'
        rows.append(dict(date=pay['date'],account=pay.get('ledger_account','legacy:'+fallback),amount=pay['amount'],title=pay.get('reference',''),source='Invoice payment #'+str(pay['id'])))
    for pay in store.find('trade_payments'):
        fallback='Cash' if pay['method']=='Cash' else 'Other' if pay['method']=='Other' else 'Bank'
        rows.append(dict(date=pay['date'],account=pay.get('ledger_account','legacy:'+fallback),amount=pay['amount']*(1 if pay['kind'] in ('SUPPLIER_REFUND','OPENING_IN') else -1),title=pay.get('reference',''),source=pay['kind']+' #'+str(pay['id'])))
    for transfer in store.find('account_transfers'):
        for key,sign in [('from_account',-1),('to_account',1)]:
            rows.append(dict(date=transfer['date'],account=transfer[key],amount=transfer['amount']*sign,title=transfer['reference'],source='Transfer #'+str(transfer['id'])))
    dates={}
    for row in rows:
        if row.get('opening') and (as_of is None or row['date']<=as_of): dates[row['account']]=max(dates.get(row['account'],''),row['date'])
    return sorted([row for row in rows if row['date']>=dates.get(row['account'],'') and (as_of is None or row['date']<=as_of)],key=lambda r:r['date'])


def install_accounts(app,db,owned,audit,money,today):
    @app.route('/accounts',methods=['GET','POST'])
    def accounts_page():
        if request.method=='POST':
            action=request.form.get('action');token=request.form.get('submission','');day=date.fromisoformat(request.form.get('date','')).isoformat()
            if len(token)!=64: raise ValueError('Refresh before saving.')
            if action=='create':
                existing=db().one('bank_accounts',{'submission':token})
                if existing:
                    if request.accept_mimetypes.best=='application/json': return {'account':dict(id=existing['id'],name=existing['name'])}
                    return redirect(url_for('accounts_page'))
                name=request.form.get('name','').strip();kind=request.form.get('kind')
                if not name or kind not in ('Cash','Bank','Other'): raise ValueError('Enter an account name and type.')
                details={key:request.form.get(key,'').strip() for key in ('bank','account_number','ifsc','upi','holder')}
                ident=db().insert('bank_accounts',dict(name=name,kind=kind,date=day,opening=money(request.form.get('opening') or '0'),data=details,archived=False,submission=token))
                audit('create','bank_account',ident)
                if request.accept_mimetypes.best=='application/json': return {'account':dict(id=ident,name=name)},201
            elif action=='transfer':
                if db().one('account_transfers',{'submission':token}): return redirect(url_for('accounts_page'))
                source=account_key(db(),request.form.get('from_account',''),'Cash',day);target=account_key(db(),request.form.get('to_account',''),'Bank',day)
                amount=money(request.form.get('amount') or '0')
                if source==target or amount<=0: raise ValueError('Choose different accounts and a positive transfer amount.')
                daily=defaultdict(int)
                for row in ledger_rows(db()):
                    if row['account']==source: daily[row['date']]+=row['amount']
                balance=sum(value for key,value in daily.items() if key<=day);available=balance
                for key in sorted(k for k in daily if k>day): balance+=daily[key];available=min(available,balance)
                if amount>available: raise ValueError('Transfer would overdraw the source account on this or a later recorded date.')
                ident=db().insert('account_transfers',dict(date=day,from_account=source,to_account=target,amount=amount,reference=request.form.get('reference','').strip(),submission=token))
                audit('transfer','account',ident)
            else: raise ValueError('Choose a valid account action.')
            flash('Account transaction saved.');return redirect(url_for('accounts_page'))
        choices=[dict(key='legacy:'+name,name='Existing '+name) for name in ('Cash','Bank','Other')]+[dict(key=str(a['id']),name=a['name']) for a in db().find('bank_accounts')]
        end=date.fromisoformat(request.args.get('to') or today()).isoformat()
        rows=ledger_rows(db(),as_of=end);balances=defaultdict(int)
        for row in rows: balances[row['account']]+=row['amount']
        chosen=request.args.get('account','');running=0;entries=[]
        for row in rows:
            if chosen and row['account']!=chosen: continue
            running+=row['amount'];entries.append(dict(row,balance=running))
        return render_template('accounts.html',title='Cash & bank accounts',choices=choices,balances=balances,entries=entries,chosen=chosen,end=end,submission=secrets.token_hex(32))
    return {'accounts_page':('finance.view','finance.manage')}
