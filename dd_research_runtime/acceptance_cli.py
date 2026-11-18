"""Read acceptance status or prepare an unapproved public-source case. No approval flags."""
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from .checkpoints import _ReadOnlySource
from .persistent_ingestion import PersistentEvidenceStore
from .review_ledger import ReviewLedger
from .acceptance import case_status


def inspect_acceptance(database,report_id):
    source=_ReadOnlySource(database)
    store=object.__new__(PersistentEvidenceStore);store.ledger=object.__new__(ReviewLedger)
    with closing(source._connect()) as db:
        db.execute('BEGIN');state,revision,_,_=store._verify_integrity(db)
        result=case_status(state,report_id,db=db);result['state_revision']=revision
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    inspect=commands.add_parser('inspect');inspect.add_argument('database');inspect.add_argument('report_id')
    prepare=commands.add_parser('prepare-public');prepare.add_argument('destination')
    args=parser.parse_args(argv)
    try:
        if args.command=='inspect':result=inspect_acceptance(args.database,args.report_id)
        else:
            from .public_case import prepare_public_case
            result=prepare_public_case(args.destination)
        print(json.dumps(result,indent=2));return 0
    except (OSError,ValueError,KeyError,sqlite3.Error) as exc:
        print(json.dumps(dict(ok=False,error=str(exc))),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
