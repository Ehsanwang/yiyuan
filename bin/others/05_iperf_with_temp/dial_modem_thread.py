# -*- encoding=utf-8 -*-
from threading import Thread
import time
import datetime
import logging
import os
import serial
import serial.tools.list_ports
import re


class ModemThread(Thread):
    def __init__(self, runtimes, log_queue, modem_port, modem_queue):
        super().__init__()
        self.modem_port = modem_port.upper() if os.name == 'nt' else modem_port  # win平台转换为大写便于后续判断
        self.modem_port_opened = type(serial)
        self.runtimes = runtimes
        self.log_queue = log_queue
        self.modem_queue = modem_queue
        self.modem_flag = False
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.logger = logging.getLogger(__name__)
        self.log_queue.put(['modem_log', '请搜索ERROR查看modem口是否有异常\n' * 3])

    def run(self):
        runtimes_cache = 0
        while True:
            self.close_modem()
            while True:
                time.sleep(0.1)
                if runtimes_cache != self.runtimes:  # 拨号成功时开始
                    runtimes_cache = self.runtimes
                    self.log_queue.put(['modem_log', '[{}] {}runtimes:{}{}'.format(datetime.datetime.now(), '=' * 30, self.runtimes, '=' * 30)])
                    break
            self.open_modem()
            while True:
                time.sleep(0.5)
                if self.modem_flag:
                    self.modem_flag = False
                    break
                self.check_dial_netstatus(self.runtimes)

    def open_modem(self):
        """
        打开modem口
        :return: None
        """
        for _ in range(10):
            self.logger.info(self.modem_port_opened)
            try:  # 打开之前判断是否有close属性，有则close，没有pass
                getattr(self.modem_port_opened, 'close')
                self.modem_port_opened.close()
            except AttributeError:
                pass
            try:  # 端口打开失败->等待3S->再次打开端口->失败报端口异常
                self.modem_port_opened = serial.Serial(self.modem_port, baudrate=115200, timeout=0)
                return True
            except serial.serialutil.SerialException:
                time.sleep(2)
        self.log_queue.put(['modem_log', '[{}] 连续10次打开Modem口失败'.format(datetime.datetime.now())])

    def close_modem(self):
        """
        关闭modem口
        :return: None
        """
        try:
            self.logger.info(self.modem_port_opened)
            self.modem_port_opened.close()
        except AttributeError:
            pass

    def check_dial_netstatus(self, runtimes):
        """
        仅查询拨号过程中网络状态情况
        :param runtimes:
        :return: None
        """
        self.send_modem('AT+CREG?', self.modem_port_opened, runtimes)
        self.send_modem('AT+CGREG?', self.modem_port_opened, runtimes)
        self.send_modem('AT+CEREG?', self.modem_port_opened, runtimes)
        self.send_modem('AT+CSQ', self.modem_port_opened, runtimes)
        self.send_modem('AT+COPS?', self.modem_port_opened, runtimes, timeout=180)
        self.send_modem('AT+QENG="SERVINGCELL"', self.modem_port_opened, runtimes)

    def send_modem(self, at_command, modem_port_open, runtimes, timeout=0.3):
        """
        发送AT指令。（用于返回OK的AT指令）
        :param at_command: AT指令内容
        :param modem_port_open: 打开的modem口
        :param runtimes: 当前脚本的运行次数
        :param timeout: AT指令的超时时间，参考AT文档
        :return: AT指令返回值
        """
        try:
            for _ in range(1, 11):  # 连续10次发送AT返回空，并且每次检测到口还在，则判定为AT不通
                at_start_timestamp = time.time()
                modem_port_open.write('{}\r\n'.format(at_command).encode('utf-8'))
                self.log_queue.put(['modem_log', '[{} Send] {}'.format(datetime.datetime.now(), '{}\\r\\n'.format(at_command))])
                return_value_cache = ''
                while True:
                    # modem端口值获取
                    time.sleep(0.001)  # 减小CPU开销
                    return_value = self.readline(modem_port_open)
                    if return_value != '':
                        self.log_queue.put(['modem_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                        return_value_cache += '[{}] {}'.format(datetime.datetime.now(), return_value)
                        if 'OK' in return_value and at_command in return_value_cache:  # 避免发AT无返回值后，再次发AT获取到返回值的情况
                            return return_value_cache
                        if re.findall(r'ERROR\s+', return_value) and at_command in return_value_cache:
                            self.log_queue.put(['modem_log', '[{}] runtimes:{} {}指令返回ERROR'.format(datetime.datetime.now(), runtimes, at_command)]) if 'COPS' not in at_command else ''  # *屏蔽锁pin AT+COPS错误
                            return return_value_cache
                    # 超时等判断
                    current_total_time = time.time() - at_start_timestamp
                    if current_total_time > timeout:
                        if return_value_cache and at_command in return_value_cache:
                            self.log_queue.put(['modem_log', '[{}] ERROR {}命令执行超时'.format(datetime.datetime.now(), at_command)])
                            return return_value_cache
                        elif return_value_cache and at_command not in return_value_cache and 'OK' in return_value_cache:
                            self.log_queue.put(['modem_log', '[{}] ERROR {}命令执行返回格式错误，未返回AT指令本身'.format(datetime.datetime.now(), at_command)])
                            return return_value_cache
                        else:
                            self.log_queue.put(['modem_log', '[{}] ERROR {}命令执行{}S内无任何回显'.format(datetime.datetime.now(), at_command, timeout)])
                            time.sleep(0.5)
                            break
            else:
                self.log_queue.put(['modem_log', '[{}] ERROR modem线程连续10次执行{}命令无任何回显，AT不通'.format(datetime.datetime.now(), at_command)])
        except Exception as e:
            self.log_queue.put(['modem_log', '[{}] ERROR {}'.format(datetime.datetime.now(), e)])
            pass

    def readline(self, port):
        """
        重写readline方法，首先用in_waiting方法获取IO buffer中是否有值：
        如果有值，读取直到\n；
        如果有值，超过1S，直接返回；
        如果没有值，返回 ''
        :param port: 已经打开的端口
        :return: buf:端口读取到的值；没有值返回 ''
        """
        buf = ''
        try:
            if port.in_waiting > 0:
                start_time = time.time()
                while True:
                    buf += port.read(1).decode('utf-8', 'replace')
                    if buf.endswith('\n'):
                        return buf
                    elif time.time() - start_time > 1:
                        self.logger.info('异常 {}'.format(repr(buf)))
                        return buf
            else:
                return buf
        except OSError as error:
            self.logger.info('Fatal ERROR: {}'.format(error))
            return buf
