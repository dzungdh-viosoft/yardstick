# Copyright (c) 2016-2017 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from multiprocessing import Process, Queue
import time

import mock
from six.moves import configparser
import unittest

from yardstick.benchmark.contexts import base as ctx_base
from yardstick.network_services.nfvi.resource import ResourceProfile
from yardstick.network_services.vnf_generic.vnf import base as vnf_base
from yardstick.network_services.vnf_generic.vnf import sample_vnf
from yardstick.network_services.vnf_generic.vnf import vpe_vnf
from yardstick.tests.unit.network_services.vnf_generic.vnf import test_base


TEST_FILE_YAML = 'nsb_test_case.yaml'

NAME = 'vnf_1'

PING_OUTPUT_1 = "Pkts in: 101\r\n\tPkts dropped by AH: 100\r\n\tPkts dropped by other: 100"

MODULE_PATH = test_base.FileAbsPath(__file__)
get_file_abspath = MODULE_PATH.get_path


class TestConfigCreate(unittest.TestCase):

    VNFD_0 = {
        'short-name': 'VpeVnf',
        'vdu': [
            {
                'routing_table': [
                    {
                        'network': '152.16.100.20',
                        'netmask': '255.255.255.0',
                        'gateway': '152.16.100.20',
                        'if': 'xe0'
                    },
                    {
                        'network': '152.16.40.20',
                        'netmask': '255.255.255.0',
                        'gateway': '152.16.40.20',
                        'if': 'xe1'
                    },
                ],
                'description': 'VPE approximation using DPDK',
                'name': 'vpevnf-baremetal',
                'nd_route_tbl': [
                    {
                        'network': '0064:ff9b:0:0:0:0:9810:6414',
                        'netmask': '112',
                        'gateway': '0064:ff9b:0:0:0:0:9810:6414',
                        'if': 'xe0'
                    },
                    {
                        'network': '0064:ff9b:0:0:0:0:9810:2814',
                        'netmask': '112',
                        'gateway': '0064:ff9b:0:0:0:0:9810:2814',
                        'if': 'xe1'
                    },
                ],
                'id': 'vpevnf-baremetal',
                'external-interface': [
                    {
                        'virtual-interface': {
                            'dst_mac': '00:00:00:00:00:03',
                            'vpci': '0000:05:00.0',
                            'local_ip': '152.16.100.19',
                            'type': 'PCI-PASSTHROUGH',
                            'netmask': '255.255.255.0',
                            'dpdk_port_num': 0,
                            'bandwidth': '10 Gbps',
                            'dst_ip': '152.16.100.20',
                            'local_mac': '00:00:00:00:00:01',
                            'vld_id': 'uplink_0',
                            'ifname': 'xe0',
                        },
                        'vnfd-connection-point-ref': 'xe0',
                        'name': 'xe0'
                    },
                    {
                        'virtual-interface': {
                            'dst_mac': '00:00:00:00:00:04',
                            'vpci': '0000:05:00.1',
                            'local_ip': '152.16.40.19',
                            'type': 'PCI-PASSTHROUGH',
                            'netmask': '255.255.255.0',
                            'dpdk_port_num': 1,
                            'bandwidth': '10 Gbps',
                            'dst_ip': '152.16.40.20',
                            'local_mac': '00:00:00:00:00:02',
                            'vld_id': 'downlink_0',
                            'ifname': 'xe1',
                        },
                        'vnfd-connection-point-ref': 'xe1',
                        'name': 'xe1'
                    },
                ],
            },
        ],
        'description': 'Vpe approximation using DPDK',
        'mgmt-interface': {
            'vdu-id': 'vpevnf-baremetal',
            'host': '1.1.1.1',
            'password': 'r00t',
            'user': 'root',
            'ip': '1.1.1.1'
        },
        'benchmark': {
            'kpi': [
                'packets_in',
                'packets_fwd',
                'packets_dropped',
            ],
        },
        'connection-point': [
            {
                'type': 'VPORT',
                'name': 'xe0',
            },
            {
                'type': 'VPORT',
                'name': 'xe1',
            },
        ],
        'id': 'VpeApproxVnf', 'name': 'VPEVnfSsh'
    }

    def test___init__(self):
        vnfd_helper = vnf_base.VnfdHelper(self.VNFD_0)
        config_create = vpe_vnf.ConfigCreate(vnfd_helper, 2)
        self.assertEqual(config_create.uplink_ports, ['xe0'])
        self.assertEqual(config_create.downlink_ports, ['xe1'])
        self.assertEqual(config_create.socket, 2)

    def test_dpdk_port_to_link_id(self):
        vnfd_helper = vnf_base.VnfdHelper(self.VNFD_0)
        config_create = vpe_vnf.ConfigCreate(vnfd_helper, 2)
        self.assertEqual(config_create.dpdk_port_to_link_id_map, {'xe0': 0, 'xe1': 1})

    def test_vpe_initialize(self):
        vnfd_helper = vnf_base.VnfdHelper(self.VNFD_0)
        config_create = vpe_vnf.ConfigCreate(vnfd_helper, 2)
        config = configparser.ConfigParser()
        config_create.vpe_initialize(config)
        self.assertEqual(config.get('EAL', 'log_level'), '0')
        self.assertEqual(config.get('PIPELINE0', 'type'), 'MASTER')
        self.assertEqual(config.get('PIPELINE0', 'core'), 's2C0')
        self.assertEqual(config.get('MEMPOOL0', 'pool_size'), '256K')
        self.assertEqual(config.get('MEMPOOL1', 'pool_size'), '2M')

    def test_vpe_rxq(self):
        vnfd_helper = vnf_base.VnfdHelper(self.VNFD_0)
        config_create = vpe_vnf.ConfigCreate(vnfd_helper, 2)
        config = configparser.ConfigParser()
        config_create.downlink_ports = ['xe0']
        config_create.vpe_rxq(config)
        self.assertEqual(config.get('RXQ0.0', 'mempool'), 'MEMPOOL1')

    def test_get_sink_swq(self):
        vnfd_helper = vnf_base.VnfdHelper(self.VNFD_0)
        config_create = vpe_vnf.ConfigCreate(vnfd_helper, 2)
        config = configparser.ConfigParser()
        config.add_section('PIPELINE0')
        config.set('PIPELINE0', 'key1', 'value1')
        config.set('PIPELINE0', 'key2', 'value2 SINK')
        config.set('PIPELINE0', 'key3', 'TM value3')
        config.set('PIPELINE0', 'key4', 'value4')
        config.set('PIPELINE0', 'key5', 'the SINK value5')

        self.assertEqual(config_create.get_sink_swq(config, 'PIPELINE0', 'key1', 5), 'SWQ-1')
        self.assertEqual(config_create.get_sink_swq(config, 'PIPELINE0', 'key2', 5), 'SWQ-1 SINK0')
        self.assertEqual(config_create.get_sink_swq(config, 'PIPELINE0', 'key3', 5), 'SWQ-1 TM5')
        config_create.sw_q += 1
        self.assertEqual(config_create.get_sink_swq(config, 'PIPELINE0', 'key4', 5), 'SWQ0')
        self.assertEqual(config_create.get_sink_swq(config, 'PIPELINE0', 'key5', 5), 'SWQ0 SINK1')

    def test_generate_vpe_script(self):
        vnfd_helper = vnf_base.VnfdHelper(self.VNFD_0)
        vpe_config_vnf = vpe_vnf.ConfigCreate(vnfd_helper, 2)
        intf = [
            {
                "name": 'xe1',
                "virtual-interface": {
                    "dst_ip": "1.1.1.1",
                    "dst_mac": "00:00:00:00:00:00:02",
                },
            },
            {
                "name": 'xe2',
                "virtual-interface": {
                    "dst_ip": "1.1.1.1",
                    "dst_mac": "00:00:00:00:00:00:02",
                },
            },
        ]
        vpe_config_vnf.downlink_ports = ['xe1']
        vpe_config_vnf.uplink_ports = ['xe2']
        result = vpe_config_vnf.generate_vpe_script(intf)
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, '')

    def test_create_vpe_config(self):
        vnfd_helper = vnf_base.VnfdHelper(self.VNFD_0)
        config_create = vpe_vnf.ConfigCreate(vnfd_helper, 23)
        config_create.uplink_ports = ['xe1']
        with mock.patch.object(config_create, 'vpe_upstream') as mock_up, \
                mock.patch.object(config_create, 'vpe_downstream') as \
                mock_down, \
                mock.patch.object(config_create, 'vpe_tmq') as mock_tmq, \
                mock.patch.object(config_create, 'vpe_initialize') as \
                mock_ini, \
                mock.patch.object(config_create, 'vpe_rxq') as mock_rxq:
            mock_ini_obj = mock.Mock()
            mock_rxq_obj = mock.Mock()
            mock_up_obj = mock.Mock()
            mock_down_obj = mock.Mock()
            mock_tmq_obj = mock.Mock()
            mock_ini.return_value = mock_ini_obj
            mock_rxq.return_value = mock_rxq_obj
            mock_up.return_value = mock_up_obj
            mock_down.return_value = mock_down_obj
            mock_tmq.return_value = mock_tmq_obj
            config_create.create_vpe_config('fake_config_file')

        mock_rxq.assert_called_once_with(mock_ini_obj)
        mock_up.assert_called_once_with('fake_config_file', 0)
        mock_down.assert_called_once_with('fake_config_file', 0)
        mock_tmq.assert_called_once_with(mock_down_obj, 0)
        mock_up_obj.write.assert_called_once()
        mock_tmq_obj.write.assert_called_once()


class TestVpeApproxVnf(unittest.TestCase):

    VNFD_0 = {
        'short-name': 'VpeVnf',
        'vdu': [
            {
                'routing_table': [
                    {
                        'network': '152.16.100.20',
                        'netmask': '255.255.255.0',
                        'gateway': '152.16.100.20',
                        'if': 'xe0',
                    },
                    {
                        'network': '152.16.40.20',
                        'netmask': '255.255.255.0',
                        'gateway': '152.16.40.20',
                        'if': 'xe1',
                    },
                ],
                'description': 'VPE approximation using DPDK',
                'name': 'vpevnf-baremetal',
                'nd_route_tbl': [
                    {
                        'network': '0064:ff9b:0:0:0:0:9810:6414',
                        'netmask': '112',
                        'gateway': '0064:ff9b:0:0:0:0:9810:6414',
                        'if': 'xe0',
                    },
                    {
                        'network': '0064:ff9b:0:0:0:0:9810:2814',
                        'netmask': '112',
                        'gateway': '0064:ff9b:0:0:0:0:9810:2814',
                        'if': 'xe1',
                    },
                ],
                'id': 'vpevnf-baremetal',
                'external-interface': [
                    {
                        'virtual-interface': {
                            'dst_mac': '00:00:00:00:00:04',
                            'vpci': '0000:05:00.0',
                            'local_ip': '152.16.100.19',
                            'type': 'PCI-PASSTHROUGH',
                            'netmask': '255.255.255.0',
                            'dpdk_port_num': 0,
                            'bandwidth': '10 Gbps',
                            'driver': "i40e",
                            'dst_ip': '152.16.100.20',
                            'local_iface_name': 'xe0',
                            'local_mac': '00:00:00:00:00:02',
                            'vld_id': 'uplink_0',
                            'ifname': 'xe0',
                        },
                        'vnfd-connection-point-ref': 'xe0',
                        'name': 'xe0',
                    },
                    {
                        'virtual-interface': {
                            'dst_mac': '00:00:00:00:00:03',
                            'vpci': '0000:05:00.1',
                            'local_ip': '152.16.40.19',
                            'type': 'PCI-PASSTHROUGH',
                            'driver': "i40e",
                            'netmask': '255.255.255.0',
                            'dpdk_port_num': 1,
                            'bandwidth': '10 Gbps',
                            'dst_ip': '152.16.40.20',
                            'local_iface_name': 'xe1',
                            'local_mac': '00:00:00:00:00:01',
                            'vld_id': 'downlink_0',
                            'ifname': 'xe1',
                        },
                        'vnfd-connection-point-ref': 'xe1',
                        'name': 'xe1',
                    },
                ],
            },
        ],
        'description': 'Vpe approximation using DPDK',
        'mgmt-interface': {
            'vdu-id': 'vpevnf-baremetal',
            'host': '1.2.1.1',
            'password': 'r00t',
            'user': 'root',
            'ip': '1.2.1.1',
        },
        'benchmark': {
            'kpi': [
                'packets_in',
                'packets_fwd',
                'packets_dropped',
            ],
        },
        'connection-point': [
            {
                'type': 'VPORT',
                'name': 'xe0',
            },
            {
                'type': 'VPORT',
                'name': 'xe1',
            },
        ],
        'id': 'VpeApproxVnf',
        'name': 'VPEVnfSsh',
    }

    VNFD = {
        'vnfd:vnfd-catalog': {
            'vnfd': [
                VNFD_0,
            ],
        },
    }

    SCENARIO_CFG = {
        'options': {
            'packetsize': 64,
            'traffic_type': 4,
            'rfc2544': {
                'allowed_drop_rate': '0.8 - 1',
            },
            'vnf__1': {
                'cfg': 'acl_1rule.yaml',
                'vnf_config': {
                    'lb_config': 'SW',
                    'lb_count': 1,
                    'worker_config':
                    '1C/1T',
                    'worker_threads': 1,
                },
            }
        },
        'task_id': 'a70bdf4a-8e67-47a3-9dc1-273c14506eb7',
        'tc': 'tc_ipv4_1Mflow_64B_packetsize',
        'runner': {
            'object': 'NetworkServiceTestCase',
            'interval': 35,
            'output_filename': '/tmp/yardstick.out',
            'runner_id': 74476,
            'duration': 400,
            'type': 'Duration',
        },
        'traffic_profile': 'ipv4_throughput_vpe.yaml',
        'traffic_options': {
            'flow': 'ipv4_Packets_vpe.yaml',
            'imix': 'imix_voice.yaml',
        },
        'type': 'ISB',
        'nodes': {
            'tg__2': 'trafficgen_2.yardstick',
            'tg__1': 'trafficgen_1.yardstick',
            'vnf__1': 'vnf.yardstick',
        },
        'topology': 'vpe-tg-topology-baremetal.yaml',
    }

    CONTEXT_CFG = {
        'nodes': {
            'tg__2': {
                'member-vnf-index': '3',
                'role': 'TrafficGen',
                'name': 'trafficgen_2.yardstick',
                'vnfd-id-ref': 'tg__2',
                'ip': '1.2.1.1',
                'interfaces': {
                    'xe0': {
                        'local_iface_name': 'ens513f0',
                        'vld_id': vpe_vnf.VpeApproxVnf.DOWNLINK,
                        'netmask': '255.255.255.0',
                        'local_ip': '152.16.40.20',
                        'dst_mac': '00:00:00:00:00:01',
                        'local_mac': '00:00:00:00:00:03',
                        'dst_ip': '152.16.40.19',
                        'driver': 'ixgbe',
                        'vpci': '0000:02:00.0',
                        'dpdk_port_num': 0,
                    },
                    'xe1': {
                        'local_iface_name': 'ens513f1',
                        'netmask': '255.255.255.0',
                        'network': '202.16.100.0',
                        'local_ip': '202.16.100.20',
                        'local_mac': '00:1e:67:d0:60:5d',
                        'driver': 'ixgbe',
                        'vpci': '0000:02:00.1',
                        'dpdk_port_num': 1,
                    },
                },
                'password': 'r00t',
                'VNF model': 'l3fwd_vnf.yaml',
                'user': 'root',
            },
            'tg__1': {
                'member-vnf-index': '1',
                'role': 'TrafficGen',
                'name': 'trafficgen_1.yardstick',
                'vnfd-id-ref': 'tg__1',
                'ip': '1.2.1.1',
                'interfaces': {
                    'xe0': {
                        'local_iface_name': 'ens785f0',
                        'vld_id': vpe_vnf.VpeApproxVnf.UPLINK,
                        'netmask': '255.255.255.0',
                        'local_ip': '152.16.100.20',
                        'dst_mac': '00:00:00:00:00:02',
                        'local_mac': '00:00:00:00:00:04',
                        'dst_ip': '152.16.100.19',
                        'driver': 'i40e',
                        'vpci': '0000:05:00.0',
                        'dpdk_port_num': 0,
                    },
                    'xe1': {
                        'local_iface_name': 'ens785f1',
                        'netmask': '255.255.255.0',
                        'local_ip': '152.16.100.21',
                        'local_mac': '00:00:00:00:00:01',
                        'driver': 'i40e',
                        'vpci': '0000:05:00.1',
                        'dpdk_port_num': 1,
                    },
                },
                'password': 'r00t',
                'VNF model': 'tg_rfc2544_tpl.yaml',
                'user': 'root',
            },
            'vnf__1': {
                'name': 'vnf.yardstick',
                'vnfd-id-ref': 'vnf__1',
                'ip': '1.2.1.1',
                'interfaces': {
                    'xe0': {
                        'local_iface_name': 'ens786f0',
                        'vld_id': vpe_vnf.VpeApproxVnf.UPLINK,
                        'netmask': '255.255.255.0',
                        'local_ip': '152.16.100.19',
                        'dst_mac': '00:00:00:00:00:04',
                        'local_mac': '00:00:00:00:00:02',
                        'dst_ip': '152.16.100.20',
                        'driver': 'i40e',
                        'vpci': '0000:05:00.0',
                        'dpdk_port_num': 0,
                    },
                    'xe1': {
                        'local_iface_name': 'ens786f1',
                        'vld_id': vpe_vnf.VpeApproxVnf.DOWNLINK,
                        'netmask': '255.255.255.0',
                        'local_ip': '152.16.40.19',
                        'dst_mac': '00:00:00:00:00:03',
                        'local_mac': '00:00:00:00:00:01',
                        'dst_ip': '152.16.40.20',
                        'driver': 'i40e',
                        'vpci': '0000:05:00.1',
                        'dpdk_port_num': 1,
                    },
                },
                'routing_table': [
                    {
                        'netmask': '255.255.255.0',
                        'gateway': '152.16.100.20',
                        'network': '152.16.100.20',
                        'if': 'xe0',
                    },
                    {
                        'netmask': '255.255.255.0',
                        'gateway': '152.16.40.20',
                        'network': '152.16.40.20',
                        'if': 'xe1',
                    },
                ],
                'member-vnf-index': '2',
                'host': '1.2.1.1',
                'role': 'vnf',
                'user': 'root',
                'nd_route_tbl': [
                    {
                        'netmask': '112',
                        'gateway': '0064:ff9b:0:0:0:0:9810:6414',
                        'network': '0064:ff9b:0:0:0:0:9810:6414',
                        'if': 'xe0',
                    },
                    {
                        'netmask': '112',
                        'gateway': '0064:ff9b:0:0:0:0:9810:2814',
                        'network': '0064:ff9b:0:0:0:0:9810:2814',
                        'if': 'xe1',
                    },
                ],
                'password': 'r00t',
                'VNF model': 'vpe_vnf.yaml',
            },
        },
    }

    def setUp(self):
        self._mock_time_sleep = mock.patch.object(time, 'sleep')
        self.mock_time_sleep = self._mock_time_sleep.start()
        self.addCleanup(self._stop_mocks)

    def _stop_mocks(self):
        self._mock_time_sleep.stop()

    def test___init__(self):
        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        self.assertIsNone(vpe_approx_vnf._vnf_process)

    @mock.patch.object(ctx_base.Context, 'get_physical_node_from_server',
                       return_value='mock_node')
    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_collect_kpi_sa_not_running(self, ssh, *args):
        test_base.mock_ssh(ssh)

        resource = mock.Mock(autospec=ResourceProfile)
        resource.check_if_system_agent_running.return_value = 1, ''
        resource.amqp_collect_nfvi_kpi.return_value = {'foo': 234}
        resource.check_if_system_agent_running.return_value = (1, None)

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf.scenario_helper.scenario_cfg = {
            'nodes': {vpe_approx_vnf.name: "mock"}
        }
        vpe_approx_vnf.q_in = mock.MagicMock()
        vpe_approx_vnf.q_out = mock.MagicMock()
        vpe_approx_vnf.q_out.qsize = mock.Mock(return_value=0)
        vpe_approx_vnf.resource_helper.resource = resource

        expected = {
            'physical_node': 'mock_node',
            'pkt_in_down_stream': 0,
            'pkt_in_up_stream': 0,
            'pkt_drop_down_stream': 0,
            'pkt_drop_up_stream': 0,
            'collect_stats': {'core': {}},
        }
        self.assertEqual(vpe_approx_vnf.collect_kpi(), expected)

    @mock.patch.object(ctx_base.Context, 'get_physical_node_from_server',
                       return_value='mock_node')
    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_collect_kpi_sa_running(self, ssh, *args):
        test_base.mock_ssh(ssh)

        resource = mock.Mock(autospec=ResourceProfile)
        resource.check_if_system_agent_running.return_value = 0, '1234'
        resource.amqp_collect_nfvi_kpi.return_value = {'foo': 234}

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf.scenario_helper.scenario_cfg = {
            'nodes': {vpe_approx_vnf.name: "mock"}
        }
        vpe_approx_vnf.q_in = mock.MagicMock()
        vpe_approx_vnf.q_out = mock.MagicMock()
        vpe_approx_vnf.q_out.qsize = mock.Mock(return_value=0)
        vpe_approx_vnf.resource_helper.resource = resource

        expected = {
            'physical_node': 'mock_node',
            'pkt_in_down_stream': 0,
            'pkt_in_up_stream': 0,
            'pkt_drop_down_stream': 0,
            'pkt_drop_up_stream': 0,
            'collect_stats': {'core': {'foo': 234}},
        }
        self.assertEqual(vpe_approx_vnf.collect_kpi(), expected)

    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_vnf_execute(self, ssh):
        test_base.mock_ssh(ssh)
        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf.q_in = mock.MagicMock()
        vpe_approx_vnf.q_out = mock.MagicMock()
        vpe_approx_vnf.q_out.qsize = mock.Mock(return_value=0)
        self.assertEqual(vpe_approx_vnf.vnf_execute("quit", 0), '')

    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_run_vpe(self, ssh):
        test_base.mock_ssh(ssh)

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf.tc_file_name = get_file_abspath(TEST_FILE_YAML)
        vpe_approx_vnf.vnf_cfg = {
            'lb_config': 'SW',
            'lb_count': 1,
            'worker_config': '1C/1T',
            'worker_threads': 1,
        }
        vpe_approx_vnf.scenario_helper.scenario_cfg = {
            'options': {
                NAME: {
                    'traffic_type': '4',
                    'topology': 'nsb_test_case.yaml',
                    'vnf_config': 'vpe_config',
                }
            }
        }
        vpe_approx_vnf.topology = "nsb_test_case.yaml"
        vpe_approx_vnf.nfvi_type = "baremetal"
        vpe_approx_vnf._provide_config_file = mock.Mock()
        vpe_approx_vnf._build_config = mock.MagicMock()

        self.assertIsInstance(vpe_approx_vnf.ssh_helper, mock.Mock)
        self.assertIsInstance(vpe_approx_vnf.ssh_helper, mock.Mock)
        self.assertIsNone(vpe_approx_vnf._run())

    @mock.patch("yardstick.network_services.vnf_generic.vnf.sample_vnf.MultiPortConfig")
    @mock.patch("yardstick.network_services.vnf_generic.vnf.vpe_vnf.ConfigCreate")
    @mock.patch("six.moves.builtins.open")
    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_build_config(self, ssh, *args):
        test_base.mock_ssh(ssh)
        vpe_approx_vnf = vpe_vnf.VpeApproxSetupEnvHelper(
            mock.MagicMock(), mock.MagicMock(), mock.MagicMock())
        vpe_approx_vnf.tc_file_name = get_file_abspath(TEST_FILE_YAML)
        vpe_approx_vnf.generate_port_pairs = mock.Mock()
        vpe_approx_vnf.vnf_cfg = {
            'lb_config': 'SW',
            'lb_count': 1,
            'worker_config': '1C/1T',
            'worker_threads': 1,
        }
        vpe_approx_vnf.scenario_helper.scenario_cfg = {
            'options': {
                NAME: {
                    'traffic_type': '4',
                    'topology': 'nsb_test_case.yaml',
                    'vnf_config': 'vpe_config',
                }
            }
        }
        vpe_approx_vnf.topology = "nsb_test_case.yaml"
        vpe_approx_vnf.nfvi_type = "baremetal"
        vpe_approx_vnf._provide_config_file = mock.Mock()

        vpe_approx_vnf.ssh_helper = mock.MagicMock()
        vpe_approx_vnf.scenario_helper = mock.MagicMock()
        vpe_approx_vnf.ssh_helper.bin_path = mock.Mock()
        vpe_approx_vnf.ssh_helper.upload_config_file = mock.MagicMock()
        self.assertIsNone(vpe_approx_vnf._build_vnf_ports())

        vpe_approx_vnf.ssh_helper.provision_tool = mock.Mock(return_value='tool_path')
        vpe_approx_vnf.ssh_helper.all_ports = mock.Mock()
        vpe_approx_vnf.vnfd_helper.port_nums = mock.Mock(return_value=[0, 1])
        vpe_approx_vnf.scenario_helper.vnf_cfg = {'lb_config': 'HW'}

        expected = 'sudo tool_path -p 0x3 -f /tmp/vpe_config -s /tmp/vpe_script  --hwlb 3'
        self.assertEqual(vpe_approx_vnf.build_config(), expected)

    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_wait_for_instantiate(self, ssh):
        test_base.mock_ssh(ssh)

        mock_process = mock.Mock(autospec=Process)
        mock_process.is_alive.return_value = True
        mock_process.exitcode = 432

        mock_q_out = mock.Mock(autospec=Queue)
        mock_q_out.get.side_effect = iter(["pipeline>"])
        mock_q_out.qsize.side_effect = range(1, -1, -1)

        mock_resource = mock.MagicMock()

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf._vnf_process = mock_process
        vpe_approx_vnf.q_out = mock_q_out
        vpe_approx_vnf.queue_wrapper = mock.Mock(
            autospec=vnf_base.QueueFileWrapper)
        vpe_approx_vnf.resource_helper.resource = mock_resource

        vpe_approx_vnf.q_out.put("pipeline>")
        self.assertEqual(vpe_approx_vnf.wait_for_instantiate(), 432)

    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_wait_for_instantiate_fragmented(self, ssh):
        test_base.mock_ssh(ssh)

        mock_process = mock.Mock(autospec=Process)
        mock_process.is_alive.return_value = True
        mock_process.exitcode = 432

        # test that fragmented pipeline prompt is recognized
        mock_q_out = mock.Mock(autospec=Queue)
        mock_q_out.get.side_effect = iter(["wow pipel", "ine>"])
        mock_q_out.qsize.side_effect = range(2, -1, -1)

        mock_resource = mock.MagicMock()

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf._vnf_process = mock_process
        vpe_approx_vnf.q_out = mock_q_out
        vpe_approx_vnf.queue_wrapper = mock.Mock(
            autospec=vnf_base.QueueFileWrapper)
        vpe_approx_vnf.resource_helper.resource = mock_resource

        self.assertEqual(vpe_approx_vnf.wait_for_instantiate(), 432)

    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_wait_for_instantiate_crash(self, ssh):
        test_base.mock_ssh(ssh, exec_result=(1, "", ""))

        mock_process = mock.Mock(autospec=Process)
        mock_process.is_alive.return_value = False
        mock_process.exitcode = 432

        mock_resource = mock.MagicMock()

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf._vnf_process = mock_process
        vpe_approx_vnf.resource_helper.resource = mock_resource

        with self.assertRaises(RuntimeError) as raised:
            vpe_approx_vnf.wait_for_instantiate()

        self.assertIn('VNF process died', str(raised.exception))

    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_wait_for_instantiate_panic(self, ssh):
        test_base.mock_ssh(ssh, exec_result=(1, "", ""))

        mock_process = mock.Mock(autospec=Process)
        mock_process.is_alive.return_value = True
        mock_process.exitcode = 432

        mock_resource = mock.MagicMock()

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf._vnf_process = mock_process
        vpe_approx_vnf.resource_helper.resource = mock_resource

        vpe_approx_vnf.q_out.put("PANIC")
        with self.assertRaises(RuntimeError) as raised:
            vpe_approx_vnf.wait_for_instantiate()

        self.assertIn('Error starting', str(raised.exception))

    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_wait_for_instantiate_panic_fragmented(self, ssh):
        test_base.mock_ssh(ssh, exec_result=(1, "", ""))

        mock_process = mock.Mock(autospec=Process)
        mock_process.is_alive.return_value = True
        mock_process.exitcode = 432

        # test that fragmented PANIC is recognized
        mock_q_out = mock.Mock(autospec=Queue)
        mock_q_out.get.side_effect = iter(["omg PA", "NIC this is bad"])
        mock_q_out.qsize.side_effect = range(2, -1, -1)

        mock_resource = mock.MagicMock()

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf._vnf_process = mock_process
        vpe_approx_vnf.q_out = mock_q_out
        vpe_approx_vnf.resource_helper.resource = mock_resource

        with self.assertRaises(RuntimeError) as raised:
            vpe_approx_vnf.wait_for_instantiate()

        self.assertIn('Error starting', str(raised.exception))

    @mock.patch.object(sample_vnf, 'VnfSshHelper')
    def test_terminate(self, ssh):
        test_base.mock_ssh(ssh)

        vpe_approx_vnf = vpe_vnf.VpeApproxVnf(NAME, self.VNFD_0, 'task_id')
        vpe_approx_vnf._vnf_process = mock.MagicMock()
        vpe_approx_vnf._resource_collect_stop = mock.Mock()
        vpe_approx_vnf.resource_helper = mock.MagicMock()

        self.assertIsNone(vpe_approx_vnf.terminate())
