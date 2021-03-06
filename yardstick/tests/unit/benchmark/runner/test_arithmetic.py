##############################################################################
# Copyright (c) 2018 Nokia and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Apache License, Version 2.0
# which accompanies this distribution, and is available at
# http://www.apache.org/licenses/LICENSE-2.0
##############################################################################

import mock
import unittest
import multiprocessing
import os
import time

from yardstick.benchmark.runners import arithmetic


class ArithmeticRunnerTest(unittest.TestCase):
    class MyMethod(object):
        def __init__(self):
            self.count = 101

        def __call__(self, data):
            self.count += 1
            data['my_key'] = self.count
            return self.count

    def setUp(self):
        self.scenario_cfg = {
            'runner': {
                'interval': 0,
                'iter_type': 'nested_for_loops',
                'iterators': [
                    {
                        'name': 'stride',
                        'start': 64,
                        'stop': 128,
                        'step': 64
                    },
                    {
                        'name': 'size',
                        'start': 500,
                        'stop': 2000,
                        'step': 500
                    }
                ]
            },
            'type': 'some_type'
        }

        self.benchmark = mock.Mock()
        self.benchmark_cls = mock.Mock(return_value=self.benchmark)

    def _assert_defaults__worker_process_run_setup_and_teardown(self):
        self.benchmark_cls.assert_called_once_with(self.scenario_cfg, {})
        self.benchmark.setup.assert_called_once()
        self.benchmark.teardown.assert_called_once()

    @mock.patch.object(os, 'getpid')
    @mock.patch.object(multiprocessing, 'Process')
    def test__run_benchmark_called_with(self, mock_multiprocessing_process,
                                        mock_os_getpid):
        mock_os_getpid.return_value = 101

        runner = arithmetic.ArithmeticRunner({})
        benchmark_cls = mock.Mock()
        runner._run_benchmark(benchmark_cls, 'my_method', self.scenario_cfg,
                              {})
        mock_multiprocessing_process.assert_called_once_with(
            name='Arithmetic-some_type-101',
            target=arithmetic._worker_process,
            args=(runner.result_queue, benchmark_cls, 'my_method',
                  self.scenario_cfg, {}, runner.aborted, runner.output_queue))

    @mock.patch.object(os, 'getpid')
    def test__worker_process_runner_id(self, mock_os_getpid):
        mock_os_getpid.return_value = 101

        arithmetic._worker_process(mock.Mock(), self.benchmark_cls,
                                   'my_method', self.scenario_cfg, {},
                                   multiprocessing.Event(), mock.Mock())

        self.assertEqual(self.scenario_cfg['runner']['runner_id'], 101)

    @mock.patch.object(time, 'sleep')
    def test__worker_process_calls_nested_for_loops(self, mock_time_sleep):
        self.scenario_cfg['runner']['interval'] = 99

        arithmetic._worker_process(mock.Mock(), self.benchmark_cls,
                                   'my_method', self.scenario_cfg, {},
                                   multiprocessing.Event(), mock.Mock())

        self._assert_defaults__worker_process_run_setup_and_teardown()
        self.benchmark.my_method.assert_has_calls([mock.call({})] * 8)
        self.assertEqual(self.benchmark.my_method.call_count, 8)
        mock_time_sleep.assert_has_calls([mock.call(99)] * 8)
        self.assertEqual(mock_time_sleep.call_count, 8)

    @mock.patch.object(time, 'sleep')
    def test__worker_process_calls_tuple_loops(self, mock_time_sleep):
        self.scenario_cfg['runner']['interval'] = 99
        self.scenario_cfg['runner']['iter_type'] = 'tuple_loops'

        arithmetic._worker_process(mock.Mock(), self.benchmark_cls,
                                   'my_method', self.scenario_cfg, {},
                                   multiprocessing.Event(), mock.Mock())

        self._assert_defaults__worker_process_run_setup_and_teardown()
        self.benchmark.my_method.assert_has_calls([mock.call({})] * 2)
        self.assertEqual(self.benchmark.my_method.call_count, 2)
        mock_time_sleep.assert_has_calls([mock.call(99)] * 2)
        self.assertEqual(mock_time_sleep.call_count, 2)

    def test__worker_process_stored_options_nested_for_loops(self):
        arithmetic._worker_process(mock.Mock(), self.benchmark_cls,
                                   'my_method', self.scenario_cfg, {},
                                   multiprocessing.Event(), mock.Mock())

        self.assertDictEqual(self.scenario_cfg['options'],
                             {'stride': 128, 'size': 2000})

    def test__worker_process_stored_options_tuple_loops(self):
        self.scenario_cfg['runner']['iter_type'] = 'tuple_loops'

        arithmetic._worker_process(mock.Mock(), self.benchmark_cls,
                                   'my_method', self.scenario_cfg, {},
                                   multiprocessing.Event(), mock.Mock())

        self.assertDictEqual(self.scenario_cfg['options'],
                             {'stride': 128, 'size': 1000})

    def test__worker_process_aborted_set_early(self):
        aborted = multiprocessing.Event()
        aborted.set()
        arithmetic._worker_process(mock.Mock(), self.benchmark_cls,
                                   'my_method', self.scenario_cfg, {},
                                   aborted, mock.Mock())

        self._assert_defaults__worker_process_run_setup_and_teardown()
        self.assertEqual(self.scenario_cfg['options'], {})
        self.benchmark.my_method.assert_not_called()

    def test__worker_process_output_queue_nested_for_loops(self):
        self.benchmark.my_method = self.MyMethod()

        output_queue = multiprocessing.Queue()
        arithmetic._worker_process(mock.Mock(), self.benchmark_cls,
                                   'my_method', self.scenario_cfg, {},
                                   multiprocessing.Event(), output_queue)
        time.sleep(0.01)

        self._assert_defaults__worker_process_run_setup_and_teardown()
        self.assertEqual(self.benchmark.my_method.count, 109)
        result = []
        while not output_queue.empty():
            result.append(output_queue.get())
        self.assertListEqual(result, [102, 103, 104, 105, 106, 107, 108, 109])

    def test__worker_process_output_queue_tuple_loops(self):
        self.scenario_cfg['runner']['iter_type'] = 'tuple_loops'
        self.benchmark.my_method = self.MyMethod()

        output_queue = multiprocessing.Queue()
        arithmetic._worker_process(mock.Mock(), self.benchmark_cls,
                                   'my_method', self.scenario_cfg, {},
                                   multiprocessing.Event(), output_queue)
        time.sleep(0.01)

        self._assert_defaults__worker_process_run_setup_and_teardown()
        self.assertEqual(self.benchmark.my_method.count, 103)
        result = []
        while not output_queue.empty():
            result.append(output_queue.get())
        self.assertListEqual(result, [102, 103])

    def test__worker_process_queue_nested_for_loops(self):
        self.benchmark.my_method = self.MyMethod()

        queue = multiprocessing.Queue()
        timestamp = time.time()
        arithmetic._worker_process(queue, self.benchmark_cls, 'my_method',
                                   self.scenario_cfg, {},
                                   multiprocessing.Event(), mock.Mock())
        time.sleep(0.01)

        self._assert_defaults__worker_process_run_setup_and_teardown()
        self.assertEqual(self.benchmark.my_method.count, 109)
        count = 0
        while not queue.empty():
            count += 1
            result = queue.get()
            self.assertEqual(result['errors'], '')
            self.assertEqual(result['data'], {'my_key': count + 101})
            self.assertEqual(result['sequence'], count)
            self.assertGreater(result['timestamp'], timestamp)
            timestamp = result['timestamp']

    def test__worker_process_queue_tuple_loops(self):
        self.scenario_cfg['runner']['iter_type'] = 'tuple_loops'
        self.benchmark.my_method = self.MyMethod()

        queue = multiprocessing.Queue()
        timestamp = time.time()
        arithmetic._worker_process(queue, self.benchmark_cls, 'my_method',
                                   self.scenario_cfg, {},
                                   multiprocessing.Event(), mock.Mock())
        time.sleep(0.01)

        self._assert_defaults__worker_process_run_setup_and_teardown()
        self.assertEqual(self.benchmark.my_method.count, 103)
        count = 0
        while not queue.empty():
            count += 1
            result = queue.get()
            self.assertEqual(result['errors'], '')
            self.assertEqual(result['data'], {'my_key': count + 101})
            self.assertEqual(result['sequence'], count)
            self.assertGreater(result['timestamp'], timestamp)
            timestamp = result['timestamp']
