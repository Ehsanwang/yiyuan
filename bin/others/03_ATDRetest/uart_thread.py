# -*- encoding=utf-8 -*-
import datetime
import time
from threading import Thread
import serial
import os
import logging


class UartThread(Thread):
    def __init__(self, uart_port, debug_port, uart_queue, main_queue, log_queue, debug_port_pwd):
        super().__init__()
        self.uart_queue = uart_queue
        self.uart_port = uart_port
        self.main_queue = main_queue
        self.log_queue = log_queue
        self.debug_port_pwd = debug_port_pwd
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.debug_port = debug_port
        self.debug_port_read_flag = True if self.debug_port != '' else False
        self.logger = logging.getLogger(__name__)

    def run(self):
        try:
            self.uart_port = serial.Serial(self.uart_port, baudrate=115200, timeout=0)
        except serial.serialutil.SerialException:
            os.system("echo UART端口被占用，请关闭脚本并重新运行！ & pause >nul")
            exit()
        # if self.debug_port != '':
        #     self.debug_port = serial.Serial(self.debug_port, baudrate=115200, timeout=0)
        self.uart_port.setDTR(False)
        self.uart_port.setRTS(False)
        # timestamp = time.time()
        while True:
            # TODO:UART需要同时拉DTR和读取LOG
            # 传入参数参考：['init_module', 5, 'M.2', 0.5, <threading.Event object at 0x...>]
            time.sleep(0.001)
            (func, *param), evt = ['0', '0'] if self.uart_queue.empty() else self.uart_queue.get()
            self.logger.info('{}->{}->{}'.format(func, param, evt)) if func != '0' else ''
            if func in self._methods_list:
                getattr(self.__class__, '{}'.format(func))(self, *param)
                self.main_queue.put(True)
                evt.set()
            # if self.debug_port_read_flag:
            #     debug_log = self.debug_port.readline().decode('utf-8', 'ignore')
            #     if debug_log != '':
            #         self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(debug_log))])
            #         if "sdxprairie login:" in debug_log:
            #             self.debug_port.write('root\r\n'.encode('utf-8'))
            #         if 'Password:' in debug_log:
            #             self.debug_port.write('{}\r\n'.format(self.debug_port_pwd).encode('utf-8'))
            #             time.sleep(1)
            #             self.debug_port.write('cat /run/ql_voice_server.log\n'.format(self.debug_port_pwd).encode('utf-8'))
            #             while True:
            #                 debug_log = self.debug_port.readline().decode('utf-8', 'ignore')
            #                 self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), debug_log)])
            #                 if 'msg_id=0x2E' in debug_log and 'msg_id=0x1F' in debug_log:
            #                     return True
            #                 elif time.time()-timestamp > 120:
            #                     os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")
            # else:
            #     debug_log = self.uart_port.readline().decode('utf-8', 'ignore')
            #     if debug_log != '':
            #         self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(debug_log))])

    def set_dtr_true(self):
        self.uart_port.setDTR(True)
        self.logger.info('dtr: {}'.format(self.uart_port.dtr))

    def set_dtr_false(self):
        self.uart_port.setDTR(False)
        self.logger.info('dtr: {}'.format(self.uart_port.dtr))

    def set_rts_true(self):
        self.uart_port.setRTS(True)
        self.logger.info('rts: {}'.format(self.uart_port.rts))

    def set_rts_false(self):
        self.uart_port.setRTS(False)
        self.logger.info('rts: {}'.format(self.uart_port.rts))
