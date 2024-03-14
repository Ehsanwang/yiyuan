# -*- encoding=utf-8 -*-
import datetime
from threading import Event
import logging
import time


class TcpUdpManager:
    def __init__(self, main_queue, route_queue, log_queue, uart_port, version, imei, connect_mode, access_mode, connect_type, server_ip, server_port, contextID, context_type, apn, restore_times, runtimes):
        self.main_queue = main_queue
        self.route_queue = route_queue
        # self.uart_queue = uart_queue
        self.uart_port = uart_port
        self.imei = imei
        self.version = version
        self.runtimes = runtimes
        self.log_queue = log_queue
        self.access_mode = access_mode
        self.connect_type = connect_type
        self.server_ip = server_ip
        self.server_port = server_port
        self.connect_mode = connect_mode
        self.contextID = contextID
        self.context_type = context_type
        self.apn = apn
        self.restore_times = restore_times
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
        5G-EVB_V2.1：拉高DTR断电->检测驱动消失->拉低DTR上电。
        :return: None
        """
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电".format(datetime.datetime.now())])
        # 断电
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        # 等待3S上电
        time.sleep(3)
        # 上电
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])

    def dial_init_tcp(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 3. 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # 5. 普通AT初始化，仅在runtimes=0的时候使用
        if self.runtimes == 0:
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
            if main_queue_data is False:
                return False
        # 7. 检查网络
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False
        # 8. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def dial_init_tcp_reboot(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. CFUN11重启
        self.route_queue_put('AT', 'AT+CFUN=1,1', 6, 1, self.runtimes)
        # 检测掉口成功
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        if main_queue_data is False:
            return False
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
        # 5. 检查网络
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False
        # 6. 长连需要重新建立连接
        if self.connect_mode == 0:
            main_queue_data = self.route_queue_put('AT', 'client_connect', self.connect_type, self.server_ip, self.server_port, self.access_mode, self.runtimes)
            if main_queue_data is False:
                return False
        # 7. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
