#!/usr/bin/env python3
"""Cross-platform entry point for conversion, analysis and dataset releases."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
STAGES = ('sources', 'normalized', 'tiles', 'audit', 'types', 'stats', 'report', 'all')


def run(command, cwd=ROOT):
    return subprocess.call([str(x) for x in command], cwd=cwd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', nargs='?', choices=('env', 'build', 'up', 'down', 'logs', 'restart', 'convert', 'analyze', 'maps', 'export-dataset', 'download-sources', 'test', *STAGES))
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv[:1])
    remaining = argv[1:]
    command = args.command
    if command is None:
        choices = ['up', 'all', 'maps', 'test', 'down', 'export-dataset']
        print('\n'.join(f'{i+1}. {name}' for i, name in enumerate(choices)))
        selection = input('Operation [1]: ').strip() or '1'
        if not selection.isdigit() or not 1 <= int(selection) <= len(choices):
            parser.error('Select a listed number')
        command = choices[int(selection)-1]
        if command == 'export-dataset':
            source = input('Analysis directory [docs/data]: ').strip() or 'docs/data'
            output = input('Dataset export directory [releases/dataset-v1]: ').strip() or 'releases/dataset-v1'
            remaining = ['--input', source, '--output', output]
    if command == 'env':
        if remaining[:1] == ['sync']:
            remaining.pop(0)
        return run(['uv', 'sync', '--frozen', *remaining])
    compose = ['docker', 'compose', '-f', ROOT/'app/docker-compose.yml']
    if command == 'build':
        return run([*compose, 'build', *remaining])
    if command in ('up', 'down', 'logs', 'restart'):
        return run([*compose, command, *(['-d', '--build'] if command == 'up' else []), *remaining])
    if command == 'convert':
        return run([*compose, 'run', '--rm', 'api', 'src.convert', *remaining])
    python = ROOT/'.venv'/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    python = python if python.exists() else Path(sys.executable)
    if command in STAGES or command == 'analyze':
        stage = command if command in STAGES else (remaining.pop(0) if remaining and not remaining[0].startswith('-') else 'all')
        return run([python, '-u', '-m', 'analysis.pipeline', stage, *remaining])
    if command == 'maps':
        return run([python, '-m', 'analysis.map_figures', *remaining])
    if command in ('export-dataset', 'download-sources'):
        return run([python, '-m', 'analysis.release', command, *remaining])
    if command == 'test':
        checks = ([python, '-m', 'unittest', 'discover', '-s', 'analysis/tests', '-v', *remaining],
                  [python, '-m', 'pytest', 'app/converter/tests', *remaining])
        for check in checks:
            result = run(check)
            if result:
                return result
        return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
