# -*- encoding=utf-8 -*-
from threading import Thread
import logging


class RouteThread(Thread):
    def __init__(self, route_queue, uart_queue, process_queue, at_queue):
        super().__init__()
        self.route_queue = route_queue
        self.uart_queue = uart_queue
        self.process_queue = process_queue
        self.at_queue = at_queue
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.logger = logging.getLogger(__name__)

    def run(self):
        while True:
            # 接收到信息参考 ['Uart', 'init_module', 5, 'M.2', 0.5, <threading.Event object at 0x000001BBF6DCE8D0>]
            module, *param, evt = self.route_queue.get()
            self.logger.info('{}->{}->{}'.format(module, param, evt))
            module = module.lower()
            if module in self._methods_list:
                getattr(self.__class__, '{}'.format(module))(self, param, evt)

    def uart(self, param, evt):
        self.uart_queue.put([param, evt])

    def process(self, param, evt):
        self.process_queue.put([param, evt])

    def at(self, param, evt):
        self.at_queue.put([param, evt])
