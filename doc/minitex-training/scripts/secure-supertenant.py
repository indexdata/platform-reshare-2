#!/usr/bin/python3

import argparse
import getpass
import json
import re
import sys
import urllib.error
import urllib.request
import uuid


SUPERUSER_PERMISSIONS = [
    "okapi.all",
    "perms.all",
    "login.all",
    "users.all"
]
REQUEST_TIMEOUT_SECONDS = 30

# main logic for this script goes here, functions used are defined below
def main():
    # parse arguments
    args = parse_command_line_args()
    okapi_url = args.okapi_url
    ensure_one_shot_run(okapi_url)
    password = getpass.getpass('Okapi super user password: ')

    # enable mod-permissions, mod-users, mod-login
    module_list = ['mod-permissions', 'mod-users', 'mod-login']
    module_ids = fetch_module_ids(module_list, okapi_url)
    for module in module_list:
        module_id = module_ids[module]
        print("Enabling module {}...".format(module_id))
        enable_module(module_id, okapi_url)
        print("Success")

    # Create user
    print("Creating new user: " + args.user_name)
    newuser = create_user_mod_users(args.user_name, okapi_url)
    newuser_json = json.loads(newuser)
    print("Successfully created user {} with id {}".format(args.user_name, newuser_json['id']))

    # Grant permissions to user
    print("Granting the following permissions to {}".format(args.user_name))
    for perm in SUPERUSER_PERMISSIONS:
        print(perm)
    add_permissions(newuser_json['id'], SUPERUSER_PERMISSIONS, okapi_url)

    # Create login credentials
    create_login_credentials(args.user_name, password, okapi_url)

    # Enable mod-authtoken
    mod_authtoken_id = fetch_module_ids(['mod-authtoken'], okapi_url)['mod-authtoken']
    print("Enabling module {}...".format(mod_authtoken_id))
    enable_module(mod_authtoken_id, okapi_url)

    # Log in to verify that the secured Okapi accepts the new credentials.
    print("Successfully secured Okapi, logging in...")
    payload = json.dumps({
        'username': args.user_name,
        'password': password
    }).encode('UTF-8')

    okapi_post(okapi_url + '/authn/login', payload)
    print("Successfully logged in as {}.".format(args.user_name))

# functions used in main() are defined here
def parse_command_line_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Secure a new Okapi supertenant. This is a one-shot bootstrap script; '
            'it refuses to run if the supertenant already requires authentication.'
        )
    )
    parser.add_argument('-u', '--user-name', help='okapi super user username', required=True)
    parser.add_argument('-o', '--okapi-url', help='Default http://localhost:9130',
                        default='http://localhost:9130', required=False)

    args = parser.parse_args(argv)

    return args

# Generic GET request for Okapi
def okapi_get(url, tenant=None):
    tenant = tenant or 'supertenant'
    headers = {
        'X-Okapi-Tenant': tenant,
        'Accept': 'application/json'
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS)
        response_data = response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        exit_http_error('GET', e)
    except urllib.error.URLError as e:
        exit_connection_error('GET', url, e.reason)
    except TimeoutError:
        exit_connection_error('GET', url, 'request timed out')
    return response_data

# Generic POST request for Okapi
def okapi_post(url, payload, tenant=None, return_headers=False):
    tenant = tenant or 'supertenant'
    headers = {
        'X-Okapi-Tenant':tenant,
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS)
        if return_headers:
            response_data = resp.headers
        else:
            response_data =  resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        exit_http_error('POST', e)
    except urllib.error.URLError as e:
        exit_connection_error('POST', url, e.reason)
    except TimeoutError:
        exit_connection_error('POST', url, 'request timed out')
    return response_data


def exit_http_error(method, error):
    response_body = error.read().decode('utf-8', errors='replace')
    sys.exit(' - '.join([
        'ERROR', method, error.url,
        str(error.code), response_body
    ]))


def exit_connection_error(method, url, reason):
    sys.exit(' - '.join([
        'ERROR', method, url, str(reason)
    ]))


def ensure_one_shot_run(okapi_url):
    """Fail before mutation if Okapi already requires an authentication token."""
    url = okapi_url + '/_/discovery/modules'
    headers = {
        'X-Okapi-Tenant': 'supertenant',
        'Accept': 'application/json'
    }
    req = urllib.request.Request(url, headers=headers)

    try:
        urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as error:
        response_body = error.read().decode('utf-8', errors='replace')
        if (
            error.code == 400
            and 'Token missing, access requires permission:' in response_body
        ):
            sys.exit(
                'ERROR: The supertenant is already secured. '
                'This one-shot bootstrap cannot be run again.'
            )
        sys.exit(' - '.join([
            'ERROR', 'GET', error.url,
            str(error.code), response_body
        ]))
    except urllib.error.URLError as error:
        exit_connection_error('GET', url, error.reason)
    except TimeoutError:
        exit_connection_error('GET', url, 'request timed out')

def fetch_module_ids(module_names, okapi_url):
    r = okapi_get(okapi_url + '/_/discovery/modules')
    all_mods = json.loads(r)
    module_ids = {}

    for name in module_names:
        candidates = []
        for mod in all_mods:
            service_id = mod.get('srvcId', '')
            version_key = module_version_key(name, service_id)
            if version_key is not None:
                candidates.append((version_key, service_id))

        if not candidates:
            sys.exit('ERROR: No semantic-versioned discovery module found for {}'.format(name))

        module_ids[name] = max(candidates)[1]

    return module_ids


def module_version_key(module_name, service_id):
    """Return a SemVer precedence key when service_id belongs to module_name."""
    version_pattern = re.compile(
        r'^{}-(\d+)\.(\d+)\.(\d+)'.format(re.escape(module_name))
        + r'(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$'
    )
    match = version_pattern.fullmatch(service_id)
    if not match:
        return None

    major, minor, patch = (int(value) for value in match.group(1, 2, 3))
    prerelease = match.group(4)
    if prerelease is None:
        return major, minor, patch, 1, ()

    prerelease_key = tuple(
        (0, int(identifier)) if identifier.isdigit() else (1, identifier)
        for identifier in prerelease.split('.')
    )
    return major, minor, patch, 0, prerelease_key

def enable_module(module_id, okapi_url, tenant=None):
    tenant = tenant or 'supertenant'
    payload = json.dumps([{
                'id' : module_id,
                'action': 'enable'
            }]).encode('UTF-8')
    return okapi_post(okapi_url +
                      '/_/proxy/tenants/{}/install?deploy=false&preRelease=false&tenantParameters=loadSample%3Dfalse%2CloadReference%3Dfalse'.format(tenant),
                      payload)

def create_user_mod_users(username, okapi_url, id=None, tenant=None):
    id = id or str(uuid.uuid4())
    payload = json.dumps({
        'id' : id,
        'username': username,
        'active' : True
    }).encode('UTF-8')
    return okapi_post(okapi_url + '/users', payload)

def add_permissions(id, permissions, okapi_url):
    payload = json.dumps({
        'userId' : id,
        'permissions' : permissions
    }).encode('UTF-8')
    return okapi_post(okapi_url + '/perms/users', payload)

def create_login_credentials(username, password, okapi_url):
    payload = json.dumps({
        'username': username,
        'password': password
    }).encode('UTF-8')
    return okapi_post(okapi_url + '/authn/credentials', payload)

if __name__ == "__main__":
    main()
