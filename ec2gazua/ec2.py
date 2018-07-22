# -*- coding: utf-8 -*-

import boto3

from os.path import expanduser
from os.path import isfile

from ec2gazua.config import Config
from ec2gazua.logger import console


class EC2InstanceManager(object):
    instances = {}
    aws_names = set()
    groups = set()

    def add_instance(self, aws_name, group, instance):
        self.aws_names.add(aws_name)
        self.groups.add(group)

        if aws_name not in self.instances:
            self.instances[aws_name] = {}

        if group not in self.instances[aws_name]:
            self.instances[aws_name][group] = []

        self.instances[aws_name][group].append(instance)


class EC2InstanceLoader(object):
    config = Config()

    def _request_instances(self, aws_name):
        credential = self.config[aws_name]['credential']
        session = boto3.Session(
            aws_access_key_id=credential['aws_access_key_id'],
            aws_secret_access_key=credential['aws_secret_access_key'],
            region_name=credential['region'])

        client = session.client('ec2')

        return [i['Instances'][0] for i in
                client.describe_instances()['Reservations']]

    def load_all(self):
        manager = EC2InstanceManager()

        for aws_name, item in self.config.items():
            console('Instance loading [%s]' % aws_name)
            aws_instances = self._request_instances(aws_name)

            for aws_instance in aws_instances:
                ec2_instance = EC2Instance(self.config[aws_name], aws_instance)
                manager.add_instance(aws_name, ec2_instance.group,
                                     ec2_instance)

        return manager


class EC2Instance(object):
    DEFAULT_NAME = "UNKNOWN-NAME"
    DEFAULT_GROUP = "UNKNOWN-GROUP"

    def __init__(self, config, instance):
        self.config = config
        self.instance = instance

    @property
    def tags(self):
        return {t['Key']: t['Value'] for t in self.instance.get('Tags', {}) if
                t['Value'] != ''}

    @property
    def id(self):
        return self.instance['InstanceId']

    @property
    def name(self):
        if self.config['name-tag'] in self.tags:
            return self.tags[self.config['name-tag']]
        return self.DEFAULT_NAME

    @property
    def group(self):
        if self.config['group-tag'] in self.tags:
            return self.tags[self.config['group-tag']]
        return self.DEFAULT_GROUP

    @property
    def type(self):
        return self.instance['InstanceType']

    @property
    def key_name(self):
        option = self.config['key-file']['default']
        key_name = self.instance.get('KeyName') if option == 'auto' else option
        override = self.config['key-file']
        for group, value in override.get('group', {}).items():
            if group in self.group:
                key_name = value
        for name, value in override.get('name', {}).items():
            if name in self.name:
                key_name = value
        return key_name

    @property
    def key_file(self):
        return self.config['ssh-path'] + self.key_name

    @property
    def private_ip(self):
        return self.instance.get('PrivateIpAddress')

    @property
    def public_ip(self):
        return self.instance.get('PublicIpAddress')

    @property
    def connect_ip(self):
        ip_type = self.config['connect-ip']['default']
        override = self.config['connect-ip']
        for group, value in override.get('group', {}).items():
            if group in self.group:
                ip_type = value
        for name, value in override.get('name', {}).items():
            if name in self.name:
                ip_type = value
        return self.public_ip if ip_type == 'public' else self.private_ip

    @property
    def user(self):
        user = self.config['user']['default']
        override = self.config['user']
        for group, value in override.get('group', {}).items():
            if group in self.group:
                user = value
        for name, value in override.get('name', {}).items():
            if name in self.name:
                user = value
        return user

    @property
    def has_key_file(self):
        key_path = expanduser(self.key_name)
        if isfile(key_path):
            return True
        if key_path.lower().endswith('.pem'):
            return isfile(key_path.rsplit('.pem', 1)[0])
        return isfile(key_path + '.pem')

    @property
    def is_running(self):
        return self.instance['State']['Name'] == 'running'

    @property
    def is_connectable(self):
        return self.is_running and self.has_key_file and \
               self.connect_ip is not None