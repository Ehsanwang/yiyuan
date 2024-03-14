# -*- encoding=utf-8 -*-
import random
import time
from threading import Event
import datetime
import logging
from functions import pause


class RestartManager:
    def __init__(self, main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port, dtr_on_time, dtr_off_time, evb, restart_mode, version, imei, cpin_flag, runtimes):
        self.route_queue = route_queue
        self.uart_queue = uart_queue
        self.at_queue = at_queue
        self.log_queue = log_queue
        self.at_port = at_port
        self.uart_port = uart_port
        self.dtr_on_time = dtr_on_time
        self.dtr_on_time_init = dtr_on_time
        self.dtr_off_time = dtr_off_time
        self.evb = evb
        self.runtimes = runtimes
        self.restart_mode = restart_mode
        self.version = version
        self.imei = imei
        self.main_queue = main_queue
        self.cpin_flag = cpin_flag
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
        return _main_queue_data

    def init(self):
        """
        给开关机方式中需要初始化的开关机方式初始化。
        :return: None
        """
        # 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            return False
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # Prepare AT
        main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, self.cpin_flag, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False

    def re_init(self):
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            return False
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'AT+CFUN=1,1', 15, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        # 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            return False
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # 检测开机URC
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            return False
