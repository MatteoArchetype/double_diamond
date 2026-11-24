"""Run every test module in its own process and report where it stops.

One module that blocks would otherwise take the whole job with it: pytest
prints failure tracebacks only when the session ends, so a hang at 36% hides
every result gathered before it. Each module now gets its own process, its own
time budget and its own log, so a hang is one line in the summary instead of a
cancelled job.

Usage: python ci/suite_by_file.py [--cap SECONDS] [--lines N] [module ...]
"""
import argparse
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILURE_LINES = 60


def kill_tree(process):
    """Stop the module and anything it started; children can hold the log open."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def run_module(module, cap, log):
    """Run one test module, returning 'passed', 'failed' or 'hung'."""
    keyword = {}
    if os.name == 'nt':
        keyword['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        keyword['start_new_session'] = True
    with open(log, 'wb') as sink:
        process = subprocess.Popen([sys.executable, '-m', 'pytest', module, '-p', 'no:cacheprovider'],
                                   cwd=ROOT, stdout=sink, stderr=subprocess.STDOUT, **keyword)
        deadline = time.monotonic() + cap
        while process.poll() is None:
            if time.monotonic() > deadline:
                kill_tree(process)
                return 'hung'
            time.sleep(0.5)
    return 'passed' if process.returncode == 0 else 'failed'


def tail(path, count):
    text = Path(path).read_text(errors='replace').strip().splitlines()
    return text[-count:] if text else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cap', type=int, default=900, help='seconds one test module may take')
    parser.add_argument('--lines', type=int, default=FAILURE_LINES, help='log lines printed per problem')
    parser.add_argument('modules', nargs='*', help='test modules; defaults to every test_*.py')
    options = parser.parse_args()
    modules = options.modules or sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'tests').glob('test_*.py'))
    reports = {}
    workdir = Path(tempfile.mkdtemp(prefix='suite-by-file-'))
    for module in modules:
        log = workdir / (Path(module).stem + '.log')
        started = time.monotonic()
        outcome = run_module(module, options.cap, log)
        reports[module] = (outcome, log)
        print(f'{outcome:6} {module} ({time.monotonic() - started:.0f}s)', flush=True)
    problems = {m: (o, log) for m, (o, log) in reports.items() if o != 'passed'}
    for module, (outcome, log) in problems.items():
        print(f'\n----- {outcome} {module}', flush=True)
        print('\n'.join(tail(log, options.lines)), flush=True)
    hung = [m for m, (o, _) in reports.items() if o == 'hung']
    failed = [m for m, (o, _) in reports.items() if o == 'failed']
    print(f'\n{len(reports) - len(problems)} of {len(reports)} modules passed', flush=True)
    if hung:
        print('hung: ' + ', '.join(hung), flush=True)
    if failed:
        print('failed: ' + ', '.join(failed), flush=True)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
