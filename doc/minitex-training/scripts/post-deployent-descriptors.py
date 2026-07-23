#!/usr/bin/python3

import argparse
import json
from pathlib import Path
import re
import sys
import urllib.request
import uuid


def main():
    # parse command line arguments
    args = parse_command_line_args()

    okapi_is_secured = is_okapi_secured(args.okapi_url)

    if okapi_is_secured:
        if not args.password:
            sys.exit('ERROR: Okapi is secured, but no password was provided. Use -p to provide a password.')
        token = get_okapi_token(args.okapi_url, args.user_name, args.password)
    else:
        token = None
        print('Okapi is not secured, proceeding without authentication.')

    if args.file:
        descriptors = [load_descriptor_from_file(args.file)]
        source = f'file {args.file}'
    else:
        descriptors = load_descriptors_from_directory(args.directory)
        source = f'directory {args.directory}'

    for descriptor in descriptors:
        response = post_deployment_descriptor(args.okapi_url, descriptor, token)
        print(f'Successfully posted deployment descriptor from {source}. Response: {response}')

def parse_command_line_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--user-name', help='okapi super user username', required=False, default='okapi_admin')
    parser.add_argument('-p', '--password', help='okapi super user password', required=False)
    parser.add_argument('-o', '--okapi-url', help='Default http://localhost:9130',
                        default='http://localhost:9130', required=False)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('-d', '--directory', help='directory containing module descriptor JSON files')
    source.add_argument('-f', '--file', help='file containing a module descriptor')


    args = parser.parse_args(argv)

    if args.file:
        descriptor_file = Path(args.file)
        if not descriptor_file.is_file():
            parser.error('{} is not a file'.format(descriptor_file))
        args.descriptor_files = [descriptor_file]
    else:
        descriptor_directory = Path(args.directory)
        if not descriptor_directory.is_dir():
            parser.error('{} is not a directory'.format(descriptor_directory))
        args.descriptor_files = sorted(
            path for path in descriptor_directory.glob('*.json')
            if path.is_file()
        )

    return args

# check if okapi is secured
def is_okapi_secured(okapi_url):
    url = okapi_url + '/_/discovery/modules'
    try:
        r = urllib.request.urlopen(url)
        return False
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return True
        else:
            sys.exit(' - '.join([
                'ERROR', 'GET', e.url,
                str(e.status), str(e.read())
            ]))

# get a token, uses /authn/login
def get_okapi_token(okapi_url, user_name, password):
    url = okapi_url + '/authn/login'
    payload = json.dumps({
        'username': user_name,
        'password': password
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        response_data = resp.read().decode('utf-8')
        token = json.loads(response_data)['token']
    except urllib.error.HTTPError as e:
        sys.exit(' - '.join([
                'ERROR', 'POST', e.url,
                str(e.status), str(e.read().decode('utf-8'))
            ]))
    return token

def post_deployment_descriptor(okapi_url, descriptor, token=None):
    url = okapi_url + '/_/discovery/modules'
    payload = json.dumps(descriptor).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    if token:
        headers['X-Okapi-Token'] = token
    req = urllib.request.Request(url, data=payload, headers=headers)
    try:
        resp = urllib.request.urlopen(req)
        response_data = resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        response_data = e.read().decode('utf-8')
        if e.code == 400 and response_data.startswith('Duplicate instId'):
            return response_data
        sys.exit(' - '.join([
                'ERROR', 'POST', e.url,
                str(e.status), response_data
            ]))
    return response_data

def load_descriptor_from_file(file_path):
    with open(file_path, 'r') as f:
        descriptor = json.load(f)
    return descriptor

def load_descriptors_from_directory(directory_path):
    directory = Path(directory_path)
    descriptor_files = sorted(
        path for path in directory.glob('*.json')
        if path.is_file()
    )
    return [load_descriptor_from_file(path) for path in descriptor_files]

if __name__ == "__main__":
    main()
