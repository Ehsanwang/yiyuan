# -*- encoding=utf-8 -*-
import datetime
from threading import Event
import logging
import time
from functions import pause


class DfotaManager:
    def __init__(self, main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, after_upgrade_version, imei, package_error_list, upgrade_error_list, mode, adb_or_at,
                 is_5g_m2_evb, runtimes):
        self.main_queue = main_queue
        self.route_queue = route_queue
        self.uart_queue = uart_queue
        self.uart_port = uart_port
        self.evb = evb
        self.imei = imei
        self.version = version
        self.after_upgrade_version = after_upgrade_version
        self.runtimes = runtimes
        self.log_queue = log_queue
        self.package_error_list = package_error_list
        self.upgrade_error_list = upgrade_error_list
        self.mode = mode
        self.adb_or_at = adb_or_at
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

    def abdfota_init(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
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
        # 6. AT方式上传差分包 初始化文件相关指令
        if self.adb_or_at == 1:
            main_queue_data = self.route_queue_put('AT', 'ufs_compare_init', self.runtimes)
            if main_queue_data is False:
                print('文件相关指令初始化异常，退出脚本')
                exit()
        # 7. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            print('初始化关闭端口出现异常，退出脚本')
            exit()

    def abfota_upgrade_exception_init(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 断电后上电
        self.vbat()

    def dfota_upgradeAB_vbat(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 断电
        self.vbat()
        # 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            self.log_queue.put(['all', '[{}] runtimes:{} 升级断电后驱动未加载'])
            pause()

        time.sleep(5)
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False

        # 5. 检测URC
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            return False

        main_queue_data = self.route_queue_put('AT', 'absystem_upgrade_log', self.runtimes)
        if main_queue_data is False:
            return False

        main_queue_data = self.route_queue_put('AT', 'check_adbfota_status', [self.version, self.after_upgrade_version],
                                               self.package_error_list, self.upgrade_error_list, self.mode, False,
                                               self.runtimes)
        if main_queue_data is False:
            return False

    def dfota_backupAB_vbat(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 断电
        self.vbat()
        # 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            self.log_queue.put(['all', '[{}] runtimes:{} 升级断电后驱动未加载'])
            pause()

        time.sleep(5)
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False

        # 5. 检测URC
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            return False

        main_queue_data = self.route_queue_put('AT', 'check_twosystem_vbatbackup', self.mode, self.runtimes)
        if main_queue_data is False:
            return False

    def dfota_ab_exception_init(self):
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
        # 7. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def online_abfota_download_vbat(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 断电
        self.vbat()
        # 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            self.log_queue.put(['all', '[{}] runtimes:{} 升级断电后驱动未加载'])
            pause()

        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False

        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            return False

        time.sleep(3)
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            return False

        if main_queue_data is False:
            return False