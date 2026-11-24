"""Inspect or export a proposed research agenda. No run, contact or approval command."""
import argparse
import json
import sqlite3
import sys
from .research_agenda import read_agenda,export_agenda


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    inspect=commands.add_parser('inspect');inspect.add_argument('database');inspect.add_argument('agenda_id')
    export=commands.add_parser('export');export.add_argument('database');export.add_argument('agenda_id');export.add_argument('destination');export.add_argument('--format',choices=['markdown','json'],default='markdown');export.add_argument('--allow-stale',action='store_true')
    args=parser.parse_args(argv)
    try:
        result=read_agenda(args.database,args.agenda_id) if args.command=='inspect' else export_agenda(args.database,args.agenda_id,args.destination,format=args.format,allow_stale=args.allow_stale)
        print(json.dumps(result,indent=2));return 0
    except (OSError,ValueError,KeyError,sqlite3.Error) as exc:
        print(json.dumps(dict(ok=False,error=str(exc))),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
