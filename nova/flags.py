# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Package-level global flags are defined here, the rest are defined
where they're used.
"""

import getopt
import os
import socket
import string
import sys

import gflags


class FlagValues(gflags.FlagValues):
    """Extension of gflags.FlagValues that allows undefined and runtime flags.

    Unknown flags will be ignored when parsing the command line, but the
    command line will be kept so that it can be replayed if new flags are
    defined after the initial parsing.

    """

    def __init__(self, extra_context=None):
        gflags.FlagValues.__init__(self)
        self.__dict__['__dirty'] = []
        self.__dict__['__was_already_parsed'] = False
        self.__dict__['__stored_argv'] = []
        self.__dict__['__extra_context'] = extra_context

    def __call__(self, argv):
        # We're doing some hacky stuff here so that we don't have to copy
        # out all the code of the original verbatim and then tweak a few lines.
        # We're hijacking the output of getopt so we can still return the
        # leftover args at the end
        sneaky_unparsed_args = {"value": None}
        original_argv = list(argv)

        if self.IsGnuGetOpt():
            orig_getopt = getattr(getopt, 'gnu_getopt')
            orig_name = 'gnu_getopt'
        else:
            orig_getopt = getattr(getopt, 'getopt')
            orig_name = 'getopt'

        def _sneaky(*args, **kw):
            optlist, unparsed_args = orig_getopt(*args, **kw)
            sneaky_unparsed_args['value'] = unparsed_args
            return optlist, unparsed_args

        try:
            setattr(getopt, orig_name, _sneaky)
            args = gflags.FlagValues.__call__(self, argv)
        except gflags.UnrecognizedFlagError:
            # Undefined args were found, for now we don't care so just
            # act like everything went well
            # (these three lines are copied pretty much verbatim from the end
            # of the __call__ function we are wrapping)
            unparsed_args = sneaky_unparsed_args['value']
            if unparsed_args:
                if self.IsGnuGetOpt():
                    args = argv[:1] + unparsed_args
                else:
                    args = argv[:1] + original_argv[-len(unparsed_args):]
            else:
                args = argv[:1]
        finally:
            setattr(getopt, orig_name, orig_getopt)

        # Store the arguments for later, we'll need them for new flags
        # added at runtime
        self.__dict__['__stored_argv'] = original_argv
        self.__dict__['__was_already_parsed'] = True
        self.ClearDirty()
        return args

    def Reset(self):
        gflags.FlagValues.Reset(self)
        self.__dict__['__dirty'] = []
        self.__dict__['__was_already_parsed'] = False
        self.__dict__['__stored_argv'] = []

    def SetDirty(self, name):
        """Mark a flag as dirty so that accessing it will case a reparse."""
        self.__dict__['__dirty'].append(name)

    def IsDirty(self, name):
        return name in self.__dict__['__dirty']

    def ClearDirty(self):
        self.__dict__['__is_dirty'] = []

    def WasAlreadyParsed(self):
        return self.__dict__['__was_already_parsed']

    def ParseNewFlags(self):
        if '__stored_argv' not in self.__dict__:
            return
        new_flags = FlagValues(self)
        for k in self.__dict__['__dirty']:
            new_flags[k] = gflags.FlagValues.__getitem__(self, k)

        new_flags(self.__dict__['__stored_argv'])
        for k in self.__dict__['__dirty']:
            setattr(self, k, getattr(new_flags, k))
        self.ClearDirty()

    def __setitem__(self, name, flag):
        gflags.FlagValues.__setitem__(self, name, flag)
        if self.WasAlreadyParsed():
            self.SetDirty(name)

    def __getitem__(self, name):
        if self.IsDirty(name):
            self.ParseNewFlags()
        return gflags.FlagValues.__getitem__(self, name)

    def __getattr__(self, name):
        if self.IsDirty(name):
            self.ParseNewFlags()
        val = gflags.FlagValues.__getattr__(self, name)
        if type(val) is str:
            tmpl = string.Template(val)
            context = [self, self.__dict__['__extra_context']]
            return tmpl.substitute(StrWrapper(context))
        return val


class StrWrapper(object):
    """Wrapper around FlagValues objects

    Wraps FlagValues objects for string.Template so that we're
    sure to return strings."""
    def __init__(self, context_objs):
        self.context_objs = context_objs

    def __getitem__(self, name):
        for context in self.context_objs:
            val = getattr(context, name, False)
            if val:
                return str(val)
        raise KeyError(name)


FLAGS = FlagValues()
gflags.FLAGS = FLAGS
gflags.DEFINE_flag(gflags.HelpFlag(), FLAGS)


def _wrapper(func):
    def _wrapped(*args, **kw):
        kw.setdefault('flag_values', FLAGS)
        func(*args, **kw)
    _wrapped.func_name = func.func_name
    return _wrapped


DEFINE = _wrapper(gflags.DEFINE)
DEFINE_string = _wrapper(gflags.DEFINE_string)
DEFINE_integer = _wrapper(gflags.DEFINE_integer)
DEFINE_bool = _wrapper(gflags.DEFINE_bool)
DEFINE_boolean = _wrapper(gflags.DEFINE_boolean)
DEFINE_float = _wrapper(gflags.DEFINE_float)
DEFINE_enum = _wrapper(gflags.DEFINE_enum)
DEFINE_list = _wrapper(gflags.DEFINE_list)
DEFINE_spaceseplist = _wrapper(gflags.DEFINE_spaceseplist)
DEFINE_multistring = _wrapper(gflags.DEFINE_multistring)
DEFINE_multi_int = _wrapper(gflags.DEFINE_multi_int)
DEFINE_flag = _wrapper(gflags.DEFINE_flag)


HelpFlag = gflags.HelpFlag
HelpshortFlag = gflags.HelpshortFlag
HelpXMLFlag = gflags.HelpXMLFlag


def DECLARE(name, module_string, flag_values=FLAGS):
    if module_string not in sys.modules:
        __import__(module_string, globals(), locals())
    if name not in flag_values:
        raise gflags.UnrecognizedFlag(
                "%s not defined by %s" % (name, module_string))


# __GLOBAL FLAGS ONLY__
# Define any app-specific flags in their own files, docs at:
# http://code.google.com/p/python-gflags/source/browse/trunk/gflags.py#39

DEFINE_list('region_list',
            [],
            'list of region=url pairs separated by commas')
DEFINE_string('connection_type', 'libvirt', 'libvirt, xenapi or fake')
DEFINE_string('aws_access_key_id', 'admin', 'AWS Access ID')
DEFINE_string('aws_secret_access_key', 'admin', 'AWS Access Key')
DEFINE_integer('glance_port', 9292, 'glance port')
DEFINE_string('glance_host', '127.0.0.1', 'glance host')
DEFINE_integer('s3_port', 3333, 's3 port')
DEFINE_string('s3_host', '127.0.0.1', 's3 host (for infrastructure)')
DEFINE_string('s3_dmz', '127.0.0.1', 's3 dmz ip (for instances)')
DEFINE_string('compute_topic', 'compute', 'the topic compute nodes listen on')
DEFINE_string('console_topic', 'console',
              'the topic console proxy nodes listen on')
DEFINE_string('scheduler_topic', 'scheduler',
              'the topic scheduler nodes listen on')
DEFINE_string('volume_topic', 'volume', 'the topic volume nodes listen on')
DEFINE_string('network_topic', 'network', 'the topic network nodes listen on')

DEFINE_bool('verbose', False, 'show debug output')
DEFINE_boolean('fake_rabbit', False, 'use a fake rabbit')
DEFINE_bool('fake_network', False,
            'should we use fake network devices and addresses')
DEFINE_string('rabbit_host', 'localhost', 'rabbit host')
DEFINE_integer('rabbit_port', 5672, 'rabbit port')
DEFINE_string('rabbit_userid', 'guest', 'rabbit userid')
DEFINE_string('rabbit_password', 'guest', 'rabbit password')
DEFINE_string('rabbit_virtual_host', '/', 'rabbit virtual host')
DEFINE_integer('rabbit_retry_interval', 10, 'rabbit connection retry interval')
DEFINE_integer('rabbit_max_retries', 12, 'rabbit connection attempts')
DEFINE_string('control_exchange', 'nova', 'the main exchange to connect to')
DEFINE_string('ec2_prefix', 'http', 'prefix for ec2')
DEFINE_string('cc_host', '127.0.0.1', 'ip of api server')
DEFINE_string('cc_dmz', '127.0.0.1', 'internal ip of api server')
DEFINE_integer('cc_port', 8773, 'cloud controller port')
DEFINE_string('ec2_suffix', '/services/Cloud', 'suffix for ec2')

DEFINE_string('default_project', 'openstack', 'default project for openstack')
DEFINE_string('default_image', 'ami-11111',
              'default image to use, testing only')
DEFINE_string('default_instance_type', 'm1.small',
              'default instance type to use, testing only')
DEFINE_string('null_kernel', 'nokernel',
              'kernel image that indicates not to use a kernel,'
              ' but to use a raw disk image instead')

DEFINE_string('vpn_image_id', 'ami-cloudpipe', 'AMI for cloudpipe vpn server')
DEFINE_string('vpn_key_suffix',
              '-vpn',
              'Suffix to add to project name for vpn key and secgroups')

DEFINE_integer('auth_token_ttl', 3600, 'Seconds for auth tokens to linger')

DEFINE_string('state_path', os.path.join(os.path.dirname(__file__), '../'),
              "Top-level directory for maintaining nova's state")

DEFINE_string('sql_connection',
              'sqlite:///$state_path/nova.sqlite',
              'connection string for sql database')
DEFINE_string('sql_idle_timeout',
              '3600',
              'timeout for idle sql database connections')
DEFINE_integer('sql_max_retries', 12, 'sql connection attempts')
DEFINE_integer('sql_retry_interval', 10, 'sql connection retry interval')

DEFINE_string('compute_manager', 'nova.compute.manager.ComputeManager',
              'Manager for compute')
DEFINE_string('console_manager', 'nova.console.manager.ConsoleProxyManager',
              'Manager for console proxy')
DEFINE_string('network_manager', 'nova.network.manager.VlanManager',
              'Manager for network')
DEFINE_string('volume_manager', 'nova.volume.manager.VolumeManager',
              'Manager for volume')
DEFINE_string('scheduler_manager', 'nova.scheduler.manager.SchedulerManager',
              'Manager for scheduler')

# The service to use for image search and retrieval
DEFINE_string('image_service', 'nova.image.s3.S3ImageService',
              'The service to use for retrieving and searching for images.')

DEFINE_string('host', socket.gethostname(),
              'name of this node')

# UNUSED
DEFINE_string('node_availability_zone', 'nova',
              'availability zone of this node')
