# -*- encoding=utf-8 -*-
import random
import time
from threading import Event
import datetime
import logging
from functions import pause


class RestartManager:
    def __init__(self, main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port, evb, version, runtimes):
        self.route_queue = route_queue
        self.uart_queue = uart_queue
        self.at_queue = at_queue
        self.log_queue = log_queue
        self.at_port = at_port
        self.uart_port = uart_port
        self.evb = evb
        self.runtimes = runtimes
        self.version = version
        self.main_queue = main_queue
        self.logger = logging.getLogger(__name__)

    def route_queue_put(self, *args, queue=None):
        """
        往某个queue队列put内容，默认为None时向route_queue发送内容，并且接收main_queue队列如果有内容，就接收。
        :param args: 需要往queue中发送的内容
        :param queue: 指定queue发送，默认route_queue
        :return: main_queue内容
        """
        self.logger.info('{}->{}'.format(queue, args))
        if queue is None:
            evt = Event()
            self.route_queue.put([*args, evt])
            evt.wait()
        else:
            evt = Event()
            queue.put([*args, evt])
            evt.wait()
        _main_queue_data = self.main_queue.get(timeout=0.1)
        self.log_queue.put(['df', self.runtimes, 'error', 1]) if _main_queue_data is False else ''
        return _main_queue_data

    def init(self):
        if self.runtimes == 0:
            self.log_queue.put(['at_log', '{}initialize{}'.format('=' * 30, '=' * 30)])
            print("\rinitialize", end="")

        self.vbat()

        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)

        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False

        # 检测开机URC
        self.route_queue_put('AT', 'check_urc', self.runtimes)

        # 检测注网
        self.route_queue_put('AT', 'check_network', False, self.runtimes)

        # at+qcfg="aprstlevel",0
        main_queue_data = self.route_queue_put('AT', 'at+qcfg="aprstlevel",0', 15, 1, self.runtimes)
        if main_queue_data is False:
            return False
        # at+qcfg="modemrstlevel",0
        main_queue_data = self.route_queue_put('AT', 'at+qcfg="modemrstlevel",0', 15, 1, self.runtimes)
        if main_queue_data is False:
            return False
        # AT+QPCMV=1,0
        main_queue_data = self.route_queue_put('AT', 'AT+QPCMV=1,0', 15, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def vbat(self):
        """
        M.2 EVB：拉高DTR断电->检测驱动消失->拉低DTR上电；
        5G-EVB_V2.1：拉高RTS->拉高DTR断电->检测驱动消失->拉低DTR上电。
        :return: None
        """
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电".format(datetime.datetime.now())])
        # 断电
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        # 上电
        time.sleep(3)
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
