"""Run the company proposal UI using an isolated Atlas test database."""
import sys
import threading
import secrets
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_app import mongo_backend,workspace
from test_proposals import proposal_data
from waitress import create_server

generator=mongo_backend.__wrapped__(); backend=next(generator); server=None
try:
    client,post,_=workspace.__wrapped__(backend)
    post('/proposals/new',proposal_data())
    client.application.config.update(SECRET_KEY=secrets.token_hex(32),SESSION_COOKIE_NAME='ledger_proposal_qa')
    server=create_server(client.application,host='127.0.0.1',port=5002)
    threading.Thread(target=server.run,daemon=True).start()
    print('Isolated proposal QA ready at http://127.0.0.1:5002/login',flush=True)
    input('Press Enter to close and clean the test database.\n')
finally:
    if server:
        server.close(); server.task_dispatcher.shutdown()
    try: next(generator)
    except StopIteration: pass
    print('Proposal QA database cleaned.',flush=True)
