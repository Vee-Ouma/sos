#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.
import zmq

import threading
from .utils import env
from .signatures import TargetSignatures, StepSignatures, WorkflowSignatures
from zmq.utils.monitor import recv_monitor_message

class Controller(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True

        self.target_signatures = TargetSignatures()
        self.step_signatures = StepSignatures()
        self.workflow_signatures = WorkflowSignatures()

        self._num_clients = 0

        # self.event_map = {}
        # for name in dir(zmq):
        #     if name.startswith('EVENT_'):
        #         value = getattr(zmq, name)
        #          self.event_map[value] = name

    def run(self):
        # there are two sockets
        #
        # signature_push is used to write signatures. It is a single push operation with no reply.
        # signature_req is used to query information. The sender would need to get an response.
        push_socket = env.zmq_context.socket(zmq.PULL)
        env.config['sockets']['signature_push'] = push_socket.bind_to_random_port('tcp://127.0.0.1')
        req_socket = env.zmq_context.socket(zmq.REP)
        env.config['sockets']['signature_req'] = req_socket.bind_to_random_port('tcp://127.0.0.1')

        monitor_socket = req_socket.get_monitor_socket()

        # Process messages from receiver and controller
        poller = zmq.Poller()
        poller.register(push_socket, zmq.POLLIN)
        poller.register(req_socket, zmq.POLLIN)
        poller.register(monitor_socket, zmq.POLLIN)

        while True:
            try:
                socks = dict(poller.poll())

                if push_socket in socks:
                    msg = push_socket.recv_pyobj()
                    if msg[0] == 'workflow':
                        self.workflow_signatures.write(*msg[1:])
                    elif msg[0] == 'target':
                        self.target_signatures.set(*msg[1:])
                    elif msg[0] == 'step':
                        self.step_signatures.set(*msg[1:])
                    else:
                        env.logger.warning(f'Unknown message passed {msg}')

                if req_socket in socks:
                    msg = req_socket.recv_pyobj()
                    if msg[0] == 'workflow':
                        if msg[1] == 'clear':
                            self.workflow_signatures.clear()
                            req_socket.send_pyobj('ok')
                        elif msg[1] == 'placeholders':
                            req_socket.send_pyobj(self.workflow_signatures.placeholders(msg[2]))
                        else:
                            env.logger.warning(f'Unknown request {msg}')
                    elif msg[0] == 'target':
                        if msg[1] == 'get':
                            req_socket.send_pyobj(self.target_signatures.get(msg[2]))
                        else:
                            env.logger.warning(f'Unknown request {msg}')
                    elif msg[0] == 'step':
                        if msg[1] == 'get':
                            req_socket.send_pyobj(self.step_signatures.get(*msg[2:]))
                        else:
                            env.logger.warning(f'Unknown request {msg}')
                    elif msg[0] == 'nprocs':
                        req_socket.send_pyobj(self._num_clients)
                    else:
                        raise RuntimeError(f'Unrecognized request {msg}')

                if monitor_socket in socks:
                    evt = recv_monitor_message(monitor_socket)
                    if evt['event'] == zmq.EVENT_ACCEPTED:
                        self._num_clients += 1
                    elif evt['event'] == zmq.EVENT_DISCONNECTED:
                        self._num_clients -= 1
            except Exception as e:
                env.logger.warning(f'Signature handling warning: {e}')
            except KeyboardInterrupt:
                break