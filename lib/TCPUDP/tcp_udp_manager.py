# -*- encoding=utf-8 -*-
import datetime
from threading import Event
import logging
import time


class TcpUdpManager:
    def __init__(self, main_queue, route_queue, uart_queue, log_queue, uart_port, version, imei, connect_mode,
                 access_mode, connect_type, server_ip, server_port, contextID, context_type, apn, restore_times,
                 is_5g_m2_evb, runtimes):
        self.main_queue = main_queue
        self.route_queue = route_queue
        self.uart_queue = uart_queue
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
        self.is_5g_m2_evb = is_5g_m2_evb
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

    def dial_init_tcp(self):
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
        # 5. 普通AT初始化，仅在runtimes=0的时候使用
        if self.runtimes == 0:
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
            if main_queue_data is False:
                return False
        # 7. 检查网络
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False
        self.route_queue_put('AT', 'AT+QIACT=1', 6, 1, self.runtimes)
        # 8. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def dial_init_tcp_reboot(self):
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
        # 5. 检查网络
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False
        self.route_queue_put('AT', 'AT+QIACT=1', 6, 1, self.runtimes)
        # 6. 长连需要重新建立连接
        if self.connect_mode == 0 and self.access_mode != 2:
            main_queue_data = self.route_queue_put('AT', 'client_connect', self.connect_type, self.server_ip, self.server_port, self.access_mode, self.runtimes)
            if main_queue_data is False:
                return False
        if self.connect_mode == 0 and self.access_mode == 2:
            main_queue_data = self.route_queue_put('AT', 'client_connect_trans_init', self.connect_type, self.server_ip, self.server_port, self.access_mode, self.runtimes)
            if main_queue_data is False:
                return False
        # 7. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def act_deact_init(self):
        # 1. 断电后上电
        self.vbat()
        # 2. 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            print('初始化检测驱动加载失败，退出脚本')
            exit()
        # 3. 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口异常，退出脚本')
            exit()
        # 4. 检测开机URC
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            print('初始化未检测到URC上报，退出脚本')
            exit()
        # 5. 普通AT初始化
        main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
        if main_queue_data is False:
            print('AT初始化异常，退出脚本')
            exit()
        # 6. 注网，配置APN
        main_queue_data = self.route_queue_put('AT', 'act_deact_init', self.contextID, self.context_type, self.apn, self.runtimes)
        if main_queue_data is False:
            print('AT初始化异常，退出脚本')
            exit()
        # 8. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            print('初始化关闭端口出现异常，退出脚本')
            exit()

    def qprtpara_restore(self):
        main_queue_data = self.route_queue_put('AT', 'qprtpara_restore', self.restore_times, self.runtimes)
        if main_queue_data is False:
            return False

    def act_deact_reinit(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. 断电后上电
        self.vbat()
        # 3. 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            return False
        # 4. 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # 5. 检测URC
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            return False
        # 6. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def dial_init_many_tcp_reboot(self):
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
        # 5. 检查网络
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False
        self.route_queue_put('AT', 'AT+QIACT=1', 6, 1, self.runtimes)
        # 6. 长连需要重新建立连接
        if self.connect_mode == 0:
            main_queue_data = self.route_queue_put('AT', 'many_client_connect', self.connect_type, self.server_ip, self.server_port, self.access_mode, self.runtimes)
            if main_queue_data is False:
                return False
        # 7. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
