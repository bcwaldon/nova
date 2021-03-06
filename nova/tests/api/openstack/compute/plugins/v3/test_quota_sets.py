# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack Foundation
# Copyright 2013 IBM Corp.
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

from lxml import etree
import webob

from nova.api.openstack.compute.plugins.v3 import quota_sets as quotas
from nova.api.openstack import wsgi
from nova import context as context_maker
from nova import quota
from nova import test
from nova.tests.api.openstack import fakes


class QuotaSetsTest(test.TestCase):

    def setUp(self):
        super(QuotaSetsTest, self).setUp()
        self.controller = quotas.QuotaSetsController()

    def _generate_quota_set(self, **kwargs):
        quota_set = {
            'quota_set': {'metadata_items': 128,
                          'ram': 51200,
                          'floating_ips': 10,
                          'fixed_ips': -1,
                          'instances': 10,
                          'injected_files': 5,
                          'cores': 20,
                          'injected_file_content_bytes': 10240,
                          'security_groups': 10,
                          'security_group_rules': 20,
                          'key_pairs': 100,
                          'injected_file_path_bytes': 255}
        }
        quota_set['quota_set'].update(kwargs)
        return quota_set

    def test_format_quota_set(self):
        raw_quota_set = self._generate_quota_set()['quota_set']
        quota_set = self.controller._format_quota_set('1234', raw_quota_set)
        qs = quota_set['quota_set']

        self.assertEqual(qs['id'], '1234')
        self.assertEqual(qs['instances'], 10)
        self.assertEqual(qs['cores'], 20)
        self.assertEqual(qs['ram'], 51200)
        self.assertEqual(qs['floating_ips'], 10)
        self.assertEqual(qs['fixed_ips'], -1)
        self.assertEqual(qs['metadata_items'], 128)
        self.assertEqual(qs['injected_files'], 5)
        self.assertEqual(qs['injected_file_path_bytes'], 255)
        self.assertEqual(qs['injected_file_content_bytes'], 10240)
        self.assertEqual(qs['security_groups'], 10)
        self.assertEqual(qs['security_group_rules'], 20)
        self.assertEqual(qs['key_pairs'], 100)

    def test_quotas_defaults(self):
        uri = '/os-quota-sets/defaults'

        req = fakes.HTTPRequestV3.blank(uri)
        res_dict = self.controller.defaults(req, 'fake_tenant')

        expected = self._generate_quota_set(id='fake_tenant')

        self.assertEqual(res_dict, expected)

    def test_quotas_show_as_admin(self):
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/1234',
                                      use_admin_context=True)
        res_dict = self.controller.show(req, '1234')

        self.assertEqual(res_dict, self._generate_quota_set(id='1234'))

    def test_quotas_show_as_unauthorized_user(self):
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/1234')
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.show,
                          req, '1234')

    def test_quotas_update_as_admin(self):
        id = 'update_me'
        body = self._generate_quota_set()
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/' + id,
                                      use_admin_context=True)
        res_dict = self.controller.update(req, id, body)
        body['quota_set'].update(id=id)
        self.assertEqual(res_dict, body)

    def test_quotas_update_as_user(self):
        body = self._generate_quota_set()

        req = fakes.HTTPRequestV3.blank('/os-quota-sets/update_me')
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          req, 'update_me', body)

    def test_quotas_update_invalid_key(self):
        body = self._generate_quota_set()
        body['quota_set'].pop('instances')
        body['quota_set']['instances2'] = 10

        req = fakes.HTTPRequestV3.blank('/os-quota-sets/update_me',
                                      use_admin_context=True)
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          req, 'update_me', body)

    def test_quotas_update_invalid_limit(self):
        body = self._generate_quota_set(instances=-2)

        req = fakes.HTTPRequestV3.blank('/os-quota-sets/update_me',
                                      use_admin_context=True)
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          req, 'update_me', body)

    def test_quotas_update_invalid_value_json_fromat_empty_string(self):
        id = 'update_me'
        expected_resp = self._generate_quota_set(id=id)

        # when PUT JSON format with empty string for quota
        body = self._generate_quota_set(ram='')
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/' + id,
                                      use_admin_context=True)
        res_dict = self.controller.update(req, id, body)
        self.assertEqual(res_dict, expected_resp)

    def test_quotas_update_invalid_value_xml_fromat_empty_string(self):
        id = 'update_me'
        expected_resp = self._generate_quota_set(id=id)

        # when PUT XML format with empty string for quota
        body = self._generate_quota_set(ram={})
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/' + id,
                                      use_admin_context=True)
        res_dict = self.controller.update(req, id, body)
        self.assertEqual(res_dict, expected_resp)

    def test_quotas_update_invalid_value_non_int(self):
        # when PUT non integer value
        body = self._generate_quota_set(ram={}, instances=test)
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/update_me',
                                      use_admin_context=True)
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          req, 'update_me', body)

    def test_quotas_delete_as_unauthorized_user(self):
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/1234')
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.delete,
                          req, '1234')

    def test_quotas_delete_as_admin(self):
        context = context_maker.get_admin_context()
        self.req = fakes.HTTPRequestV3.blank('/os-quota-sets/1234')
        self.req.environ['nova.context'] = context
        self.mox.StubOutWithMock(quota.QUOTAS,
                                 "destroy_all_by_project")
        quota.QUOTAS.destroy_all_by_project(context, '1234')
        self.mox.ReplayAll()
        res = self.controller.delete(self.req, '1234')
        self.mox.VerifyAll()

    def test_quotas_update_exceed_in_used(self):

        body = {'quota_set': {'cores': 10}}

        self.stubs.Set(quotas.QuotaSetsController, '_get_quotas',
                       fake_get_quotas)
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/update_me',
                                      use_admin_context=True)
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          req, 'update_me', body)

    def test_quotas_force_update_exceed_in_used(self):
        id = 'update_me'
        self.stubs.Set(quotas.QuotaSetsController, '_get_quotas',
                       fake_get_quotas)
        req = fakes.HTTPRequestV3.blank('/os-quota-sets/' + id,
                                      use_admin_context=True)
        expected = {'quota_set': {'ram': 25600, 'instances': 200, 'cores': 10,
                                  'id': id}}
        body = {'quota_set': {'ram': 25600,
                              'instances': 200,
                              'cores': 10,
                              'force': 'True'}}
        fake_quotas.get('ram')['limit'] = 25600
        fake_quotas.get('cores')['limit'] = 10
        fake_quotas.get('instances')['limit'] = 200

        res_dict = self.controller.update(req, id, body)
        self.assertEqual(res_dict, expected)

    def test_user_quotas_show_as_admin(self):
        req = fakes.HTTPRequest.blank('/v2/fake4/os-quota-sets/1234?user_id=1',
                                      use_admin_context=True)
        res_dict = self.controller.show(req, '1234')

        self.assertEqual(res_dict, self._generate_quota_set(id='1234'))

    def test_user_quotas_show_as_unauthorized_user(self):
        req = fakes.HTTPRequest.blank('/v2/fake4/os-quota-sets/1234?user_id=1')
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.show,
                          req, '1234')

    def test_user_quotas_update_as_admin(self):
        body = self._generate_quota_set()

        url = '/v2/fake4/os-quota-sets/update_me?user_id=1'
        req = fakes.HTTPRequest.blank(url, use_admin_context=True)
        res_dict = self.controller.update(req, 'update_me', body)
        body['quota_set'].update({'id': 'update_me'})
        self.assertEqual(res_dict, body)

    def test_user_quotas_update_as_user(self):
        body = self._generate_quota_set()

        url = '/v2/fake4/os-quota-sets/update_me?user_id=1'
        req = fakes.HTTPRequest.blank(url)
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.update,
                          req, 'update_me', body)

    def test_user_quotas_update_exceed_project(self):
        body = {'quota_set': {'instances': 20}}
        url = '/v2/fake4/os-quota-sets/update_me?user_id=1'
        req = fakes.HTTPRequest.blank(url, use_admin_context=True)
        self.assertRaises(webob.exc.HTTPBadRequest, self.controller.update,
                          req, 'update_me', body)

    def test_user_quotas_delete_as_unauthorized_user(self):
        req = fakes.HTTPRequest.blank('/v2/fake4/os-quota-sets/1234?user_id=1')
        self.assertRaises(webob.exc.HTTPForbidden, self.controller.delete,
                          req, '1234')

    def test_user_quotas_delete_as_admin(self):
        context = context_maker.get_admin_context()
        url = '/v2/fake4/os-quota-sets/1234?user_id=1'
        self.req = fakes.HTTPRequest.blank(url)
        self.req.environ['nova.context'] = context
        self.mox.StubOutWithMock(quota.QUOTAS,
                                 "destroy_all_by_project_and_user")
        quota.QUOTAS.destroy_all_by_project_and_user(context, '1234', '1')
        self.mox.ReplayAll()
        res = self.controller.delete(self.req, '1234')
        self.mox.VerifyAll()


class QuotaXMLSerializerTest(test.TestCase):
    def setUp(self):
        super(QuotaXMLSerializerTest, self).setUp()
        self.serializer = quotas.QuotaTemplate()
        self.deserializer = wsgi.XMLDeserializer()

    def test_serializer(self):
        exemplar = dict(quota_set=dict(
                id='project_id',
                metadata_items=10,
                injected_file_path_bytes=255,
                injected_file_content_bytes=20,
                ram=50,
                floating_ips=60,
                fixed_ips=-1,
                instances=70,
                injected_files=80,
                security_groups=10,
                security_group_rules=20,
                key_pairs=100,
                cores=90))
        text = self.serializer.serialize(exemplar)

        tree = etree.fromstring(text)

        self.assertEqual('quota_set', tree.tag)
        self.assertEqual('project_id', tree.get('id'))
        self.assertEqual(len(exemplar['quota_set']) - 1, len(tree))
        for child in tree:
            self.assertTrue(child.tag in exemplar['quota_set'])
            self.assertEqual(int(child.text), exemplar['quota_set'][child.tag])

    def test_deserializer(self):
        exemplar = dict(quota_set=dict(
                metadata_items='10',
                injected_file_content_bytes='20',
                ram='50',
                floating_ips='60',
                fixed_ips='-1',
                instances='70',
                injected_files='80',
                security_groups='10',
                security_group_rules='20',
                key_pairs='100',
                cores='90'))
        intext = ("<?xml version='1.0' encoding='UTF-8'?>\n"
                  '<quota_set>'
                  '<metadata_items>10</metadata_items>'
                  '<injected_file_content_bytes>20'
                  '</injected_file_content_bytes>'
                  '<ram>50</ram>'
                  '<floating_ips>60</floating_ips>'
                  '<fixed_ips>-1</fixed_ips>'
                  '<instances>70</instances>'
                  '<injected_files>80</injected_files>'
                  '<security_groups>10</security_groups>'
                  '<security_group_rules>20</security_group_rules>'
                  '<key_pairs>100</key_pairs>'
                  '<cores>90</cores>'
                  '</quota_set>')

        result = self.deserializer.deserialize(intext)['body']
        self.assertEqual(result, exemplar)


fake_quotas = {'ram': {'limit': 51200,
                       'in_use': 12800,
                       'reserved': 12800},
               'cores': {'limit': 20,
                         'in_use': 10,
                         'reserved': 5},
               'instances': {'limit': 100,
                             'in_use': 0,
                             'reserved': 0}}


def fake_get_quotas(self, context, id, user_id=None, usages=False):
    if usages:
        return fake_quotas
    else:
        return dict((k, v['limit']) for k, v in fake_quotas.items())
