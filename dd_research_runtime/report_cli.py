"""Export an existing, verified saved draft without source mutation/migration."""
import argparse
import json
import sqlite3
import sys
from .reporting import export_report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database');parser.add_argument('report_id');parser.add_argument('destination')
    parser.add_argument('--format',choices=['markdown','json'],default='markdown')
    parser.add_argument('--allow-stale',action='store_true')
    args=parser.parse_args(argv)
    try:
        result=export_report(args.database,args.report_id,args.destination,format=args.format,allow_stale=args.allow_stale)
        print(json.dumps(result));return 0
    except (OSError,ValueError,KeyError,sqlite3.Error) as exc:
        print(json.dumps(dict(ok=False,error=str(exc))),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
