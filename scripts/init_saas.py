"""Initialize SaaS collections, preserve existing workspaces, create private setup link."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mongo_store import MongoBackend, load_configuration
from saas import initialize_saas, bootstrap_link

if __name__=='__main__':
    backend=None
    try:
        backend=MongoBackend(*load_configuration()); initialize_saas(backend)
        path=bootstrap_link(backend)
        print('SaaS initialized. Existing workspaces preserved.')
        if path: print('Private owner setup link saved in:',path)
        else: print('Owner account already exists. Sign in at http://127.0.0.1:5001/login')
    except Exception as error:
        print('Initialization failed. Error type:',type(error).__name__); sys.exit(1)
    finally:
        if backend: backend.client.close()
