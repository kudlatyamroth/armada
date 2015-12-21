from __future__ import print_function
import argparse
import os
import json

import armada_api
import armada_utils
from armada_command.consul.consul import consul_query


def parse_args():
    parser = argparse.ArgumentParser(description='ssh into docker container.')
    add_arguments(parser)
    return parser.parse_args()


def add_arguments(parser):
    parser.add_argument('microservice_name', nargs='?',
                        help='Name of the microservice or container_id to ssh into. '
                             'If not provided it will use MICROSERVICE_NAME env variable.')
    parser.add_argument('command', nargs=argparse.REMAINDER,
                        help='Execute command inside the container. '
                             'If not provided it will create interactive bash terminal.')
    parser.add_argument('-t', '--tty', default=False, action='store_true',
                        help='Allocate a pseudo-TTY.')
    parser.add_argument('-i', '--interactive', default=False, action='store_true',
                        help='Keep STDIN open even if not attached.')


def command_ssh(args):
    microservice_name = args.microservice_name or os.environ['MICROSERVICE_NAME']
    if not microservice_name:
        raise ValueError('No microservice name supplied.')

    instances = armada_utils.get_matched_containers(microservice_name)
    instances_count = len(instances)
    if instances_count > 1:
        raise armada_utils.ArmadaCommandException(
            'There are too many ({instances_count}) matching containers. '
            'Provide more specific container_id or microservice name.'.format(**locals()))
    instance = instances[0]

    service_id = instance['ServiceID']
    container_id = service_id.split(':')[0]
    payload = {'container_id': container_id}

    is_local = False
    local_microservices_ids = set(consul_query('agent/services').keys())
    if container_id in local_microservices_ids:
        is_local = True

    if not is_local:
        result = json.loads(armada_api.get('ssh-address', payload, ship_name=instance['Node']))

        if result['status'] != 'ok':
            raise armada_utils.ArmadaCommandException('armada API error: {0}'.format(result['error']))
        ssh_host = result['ssh'].split(':')[0]

        docker_key_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'keys/docker.key')

    if args.command:
        command = ' '.join(args.command)
    else:
        command = 'bash'
        args.tty = True
        args.interactive = True

    tty = '-t' if args.tty else ''
    interactive = '-i' if args.interactive else ''
    term = os.environ.get('TERM') or 'dummy'

    ssh_command = 'docker exec {interactive} {tty} {container_id} env TERM={term} {command}'.format(**locals())
    if is_local:
        print("Connecting to {0}...".format(instance['ServiceName']))
    else:
        ssh_command = 'ssh -t {tty} -p 2201 -i {docker_key_file} -o StrictHostKeyChecking=no docker@{ssh_host} sudo {ssh_command}'.format(
            **locals())
        print("Connecting to {0} on host {1}...".format(instance['ServiceName'], ssh_host))

    ssh_args = ssh_command.split()
    os.execvp(ssh_args[0], ssh_args)
