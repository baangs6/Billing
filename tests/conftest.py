"""Isolate WSGI import-time storage setup before any application module is imported."""
import os
import secrets
import sys
import pytest

BOOTSTRAP_DATABASE='ledger_test_bootstrap_'+secrets.token_hex(8)
os.environ['MONGODB_DATABASE']=BOOTSTRAP_DATABASE


def pytest_sessionfinish(session,exitstatus):
    if 'app' not in sys.modules and 'admin_app' not in sys.modules and exitstatus!=2: return
    from mongo_store import MongoBackend,load_configuration
    uri,_=load_configuration()
    backend=MongoBackend(uri,BOOTSTRAP_DATABASE)
    try:
        assert backend.name==BOOTSTRAP_DATABASE and backend.name.startswith('ledger_test_bootstrap_')
        backend.client.drop_database(backend.name)
    finally: backend.client.close()


@pytest.fixture(scope='session')
def shared_mongo_backend():
    # Imported fixture aliases must share one backend across all test modules.
    from test_app import mongo_backend
    yield from mongo_backend.__wrapped__(None)
