# -*- encoding=utf-8 -*-
import random
import time
from threading import Event
import datetime
import logging
from functions import pause


class RestartManager:
    def __init__(self, main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port, dtr_on_time,
                 dtr_off_time, evb, restart_mode, version, imei, cpin_flag, is_5g_m2_evb, is_x6x, runtimes):
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
        self.is_5g_m2_evb = is_5g_m2_evb
        self.is_x6x = is_x6x
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
        """
        给开关机方式中需要初始化的开关机方式初始化。
        :return: None
        """
        self.log_queue.put(['at_log', '{}initialize{}'.format('=' * 30, '=' * 30)])
        print("\rinitialize", end="")
        module_need_init_list = [0, 3, 5, 6, 8, 9, 10, 11, 12]  # 需要初始化引脚的开关机类型
        if self.restart_mode in module_need_init_list:
            # 1.初始化拉引脚
            self.init_module()
            # 2.初始化检测USB驱动
            main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
            if main_queue_data is False:
                print('初始化模块时USB驱动加载失败，请重新运行脚本')
                exit()
            # 打开AT口
            main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
            if main_queue_data is False:
                print('初始化模块打开AT口失败，请重新运行脚本')
                exit()
            # 3.检测开机URC
            main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
            if main_queue_data is False:
                print('初始化模块URC检测异常，请重新运行脚本')
                exit()
            # 4.Prepare AT
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, self.cpin_flag, self.runtimes)
            if main_queue_data is False:
                print('初始化AT时异常，请重新运行脚本')
                exit()
            # 关闭AT口
            main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
            if main_queue_data is False:
                print('初始化模块关闭AT口失败，请重新运行脚本')
                exit()
        else:  # 不需要初始化的开关机方式仅需要进行at指令的初始化
            # 打开AT口
            main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
            if main_queue_data is False:
                print('初始化模块打开AT口失败，请重新运行脚本')
                exit()
            # Prepare AT
            main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, self.cpin_flag, self.runtimes)
            if main_queue_data is False:
                print('初始化AT时异常，请重新运行脚本')
                exit()
            # 关闭AT口
            main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
            if main_queue_data is False:
                print('初始化模块关闭AT口失败，请重新运行脚本')
                exit()

    def powerkey(self):
        """
        M.2 EVB：拉低DTR->模块关机->检测POWERED DOWN上报->检测驱动消失->拉高DTR开机；
        5G-EVB_V2.1：拉高RTS800ms后拉低RTS关机模拟按压POWERKEY800ms->模块关机检测POWERED DOWN上报->检测驱动消失->
        拉高RTS 500ms后 拉低RTS开机模拟按压POWERKEY500ms开机。
        :return: None
        """
        # 按Powerkey之前必须要检测debug log上报 Started Modem Shutdown Service
        self.route_queue_put('Uart', 'check_modem_shutdown_service', 60, self.runtimes)
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        if 'M.2' in self.evb:
            if self.is_5g_m2_evb:
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                self.log_queue.put(['df', self.runtimes, 'power_off_start_timestamp', time.time()])  # 记录关机开始时间戳
                main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
                if main_queue_data is False:
                    return False
                if self.is_x6x:
                    # X6X项目检测 check debuglog "Started Power-Off"
                    main_queue_data = self.route_queue_put('Uart', 'check_started_power_off', 60, self.runtimes)
                    if main_queue_data is False:
                        return False
                else:
                    # X55项目检测 check debuglog "Starting Power-Off"
                    main_queue_data = self.route_queue_put('Uart', 'check_starting_power_off', 60, self.runtimes)
                    if main_queue_data is False:
                        return False
            else:
                self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY关机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                # x55项目关机会上报关机信息
                self.log_queue.put(['df', self.runtimes, 'power_off_start_timestamp', time.time()])  # 记录关机开始时间戳
                main_queue_data = self.route_queue_put('AT', 'check_power_down_urc', 300, self.runtimes)
                if main_queue_data is False:
                    return False
                main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
                if main_queue_data is False:
                    return False
                if self.is_x6x:
                    # X6X项目检测 check debuglog "Started Power-Off"
                    main_queue_data = self.route_queue_put('Uart', 'check_started_power_off', 60, self.runtimes)
                    if main_queue_data is False:
                        return False
                else:
                    # X55项目检测 check debuglog "Starting Power-Off"
                    main_queue_data = self.route_queue_put('Uart', 'check_starting_power_off', 60, self.runtimes)
                    if main_queue_data is False:
                        return False

        elif 'EVB' in self.evb:
            self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            time.sleep(self.dtr_off_time)
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            # x55项目关机会上报关机信息
            self.log_queue.put(['df', self.runtimes, 'power_off_start_timestamp', time.time()])  # 记录关机开始时间戳
            main_queue_data = self.route_queue_put('AT', 'check_power_down_urc', 300, self.runtimes)
            if main_queue_data is False:
                return False
            main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
            if main_queue_data is False:
                return False
            if self.is_x6x:
                # X6X项目检测 check debuglog "Started Power-Off"
                main_queue_data = self.route_queue_put('Uart', 'check_started_power_off', 60, self.runtimes)
                if main_queue_data is False:
                    return False
            else:
                # X55项目检测 check debuglog "Starting Power-Off"
                main_queue_data = self.route_queue_put('Uart', 'check_starting_power_off', 60, self.runtimes)
                if main_queue_data is False:
                    return False
        self.log_queue.put(['df', self.runtimes, 'power_off_end_timestamp', time.time()])  # 记录关机结束时间戳
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver_dis', False, self.runtimes)
        if main_queue_data is False:
            return False
        if self.evb == 'M.2':
            if self.is_5g_m2_evb:
                time.sleep(1)
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            else:
                self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        elif self.evb == 'EVB':
            self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            time.sleep(self.dtr_on_time)
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])

    def qpowd0(self):
        """
        M.2 EVB：打开AT口发送AT+QPOWD=0后关闭AT口->检测驱动消失；
        5G-EVB_V2.1：拉高RTS->打开AT口发送AT+QPOWD=0后关闭AT口->检测驱动消失。
        :return: None
        """
        # 发送 AT+QPOWD=0
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # AT, at_command, timeout, runtimes, repeat_times, result, mode 仅供参考
        main_queue_data = self.route_queue_put('AT', 'AT+QPOWD=0', 0.3, 1, 'POWERED DOWN', 60, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)

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
        self.log_queue.put(['df', self.runtimes, 'power_off_start_timestamp', time.time()])  # 记录关机开始时间戳
        # AT, at_command, timeout, runtimes, repeat_times, result, mode 仅供参考
        main_queue_data = self.route_queue_put('AT', 'AT+QPOWD=1', 0.3, 1, 'POWERED DOWN', 60, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        if self.is_x6x:
            # X6X项目检测 check debuglog "Started Power-Off"
            main_queue_data = self.route_queue_put('Uart', 'check_started_power_off', 60, self.runtimes)
            if main_queue_data is False:
                return False
        else:
            # X55项目检测 check debuglog "Starting Power-Off"
            main_queue_data = self.route_queue_put('Uart', 'check_starting_power_off', 60, self.runtimes)
            if main_queue_data is False:
                return False
        self.log_queue.put(['df', self.runtimes, 'power_off_end_timestamp', time.time()])  # 记录关机结束时间戳
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)

    def reset(self):
        """
        M.2 EVB：拉高DTR拉高RESET引脚->检测驱动消失->拉低DTR拉低RESET引脚；
        5G-EVB_V2.1：拉高RTS->拉高DTR拉高RTS引脚->检测驱动消失->拉低DTR拉低RESET引脚。
        :return: None
        """
        if self.is_5g_m2_evb:
            # POWERKEY关机
            self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            # 检测驱动消失
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            # POWERKEY开机
            self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
        else:
            self.log_queue.put(['at_log', '[{}] 拉动DTR控制RESET重启'.format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])

    def cfun1_1(self):
        """
        M.2 EVB：打开AT口发送AT+CFUN=1,1后关闭AT口->检测驱动消失；
        5G-EVB_V2.1：拉高RTS->打开AT口发送AT+CFUN=1,1后关闭AT口->检测驱动消失。
        :return: None
        """
        # 发送 AT+CFUN=1,1
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        self.log_queue.put(['df', self.runtimes, 'power_off_start_timestamp', time.time()])  # 记录关机开始时间戳
        # AT, at_command, timeout, runtimes, repeat_times, result, mode
        main_queue_data = self.route_queue_put('AT', 'AT+CFUN=1,1', 15, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        if self.is_x6x:
            # X6X项目检测 check debuglog "Started Reboot"
            main_queue_data = self.route_queue_put('Uart', 'check_started_reboot', 60, self.runtimes)
            if main_queue_data is False:
                return False
        else:
            # X55项目检测 check debuglog "Starting Reboot"
            main_queue_data = self.route_queue_put('Uart', 'check_starting_reboot', 60, self.runtimes)
            if main_queue_data is False:
                return False
        self.log_queue.put(['df', self.runtimes, 'power_off_end_timestamp', time.time()])  # 记录关机结束时间戳
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)

    def vbat(self):
        """
        M.2 EVB：拉高DTR断电->检测驱动消失->拉低DTR上电；
        5G-EVB_V2.1：拉高RTS->拉高DTR断电->检测驱动消失->拉低DTR上电。
        :return: None
        """
        if self.is_5g_m2_evb:
            self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电".format(datetime.datetime.now())])
            # 断电
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            # 检测驱动消失
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            # 等待5S上电
            time.sleep(5)
            # 上电
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        else:
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

    def qpowd1_powerkey(self):
        """
        M.2 EVB：打开AT口发送AT+QPOWD=1后关闭AT口->检测驱动消失->拉低DTR 一定时间后拉高DTR模拟按压POWERKEY开机；
        5G-EVB_V2.1：打开AT口发送AT+QPOWD=1后关闭AT口->检测驱动消失->拉高RTS 500ms后 拉低RTS模拟按压POWERKEY开机。
        :return: None
        """
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        self.log_queue.put(['df', self.runtimes, 'power_off_start_timestamp', time.time()])  # 记录关机开始时间戳
        # 发送AT+QPOWD=1
        main_queue_data = self.route_queue_put('AT', 'AT+QPOWD=1', 0.3, 1, 'POWERED DOWN', 60, 1, self.runtimes)
        if main_queue_data is False:
            return False
        # RM模块 DTR 设置为低，防止关机后自己开机
        if 'M.2' in self.evb:
            if self.is_5g_m2_evb:
                # POWERKEY关机
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            else:
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        # check debuglog "Starting Power-Off"
        main_queue_data = self.route_queue_put('Uart', 'check_starting_power_off', 60, self.runtimes)
        if main_queue_data is False:
            return False
        self.log_queue.put(['df', self.runtimes, 'power_off_end_timestamp', time.time()])  # 记录关机结束时间戳
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        if 'M.2' in self.evb:
            if self.is_5g_m2_evb:
                # POWERKEY开机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            else:
                self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        elif 'EVB' in self.evb:
            self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            time.sleep(self.dtr_on_time)  # POWERKEY开机脉冲时间500ms
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])

    def cfun0_1(self):
        """
        M.2 EVB：打开AT口->发送AT+CFUN=0->发送AT+CFUN=1->关闭AT口；
        5G-EVB_V2.1：打开AT口->发送AT+CFUN=0->发送AT+CFUN=1->关闭AT口。
        :return: None
        """
        # 发送 AT+CFUN=0 和 AT+CFUN=1
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'AT+CFUN=0', 15, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'AT+CFUN=1', 15, 1, self.runtimes)
        if main_queue_data is False:
            return False
        # CPIN上报READY之后AT线程的check_module_info的AT+CPIN?命令才不会返回CME ERROR
        main_queue_data = self.route_queue_put('AT', 'check_specified_urc', 'READY', 10, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False

    def qpowd1_vbat(self):
        """
        M.2 EVB：暂无需关注；
        5G-EVB_V2.1：打开AT口发送AT+QPOWD=1后关闭AT口->拉高RTS->拉高DTR断电->拉低DTR上电。
        :return: None
        """
        # 发送 AT+QPOWD=1
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'AT+QPOWD=1', 0.3, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        random_dtr_time = random.uniform(3.5, 5.5)
        self.log_queue.put(['at_log', "[{}] 随机等待{:.2f}秒后断电".format(datetime.datetime.now(), random_dtr_time)])
        time.sleep(random_dtr_time)
        # RTS-false, DTR-false(断电-拉高)
        if 'M.2' in self.evb:
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
        elif 'EVB' in self.evb:
            self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            # 检测驱动消失
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            # 等待3S上电
            time.sleep(3)
            # VBAT上电
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])

    def qpowd1_reset(self):
        """
        M.2 EVB：打开AT口发送AT+QPOWD=1后关闭AT口->拉高DTR将RESET引脚拉高->检测驱动消失->拉低DTR将RESET引脚拉低；
        5G-EVB_V2.1：打开AT口发送AT+QPOWD=1后关闭AT口->拉高RTS->拉高DTR将RESET引脚拉高->检测驱动消失->拉低DTR将RESET引脚拉低。
        :return: None
        """
        # 发送 AT+QPOWD=1
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'AT+QPOWD=1', 0.3, 1, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        if self.is_5g_m2_evb:
            # POWERKEY关机
            self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            # 检测驱动消失
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            # POWERKEY开机
            self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
        else:
            self.log_queue.put(['at_log', '[{}] 拉动DTR控制RESET重启'.format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])

    def qpowd1_powerkey_vbat(self):
        """
        M.2 EVB：M.2无RTS引脚，暂时无法测试
        5G-EVB_V2.1：打开AT口发送AT+QPOWD=1后关闭AT口->随机断电3.5-5.5s->拉高DTR控制断电->检测驱动消失->拉低控制DTR上电->等待300ms
        拉高RTS等待500ms脉冲开机时间->拉低RTS开机
        :return: None
        """
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # 发送AT,具体注释查看at_thread的AT部分  at_command, timeout, runtimes, repeat_times, result, mode
        main_queue_data = self.route_queue_put('AT', 'AT+QPOWD=1', 0.3, 1, self.runtimes)
        if main_queue_data is False:
            return False
        # 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        if 'M.2' in self.evb:
            if self.runtimes % 5 != 1:
                random_off_time = random.uniform(3.5, 5.5)
                self.log_queue.put(['at_log', '[{}] 随机等待{:.2f}秒后断电'.format(datetime.datetime.now(), random_off_time)])
                time.sleep(random_off_time)
            self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            time.sleep(3)
            # 上电
            self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
        elif 'EVB' in self.evb:
            if self.runtimes % 5 != 1:
                random_off_time = random.uniform(3.5, 5.5)
                self.log_queue.put(['at_log', '[{}] 随机等待{:.2f}秒后断电'.format(datetime.datetime.now(), random_off_time)])
                time.sleep(random_off_time)
            # VBAT断电
            self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            time.sleep(3)
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            time.sleep(self.dtr_on_time)
            # 按压POWERKEY
            self.log_queue.put(['at_log', '[{}] 拉动RTS控制POWERKEY开机'.format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            time.sleep(self.dtr_on_time)  # POWERKEY开机脉冲时间500ms
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])

    def powerkey_vbat(self):
        """
        M.2 EVB：暂无需关注；
        5G-EVB_V2.1：拉高DTR断电->检测驱动消失->拉低DTR上电->拉高RTS后等待500ms后拉低RTS模拟按压POWERKEY500ms。
        :return: None
        """
        if 'M.2' in self.evb:
            if self.is_5g_m2_evb:
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                # 上电
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
        elif 'EVB' in self.evb:
            # VBAT断电
            self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_false')
            self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            time.sleep(3)
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            time.sleep(self.dtr_on_time)
            # 按压POWERKEY
            self.log_queue.put(['at_log', '[{}] 拉动RTS控制POWERKEY开机'.format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            time.sleep(self.dtr_on_time)  # POWERKEY开机脉冲时间500ms
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])

    def vbat_random(self):
        """
        M.2 EVB：拉高DTR断电->检测驱动消失->拉低DTR上电,每隔6次,第七次模块正常开机；
        5G-EVB_V2.1：拉高RTS->拉高DTR断电->检测驱动消失->拉低DTR上电,每隔6次,第七次模块正常开机。
        :return: None
        """
        for num in range(1, 7):
            self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电{}次'.format(datetime.datetime.now(), num)])
            # 随机等待7-10s再进行掉电
            random_off_time = random.uniform(7, 10)
            self.log_queue.put(['at_log', "[{}] 随机等待{:.2f}秒后断电".format(datetime.datetime.now(), random_off_time)])
            time.sleep(random_off_time)
            if self.is_5g_m2_evb:
                # 断电
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                time.sleep(3)
                # 上电
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            else:
                # 掉电
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                # 上电
                time.sleep(3)
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        else:
            # 第七次模块正常开机
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
                # 第七次模块正常开机
                # 掉电
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                # 检测驱动消失
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                # 上电
                time.sleep(3)
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])

    def re_init(self):
        """
        开关机驱动加载失败或者无URC上报时进行模块的初始化。
        :return: None
        """
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        if self.restart_mode == 0:  # 如果POWERKEY方式出现异常，则检测当前模块状态，并尝试每次拉动RTS的时间增加0.05s，10次都开机失败，脚本暂停
            for i in range(10):
                self.log_queue.put(['at_log', "[{}] 进入POWERKEY异常恢复流程".format(datetime.datetime.now())])
                # 如果驱动在，则需要关机
                main_queue_data = self.route_queue_put('Process', 'check_usb_driver', False, self.runtimes)
                if self.evb == 'M.2' and main_queue_data:
                    time.sleep(30)
                    if self.is_5g_m2_evb:
                        # POWERKEY关机
                        self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                        self.route_queue_put('Uart', 'set_rts_true')
                        self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                    else:
                        self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY关机".format(datetime.datetime.now())])
                        self.route_queue_put('Uart', 'set_dtr_true')
                        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                    main_queue_data = self.route_queue_put('Process', 'check_usb_driver_dis', False, self.runtimes)
                    if main_queue_data is False:  # 如果驱动未消失，重新拉引脚
                        continue
                elif self.evb == 'EVB' and main_queue_data:
                    time.sleep(30)
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_false')
                    self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                    time.sleep(self.dtr_off_time)
                    self.route_queue_put('Uart', 'set_rts_true')
                    self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                    main_queue_data = self.route_queue_put('Process', 'check_usb_driver_dis', False, self.runtimes)
                    if main_queue_data is False:  # 如果驱动未消失，重新拉引脚
                        continue
                # 初始化开机时间
                self.dtr_on_time_init += 0.05
                self.log_queue.put(['at_log', "[{}] POWERKEY初始化，当前dtr_on_time：{}".format(datetime.datetime.now(),
                                                                                         self.dtr_on_time_init)])
                # 开机
                if self.evb == 'M.2':
                    if self.is_5g_m2_evb:
                        # POWERKEY开机
                        time.sleep(1)
                        self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                        self.route_queue_put('Uart', 'set_rts_false')
                        self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                    else:
                        self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY开机".format(datetime.datetime.now())])
                        self.route_queue_put('Uart', 'set_dtr_false')
                        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                elif self.evb == 'EVB':
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_false')
                    self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                    time.sleep(self.dtr_on_time_init)
                    self.route_queue_put('Uart', 'set_rts_true')
                    self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                # 检测驱动->打开口->检测URC->关闭口->等待20S
                main_queue_data = self.route_queue_put('Process', 'check_usb_driver', False, self.runtimes)
                if main_queue_data is False:  # 如果驱动没有出现，继续
                    continue
                self.route_queue_put('AT', 'open', self.runtimes)
                self.route_queue_put('AT', 'check_urc', self.runtimes)
                self.route_queue_put('AT', 'close', self.runtimes)
                self.dtr_on_time_init = self.dtr_on_time
                time.sleep(20)
                break
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} POWERKEY开机过程异常，初始化10次开机均失败'.format(datetime.datetime.now(),
                                                                                                self.runtimes)])
                pause()
        elif self.restart_mode == 3:
            if self.is_5g_m2_evb:
                # POWERKEY关机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                # 检测驱动消失
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                # POWERKEY开机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            else:
                self.log_queue.put(['at_log', "[{}] 拉动DTR控制RESET重启".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                # 检测驱动消失
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                # 上电
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
            self.route_queue_put('AT', 'open', self.runtimes)
            self.route_queue_put('AT', 'check_urc', self.runtimes)
            self.route_queue_put('AT', 'close', self.runtimes)
        elif self.restart_mode in [1, 2, 4]:
            return
        elif self.restart_mode == 6:
            if 'M.2' in self.evb:
                if self.is_5g_m2_evb:
                    # POWERKEY关机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_true')
                    self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                    # 检测驱动消失
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    # POWERKEY开机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_false')
                    self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                else:
                    self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                    time.sleep(self.dtr_off_time)
                    self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            elif 'EVB' in self.evb:
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)  # POWERKEY开机脉冲时间500ms
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
            self.route_queue_put('AT', 'open', self.runtimes)
            self.route_queue_put('AT', 'check_urc', self.runtimes)
            self.route_queue_put('AT', 'close', self.runtimes)
        elif self.restart_mode == 8:
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
                self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电".format(datetime.datetime.now())])
                # 断电
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                # 检测驱动消失
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                # 上电
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
            self.route_queue_put('AT', 'open', self.runtimes)
            self.route_queue_put('AT', 'check_urc', self.runtimes)
            self.route_queue_put('AT', 'close', self.runtimes)
        elif self.restart_mode == 9:
            if self.is_5g_m2_evb:
                # POWERKEY关机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                # 检测驱动消失
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                # POWERKEY开机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            else:
                self.log_queue.put(['at_log', "[{}] 拉动DTR控制RESET重启".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                # 检测驱动消失
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                # 上电
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
            self.route_queue_put('AT', 'open', self.runtimes)
            self.route_queue_put('AT', 'check_urc', self.runtimes)
            self.route_queue_put('AT', 'close', self.runtimes)
        elif self.restart_mode == 10 or self.restart_mode == 11:
            if self.is_5g_m2_evb:
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                # 上电
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            else:
                # VBAT断电
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(3)
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)
                # 按压POWERKEY
                self.log_queue.put(['at_log', '[{}] 拉动RTS控制POWERKEY开机'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)  # POWERKEY开机脉冲时间500ms
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
            self.route_queue_put('AT', 'open', self.runtimes)
            self.route_queue_put('AT', 'check_urc', self.runtimes)
            self.route_queue_put('AT', 'close', self.runtimes)

    def init_module(self):
        """
        跟据不同的开关机方式进行模块的初始化
        :return: None
        """
        if self.evb == 'M.2':
            if self.restart_mode == 0:  # POWERKEY
                if self.is_5g_m2_evb:
                    # POWERKEY关机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_true')
                    self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                    # 检测驱动消失
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    # POWERKEY开机
                    time.sleep(1)
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_false')
                    self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                else:
                    # 关机
                    self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                    # 检测驱动消失
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    # 开机
                    self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            elif self.restart_mode == 3:  # RESET
                if self.is_5g_m2_evb:
                    # POWERKEY关机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_true')
                    self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                    # 检测驱动消失
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    # POWERKEY开机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_false')
                    self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                else:
                    self.log_queue.put(['at_log', '[{}] 拉动DTR控制RESET重启'.format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            elif self.restart_mode == 5:  # VBAT
                if self.is_5g_m2_evb:
                    self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    time.sleep(3)
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                else:
                    self.log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    time.sleep(3)
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            elif self.restart_mode == 6:  # QPOWD1+POWERKEY开关机
                if self.is_5g_m2_evb:
                    # POWERKEY关机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_true')
                    self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                    # 检测驱动消失
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    # POWERKEY开机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_false')
                    self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                else:
                    # 关机
                    self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                    # 检测驱动消失
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    # 开机
                    self.log_queue.put(['at_log', "[{}] 拉动DTR控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
            elif self.restart_mode == 8:  # QPOWD1+VBAT
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
                    self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    time.sleep(3)
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            elif self.restart_mode == 9:  # QPOWD1_RESET
                if self.is_5g_m2_evb:
                    # POWERKEY关机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_true')
                    self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                    # 检测驱动消失
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    # POWERKEY开机
                    self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_rts_false')
                    self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                else:
                    self.log_queue.put(['at_log', '[{}] 拉动DTR控制RESET重启'.format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            elif self.restart_mode == 10:  # QPOWD1+POWERKEY+VBAT开关机
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                # 上电
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            elif self.restart_mode == 11:  # POWERKEY+VBAT开关机
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                # 上电
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            elif self.restart_mode == 12:  # VBAT
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
                    self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                    self.route_queue_put('Uart', 'set_dtr_false')
                    self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                    self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                    time.sleep(3)
                    self.route_queue_put('Uart', 'set_dtr_true')
                    self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        elif self.evb == 'EVB':
            if self.restart_mode == 0:  # POWERKEY
                # POWERKEY关机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(self.dtr_off_time)
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                # 检测驱动消失
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                # POWERKEY开机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            elif self.restart_mode == 3:  # RESET
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制RESET重启'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            elif self.restart_mode == 5:  # VBAT
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            elif self.restart_mode == 6:  # qpowd1_powerkey
                # POWERKEY关机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY关机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(self.dtr_off_time)
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                # 检测驱动消失
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                # POWERKEY开机
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            elif self.restart_mode == 8:  # QPOWD1+VBAT
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            elif self.restart_mode == 9:  # QPOWD1+RESET
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制RESET重启'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
            elif self.restart_mode == 10:  # QPOWD1+POWERKEY+VBAT开关机
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            elif self.restart_mode == 11:  # POWERKEY+VBAT
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)
                self.log_queue.put(['at_log', "[{}] 拉动RTS控制POWERKEY开机".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                time.sleep(self.dtr_on_time)
                self.route_queue_put('Uart', 'set_rts_true')
                self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
            elif self.restart_mode == 12:  # VBAT
                self.log_queue.put(['at_log', '[{}] 拉动DTR控制VBAT断电上电'.format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_dtr_false')
                self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
                self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
                time.sleep(3)
                self.route_queue_put('Uart', 'set_dtr_true')
                self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
