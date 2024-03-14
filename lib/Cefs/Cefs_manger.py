# -*- encoding=utf-8 -*-
import time
from threading import Event
import datetime
import logging


class CefsManger:
    def __init__(self, main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, is_5g_m2_evb,
                 runtimes):
        self.route_queue = route_queue
        self.uart_queue = uart_queue
        self.log_queue = log_queue
        self.uart_port = uart_port
        self.evb = evb
        self.runtimes = runtimes
        self.version = version
        self.imei = imei
        self.is_5g_m2_evb = is_5g_m2_evb
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
        return _main_queue_data

    def vbat(self):
        """
        M.2 EVB：拉高DTR断电->检测驱动消失->拉低DTR上电；
        5G-EVB_V2.1：拉高RTS->拉高DTR断电->检测驱动消失->拉低DTR上电。
        5G-M.2-EVB: 拉低DTR断电 -> 检测驱动消失 -> 拉高DTR上电：
        :return: None
        """
        if self.is_5g_m2_evb:
            self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电\n".format(datetime.datetime.now())])
            # 断电
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            # 检测驱动消失
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            time.sleep(3)
            # 上电
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        else:
            self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电\n".format(datetime.datetime.now())])
            # 断电
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            # 检测驱动消失
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            time.sleep(3)
            # 上电
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])

    def init(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. 断电后上电
        self.vbat()
        # 2. 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            return False
        # 3. 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # 4. 检测开机URC
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            return False
        if self.runtimes == 0:
            # 5. 普通AT初始化
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
            if main_queue_data is False:
                return False
        # 检测PB DONE上报
        self.route_queue_put('AT', 'check_pb_done')
        # 6. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def cefs_vbat(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        self.vbat()
