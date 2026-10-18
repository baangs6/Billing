"""Dry-run by default. Apply only after review and verified backup of the selected database."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from bson import json_util
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mongo_store import MongoBackend,load_configuration

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--backup',type=Path)
    args=parser.parse_args();backend=MongoBackend(*load_configuration())
    try:
        print('Additive purchasing/account schemas. No existing tenant documents are rewritten.')
        if not args.apply: print('Dry run only. Apply requires --backup and explicit operator authorization.');sys.exit(0)
        if not args.backup: raise ValueError('Supply a verified backup path.')
        content=args.backup.read_bytes();data=json_util.loads(content)
        manifest=json.loads(args.backup.with_suffix('.verified.json').read_text(encoding='utf-8'))
        if manifest['sha256']!=hashlib.sha256(content).hexdigest() or data['database']!=backend.name: raise ValueError('Backup verification or database identity mismatch.')
        backend.ensure_trade_storage()
        print('Additive storage prepared. Existing financial records and permissions were not rewritten.')
    finally: backend.client.close()
