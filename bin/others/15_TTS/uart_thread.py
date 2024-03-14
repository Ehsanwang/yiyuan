# -*- encoding=utf-8 -*-
import datetime
import time
from threading import Thread
import serial
import logging
import re
from functions import pause
# tts


class UartThread(Thread):

    PORT_CACHE = ''  # 用于UART口log拼接使用

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
        self.modem_shutdown_service_flag = False  # powerkey开关机中，必须此项服务起来之后进行拉DTR操作才会生效
        self.starting_power_off_flag = False  # powerkey等开关机中，关机必须要确认DEBUG口上报Starting Power-Off才算关机成功
        self.starting_reboot_flag = False  # CFUN1,1关机中，必须要确认最后一条log上报Starting Reboot才算关机成功

    def run(self):
        try:
            self.uart_port = serial.Serial(self.uart_port, baudrate=115200, timeout=0)
        except serial.serialutil.SerialException:
            pause("UART端口被占用或端口设置错误，请关闭脚本并重新运行")
        if self.debug_port != '':
            try:
                self.debug_port = serial.Serial(self.debug_port, baudrate=115200, timeout=0)
            except serial.serialutil.SerialException:
                pause("DEBUG端口被占用或端口设置错误，请关闭脚本并重新运行")
        self.uart_port.setDTR(False)
        self.uart_port.setRTS(False)
        while True:
            # 传入参数参考：['init_module', 5, 'M.2', 0.5, <threading.Event object at 0x...>]
            time.sleep(0.001)
            (func, *param), evt = ['0', '0'] if self.uart_queue.empty() else self.uart_queue.get()
            self.logger.info('{}->{}->{}'.format(func, param, evt)) if func != '0' else ''
            if func in self._methods_list:
                uart_status = getattr(self.__class__, '{}'.format(func))(self, *param)
                if uart_status is not False:
                    self.main_queue.put(True)
                else:
                    self.main_queue.put(False)
                evt.set()  # 取消阻塞
            if self.debug_port_read_flag:  # 如果传入了DEBUG口，则从传入的DEBUG口读取log (RG)
                self.readline(self.debug_port)
            else:  # 否则直接从UART口读取log (RM)
                self.readline(self.uart_port)

    def readline(self, port):
        """
        拼接此类不在一行的log。
        [2020-09-01 10:20:23.593831] '         Starting Create Volatile Files a'
        [2020-09-01 10:20:23.607004] 'nd Directories...\r\n'
        :param port: 需要读取的端口
        :return: '':此次readline方法读取的不是以\n结尾；all_return_value：此次读取log以\n结尾
        """
        return_value = port.readline().decode('utf-8', 'ignore')
        if return_value != '':  # 如果不为空，和PORT_CACHE拼接
            self.PORT_CACHE += return_value
        if return_value.endswith('\n') is False:  # 不以\n结尾，直接返回空串
            return ''
        else:  # 以\n结尾，赋值PORT_CACHE给all_return_value，然后清空PORT_CACHE后返回读取到的所有值
            all_return_value = self.PORT_CACHE
            all_return_value = re.sub(r'\x1b\[.*?m', '', all_return_value)  # 替换ANSI COLOR
            if 'Started Modem Shutdown Service' in all_return_value:
                self.modem_shutdown_service_flag = True
            if 'Starting Power-Off' in all_return_value:
                self.starting_power_off_flag = True
            if 'Starting Reboot' in all_return_value:
                self.starting_reboot_flag = True
            self.PORT_CACHE = ''
            self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(all_return_value))])
            return all_return_value

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

    def check_message(self, message, timeout, runtimes):
        """
        检测DEBUG LOG是否有message参数的log上报
        :param message: 需要检测的信息
        :param timeout: 检测的超时时间
        :param runtimes: 当前脚本运行的次数
        :return: True：检测成功，False：检测失败
        """
        check_message_start_time = time.time()
        while True:
            time.sleep(0.001)
            debug_return_value = self.readline(self.uart_port if self.debug_port == '' else self.debug_port)
            if debug_return_value != '' and message in debug_return_value:
                self.log_queue.put(['at_log', '[{}] DEBUG LOG 已检测到 {}'.format(datetime.datetime.now(), message)])
                return True
            if time.time() - check_message_start_time > timeout:
                self.log_queue.put(['all', '[{}] runtimes:{} {}S内 DEBUG LOG 未检测到 {}'.format(datetime.datetime.now(), runtimes, timeout, message)])
                return False

    def check_modem_shutdown_service(self, timeout, runtimes):
        """
        powerkey方式进行关机之前需要保证Started Modem Shutdown Service进程是起来的状态，不然有可能关机失败
        :param timeout: 超时时间
        :param runtimes: 当前脚本的运行次数
        :return: True：检测到上报，False：没有检测到信息上报
        """
        if self.modem_shutdown_service_flag:  # 如果服务已经起来
            self.log_queue.put(['at_log', '[{}] DEBUG LOG 已检测到 Started Modem Shutdown Service'.format(datetime.datetime.now())])
            self.modem_shutdown_service_flag = False
            return True
        else:
            check_service_start_time = time.time()
            while True:
                time.sleep(0.001)
                self.readline(self.uart_port if self.debug_port == '' else self.debug_port)
                if self.modem_shutdown_service_flag:  # 如果readline方法内部发现了 Started Modem Shutdown Service
                    self.log_queue.put(['at_log', '[{}] DEBUG LOG 已检测到 Started Modem Shutdown Service'.format(datetime.datetime.now())])
                    self.modem_shutdown_service_flag = False  # 重置标志位
                    return True
                if time.time() - check_service_start_time > timeout:
                    self.log_queue.put(['all', '[{}] runtimes:{} {}S内 DEBUG LOG 未检测到 Started Modem Shutdown Service'.format(datetime.datetime.now(), runtimes, timeout)])
                    return False

    def check_starting_power_off(self, timeout, runtimes):
        """
        powerkey方式进行关机之前需要保证DEBUG口上报Starting Power-Off，保证模块完全关机
        :param timeout: 超时时间
        :param runtimes: 当前脚本的运行次数
        :return: True：检测到上报，False：没有检测到信息上报
        """
        if self.starting_power_off_flag:  # 如果已经上报
            self.log_queue.put(['at_log', '[{}] DEBUG LOG 已检测到 Starting Power-Off'.format(datetime.datetime.now())])
            self.starting_power_off_flag = False
            return True
        else:
            check_service_start_time = time.time()
            while True:
                time.sleep(0.001)
                self.readline(self.uart_port if self.debug_port == '' else self.debug_port)
                if self.starting_power_off_flag:  # 如果readline方法内部发现了 Starting Power-Off
                    self.log_queue.put(['at_log', '[{}] DEBUG LOG 已检测到 Starting Power-Off'.format(datetime.datetime.now())])
                    self.starting_power_off_flag = False  # 重置标志位
                    return True
                if time.time() - check_service_start_time > timeout:
                    self.log_queue.put(['all', '[{}] runtimes:{} {}S内 DEBUG LOG 未检测到 Starting Power-Off'.format(datetime.datetime.now(), runtimes, timeout)])
                    return False

    def check_starting_reboot(self, timeout, runtimes):
        """
        CFUN1,1方式进行关机之前需要保证DEBUG口上报Starting Reboot，保证模块完全关机
        :param timeout: 超时时间
        :param runtimes: 当前脚本的运行次数
        :return: True：检测到上报，False：没有检测到信息上报
        """
        if self.starting_reboot_flag:  # 如果已经上报
            self.log_queue.put(['at_log', '[{}] DEBUG LOG 已检测到 Starting Reboot'.format(datetime.datetime.now())])
            self.starting_reboot_flag = False
            return True
        else:
            check_service_start_time = time.time()
            while True:
                time.sleep(0.001)
                self.readline(self.uart_port if self.debug_port == '' else self.debug_port)
                if self.starting_reboot_flag:  # 如果readline方法内部发现了 Starting Reboot
                    self.log_queue.put(['at_log', '[{}] DEBUG LOG 已检测到 Starting Reboot'.format(datetime.datetime.now())])
                    self.starting_reboot_flag = False  # 重置标志位
                    return True
                if time.time() - check_service_start_time > timeout:
                    self.log_queue.put(['all', '[{}] runtimes:{} {}S内 DEBUG LOG 未检测到 Starting Reboot'.format(datetime.datetime.now(), runtimes, timeout)])
                    return False

    def debug_check(self, debug_passwd, runtimes):
        debug_port = self.uart_port if self.debug_port == '' else self.debug_port
        debug_port.write('\r\n'.encode('utf-8'))
        debug_port.read()
        debug_port.write('\r\n'.encode('utf-8'))
        starttime = time.time()
        flag = False
        login_flag = False
        eflag = False
        fflag = False
        while True:
            return_value_login = debug_port.readline().decode('utf-8', 'ignore')
            if return_value_login != '':
                self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value_login))])
                if "login:" in return_value_login:  # 登录debug口
                    debug_port.write('root\r\n'.encode('utf-8'))
                if 'word:' in return_value_login:
                    debug_port.write('{}\r\n'.format(debug_passwd).encode('utf-8'))
                    time.sleep(3)
                    debug_port.write('\r\n'.encode('utf-8'))
                    time.sleep(2)
                if "~ #" in return_value_login:
                    flag = True
                    login_flag = True
                if flag:
                    debug_port.write('cat /run/ql_voice_server.log\r\n'.encode('utf-8'))
                    time.sleep(2)
                    flag = False
                if 'msg_id=0X2E' in return_value_login:
                    eflag = True
                if 'msg_id=0X1F' in return_value_login:
                    fflag = True
            if time.time() - starttime > 15 or return_value_login.endswith("~ # \\r\\n"):
                break
        if eflag and fflag:
            self.log_queue.put(['at_log', '[{}] 已检测到msg_id=0X2E及msg_id=0X1F'.format(datetime.datetime.now())])
            time.sleep(2)
            debug_port.write('rm /run/ql_voice_server.log\r\n'.encode('utf-8'))
            return True
        elif not login_flag:
            self.log_queue.put(['at_log', '[{}] Debug口登录失败'.format(datetime.datetime.now())])
            return False
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 未检测到msg_id=0X2E及msg_id=0X1F'.format(datetime.datetime.now(), runtimes)])
            pause()

    def debug_login(self, debug_passwd, runtimes):
        debug_port = self.uart_port if self.debug_port == '' else self.debug_port
        debug_port.write('\r\n'.encode('utf-8'))
        debug_port.read()
        debug_port.write('\r\n'.encode('utf-8'))
        starttime = time.time()
        while True:
            return_value_login = debug_port.readline().decode('utf-8', 'ignore')
            if return_value_login != '':
                self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value_login))])
                if "login:" in return_value_login:  # 登录debug口
                    debug_port.write('root\r\n'.encode('utf-8'))
                if 'word:' in return_value_login:
                    debug_port.write('{}\r\n'.format(debug_passwd).encode('utf-8'))
                    time.sleep(3)
                    debug_port.write('\r\n'.encode('utf-8'))
                    time.sleep(2)
                if "~ #" in return_value_login:
                    self.log_queue.put(['at_log', '[{}] debug口已登录'.format(datetime.datetime.now())])
                    return
            if time.time() - starttime > 10 or return_value_login.endswith("~ # \\r\\n"):
                self.log_queue.put(['all', '[{}] runtimes:{} 10S内debug口登录失败'.format(datetime.datetime.now(), runtimes)])
                return False

    def debug_query(self, input_word, check_words, re_flag, timeout, runtimes):
        debug_port = self.uart_port if self.debug_port == '' else self.debug_port
        debug_port.write('\r\n'.encode('utf-8'))
        debug_port.read()
        debug_port.write('\r\n'.encode('utf-8'))
        start_time = time.time()
        debug_port.write('{}\r\n'.format(input_word).encode('utf-8'))
        return_value_cache = ''
        key_flag = False
        word_flag = False
        while True:
            return_value = self.readline(debug_port)
            if return_value != '':
                self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value))])
                return_value_cache += return_value
            if check_words in return_value_cache and word_flag is False:
                self.log_queue.put(['at_log', '[{}] 已识别到{}'.format(datetime.datetime.now(), check_words)])
                word_flag = True
                key_flag = True
            if time.time() - start_time > timeout:
                if key_flag:
                    break
                self.log_queue.put(['all', '[{}] runtimes:{} 未识别到{}'.format(datetime.datetime.now(), runtimes, check_words)])
                self.log_queue.put(['at_log', '[{}] 实际返回值为: {}\n'.format(datetime.datetime.now(), return_value_cache)])
                self.log_queue.put(['df', runtimes, 'rmnet_Fail_times', 1])
                self.log_queue.put(['df', runtimes, 'IP_fail_times', 1])
                return False
        if re_flag:
            rmnet_info = ''.join(re.findall(r'rmnet_data0.*\n.*Mask', return_value_cache))
            ip_info = ''.join(re.findall(r'.*inet addr.*?([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})', rmnet_info))
            if re.match(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$", ip_info):
                self.log_queue.put(['at_log', '[{}] ip地址存在，地址为{}'.format(datetime.datetime.now(), ip_info)])
                self.log_queue.put(['df', runtimes, 'ip_address', ip_info])
                return
            else:
                self.log_queue.put(['at_log', '[{}] ip地址不存在'.format(datetime.datetime.now())])
                self.log_queue.put(['df', runtimes, 'IP_fail_times', 1])
                self.log_queue.put(['at_log', '[{}] return_value_cache-{}\nrmnet_info-{}\nip_info-{}'.format(datetime.datetime.now(), return_value_cache, rmnet_info, ip_info)])
