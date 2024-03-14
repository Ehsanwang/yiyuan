# -*- encoding=utf-8 -*-
import datetime
import time
from threading import Thread
import serial
import os
import logging


class UartThread(Thread):
    def __init__(self, uart_port, debug_port, uart_queue, main_queue, log_queue):
        super().__init__()
        self.uart_queue = uart_queue
        self.uart_port = uart_port
        self.main_queue = main_queue
        self.log_queue = log_queue
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.debug_port = debug_port
        self.debug_port_read_flag = True if self.debug_port != '' else False
        self.logger = logging.getLogger(__name__)

    def run(self):
        try:
            self.uart_port = serial.Serial(self.uart_port, baudrate=115200, timeout=0)
        except serial.serialutil.SerialException:
            input("UART端口被占用或端口设置错误，请关闭脚本并重新运行")
            exit()
        if self.debug_port != '':
            self.debug_port = serial.Serial(self.debug_port, baudrate=115200, timeout=0)
        self.uart_port.setDTR(False)
        self.uart_port.setRTS(False)
        while True:
            # 传入参数参考：['init_module', 5, 'M.2', 0.5, <threading.Event object at 0x...>]
            time.sleep(0.001)
            (func, *param), evt = ['0', '0'] if self.uart_queue.empty() else self.uart_queue.get()
            self.logger.info('{}->{}->{}'.format(func, param, evt)) if func != '0' else ''
            if func in self._methods_list:
                getattr(self.__class__, '{}'.format(func))(self, *param)
                self.main_queue.put(True)
                evt.set()
            if self.debug_port_read_flag:
                debug_log = self.debug_port.readline().decode('utf-8', 'ignore')
                if debug_log != '':
                    self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(debug_log))])
            else:
                debug_log = self.uart_port.readline().decode('utf-8', 'ignore')
                if debug_log != '':
                    self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(debug_log))])

    def set_dtr_true(self):
        self.uart_port.setDTR(True)

    def set_dtr_false(self):
        self.uart_port.setDTR(False)

    def set_rts_true(self):
        self.uart_port.setRTS(True)

    def set_rts_false(self):
        self.uart_port.setRTS(False)