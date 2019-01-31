import logging
import sys
import traceback
from typing import List

import gevent
from request_collector.state_db import StateDBSqlite
from request_collector.store_monitor_request import StoreMonitorRequest

from raiden_libs.gevent_error_handler import register_error_handler
from raiden_libs.messages import Message, MonitorRequest
from raiden_libs.transport import Transport

log = logging.getLogger(__name__)


def error_handler(context, exc_info):
    log.critical("Unhandled exception terminating the program")
    traceback.print_exception(
        etype=exc_info[0],
        value=exc_info[1],
        tb=exc_info[2],
    )
    sys.exit()


class RequestCollector(gevent.Greenlet):
    def __init__(
        self,
        state_db: StateDBSqlite,
        transport: Transport,
    ):
        super().__init__()

        assert isinstance(transport, Transport)

        self.state_db = state_db
        self.transport = transport
        self.stop_event = gevent.event.Event()
        self.transport.add_message_callback(lambda message: self.on_message_event(message))

        self.task_list: List[gevent.Greenlet] = []

    def _run(self):
        register_error_handler(error_handler)
        self.transport.start()

        # this loop will wait until spawned greenlets complete
        while self.stop_event.is_set() is False:
            tasks = gevent.wait(self.task_list, timeout=5, count=1)
            if len(tasks) == 0:
                gevent.sleep(1)
                continue
            task = tasks[0]
            log.info('%s completed (%s)' % (task, task.value))
            self.task_list.remove(task)

    def stop(self):
        self.transport.stop()
        self.stop_event.set()

    def on_message_event(self, message):
        """This handles messages received over the Transport"""
        assert isinstance(message, Message)
        log.debug(message)
        if isinstance(message, MonitorRequest):
            self.on_monitor_request(message)
        else:
            log.warn('Ignoring unknown message type %s' % type(message))

    def on_monitor_request(
        self,
        monitor_request: MonitorRequest,
    ):
        """Called whenever a monitor proof message is received.
        This will spawn a greenlet and store its reference in an internal list.
        Return value of the greenlet is then checked in the main loop."""
        assert isinstance(monitor_request, MonitorRequest)
        self.start_task(
            StoreMonitorRequest(self.state_db, monitor_request),
        )

    def start_task(self, task: gevent.Greenlet):
        task.start()
        self.task_list.append(task)

    @property
    def monitor_requests(self):
        return self.state_db.get_monitor_requests()

    def wait_tasks(self):
        """Wait until all internal tasks are finished"""
        while True:
            if len(self.task_list) == 0:
                return
            gevent.sleep(1)
