"""Validation shared by the billing form and saved invoice snapshots."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


def due_date(day, value, credit_days=0):
    start = date.fromisoformat(day)
    due = date.fromisoformat(value) if value else start + timedelta(days=credit_days)
    if due < start:
        raise ValueError('Due date cannot be before the invoice date.')
    return due.isoformat()


def manual_rounding(value):
    try:
        amount = Decimal(value or '0')
        if not amount.is_finite() or abs(amount) > 1 or amount != amount.quantize(Decimal('0.01')):
            raise ValueError('Manual round off must be between -1.00 and 1.00 with at most two decimal places.')
        return int(amount * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Enter a valid manual round-off amount.')


def customer_balances(store, exclude=None):
    balances = {row['id']: row.get('data', {}).get('opening_balance', 0) for row in store.find('customers', projection={'id':1,'data.opening_balance':1})}
    invoices = store.find('invoices', {'status': 'FINAL', 'deleted': {'$ne': True}, 'id': {'$ne': exclude}}, projection={'id':1,'customer_id':1,'total':1})
    parties = {row['id']: row['customer_id'] for row in invoices}
    for row in invoices:
        balances[row['customer_id']] = balances.get(row['customer_id'], 0) + row['total']
    for row in store.find('payments', {'invoice_id': {'$in': list(parties)}}, projection={'invoice_id':1,'amount':1}):
        ident = parties[row['invoice_id']]
        balances[ident] = balances.get(ident, 0) - row['amount']
    for row in store.find('sales_returns', {'invoice_id': {'$in': list(parties)}}, projection={'invoice_id':1,'total':1}):
        ident = parties[row['invoice_id']]
        balances[ident] = balances.get(ident, 0) - row['total']
    for row in store.find('trade_payments', {'customer_id': {'$exists': True}}, projection={'customer_id':1,'opening_effect':1,'kind':1,'invoice_id':1,'amount':1}):
        ident = row['customer_id']
        if 'opening_effect' in row:
            balances[ident] = balances.get(ident, 0) + row['opening_effect']
        elif row.get('kind') == 'CUSTOMER_REFUND' and row.get('invoice_id') in parties:
            balances[ident] = balances.get(ident, 0) + row['amount']
    return balances
