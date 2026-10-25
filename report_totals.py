"""Shared report dates and explicit, exact totals (never sum IDs or unit prices)."""
from datetime import date
from decimal import Decimal


def report_period(args,today,kind=''):
    start=args.get('from') or (today if kind=='Daily sales' else today[:7]+'-01' if kind=='Monthly sales' else today[:4]+'-01-01')
    end=args.get('to') or (start if kind=='Daily sales' else today)
    try: date.fromisoformat(start);date.fromisoformat(end)
    except ValueError: raise ValueError('Choose valid report dates.') from None
    if start>end: raise ValueError('From date must be on or before To date.')
    return start,end


def total_row(kind,headers,rows):
    columns={
        'Sales':(3,4,5),'Daily sales':(3,4,5),'Monthly sales':(3,4,5),'GST sales':(3,4,5),'Non-GST sales':(3,4,5),'Outstanding':(3,4,5),
        'Collections':(3,),'Product sales':(3,),'Stock movement':(), 'Inventory':(), 'Low stock':(),
        'Purchases':(3,4,5,6,7),'Receivables':(1,2,3,4,5),'Payables':(1,2,3,4,5),
        'Sales credit notes':(3,4,5,6),'Purchase debit notes':(3,4,5,6),'HSN sales':(1,2),'GST summary':(1,2,3,4),'Stock valuation':(4,),
    }[kind]
    result=['']*len(headers);result[0]='Net sales - purchases' if kind=='GST summary' else 'Total ('+str(len(rows))+(' record)' if len(rows)==1 else ' records)')
    for column in columns:
        value=sum((Decimal(str(row[column]))*(-1 if kind=='GST summary' and row[0]=='Purchases' else 1) for row in rows),Decimal(0))
        result[column]=format(value,'.2f')
    # Different units remain separate instead of producing a misleading combined quantity.
    if kind in ('Inventory','Low stock','Product sales','Stock valuation'):
        quantity,unit=(1,2) if kind=='Product sales' else (2,5) if kind=='Stock valuation' else (3,5)
        totals={}
        for row in rows: totals[row[unit]]=totals.get(row[unit],Decimal(0))+Decimal(str(row[quantity]))
        result[quantity]='; '.join(format(value,'f')+' '+str(key) for key,value in sorted(totals.items())) or '0'
    if kind=='Stock movement':
        totals={}
        for row in rows: totals[row[4]]=totals.get(row[4],Decimal(0))+Decimal(str(row[2]))
        result[2]='; '.join(format(value,'f')+' '+str(key) for key,value in sorted(totals.items())) or '0'
    return result
