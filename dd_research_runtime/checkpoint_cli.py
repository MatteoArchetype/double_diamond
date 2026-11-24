"""Explicit local checkpoint commands; no source fetching or review approval.

Run with: python -m dd_research_runtime.checkpoint_cli --help
Successful output is JSON on stdout; operational errors are JSON on stderr.
"""
import argparse
import json
import sqlite3
import sys

from .checkpoints import (create_checkpoint_from_path, inspect_checkpoint,
                          restore_checkpoint, verify_database)


def _write(value,stream,pretty=False):
    print(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2 if pretty else None,
                     allow_nan=False),file=stream,flush=True)


class _Parser(argparse.ArgumentParser):
    def error(self,message):
        _write(dict(ok=False,error=dict(code='usage',message=message)),sys.stderr)
        raise SystemExit(2)


def _parser():
    parser=_Parser(description='Verify and checkpoint Double Diamond research databases. Existing destinations are never overwritten.')
    commands=parser.add_subparsers(dest='command',required=True)
    create=commands.add_parser('create',help='Create a verified checkpoint from an existing database (no migration).')
    create.add_argument('database');create.add_argument('destination')
    inspect=commands.add_parser('inspect',help='Verify a checkpoint and report its manifest.')
    inspect.add_argument('checkpoint')
    restore=commands.add_parser('restore',help='Restore a verified checkpoint to a new database path.')
    restore.add_argument('checkpoint');restore.add_argument('destination')
    restore_case=commands.add_parser('restore-case',help='Restore a verified case into an existing browser workspace, without the browser transfer limit.')
    restore_case.add_argument('checkpoint');restore_case.add_argument('workspace')
    verify=commands.add_parser('verify',help='Verify an existing database without migration or repair.')
    verify.add_argument('database')
    for command in (create,inspect,restore,restore_case,verify):
        command.add_argument('--pretty',action='store_true',help='Indent JSON output.')
    return parser


def main(argv=None):
    args=_parser().parse_args(argv)
    try:
        if args.command == 'create':
            result=dict(manifest=create_checkpoint_from_path(args.database,args.destination))
        elif args.command == 'inspect':
            result=dict(manifest=inspect_checkpoint(args.checkpoint))
        elif args.command == 'restore':
            result=dict(manifest=restore_checkpoint(args.checkpoint,args.destination))
        elif args.command == 'restore-case':
            from .interface_backups import restore_checkpoint_to_workspace
            result=restore_checkpoint_to_workspace(args.checkpoint,args.workspace)
        else:
            result=dict(summary=verify_database(args.database))
        _write(dict(ok=True,command=args.command,**result),sys.stdout,args.pretty)
        return 0
    except KeyboardInterrupt:
        code,message,status='interrupted','Operation interrupted; a destination already published may be complete. Inspect it before retrying.',130
    except FileExistsError as exc:
        code,message,status='destination_exists',str(exc),1
    except FileNotFoundError as exc:
        code,message,status='not_found',str(exc),1
    except PermissionError as exc:
        code,message,status='permission_denied',str(exc),1
    except (ValueError,sqlite3.DatabaseError,RuntimeError,KeyError,TypeError,AttributeError) as exc:
        code,message,status='invalid_data',str(exc),1
    except OSError as exc:
        code,message,status='io_error',str(exc),1
    _write(dict(ok=False,command=args.command,error=dict(code=code,message=message)),sys.stderr)
    return status


if __name__ == '__main__':
    sys.exit(main())
