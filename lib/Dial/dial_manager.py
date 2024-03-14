# -*- encoding=utf-8 -*-
import datetime
import os
from threading import Event
import logging
import time


class DialManager:
    def __init__(self, main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, dial_mode,
                 connect_mode, connect_type, server_ip, server_port, ftp_usr_name, ftp_password, restart_mode,
                 network_driver_name, is_5g_m2_evb, runtimes):
        self.main_queue = main_queue
        self.route_queue = route_queue
        self.uart_queue = uart_queue
        self.uart_port = uart_port
        self.evb = evb
        self.imei = imei
        self.version = version
        self.runtimes = runtimes
        self.log_queue = log_queue
        self.dial_mode = dial_mode
        self.connect_type = connect_type
        self.server_ip = server_ip
        self.server_port = server_port
        self.connect_mode = connect_mode
        self.ftp_usr_name = ftp_usr_name
        self.ftp_password = ftp_password
        self.restart_mode = restart_mode
        self.network_driver_name = network_driver_name
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

    def qpowd1(self):
        """
        M.2 EVB：打开AT口发送AT+QPOWD=1后关闭AT口->检测驱动消失；
        5G-EVB_V2.1：拉高RTS->打开AT口发送AT+QPOWD=1后关闭AT口->检测驱动消失。
        :return: None
        """
        # 发送 AT+QPOWD=1
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # AT, at_command, timeout, runtimes, repeat_times, result, mode 仅供参考
        main_queue_data = self.route_queue_put('AT', 'AT+QPOWD=1', 0.3, 1, 'POWERED DOWN', 60, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)

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
        # 6. 拨号模式检测
        main_queue_data = self.route_queue_put('AT', 'dial_mode_check', self.dial_mode, self.runtimes)
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
        # 9. 检测拨号是否已经可以使用
        self.route_queue_put('Process', 'wait_dial_init', self.runtimes)
        # 10. 重置连接，如果连接关闭
        main_queue_data = self.route_queue_put('Process', 'reset_connect', self.runtimes)
        if main_queue_data is False:
            return False
        # 长连特殊情况，长连失败进入init后需要连接网络，然后连接TCP。(connect_type=1)
        if self.connect_mode == 0:
            # 用win api进行连接
            main_queue_data = self.route_queue_put('Process', 'connect', self.dial_mode, self.runtimes)
            if main_queue_data is False:
                return False
            # 检查和电脑IP的情况
            main_queue_data = self.route_queue_put('Process', 'check_ip_connect_status', self.dial_mode, self.network_driver_name, self.runtimes)
            if main_queue_data is False:
                return False
            main_queue_data = self.route_queue_put('Process', 'client_connect', self.connect_type, self.server_ip, self.server_port, self.runtimes)
            if main_queue_data is False:
                return False

    def dial_init_ftp(self):
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
            # 6. 拨号模式检测
            main_queue_data = self.route_queue_put('AT', 'dial_mode_check', self.dial_mode, self.runtimes)
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
        # 9. 检测拨号是否已经可以使用
        self.route_queue_put('Process', 'wait_dial_init', self.runtimes)
        # 10. 重置连接，如果连接关闭
        main_queue_data = self.route_queue_put('Process', 'reset_connect', self.runtimes)
        if main_queue_data is False:
            return False
        # 长连特殊情况，长连失败进入init后需要连接网络，然后连接FTP。(connect_type=1)
        if self.connect_mode == 0:
            # 用win api进行连接
            main_queue_data = self.route_queue_put('Process', 'connect', self.dial_mode, self.runtimes)
            if main_queue_data is False:
                return False
            # 检查和电脑IP的情况
            main_queue_data = self.route_queue_put('Process', 'check_ip_connect_status', self.dial_mode, self.network_driver_name, self.runtimes)
            if main_queue_data is False:
                return False
            main_queue_data = self.route_queue_put('Process', 'ftp_connect', self.connect_mode, self.dial_mode, self.server_ip, self.server_port, self.ftp_usr_name, self.ftp_password, self.runtimes)
            if main_queue_data is False:
                return False

    def dial_init_ping(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. 不同开关机方式
        if self.restart_mode is None or self.restart_mode == 1:
            self.vbat()
        elif self.restart_mode == 2:
            self.qpowd1()
            main_queue_data = self.route_queue_put('Process', 'check_usb_driver_dis', False, self.runtimes)
            if main_queue_data is False:  # 如果驱动未消失，重新拉引脚
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
        # 5. 普通AT初始化
        if self.runtimes == 0:
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
            if main_queue_data is False:
                return False
        # 6. 拨号模式检测
        main_queue_data = self.route_queue_put('AT', 'dial_mode_check', self.dial_mode, self.runtimes)
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
        # 9. 检测拨号是否已经可以使用
        self.route_queue_put('Process', 'wait_dial_init', self.runtimes)
        # 10. 重置连接，如果连接关闭
        main_queue_data = self.route_queue_put('Process', 'reset_connect', self.runtimes)
        if main_queue_data is False:
            return False
        # 11. 用win api进行连接
        main_queue_data = self.route_queue_put('Process', 'connect', self.dial_mode, self.runtimes)
        if main_queue_data is False:
            return False
        # 12. 检查和电脑IP的情况
        if self.runtimes == 0:
            main_queue_data = self.route_queue_put('Process', 'check_ip_connect_status', self.dial_mode, self.network_driver_name, self.runtimes)
            if main_queue_data is False:
                return False

    def dial_http_init(self):
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
        # 6. 拨号模式检测
        main_queue_data = self.route_queue_put('AT', 'dial_mode_check', self.dial_mode, self.runtimes)
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
        # 9. 检测拨号是否已经可以使用
        self.route_queue_put('Process', 'wait_dial_init', self.runtimes)
        # 10. 重置连接，如果连接关闭
        main_queue_data = self.route_queue_put('Process', 'reset_connect', self.runtimes)
        if main_queue_data is False:
            return False
        # 长连特殊情况，长连失败进入init后需要连接网络，然后连接TCP。(connect_type=1)
        if self.connect_mode == 0:
            # 用win api进行连接
            main_queue_data = self.route_queue_put('Process', 'connect', self.dial_mode, self.runtimes)
            if main_queue_data is False:
                return False
            # 检查和电脑IP的情况
            main_queue_data = self.route_queue_put('Process', 'check_ip_connect_status', self.dial_mode, self.network_driver_name, self.runtimes)
            if main_queue_data is False:
                return False

    def dial_poweroff_init(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. 不同开关机方式
        if self.restart_mode is None or self.restart_mode == 1:
            self.vbat()
        elif self.restart_mode == 2:
            self.qpowd1()
            main_queue_data = self.route_queue_put('Process', 'check_usb_driver_dis', False, self.runtimes)
            if main_queue_data is False:  # 如果驱动未消失，重新拉引脚
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
        # 5. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def dial_init_speedtest(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. 不同开关机方式
        if self.restart_mode is None or self.restart_mode == 1:
            self.vbat()
        elif self.restart_mode == 2:
            self.qpowd1()
            main_queue_data = self.route_queue_put('Process', 'check_usb_driver_dis', False, self.runtimes)
            if main_queue_data is False:  # 如果驱动未消失，重新拉引脚
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
        # 5. 普通AT初始化，仅在runtimes=0的时候使用
        if self.runtimes == 0:
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
            if main_queue_data is False:
                return False
        # 检测URC之后立刻查询USBNET可能报错，暂停10S
        time.sleep(10)
        # 6. 拨号模式检测
        main_queue_data = self.route_queue_put('AT', 'dial_mode_check', self.dial_mode, self.runtimes)
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
        if os.name == 'nt' and self.dial_mode.upper() == 'RGMII':  # 如果是Windows下RGMII拨号方式
            main_queue_data = self.route_queue_put('Process', 'rgmii_connect_check', self.runtimes)
            if main_queue_data is False:
                return False
        elif os.name == 'nt':  # Windows下的NDIS和MBIM拨号方式
            # 9. 检测拨号是否已经可以使用
            self.route_queue_put('Process', 'wait_dial_init', self.runtimes)
            # 10. 重置连接，如果连接关闭
            main_queue_data = self.route_queue_put('Process', 'reset_connect', self.runtimes)
            if main_queue_data is False:
                return False
            if self.connect_mode == 0:  # 如果是长拨号，则需要进行连接
                # 用win api进行连接
                main_queue_data = self.route_queue_put('Process', 'connect', self.dial_mode, self.runtimes)
                if main_queue_data is False:
                    return False
                # 检查和电脑IP的情况
                main_queue_data = self.route_queue_put('Process', 'check_ip_connect_status', self.dial_mode, self.network_driver_name, self.runtimes)
                if main_queue_data is False:
                    return False
        elif os.name != 'nt':  # Linux下操作: Linux默认都是长拨号，所以默认需要进行拨号连接
            if self.connect_mode == 1:
                if self.dial_mode.upper() == 'WWAN':
                    main_queue_data = self.route_queue_put('Process', 'wwan_connect_check', self.runtimes)
                    if main_queue_data is False:
                        return False
                    main_queue_data = self.route_queue_put('Process', 'disconnect_dial', self.dial_mode, self.runtimes)
                    if main_queue_data is False:
                        return False
                elif self.dial_mode.upper() == 'GOBINET':
                    main_queue_data = self.route_queue_put('Process', 'gobinet_connect_check', self.runtimes)
                    if main_queue_data is False:
                        return False
                    main_queue_data = self.route_queue_put('Process', 'disconnect_dial', self.dial_mode, self.runtimes)
                    if main_queue_data is False:
                        return False
                elif self.dial_mode.upper() == 'MBIM':
                    main_queue_data = self.route_queue_put('Process', 'mbim_connect_check', self.runtimes)
                    if main_queue_data is False:
                        return False
                    main_queue_data = self.route_queue_put('Process', 'disconnect_dial', self.dial_mode, self.runtimes)
                    if main_queue_data is False:
                        return False
            elif self.connect_mode == 0:
                if self.dial_mode.upper() == 'ECM':  # ECM拨号为Linux自动拨号，仅需检查驱动状态和是否拨号成功
                    main_queue_data = self.route_queue_put('Process', 'ecm_connect_check', self.runtimes)
                    if main_queue_data is False:
                        return False
                elif self.dial_mode.upper() == 'WWAN':
                    main_queue_data = self.route_queue_put('Process', 'wwan_connect_check', self.runtimes)
                    if main_queue_data is False:
                        return False
                elif self.dial_mode.upper() == 'GOBINET':
                    main_queue_data = self.route_queue_put('Process', 'gobinet_connect_check', self.runtimes)
                    if main_queue_data is False:
                        return False
                elif self.dial_mode.upper() == 'MBIM':
                    main_queue_data = self.route_queue_put('Process', 'mbim_connect_check', self.runtimes)
                    if main_queue_data is False:
                        return False

    def dial_init_speedtest_only(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # 2. 普通AT初始化，仅在runtimes=0的时候使用
        if self.runtimes == 0:
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
            if main_queue_data is False:
                return False
        # 3. 检查网络
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False

    def dial_init_iperf_only(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # 2. 普通AT初始化，仅在runtimes=0的时候使用
        if self.runtimes == 0:
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
            if main_queue_data is False:
                return False
        # 3. 检查网络
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False

    def dial_init_fusion(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 1. 不同开关机方式
        if self.restart_mode is None or self.restart_mode == 1:
            self.vbat()
        elif self.restart_mode == 2:
            self.qpowd1()
            main_queue_data = self.route_queue_put('Process', 'check_usb_driver_dis', False, self.runtimes)
            if main_queue_data is False:  # 如果驱动未消失，重新拉引脚
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
        # 5. 普通AT初始化，仅在runtimes=0的时候使用
        if self.runtimes == 0:
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
            if main_queue_data is False:
                return False
        # 检测URC之后立刻查询USBNET可能报错，暂停10S
        time.sleep(10)
        # 6. 拨号模式检测
        main_queue_data = self.route_queue_put('AT', 'dial_mode_check', self.dial_mode, self.runtimes)
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
        if os.name == 'nt' and self.dial_mode.upper() != 'RGMII' and self.dial_mode.upper() != "RTL8125":  # 如果windows下非RGMII拨号，需要等待拨号加载
            self.route_queue_put('Process', 'wait_dial_init', self.runtimes)

            main_queue_data = self.route_queue_put('Process', 'reset_connect', self.runtimes)
            if main_queue_data is False:
                return False
        else:
            time.sleep(10)  # 找网成功后等待10S

    def dial_fusion_cfun_0_1(self):
        main_queue_data = self.route_queue_put('AT', 'cfun_0_1', self.runtimes)
        if main_queue_data is False:
            return False

        if self.dial_mode.upper() == 'RGMII':
            main_queue_data = self.route_queue_put('Process', 'rgmii_connect_check', self.runtimes)
            if main_queue_data is False:
                return False
        elif self.dial_mode.upper() == "RTL8125":
            main_queue_data = self.route_queue_put('Process', 'rtl_connect_check', self.runtimes)
            if main_queue_data is False:
                return False
