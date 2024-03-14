# -*- encoding=utf-8 -*-
import re
import subprocess
import serial.tools.list_ports
from threading import Thread
import datetime
import time
import os
from subprocess import PIPE, STDOUT
import random
import logging
import requests
from functions import pause
if os.name == 'nt':
    import winreg


class ProcessThread(Thread):
    def __init__(self, at_port, dm_port, process_queue, main_queue, log_queue):
        super().__init__()
        self.main_queue = main_queue
        self.process_queue = process_queue
        self.log_queue = log_queue
        self.at_port = at_port.upper() if os.name == 'nt' else at_port  # win平台转换为大写便于后续判断
        self.dm_port = dm_port.upper() if os.name == 'nt' else dm_port  # win平台转换为大写便于后续判断
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.logger = logging.getLogger(__name__)

    def run(self):
        while True:
            (func, *param), evt = self.process_queue.get()  # ['check_usb_driver', 0] <threading.Event object at 0x...>
            self.logger.info('{}->{}->{}'.format(func, param, evt))
            runtimes = param[-1]
            if func in self._methods_list:
                process_status = getattr(self.__class__, '{}'.format(func))(self, *param)
                if process_status is not False:
                    self.main_queue.put(True)
                else:
                    self.log_queue.put(['write_result_log', runtimes])
                    self.main_queue.put(False)
                evt.set()  # 取消阻塞

    def get_port_list(self):
        """
        获取当前电脑设备管理器中所有的COM口的列表
        :return: COM口列表，例如['COM3', 'COM4']
        """
        try:
            self.logger.info('get_port_list')
            port_name_list = []
            ports = serial.tools.list_ports.comports()
            for port, _, _ in sorted(ports):
                port_name_list.append(port)
            self.logger.info(port_name_list)
            return port_name_list
        except TypeError:  # Linux偶现
            return self.get_port_list()

    def get_port_list_nt(self):
        """
        获取当前电脑的COM口
        注意！仅在win耗时操作中使用，例如检测发送AT+QPOWD=1使用get_port_list方法每隔1秒获取当前设备列表，有几率时间非常长
        导致还没有检测到POWERED DOWN就超时了，判断无URC上报
        :return: COM口列表，例如['COM3', 'COM4']
        """
        self.logger.info('get_port_list_nt')
        port_name_list = []
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
        port_nums = winreg.QueryInfoKey(key)[1]  # 获取列表中端口的数量
        try:
            for port in range(port_nums):
                name, value, _ = winreg.EnumValue(key, port)
                port_name_list.append(value)
            self.logger.info(port_name_list)
            return port_name_list
        except OSError:  # 如果正在枚举列表的时候突然端口变化，有几率触发OSError
            self.logger.info(port_name_list)
            return port_name_list

    def check_dump(self, runtimes):
        """
        检测模块是否dump
        :param runtimes:当前脚本的运行的次数
        :return: None
        """
        port_list = self.get_port_list()
        if self.dm_port in port_list and self.at_port not in port_list:  # DM口在端口列表，AT口不在端口列表，则DUMP
            self.log_queue.put(['all', '[{}] runtimes:{} 模块DUMP'.format(datetime.datetime.now(), runtimes)])
            pause()

    def get_usb_enumerate_status(self, pid_vid, runtimes):
        """
        用于Linux下获取当前USB枚举是否正常。
        :param pid_vid: 需要检测的模块的pid，vid
        :param runtimes: 当前脚本的运行次数
        :return: True，检测成功；False，检测失败
        """
        return_value = os.popen('lsusb').read()
        self.logger.info(return_value)
        if pid_vid.lower() not in return_value.lower():
            self.log_queue.put(['all', "[{}] runtimes:{} lsusb指令指令未检测到{}，请检查主脚本辅助参数pid_vid参数是否设置正确".format(datetime.datetime.now(), runtimes, pid_vid)])
            pause()

    def mbim_connect_ping(self, runtimes):
        """
        进行MBIM拨号连接
        :param runtimes: 脚本运行次数
        :return: True:连接成功；False：连接失败
        """
        interface_name = self.get_interface_name(runtimes)
        os.popen('netsh mbn connect interface="{}" connmode=tmp name=_profile.xml'.format(interface_name))
        time.sleep(10)  # 等待10秒稳定
        interface_data = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
        if '已连接' in interface_data:
            self.log_queue.put(['at_log', '[{}] {}MBIM连接成功'.format(datetime.datetime.now(), runtimes)])
            if self.get_subprocess_result():
                ping_value = ''.join(self.get_subprocess_result())
                return_send_recieve = re.search(r'已发送 = (\d+)，已接收 = (\d+)', ping_value)
                if int(return_send_recieve.group(1)) == int(return_send_recieve.group(2)):
                    self.log_queue.put(['at_log', '[{}] PING百度成功，且发送与接收数据相同'.format(datetime.datetime.now())])
                    return True
                elif int(return_send_recieve.group(1)) != int(return_send_recieve.group(2)):
                    self.log_queue.put(['at_log', '[{}] PING百度成功，但存在数据丢失'.format(datetime.datetime.now())])
                    return True
            else:
                self.log_queue.put(['all', '[{}] MBIM连接成功，但PING失败'.format(datetime.datetime.now())])
                return False
        else:
            self.log_queue.put(['all', '[{}] runtimes:{}MBIM连接失败'.format(datetime.datetime.now(), runtimes)])
            return False

    def get_interface_name(self, runtimes):
        """
        获取连接的名称
        :param runtimes: 当前运行次数
        :return: 当前连接名称
        """
        mobile_broadband_info = os.popen('netsh mbn show interface').read()
        mobile_broadband_num = ''.join(re.findall(r'系统上有 (\d+) 个接口', mobile_broadband_info))  # 手机宽带数量
        if mobile_broadband_num and int(mobile_broadband_num) > 1:
            self.log_queue.put(['all', "[{}] runtimes: {} 系统上移动宽带有{}个，多于一个".format(datetime.datetime.now(), runtimes, mobile_broadband_num)])
            pause()
        mobile_broadband_name = ''.join(re.findall(r'\s+名称\s+:\s(.*)', mobile_broadband_info))
        return mobile_broadband_name

    def get_subprocess_result(self):
        """
        :return: data_list  ping返回数据列表
        """
        sub = subprocess.Popen(['ping', 'www.baidu.com'], shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        data_list = []
        while True:
            time.sleep(0.001)
            ping_data = sub.stdout.readline().decode('GBK', 'ignore')
            if ping_data != '':
                data_list.append(ping_data)
            else:
                sub.terminate()
                return data_list

    def disconnect(self, runtimes):
        """
        断开MBIM拨号连接
        :param runtimes: 脚本的运行次数
        :return: True：拨号断开连接成功；False：拨号断开连接失败。
        """
        disconnect_times = 10
        interface_name = self.get_interface_name(runtimes)
        for i in range(disconnect_times):
            # 断开连接
            os.popen('netsh mbn disconnect interface="{}"'.format(interface_name))
            time.sleep(5)
            interface_status = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
            # 断开连接判断
            if '未连接' in interface_status:
                self.log_queue.put(['at_log', '[{}] 断开拨号连接成功'.format(datetime.datetime.now())])
                time.sleep(5)
                return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} 断开拨号连接失败'.format(datetime.datetime.now(), runtimes)])
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 连续{}次断开拨号连接失败'.format(datetime.datetime.now(), runtimes, disconnect_times)])
            return False

    def disconnect_dial(self, dial_mode, runtimes):
        """
        linux下 wwan、Gobinet断开拨号（kill quectel-CM进程）
        :param dial_mode: 拨号方式
        :param runtimes:
        :return:
        """
        dis_timeout = 10
        try:
            cmd = subprocess.run('killall quectel-CM', shell=True, timeout=dis_timeout)
            code = cmd.returncode
            if code == 1 or code == 0:
                self.log_queue.put(['at_log', '[{}]断开{}拨号成功'.format(datetime.datetime.now(), dial_mode)])
                self.log_queue.put(['df', runtimes, 'dial_disconnect_success_times', 1])
                return True
        except subprocess.TimeoutExpired as e:
            self.log_queue.put(['at_log', '[{}]{}S内断开{}拨号失败'.format(datetime.datetime.now(), dis_timeout, dial_mode)])
            self.log_queue.put(['df', runtimes, 'dial_disconnect_fail_times', 1])
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), e)])

    def ecm_connect_check(self, runtimes):
        """
        检查ECM拨号的拨号状态：
        1. ifconfig -a查询值必须包含usb0；
        2. lsusb -t查询值必须包含cdc_ether
        :param runtimes: 当前脚本的运行次数
        :return:True，检查成功；False，检查失败
        """
        # 检查ifconfig
        ifconfig_value = os.popen('ifconfig -a').read()
        self.logger.info(ifconfig_value)
        if 'usb0' not in ifconfig_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ifconfig_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} ifconfig -a指令未查询到usb0网卡'.format(datetime.datetime.now(), runtimes)])
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] ECM拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，ECM拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def wwan_connect_check(self, runtimes):
        """
        检查WWAN拨号的拨号状态：
        1. ifconfig -a查询值必须包含wwan0；
        2. lsusb -t查询值必须包含qmi_wwan
        :param runtimes: 当前脚本的运行次数
        :return:True，检查成功；False，检查失败
        """
        # 进行WWAN拨号
        os.system('quectel-CM > /home/quectel-CM.log 2>&1 &')
        time.sleep(10)  # 等待10S拨号状态正常
        # 检查ifconfig
        ifconfig_value = os.popen('ifconfig -a').read()
        self.logger.info(ifconfig_value)
        if 'usb0' not in ifconfig_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ifconfig_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} ifconfig -a指令未查询到wwan0网卡'.format(datetime.datetime.now(), runtimes)])
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] WWAN拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，WWAN拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def gobinet_connect_check(self, runtimes):
        """
        检查GobiNet拨号的拨号状态：
        1. ifconfig -a查询值必须包含usb0；
        2. lsusb -t查询值必须包含gobinet
        :param runtimes: 当前脚本的运行次数
        :return:True，检查成功；False，检查失败
        """
        # 进行GobiNet拨号
        os.system('quectel-CM > /home/quectel-CM.log 2>&1 &')
        time.sleep(10)  # 等待10S拨号状态正常
        # 检查ifconfig
        ifconfig_value = os.popen('ifconfig -a').read()
        self.logger.info(ifconfig_value)
        if 'usb0' not in ifconfig_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ifconfig_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} ifconfig -a指令未查询到usb0网卡'.format(datetime.datetime.now(), runtimes)])
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] GobiNet拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，GobiNet拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def mbim_connect_check(self, runtimes):
        """
        检查mbim拨号的拨号状态：
        1. ifconfig -a查询值必须包含usb0；
        2. lsusb -t查询值必须包含gobinet
        :param runtimes: 当前脚本的运行次数
        :return:True，检查成功；False，检查失败
        """
        # 进行Mbim拨号
        os.system('quectel-CM > /home/quectel-CM.log 2>&1 &')
        time.sleep(10)  # 等待10S拨号状态正常
        # 检查ifconfig
        ifconfig_value = os.popen('ifconfig -a').read()
        self.logger.info(ifconfig_value)
        if 'wwan0' not in ifconfig_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ifconfig_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} ifconfig -a指令未查询到wwan0网卡'.format(datetime.datetime.now(), runtimes)])
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] MBIM拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，MBIM拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def connect(self, dial_mode, runtimes):
        """
        进行MBIM或者NDIS的拨号连接
        :param dial_mode: 拨号模式，MBIM还是NDIS
        :param runtimes: 脚本运行次数
        :return: True:连接成功；False：连接失败
        """
        interface_data = ''
        connect_timeout = 30
        interface_name = self.get_interface_name(runtimes)
        dial_connect_start_timestamp = time.time()
        os.popen('netsh mbn connect interface="{}" connmode=tmp name=_profile.xml'.format(interface_name))
        self.log_queue.put(['df', runtimes, 'dial_connect_time', time.time() - dial_connect_start_timestamp])  # dial_connect_time
        for i in range(connect_timeout):
            interface_data = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
            if '已连接' in interface_data:
                self.log_queue.put(['at_log', '[{}] {}连接成功'.format(datetime.datetime.now(), dial_mode)])
                self.log_queue.put(['df', runtimes, 'dial_success_times', 1])  # runtimes_start_timestamp
                return True
            time.sleep(1)
        else:
            self.logger.info(interface_data)
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), interface_data)])
            self.log_queue.put(['all', '[{}] runtimes:{} 连续{}S，{}拨号后未连接成功'.format(datetime.datetime.now(), runtimes, connect_timeout, dial_mode)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # runtimes_start_timestamp
            return False

    def check_ip_connect_status(self, dial_mode, runtimes):
        """
        判断ipconfig中信息并判断连接信息
        :param runtimes: 运行的次数
        :param dial_mode: 拨号模式
        :return: True:没有异常；False：异常
        """
        # 判断驱动名称是否正常
        driver_name = os.popen('netsh mbn show interface | findstr "Quectel Generic"').read()
        if dial_mode.upper() == 'NDIS' and "Quectel Wireless Ethernet Adapter" not in repr(driver_name):
            self.log_queue.put(['all', '[{}] runtimes:{} 拨号驱动加载异常，NDIS拨号加载非NDIS驱动'.format(datetime.datetime.now(), runtimes)])
            pause()
        elif dial_mode.upper() == 'MBIM' and 'Generic Mobile Broadband Adapter' not in repr(driver_name):
            self.log_queue.put(['all', '[{}] runtimes:{} 拨号驱动加载异常，MBIM拨号加载非MBIM驱动'.format(datetime.datetime.now(), runtimes)])
            pause()

        # ipconfig获取ip信息并判断
        ip_abnormal_flag = False
        ip_verify_start_timestamp = time.time()
        timeout = 60
        while True:
            connection_dic = {}
            ipconfig = os.popen('ipconfig').read()  # 获取ipconfig的值
            ipconfig = re.sub('\n.*?\n\n\n', '', ipconfig)  # 去除\nWindows IP 配置\n\n\n
            ipconfig_list = ipconfig.split('\n\n')
            for i in range(0, len(ipconfig_list), 2):  # 步进2，i为key，i+1为value
                ipv4 = ''.join(re.findall(r'.*IPv4.*?([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})', ipconfig_list[i + 1]))
                self.log_queue.put(['df', runtimes, 'ip_address', ipv4])  # ip_address
                connection_dic[ipconfig_list[i]] = ipv4
            for key, value in connection_dic.items():
                self.log_queue.put(['at_log', '[{}] 网络名称：{}，IPV4地址：{}'.format(datetime.datetime.now(), key, value)])
                if '移动宽带' in key and value == '':  # 异常无ip情况
                    ip_abnormal_flag = True
                elif '自动配置' in key:  # 出现自动配置异常情况
                    ip_abnormal_flag = True
                elif '移动宽带' not in key and value != '':  # 出现宽带名称不是移动宽带并且ip不为空
                    ip_abnormal_flag = True
            if ip_abnormal_flag is False:
                break
            elif time.time() - ip_verify_start_timestamp < timeout:
                ip_abnormal_flag = False
                time.sleep(5)
            else:
                break
        if ip_abnormal_flag:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ipconfig)])
            self.log_queue.put(['all', '[{}] runtimes:{} IP异常'.format(datetime.datetime.now(), runtimes)])
            self.log_queue.put(['df', runtimes, 'ip_error_times', 1])  # ip_error_times
            return False

        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        request_status = ''
        num = 0
        for num in range(1, 11):
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    return True
                else:
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
                    self.log_queue.put(['all', '[{}] runtimes:{} 请求{}时{}秒无返回{}'.format(datetime.datetime.now(), runtimes, url, timeout, request_status)])
                    self.log_queue.put(['df', runtimes, 'ip_error_times', 1])  # ip_error_times
            except Exception as e:
                self.logger.info(e)
                self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
                self.log_queue.put(['all', '[{}] runtimes:{} 请求{}时{}秒无返回{}'.format(datetime.datetime.now(), runtimes, url, timeout, request_status)])
                self.log_queue.put(['df', runtimes, 'ip_error_times', 1])  # ip_error_times
                time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，{}拨号异常'.format(datetime.datetime.now(), runtimes, num, url, dial_mode)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False
