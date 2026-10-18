"""Closed periods reject historical financial writes without duplicating carry-forwards."""
from datetime import date

FINANCIAL={'invoices','payments','purchases','trade_payments','sales_returns','trade_returns','finance_entries','account_transfers','bank_accounts'}


def validate_period(cutoff, name, values, previous=None):
    if not cutoff: return
    if name=='finance_entries' and values.get('kind')=='OPENING':
        raise ValueError('Opening balances are locked after financial-year closing. Use dated income or expense entries in an open period.')
    if name in FINANCIAL:
        for row in (previous or {},values):
            if row.get('date') and row['date']<=cutoff:
                raise ValueError('This financial period is closed through '+cutoff+'. Use a date in an open period; historical entries cannot be edited or cancelled.')
    if name in ('customers','suppliers'):
        before=(previous or {}).get('data',{}).get('opening_balance',0)
        after=values.get('data',{}).get('opening_balance',values.get('data.opening_balance',before))
        if before!=after: raise ValueError('Opening balances are locked after financial-year closing. Use dated transactions in an open period.')


def close_date(value, today, previous=''):
    end=date.fromisoformat(value)
    if end.month!=3 or end.day!=31 or end>=date.fromisoformat(today) or end.year<2000:
        raise ValueError('Choose a completed financial year ending on 31 March.')
    if previous and value<=previous: raise ValueError('That financial year is already closed.')
    return value
