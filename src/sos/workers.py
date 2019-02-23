#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import multiprocessing as mp
import os
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Optional

import zmq

from ._version import __version__
from .controller import (close_socket, connect_controllers, create_socket,
                         disconnect_controllers)
from .eval import SoS_exec
from .executor_utils import kill_all_subprocesses
from .targets import sos_targets
from .utils import (WorkflowDict, env, get_traceback, load_config_files,
                    short_repr, ProcessKilled)

def signal_handler(*args, **kwargs):
    raise ProcessKilled()

class SoS_Worker(mp.Process):
    '''
    Worker process to process SoS step or workflow in separate process.
    '''

    def __init__(self, config: Optional[Dict[str, Any]] = None, args: Optional[Any] = None,
            **kwargs) -> None:
        '''

        config:
            values for command line options

            config_file: -c
            output_dag: -d

        args:
            command line argument passed to workflow. However, if a dictionary is passed,
            then it is assumed to be a nested workflow where parameters are made
            immediately available.
        '''
        # the worker process knows configuration file, command line argument etc
        super(SoS_Worker, self).__init__(**kwargs)
        #
        self.config = config

        self.args = [] if args is None else args

        # there can be multiple jobs for this worker, each using their own port and socket
        self._master_sockets = []
        self._master_ports = []
        self._stack_idx = 0

    def reset_dict(self):
        env.sos_dict = WorkflowDict()
        env.parameter_vars.clear()

        env.sos_dict.set('__args__', self.args)
        # initial values
        env.sos_dict.set('SOS_VERSION', __version__)
        env.sos_dict.set('__step_output__', sos_targets())

        # load configuration files
        load_config_files(env.config['config_file'])

        SoS_exec('import os, sys, glob', None)
        SoS_exec('from sos.runtime import *', None)

        if isinstance(self.args, dict):
            for key, value in self.args.items():
                if not key.startswith('__'):
                    env.sos_dict.set(key, value)

    def run(self):
        # env.logger.warning(f'Worker created {os.getpid()}')
        env.config.update(self.config)
        env.zmq_context = connect_controllers()

        # create controller socket
        env.ctrl_socket = create_socket(env.zmq_context, zmq.REQ, 'worker backend')
        env.ctrl_socket.connect(f'tcp://127.0.0.1:{self.config["sockets"]["worker_backend"]}')

        signal.signal(signal.SIGTERM, signal_handler)

        # create at last one master socket
        env.master_socket = create_socket(env.zmq_context, zmq.PAIR)
        port = env.master_socket.bind_to_random_port('tcp://127.0.0.1')
        self._master_sockets.append(env.master_socket)
        self._master_ports.append(port)

        # result socket used by substeps
        env.result_socket = None
        env.result_socket_port = None

        # wait to handle jobs
        while True:
            try:
                if not self._process_job():
                    break
            except ProcessKilled:
                # in theory, this will not be executed because the exception
                # will be caught by the step executor, and then sent to the master
                # process, which will then trigger terminate() and send a None here.
                break
            except KeyboardInterrupt:
                break
        # Finished
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        kill_all_subprocesses(os.getpid())

        close_socket(env.result_socket, 'substep result', now=True)

        for socket in self._master_sockets:
            close_socket(socket, 'worker master', now=True)
        close_socket(env.ctrl_socket, now=True)
        disconnect_controllers(env.zmq_context)

    def push_env(self):
        self._stack_idx += 1
        env.switch(self._stack_idx)
        if len(self._master_sockets) > self._stack_idx:
            # if current stack is ok
            env.master_socket = self._master_sockets[self._stack_idx]
        else:
            # a new socket is needed
            env.master_socket = create_socket(env.zmq_context, zmq.PAIR)
            port = env.master_socket.bind_to_random_port('tcp://127.0.0.1')
            self._master_sockets.append(env.master_socket)
            self._master_ports.append(port)

    def pop_env(self):
        self._stack_idx -= 1
        env.switch(self._stack_idx)
        env.master_socket = self._master_sockets[self._stack_idx]

    def _process_job(self):
        # send the current socket number as a way to notify the availability of worker
        env.ctrl_socket.send_pyobj(self._master_ports[self._stack_idx])
        work = env.ctrl_socket.recv_pyobj()
        env.logger.trace(
            f'Worker {self.name} receives request {short_repr(work)} with master port {self._master_ports[self._stack_idx]}')

        if work is None:
            return False
        elif not work: # an empty task {}
            time.sleep(0.1)
            return True

        if isinstance(work, dict):
            self.run_substep(work)
            return True
        # step and workflow can yield
        runner = self.run_step(*work[1:]) if work[0] == 'step' else self.run_workflow(*work[1:])
        try:
            poller = next(runner)
            while True:
                # if request is None, it is a normal "break" and
                # we do not need to jump off
                if poller is None:
                    poller = runner.send(None)
                    continue

                while True:
                    if poller.poll(200):
                        poller = runner.send(None)
                        break
                    # now let us ask if the master has something else for us
                    self.push_env()
                    self._process_job()
                    self.pop_env()
        except StopIteration as e:
            pass
        env.logger.debug(
            f'Worker {self.name} completes request {short_repr(work)}')
        return True

    def run_workflow(self, workflow_id, wf, targets, args, shared, config):
        #
        #
        # get workflow, args, shared, and config
        from .workflow_executor import Base_Executor

        self.args = args
        env.config.update(config)
        self.reset_dict()
        # we are in a separate process and need to set verbosity from workflow config
        # but some tests do not provide verbosity
        env.verbosity = config.get('verbosity', 2)
        env.logger.debug(
            f'Worker {self.name} working on a workflow {workflow_id} with args {args}')
        executer = Base_Executor(wf, args=args, shared=shared, config=config)
        # we send the socket to subworkflow, which would send
        # everything directly to the master process, so we do not
        # have to collect result here
        try:
            runner = executer.run_as_nested(targets=targets, parent_socket=env.master_socket,
                         my_workflow_id=workflow_id)
            try:
                yreq = next(runner)
                while True:
                    yres = yield yreq
                    yreq = runner.send(yres)
            except StopIteration:
                pass

        except Exception as e:
            env.master_socket.send_pyobj(e)

    def run_step(self, section, context, shared, args, config, verbosity):
        from .step_executor import Step_Executor

        env.logger.debug(
            f'Worker {self.name} working on {section.step_name()} with args {args}')
        env.config.update(config)
        env.verbosity = verbosity
        #
        self.args = args
        self.reset_dict()

        # Execute global namespace. The reason why this is executed outside of
        # step is that the content of the dictioary might be overridden by context
        # variables.
        try:
            SoS_exec(section.global_def)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.stderr)
        except RuntimeError:
            if env.verbosity > 2:
                sys.stderr.write(get_traceback())
            raise

        # clear existing keys, otherwise the results from some random result
        # might mess with the execution of another step that does not define input
        for k in ['__step_input__', '__default_output__', '__step_output__']:
            if k in env.sos_dict:
                env.sos_dict.pop(k)
        # if the step has its own context
        env.sos_dict.quick_update(shared)
        # context should be updated after shared because context would contain the
        # correct __step_output__ of the step, whereas shared might contain
        # __step_output__ from auxiliary steps. #526
        env.sos_dict.quick_update(context)

        executor = Step_Executor(
            section, env.master_socket, mode=env.config['run_mode'])

        runner = executor.run()
        try:
            yreq = next(runner)
            while True:
                yres = yield yreq
                yreq = runner.send(yres)
        except StopIteration:
            pass

    def run_substep(self, work):
        from .substep_executor import execute_substep
        execute_substep(**work)


class WorkerManager(object):
    # manager worker processes

    def __init__(self, max_workers, backend_socket):
        self._max_workers = max_workers

        self._workers = []
        self._num_workers = 0
        self._n_requested = 0
        self._n_processed = 0

        self._worker_alive_time = time.time()
        self._last_avail_time = time.time()

        self._substep_requests = []
        self._step_requests = {}

        self._worker_backend_socket = backend_socket

        self._available_ports = set()
        self._claimed_ports = set()

        # start a worker
        self.start()

    def report(self, msg):
        return
        env.logger.warning(f'{msg}: workers: {self._num_workers}, requested: {self._n_requested}, processed: {self._n_processed}')

    def add_request(self, port, msg):
        if port is None:
            self._substep_requests.insert(0, msg)
        else:
            self._step_requests[port] = msg
        self._n_requested += 1
        self.report(f'add_request')

        # start a worker is necessary (max_procs could be incorrectly set to be 0 or less)
        # if we are just starting, so do not start two workers
        if self._n_processed > 0 and not self._available_ports and self._num_workers < self._max_workers:
            self.start()

    def worker_available(self):
        if self._available_ports:
            claimed = self._available_ports.pop()
            self._claimed_ports.add(claimed)
            return claimed
        # no available port, can we start a new worker?
        if self._num_workers < self._max_workers:
            self.start()
        return None

    def process_request(self, port):
        if port in self._step_requests:
            # if the port is available
            self._worker_backend_socket.send(self._step_requests.pop(port))
            self._last_avail_time = time.time()
            self._n_processed += 1
            self.report(f'process step/workflow with port {port}')
            # port should be in claimed ports
            self._claimed_ports.remove(port)
        elif port in self._claimed_ports:
            # the port is claimed, but the real message is not yet available
            self._worker_backend_socket.send_pyobj({})
            # self.report(f'pending with claimed {port}')
        elif self._substep_requests:
            # port is not claimed, free to use for substep worker
            msg = self._substep_requests.pop()
            self._worker_backend_socket.send_pyobj(msg)
            self._last_avail_time = time.time()
            self._n_processed += 1
            self.report('process substep with port {port}')
            # port can however be in available ports
            if port in self._available_ports:
                self._available_ports.remove(port)
        else:
            # the port will be available for others to use
            self._available_ports.add(port)
            self._worker_backend_socket.send_pyobj({})
            # self.report(f'pending with port {port}')

    def start(self):
        worker = SoS_Worker(env.config)
        worker.start()
        self._workers.append(worker)
        self._num_workers += 1
        self.report('start worker')

    def check_workers(self):
        '''Kill workers that have been pending for a while and check if all workers
        are alive. '''
        if time.time() - self._worker_alive_time > 5:
            self._worker_alive_time = time.time()
            self._workers = [worker for worker in self._workers if worker.is_alive()]
            if len(self._workers) < self._num_workers:
                raise ProcessKilled('One of the workers has been killed.')
        # if there is at least one request has been processed in 5 seconds
        if time.time() - self._last_avail_time < 5:
            return
        # we keep at least one worker
        while self._num_workers > 1 and self._worker_backend_socket.poll(100):
            port = self._worker_backend_socket.recv_pyobj()
            if port in self._claimed_ports:
                self._worker_backend_socket.send_pyobj({})
                continue
            if port in self._available_ports:
                self._available_ports.remove(port)
            self._worker_backend_socket.send_pyobj(None)
            self._num_workers -= 1
            self.report('kill a long standing workers')

    def kill_all(self):
        '''Kill all workers'''
        while self._num_workers > 0 and self._worker_backend_socket.poll(1000):
            self._worker_backend_socket.recv_pyobj()
            self._worker_backend_socket.send_pyobj(None)
            self._num_workers -= 1
            self.report('kill a done worker')