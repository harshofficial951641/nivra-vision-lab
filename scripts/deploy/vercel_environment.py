"""Publish relay configuration through the existing Vercel CLI login and stdin."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def linked_project(root, expected_id):
    try: project = json.loads((root/'.vercel/project.json').read_text())
    except (OSError, ValueError): raise RuntimeError('Link the NIVRA Vercel project first.') from None
    if (not expected_id or project.get('projectId') != expected_id or
            project.get('projectName') != 'nivra' or not project.get('orgId')):
        raise RuntimeError('The linked Vercel project is not the confirmed NIVRA project.')
    return project


def cli_scope(project):
    scope = os.environ.get('NIVRA_VERCEL_SCOPE', project['orgId'])
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', scope):
        raise RuntimeError('The Vercel CLI scope is invalid.')
    return scope


def publish(upstream, secret, expected_id, root=ROOT):
    project = linked_project(root, expected_id)
    scope = cli_scope(project)
    if not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com', upstream):
        raise RuntimeError('The relay address is invalid.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,200}', secret):
        raise RuntimeError('The relay credential is invalid.')
    for key, value in [('NIVRA_UPSTREAM', upstream), ('NIVRA_RELAY_SECRET', secret)]:
        arguments = ['vercel', 'env', 'add', key, 'production', '--force', '--yes',
                     '--project', project['projectId'], '--scope', scope, '--type', 'secret']
        try:
            result = subprocess.run(arguments, input=value+'\n', text=True, cwd=root,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=False,
                env={**os.environ, 'VERCEL_CLI_USE_NATIVE_BINARY': '0'})
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('Vercel relay configuration could not be published.') from None
        if result.returncode: raise RuntimeError('Vercel relay configuration was rejected.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-id', required=True)
    args = parser.parse_args()
    try:
        state = ROOT/'service/state/public'
        runtime = json.loads((state/'runtime.json').read_text())
        publish(runtime['upstream'], (state/'relay-secret').read_text().strip(), args.project_id)
    except (OSError, ValueError, KeyError, RuntimeError):
        parser.exit(1, 'Vercel relay configuration failed. Check the linked NIVRA project and local host.\n')
    print('NIVRA production relay configuration updated; redeploy to apply.')


if __name__ == '__main__': main()
