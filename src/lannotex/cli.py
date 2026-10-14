"""Lannotex command-line interface.

Running bare ``lannotex`` launches the desktop application. Subcommands
(``export``, ``analyze``, ``new``) run headlessly for automation and CI and
do not import Qt.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import threading

from . import __version__

EXPORT_FORMATS = ['Labelme JSON', 'YOLO boxes', 'COCO JSON', 'Classification CSV', 'Native JSONL']


def _progress(value, message):
    print(f'[{value:3d}%] {message}', file=sys.stderr)


def _cancel():
    return threading.Event()


def build_parser():
    parser = argparse.ArgumentParser(
        prog='lannotex',
        description='Fast, offline-first image annotation for classifications, boxes, and polygons.',
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    sub = parser.add_subparsers(dest='command')

    gui = sub.add_parser('gui', help='launch the desktop application (this is the default)')
    gui.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)

    exp = sub.add_parser('export', help='export a project headlessly to a local directory')
    exp.add_argument('project', help='project folder that contains project.sqlite3')
    exp.add_argument('destination', help='directory that receives the exported files')
    exp.add_argument('--format', choices=EXPORT_FORMATS, default='Labelme JSON', help='export format (default: %(default)s)')

    ana = sub.add_parser('analyze', help='validate a project and print a health report as JSON')
    ana.add_argument('project', help='project folder that contains project.sqlite3')

    proj = sub.add_parser('new', help='create a new empty project folder')
    proj.add_argument('folder', help='folder to initialize as a project')

    host = sub.add_parser('host', help='serve a team project from this computer')
    host.add_argument('project')
    host.add_argument('--bind', default='127.0.0.1', help='use 0.0.0.0 to accept LAN connections')
    host.add_argument('--port', type=int, default=8765)
    host.add_argument('--cert', help='TLS certificate PEM')
    host.add_argument('--key', help='TLS private key PEM')
    invite = sub.add_parser('invite', help='create a reviewer token on a project host')
    invite.add_argument('project')
    invite.add_argument('name')

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command in (None, 'gui'):
        from .app import main as gui_main
        return gui_main()
    if args.command == 'export':
        from .exporters import export_project
        result = export_project(args.project, args.destination, args.format, _cancel(), _progress)
        print(f"Exported {result['included']} images to {result['path']}")
        if result['errors']:
            print('Errors:', file=sys.stderr)
            print('\n'.join(result['errors']), file=sys.stderr)
        return 0
    if args.command == 'analyze':
        from .exporters import analyze
        result = analyze(args.project, _cancel(), _progress)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == 'new':
        from .storage import Project
        Project(args.folder, create=True).close()
        print(f'Created project at {Path(args.folder).resolve()}')
        return 0
    if args.command == 'invite':
        from .team import add_member
        print(add_member(args.project, args.name))
        return 0
    if args.command == 'host':
        from .team import TeamServer
        server = TeamServer(args.project,args.bind,args.port,args.cert,args.key)
        print(f"Team host listening on {args.bind}:{server.server_address[1]}. Ctrl+C stops hosting.")
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
        return 0
    return 0
