#!/usr/bin/python3

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


REQUEST_TIMEOUT_SECONDS = 30


def main():
    # parse command line arguments
    args = parse_command_line_args()
    supertenant_password, new_admin_password = prompt_for_passwords()

    # get supertenant token
    supertenant_token = authenticate_supertenant(
        args.okapi,
        args.username,
        supertenant_password
    )

    # check for mod authtoken on target tenant
    # disable without checking deps
    authtoken_module_id = get_enabled_authtoken_module_id(
        args.okapi,
        args.tenant,
        supertenant_token
    )
    if authtoken_module_id:
        print(
            '{} is enabled for tenant {}.'.format(
                authtoken_module_id,
                args.tenant
            )
        )
        disable_authtoken(
            args.okapi,
            args.tenant,
            authtoken_module_id,
            supertenant_token
        )
        print('{} has been disabled.'.format(authtoken_module_id))
    else:
        print('mod-authtoken is not enabled for tenant {}.'.format(args.tenant))

    try:
        # create tenant admin with all top level perms
        admin_user_id = bootstrap_tenant_admin(
            args.okapi,
            args.tenant,
            args.admin_user,
            new_admin_password,
            supertenant_token
        )
    finally:
        # always re-enable authtoken
        if authtoken_module_id:
            enable_authtoken(
                args.okapi,
                args.tenant,
                authtoken_module_id,
                supertenant_token
            )
            print('{} has been re-enabled.'.format(authtoken_module_id))

    print(
        'Tenant administrator {} is configured with user ID {}.'.format(
            args.admin_user,
            admin_user_id
        )
    )

    tenant_admin_token = authenticate_tenant(
        args.okapi,
        args.tenant,
        args.admin_user,
        new_admin_password
    )
    top_level_permissions = get_top_level_permissions(
        args.okapi,
        args.tenant,
        tenant_admin_token
    )
    assigned_permissions = assign_top_level_permissions(
        args.okapi,
        args.tenant,
        admin_user_id,
        tenant_admin_token,
        top_level_permissions
    )
    print(
        'Assigned {} top-level permissions to {}.'.format(
            assigned_permissions,
            args.admin_user
        )
    )
    print('{} permissions:'.format(args.admin_user))
    print(json.dumps(top_level_permissions, indent=2))


def parse_command_line_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Bootstrap a superuser on a tenant using a supertenant administrator.'
        )
    )
    parser.add_argument(
        '-o', '--okapi',
        help='Okapi URL',
        required=True
    )
    parser.add_argument(
        '-u', '--username',
        help='Okapi supertenant administrator username',
        required=True
    )
    parser.add_argument(
        '-a', '--admin-user',
        help='New tenant administrator username',
        required=True
    )
    parser.add_argument(
        '-t', '--tenant',
        help='Tenant ID to bootstrap',
        required=True
    )

    return parser.parse_args(argv)


def prompt_for_passwords():
    supertenant_password = getpass.getpass(
        'Okapi supertenant administrator password: '
    )
    new_admin_password = getpass.getpass(
        'New tenant administrator password: '
    )
    return supertenant_password, new_admin_password


def authenticate_supertenant(okapi_url, username, password):
    response = okapi_json_request(
        'POST',
        build_okapi_url(okapi_url, '/authn/login'),
        'supertenant',
        payload={'username': username, 'password': password}
    )
    token = response.get('okapiToken') or response.get('token')
    if token:
        return token
    sys.exit(
        'ERROR: Supertenant authentication response did not contain a token. '
        'Response body: {}'.format(json.dumps(response))
    )


def get_enabled_authtoken_module_id(okapi_url, tenant, token):
    encoded_tenant = urllib.parse.quote(tenant, safe='')
    modules = okapi_json_request(
        'GET',
        build_okapi_url(
            okapi_url,
            '/_/proxy/tenants/{}/interfaces/authtoken'.format(encoded_tenant)
        ),
        'supertenant',
        token=token
    )

    if not isinstance(modules, list):
        sys.exit('ERROR: Okapi returned an invalid authtoken interface response.')
    if not modules:
        return None

    module_id = modules[0].get('id') if isinstance(modules[0], dict) else None
    if not module_id:
        sys.exit('ERROR: Okapi authtoken interface response did not contain a module ID.')

    return module_id


def disable_authtoken(okapi_url, tenant, authtoken_module_id, token):
    return change_authtoken_state(
        okapi_url, tenant, authtoken_module_id, token, 'disable'
    )


def enable_authtoken(okapi_url, tenant, authtoken_module_id, token):
    return change_authtoken_state(
        okapi_url, tenant, authtoken_module_id, token, 'enable'
    )


def change_authtoken_state(okapi_url, tenant, authtoken_module_id, token, action):
    encoded_tenant = urllib.parse.quote(tenant, safe='')
    url = (
        okapi_url.rstrip('/')
        + '/_/proxy/tenants/{}/install?depCheck=false'.format(encoded_tenant)
    )
    payload = [{
        'id': authtoken_module_id,
        'action': action
    }]
    return okapi_json_request(
        'POST',
        url,
        'supertenant',
        payload=payload,
        token=token
    )


def okapi_json_request(
    method,
    url,
    tenant,
    payload=None,
    token=None,
    allowed_error_codes=None
):
    allowed_error_codes = allowed_error_codes or set()
    headers = {
        'X-Okapi-Tenant': tenant,
        'Accept': 'application/json, text/plain'
    }
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    if token:
        headers['X-Okapi-Token'] = token

    request_data = None
    if payload is not None:
        request_data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=request_data,
        headers=headers,
        method=method
    )

    try:
        response = urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        response_body = response.read().decode('utf-8')
    except urllib.error.HTTPError as error:
        response_body = error.read().decode('utf-8', errors='replace')
        if error.code in allowed_error_codes:
            return None
        sys.exit(' - '.join([
            'ERROR', method, error.url,
            str(error.code), response_body
        ]))
    except urllib.error.URLError as error:
        sys.exit(' - '.join([
            'ERROR', method, url, str(error.reason)
        ]))
    except TimeoutError:
        sys.exit(' - '.join([
            'ERROR', method, url, 'request timed out'
        ]))

    if not response_body:
        return None
    try:
        return json.loads(response_body)
    except json.JSONDecodeError:
        sys.exit('ERROR: Okapi returned invalid JSON for {} {}.'.format(method, url))


def build_okapi_url(okapi_url, path, query=None):
    url = okapi_url.rstrip('/') + path
    if query:
        url += '?' + urllib.parse.urlencode(query)
    return url


def bootstrap_tenant_admin(
    okapi_url,
    tenant,
    username,
    password,
    supertenant_token
):
    admin_user_id = ensure_user(okapi_url, tenant, username)
    ensure_credentials(okapi_url, tenant, admin_user_id, password)
    ensure_permissions_user(okapi_url, tenant, admin_user_id)
    ensure_service_points_user(
        okapi_url,
        tenant,
        admin_user_id,
        supertenant_token
    )
    return admin_user_id


def ensure_user(okapi_url, tenant, username):
    users = okapi_json_request(
        'GET',
        build_okapi_url(
            okapi_url,
            '/users',
            {'query': 'username=={}'.format(username)}
        ),
        tenant
    )
    if users.get('totalRecords', 0) > 0:
        return users['users'][0]['id']

    admin_user_id = str(uuid.uuid4())
    okapi_json_request(
        'POST',
        build_okapi_url(okapi_url, '/users'),
        tenant,
        payload={
            'id': admin_user_id,
            'username': username,
            'active': True,
            'type': 'staff',
            'personal': {
                'lastName': '',
                'firstName': '',
                'email': ''
            }
        }
    )
    return admin_user_id


def ensure_credentials(okapi_url, tenant, admin_user_id, password):
    credentials = okapi_json_request(
        'GET',
        build_okapi_url(
            okapi_url,
            '/authn/credentials-existence',
            {'userId': admin_user_id}
        ),
        tenant
    )
    if not credentials.get('credentialsExist', False):
        okapi_json_request(
            'POST',
            build_okapi_url(okapi_url, '/authn/credentials'),
            tenant,
            payload={
                'userId': admin_user_id,
                'password': password
            }
        )


def ensure_permissions_user(okapi_url, tenant, admin_user_id):
    permissions = okapi_json_request(
        'GET',
        build_okapi_url(
            okapi_url,
            '/perms/users',
            {'query': 'userId=={}'.format(admin_user_id)}
        ),
        tenant
    )
    if permissions.get('totalRecords', 0) == 0:
        okapi_json_request(
            'POST',
            build_okapi_url(okapi_url, '/perms/users'),
            tenant,
            payload={
                'userId': admin_user_id,
                'permissions': ['perms.all']
            }
        )


def ensure_service_points_user(
    okapi_url,
    tenant,
    admin_user_id,
    supertenant_token
):
    encoded_tenant = urllib.parse.quote(tenant, safe='')
    service_points_users_interface = okapi_json_request(
        'GET',
        build_okapi_url(
            okapi_url,
            '/_/proxy/tenants/{}/interfaces/service-points-users'.format(
                encoded_tenant
            )
        ),
        'supertenant',
        token=supertenant_token
    )
    if not service_points_users_interface:
        return

    service_point_user = okapi_json_request(
        'GET',
        build_okapi_url(
            okapi_url,
            '/service-points-users',
            {'query': 'userId=={}'.format(admin_user_id)}
        ),
        tenant
    )
    if service_point_user.get('totalRecords', 0) > 0:
        return

    service_points = okapi_json_request(
        'GET',
        build_okapi_url(okapi_url, '/service-points'),
        tenant
    )
    service_point_ids = [
        service_point['id']
        for service_point in service_points.get('servicepoints', [])
    ]
    if service_point_ids:
        okapi_json_request(
            'POST',
            build_okapi_url(okapi_url, '/service-points-users'),
            tenant,
            payload={
                'userId': admin_user_id,
                'servicePointsIds': service_point_ids,
                'defaultServicePointId': service_point_ids[0]
            },
            allowed_error_codes={422}
        )


def authenticate_tenant(okapi_url, tenant, username, password):
    response = okapi_json_request(
        'POST',
        build_okapi_url(okapi_url, '/authn/login'),
        tenant,
        payload={
            'username': username,
            'password': password
        }
    )
    token = None
    if isinstance(response, dict):
        token = response.get('okapiToken') or response.get('token')
    if not token:
        sys.exit('ERROR: Tenant authentication response did not contain a token.')
    return token


def get_top_level_permissions(okapi_url, tenant, token):
    permission_query = (
        'cql.allRecords=1 '
        'not permissionName==okapi.* '
        'not permissionName==perms.users.assign.okapi '
        'not permissionName==modperms.* '
        'not permissionName==SYS#*'
    )
    response = okapi_json_request(
        'GET',
        build_okapi_url(
            okapi_url,
            '/perms/permissions',
            {'query': permission_query, 'length': 5000}
        ),
        tenant,
        token=token
    )
    permissions = response.get('permissions', [])
    total_records = response.get('totalRecords')
    if total_records is None or len(permissions) != total_records:
        sys.exit(
            'ERROR: Retrieved permission count ({}) does not match totalRecords ({}).'.format(
                len(permissions),
                total_records
            )
        )

    return [
        permission['permissionName']
        for permission in permissions
        if permission.get('permissionName')
        and all(
            parent.startswith('SYS#')
            for parent in permission.get('childOf', [])
        )
    ]


def assign_top_level_permissions(
    okapi_url,
    tenant,
    admin_user_id,
    token,
    top_level_permissions
):
    permission_users = okapi_json_request(
        'GET',
        build_okapi_url(
            okapi_url,
            '/perms/users',
            {'query': 'userId=={}'.format(admin_user_id)}
        ),
        tenant,
        token=token
    )
    records = permission_users.get('permissionUsers', [])
    if len(records) != 1:
        sys.exit(
            'ERROR: Expected one permissions record for user {}, found {}.'.format(
                admin_user_id,
                len(records)
            )
        )

    permission_user = records[0]
    permission_user_id = permission_user.get('id')
    if not permission_user_id:
        sys.exit('ERROR: Tenant administrator permissions record has no ID.')

    existing_permissions = set(permission_user.get('permissions', []))
    assigned_count = 0
    encoded_permission_user_id = urllib.parse.quote(permission_user_id, safe='')
    for permission_name in top_level_permissions:
        if permission_name in existing_permissions:
            continue
        okapi_json_request(
            'POST',
            build_okapi_url(
                okapi_url,
                '/perms/users/{}/permissions'.format(
                    encoded_permission_user_id
                )
            ),
            tenant,
            payload={'permissionName': permission_name},
            token=token
        )
        assigned_count += 1

    return assigned_count


if __name__ == "__main__":
    main()
