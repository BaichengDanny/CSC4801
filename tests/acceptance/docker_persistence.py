"""Recreate an explicitly named local QA container and verify its volume.

The container, image, volume and port must all match the existing configuration.
This script uses only synthetic accounts. --reset-after is an explicit opt-in to
restore demo data after verifying persistence; never target a user database.
"""
import argparse
import json
import subprocess
import sys
import time

from http_smoke import Session

SNAPSHOT_CODE = """
import json, os, sqlite3, sys
database = sqlite3.connect(os.environ['DATABASE'])
counts = {table: database.execute('SELECT count(*) FROM ' + table).fetchone()[0]
          for table in ('users', 'jobs', 'applications', 'slots', 'bookings', 'schema_migrations')}
user = database.execute('SELECT id, display_name FROM users WHERE email = ?', (sys.argv[1],)).fetchone()
print(json.dumps({'counts': counts, 'sentinel': user}, sort_keys=True))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--volume', required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--wsl-distro', default='Ubuntu-22.04')
    parser.add_argument('--reset-after', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use a local QA port from 1024 through 65535')
    prefix = (['wsl', '-d', args.wsl_distro, '-u', 'root', '--exec', 'docker']
              if sys.platform == 'win32' else ['docker'])

    def docker(*arguments):
        result = subprocess.run(prefix + list(arguments), text=True, capture_output=True,
                                check=True, timeout=45)
        return result.stdout.strip()

    details = json.loads(docker('inspect', args.container))[0]
    assert details['Config']['Image'] == args.image, 'Image must match before recreating'
    assert details['Config']['Env'].count('DATABASE=/app/data/recruiting.sqlite3') == 1
    assert any(m.get('Name') == args.volume and m['Destination'] == '/app/data'
               for m in details['Mounts']), 'Volume must match before recreating'
    assert details['HostConfig']['PortBindings']['8080/tcp'] == [
        {'HostIp':'127.0.0.1','HostPort':str(args.port)}], 'Local port must match'
    email = 'qa-persistence-' + str(time.time_ns()) + '@example.test'
    Session('http://127.0.0.1:' + str(args.port)).post('/api/auth/register', {
        'email': email, 'password': 'DemoPass123!', 'role': 'Candidate', 'name': 'QA Persistence Sentinel',
    }, 201)
    before = json.loads(docker('exec', args.container, 'python', '-c', SNAPSHOT_CODE, email))
    assert before['sentinel'][1] == 'QA Persistence Sentinel'
    docker('stop', args.container)
    docker('rm', args.container)
    docker('run', '-d', '--name', args.container, '-p', '127.0.0.1:' + str(args.port) + ':8080',
           '-v', args.volume + ':/app/data', args.image)
    health_code = "import urllib.request; print(urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8080/health',timeout=2).read())"
    for attempt in range(15):
        try:
            docker('exec', args.container, 'python', '-c', health_code)
            break
        except subprocess.CalledProcessError:
            if attempt == 14:
                raise
            time.sleep(1)
    after = json.loads(docker('exec', args.container, 'python', '-c', SNAPSHOT_CODE, email))
    assert before == after, (before, after)
    print(json.dumps({'container':args.container,'before':before,'after':after,
                      'persistence':'passed'}, indent=2))
    if args.reset_after:
        print(docker('exec', args.container, 'python', '-m', 'flask', '--app', 'recruiting', 'seed', '--yes'))


if __name__ == '__main__':
    main()
