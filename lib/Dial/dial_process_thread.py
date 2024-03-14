# -*- encoding=utf-8 -*-
import datetime
import filecmp
import os
import re
import socket
import subprocess
import threading
import time
from functools import partial
from ftplib import all_errors
import requests
import serial.tools.list_ports
from threading import Thread
from ftplib import FTP
from requests_toolbelt import MultipartEncoder  # 用于流式上传文件
import xml.etree.ElementTree as ET
import logging
import aioftp
import asyncio
import shutil
import numpy as np
import glob
import signal
from functions import pause, IPerfServer
from speedtest import Speedtest
import random
import string


class DialProcessThread(Thread):
    def __init__(self, at_port, dm_port, process_queue, main_queue, log_queue):
        super().__init__()
        self.main_queue = main_queue
        self.process_queue = process_queue
        self.log_queue = log_queue
        self.at_port = at_port
        self.dm_port = dm_port
        self.client_tcp_udp = ''
        self.ftp = FTP()
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.logger = logging.getLogger(__name__)
        self.unique_folder_head = None
        self.folder_name_list = None
        self.file_compare_fail_times = 0
        self.ping_cmd = 'ping www.qq.com' if os.name == 'nt' else 'ping www.qq.com -c 4'

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
                evt.set()

    def check_usb_driver(self, debug, runtimes):
        """
        检测驱动是否出现
        :param debug: True:timeout时间内检测不到驱动暂停脚本; False:timeout时间内检测不到驱动不暂停脚本
        :param runtimes:当前脚本的运行的次数
        :return: True:检测到驱动；False：没有检测到驱动
        """
        check_usb_driver_start_timestamp = time.time()
        timeout = 300
        while True:
            port_list = self.get_port_list()
            check_usb_driver_total_time = time.time() - check_usb_driver_start_timestamp
            if check_usb_driver_total_time < timeout:  # timeout S内
                if self.at_port in port_list and self.dm_port in port_list:  # 正常情况
                    self.log_queue.put(['at_log', '[{}] USB驱动{}加载成功!'.format(datetime.datetime.now(), self.at_port)])
                    self.log_queue.put(['df', runtimes, 'driver_appear_timestamp', time.time()]) if runtimes != 0 else 1  # driver_appear_timestamp
                    return True
                elif self.dm_port in port_list and self.at_port not in port_list:  # 发现仅有DM口并且没有AT口
                    for i in range(10):
                        port_list = self.get_port_list()
                        if self.at_port in port_list and self.dm_port in port_list:  # 正常情况
                            self.log_queue.put(['at_log', '[{}] USB驱动{}加载成功!'.format(datetime.datetime.now(), self.at_port)])
                            self.log_queue.put(['df', runtimes, 'driver_appear_timestamp', time.time()]) if runtimes != 0 else 1  # driver_appear_timestamp
                            return True
                        time.sleep(0.3)
                    port_list = self.get_port_list()
                    if self.dm_port in port_list and self.at_port not in port_list:
                        self.log_queue.put(['all', '[{}] runtimes:{} 模块DUMP'.format(datetime.datetime.now(), runtimes)])
                        self.check_usb_driver(True, runtimes)
                else:
                    # linux qfirehose升级端口加载100ms内可能上报RDY，所以减小延迟
                    time.sleep(0.1) if os.name == 'nt' else time.sleep(0.01)
            else:  # timeout秒驱动未加载
                if debug:
                    self.log_queue.put(['all', "[{}] runtimes:{} 模块开机{}秒内USB驱动{}加载失败".format(datetime.datetime.now(), runtimes, timeout, self.at_port)])
                    pause()
                else:
                    self.log_queue.put(['all', "[{}] runtimes:{} 模块开机{}秒内USB驱动{}加载失败".format(datetime.datetime.now(), runtimes, timeout, self.at_port)])
                    return False

    def check_usb_driver_dis(self, debug, runtimes):
        """
        检测某个COM口是否消失
        :param debug: True: timeout时间内检测不到驱动消失，暂停脚本；False：timeout时间涅日检测不到驱动消失，不暂停脚本
        :param runtimes: 当前脚本运行次数
        :return: None
        """
        check_usb_driver_dis_start_timestamp = time.time()
        timeout = 300
        while True:
            port_list = self.get_port_list()
            check_usb_driver_dis_total_time = time.time() - check_usb_driver_dis_start_timestamp
            if check_usb_driver_dis_total_time < timeout:  # 300S内
                if self.at_port not in port_list:
                    self.log_queue.put(['at_log', '[{}] USB驱动{}掉口成功!'.format(datetime.datetime.now(), self.at_port)])
                    break
                else:
                    time.sleep(0.1)
            else:
                if debug:
                    self.log_queue.put(['all', '[{}] runtimes:{} USB驱动{}掉口失败!'.format(datetime.datetime.now(), runtimes, self.at_port)])
                    pause()
                else:
                    self.log_queue.put(['all', '[{}] runtimes:{} USB驱动{}掉口失败!'.format(datetime.datetime.now(), runtimes, self.at_port)])
                    return False

    def get_port_list(self):
        """
        获取当前电脑设备管理器中所有的COM口的列表
        :return: COM口列表，例如['COM3', 'COM4']
        """
        if os.name == 'nt':
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
        else:
            return glob.glob('/dev/ttyUSB*')

    @staticmethod
    def check_port():
        """
        获取当前电脑设备管理器中所有的COM口的列表
        :return: COM口列表，例如['COM3', 'COM4']
        """
        port_name_list = []
        ports = serial.tools.list_ports.comports()
        for port, _, _ in sorted(ports):
            port_name_list.append(port)
        return port_name_list

    def check_dump(self, runtimes):
        """
        检测模块是否dump
        :param runtimes:当前脚本的运行的次数
        :return: None
        """
        port_list = self.check_port()
        if self.dm_port in port_list:  # DM口在端口列表，AT口不在端口列表，则DUMP
            if self.at_port not in port_list:
                self.log_queue.put(['all', '[{}] {} 模块DUMP'.format(datetime.datetime.now(), runtimes)])
                pause()

    def wait_dial_init(self, runtimes):
        """
        等待模块开机后PC端拨号功能加载成功
        :param runtimes:
        :return:
        """
        timeout = 100  # 等待PC端拨号可以使用的最大时间
        stat_timestamp = time.time()
        while True:
            interface_status = os.popen('netsh mbn show interface').read()
            self.log_queue.put(['at_log', "[{}] {}".format(datetime.datetime.now(), interface_status)])

            if time.time() - stat_timestamp > timeout:
                self.log_queue.put(['all', "[{}] runtimes: {} 开机成功后{}秒内PC拨号功能未加载成功，请确定原因".format(datetime.datetime.now(), runtimes, timeout)])
                pause()

            if '没有' in interface_status:
                time.sleep(3)
            else:
                self.log_queue.put(['at_log', "[{}] 拨号功能加载成功".format(datetime.datetime.now())])
                time.sleep(10)  # 等待稳定
                # 判断是否有profile，如果有，不再生成
                if os.path.exists("_profile.xml"):
                    return True
                # 获取本机移动宽带数量和移动宽带名称
                for i in range(10):
                    try:
                        mobile_broadband_info = os.popen('netsh mbn show interface').read()
                        mobile_broadband_num = ''.join(re.findall(r'系统上有 (\d+) 个接口', mobile_broadband_info))  # 手机宽带数量
                        if mobile_broadband_num and int(mobile_broadband_num) > 1:
                            self.log_queue.put(['all', "[{}] runtimes: {} 系统上移动宽带有{}个，多于一个".format(datetime.datetime.now(), runtimes, mobile_broadband_num)])
                            pause()
                        mobile_broadband_name = ''.join(re.findall(r'\s+名称\s+:\s(.*)', mobile_broadband_info))
                        # 获取SubscriberID和SimIccID
                        interface_info = os.popen('netsh mbn show ready *').read()
                        subscriber_id = ''.join(re.findall(r'订户\sID\s+:\s(.*)', interface_info))
                        sim_icc_id = ''.join(re.findall(r'SIM\sICC\sID\s+:\s(.*)', interface_info))
                        # 获取运营商编码
                        home_provider = os.popen('netsh mbn show homeprovider interface="{}"'.format(mobile_broadband_name)).read()
                        home_provider_id = ''.join(re.findall(r'ID:\s(\d+)', home_provider))
                        apn_dict = {
                            '46000': 'cmnet',  # 移动
                            '46002': 'cmnet',  # 移动
                            '46007': 'cmnet',  # 移动
                            '46004': 'cmnet',  # 移动
                            '46001': '3gnet',  # 联通
                            '46006': '3gnet',  # 联通
                            '46009': '3gnet',  # 联通
                            '46003': 'ctnet',  # 电信
                            '46005': 'ctnet',  # 电信
                            '46011': 'ctnet',  # 电信
                            '00101': 'QSS',    # 仪表
                            '50501': 'QSS',    # 仪表
                        }
                        # 写入XML文件
                        # 参考 https://docs.microsoft.com/en-us/windows/win32/mbn/element-mbnprofileext
                        mbn_profile = ET.Element('MBNProfileExt', xmlns='http://www.microsoft.com/networking/WWAN/profile/v4')
                        ET.SubElement(mbn_profile, "Name").text = apn_dict[home_provider_id]
                        ET.SubElement(mbn_profile, "IsDefault").text = 'true'
                        ET.SubElement(mbn_profile, "ProfileCreationType").text = 'DeviceProvisioned'
                        ET.SubElement(mbn_profile, "SubscriberID").text = subscriber_id
                        ET.SubElement(mbn_profile, "SimIccID").text = sim_icc_id
                        ET.SubElement(mbn_profile, "ConnectionMode").text = 'auto'  # ims : manual
                        context = ET.SubElement(mbn_profile, "Context")
                        ET.SubElement(context, "AccessString").text = apn_dict[home_provider_id]
                        ET.SubElement(context, "Compression").text = 'DISABLE'
                        ET.SubElement(context, "AuthProtocol").text = 'NONE'
                        ET.SubElement(context, "IPType").text = 'IPv4v6'
                        tree = ET.ElementTree(mbn_profile)
                        tree.write("_profile.xml")
                        return True
                    except KeyError:
                        time.sleep(1)
                        pass
                else:
                    self.log_queue.put(['all', "[{}] runtimes: {} 连续10次生成拨号配置文件失败".format(datetime.datetime.now(), runtimes)])
                    pause()

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

    def reset_connect(self, runtimes):
        """
        如果MBIM/NDIS为连接状态，则关闭连接。
        :param runtimes: 当前脚本的运行次数
        :return: True:执行成功；False:执行失败
        """
        interface_name = self.get_interface_name(runtimes)

        # 检查是否是未连接，如果是未连接，跳出
        interface_data = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
        if '未连接' in interface_data:
            return True
        os.popen('netsh mbn disconnect interface="{}"'.format(interface_name)).read()
        for i in range(10):
            time.sleep(1)
            interface_data = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
            if '未连接' in interface_data:
                self.log_queue.put(['at_log', '[{}] 连接重置成功'.format(datetime.datetime.now())])
                return True
        else:
            self.logger.info(interface_data)
            self.log_queue.put(['all', '[{}] runtimes:{} 连接重置失败'.format(datetime.datetime.now(), runtimes)])
            return False

    def check_ip_connect_status(self, dial_mode, network_driver_name, runtimes):
        """
        判断ipconfig中信息并判断连接信息
        :param runtimes: 运行的次数
        :param dial_mode: 拨号模式
        :param network_driver_name: NDIS或者MBIM拨号的网卡名称
        :return: True:没有异常；False：异常
        """
        # 判断驱动名称是否正常
        driver_name = os.popen('netsh mbn show interface | findstr "{}"'.format(network_driver_name)).read()
        if dial_mode.upper() == 'NDIS' and network_driver_name not in repr(driver_name):
            self.log_queue.put(['all', '[{}] runtimes:{} 拨号驱动加载异常，NDIS拨号加载非NDIS驱动'.format(datetime.datetime.now(), runtimes)])
            pause()
        elif dial_mode.upper() == 'MBIM' and network_driver_name not in repr(driver_name):
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
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
                    self.log_queue.put(['all', '[{}] runtimes:{} 请求{}时{}秒无返回{}'.format(datetime.datetime.now(), runtimes, url, timeout, request_status)])
                    self.log_queue.put(['df', runtimes, 'ip_error_times', 1])  # ip_error_times
            except Exception as e:
                self.logger.info(e)
                self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
                self.log_queue.put(['all', '[{}] runtimes:{} 请求{}时{}秒无返回{}'.format(datetime.datetime.now(), runtimes, url, timeout, request_status)])
                self.log_queue.put(['df', runtimes, 'ip_error_times', 1])  # ip_error_times
                time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，{}拨号异常'.format(datetime.datetime.now(), runtimes, num, url, dial_mode)])
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
        dial_status = os.popen('netsh mbn connect interface="{}" connmode=tmp name=_profile.xml'.format(interface_name)).read()
        self.logger.info('{} return {}'.format('netsh mbn connect interface="{}" connmode=tmp name=_profile.xml'.format(interface_name), dial_status))
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

    def disconnect(self, runtimes):
        """
        断开NDIS/MBIM拨号连接
        :param runtimes: 脚本的运行次数
        :return: True：拨号断开连接成功；False：拨号断开连接失败。
        """
        disconnect_times = 10
        interface_name = self.get_interface_name(runtimes)
        for i in range(disconnect_times):
            # 断开连接
            dial_disconnect_start_timestamp = time.time()
            interface_status = os.popen('netsh mbn disconnect interface="{}"'.format(interface_name)).read()
            self.logger.info(f"interface_status: {interface_status}")
            self.log_queue.put(['df', runtimes, 'dial_disconnect_time', time.time() - dial_disconnect_start_timestamp])  # dial_disconnect_time
            time.sleep(5)
            interface_status = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
            self.logger.info(f"interface_status: {interface_status}")
            # 断开连接判断
            if '未连接' in interface_status:
                self.log_queue.put(['at_log', '[{}] 断开拨号连接成功'.format(datetime.datetime.now())])
                self.log_queue.put(['df', runtimes, 'dial_disconnect_success_times', 1])  # runtimes_start_timestamp
                time.sleep(5)
                return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} 断开拨号连接失败'.format(datetime.datetime.now(), runtimes)])
            self.log_queue.put(['df', runtimes, 'dial_disconnect_fail_times', i])  # runtimes_start_timestamp
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 连续{}次断开拨号连接失败'.format(datetime.datetime.now(), runtimes, disconnect_times)])
            self.log_queue.put(['df', runtimes, 'dial_disconnect_fail_times', 10])  # runtimes_start_timestamp
            return False

    def client_connect(self, connect_type, server_ip, server_port, runtimes):
        """
        进行TCP/UDP连接
        :param connect_type: 连接是TCP还是UDP
        :param server_ip: 服务器的地址
        :param server_port: 服务器端口
        :param runtimes: 脚本的运行次数
        :return: True:连接成功；False：连接失败。
        """
        try:
            connect_times = 10
            for i in range(connect_times):  # 进行connect_times次连接，如果成功则跳出，失败继续
                tcp_udp_connect_start_timestamp = time.time()
                # 进行TCP/UDP连接
                self.client_tcp_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if connect_type == 'UDP' else socket.SOCK_STREAM)
                conn = self.client_tcp_udp.connect_ex((server_ip, server_port))
                self.client_tcp_udp.setblocking(False)
                self.log_queue.put(['df', runtimes, 'tcp_udp_connect_time', time.time() - tcp_udp_connect_start_timestamp])  # tcp_udp_connect_time
                # 发送接收数据验证连接是否正常
                self.client_tcp_udp.sendall(b"hello world!")
                hello_start_time = time.time()
                while True:
                    try:
                        data_recv = self.client_tcp_udp.recv(1024).decode('GBK')
                        if data_recv:
                            break
                    except BlockingIOError:
                        if time.time() - hello_start_time > 3:
                            data_recv = ''
                            break
                if conn == 0 and data_recv == 'hello world!':  # 正常情况
                    self.log_queue.put(['at_log', '[{}] {}连接成功'.format(datetime.datetime.now(), connect_type)])
                    self.log_queue.put(['df', runtimes, 'tcp_udp_connect_success_times', 1])  # runtimes_start_timestamp
                    return True  # 连接成功
                else:  # 异常情况
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
                    self.log_queue.put(['all', '[{}] runtimes:{} {}连接异常'.format(datetime.datetime.now(), runtimes, connect_type)])
                self.log_queue.put(['df', runtimes, 'tcp_udp_connect_fail_times', i])  # runtimes_start_timestamp
            else:  # 连续10次TCP/UDP失败返回False
                self.log_queue.put(['all', '[{}] runtimes: {} {}连续{}次连接失败'.format(datetime.datetime.now(), runtimes, connect_type, connect_times)])
                self.log_queue.put(['df', runtimes, 'tcp_udp_connect_fail_times', 10])  # runtimes_start_timestamp
                return False
        except Exception as e:
            self.log_queue.put(['all', '[{}] runtimes:{} {}'.format(datetime.datetime.now(), runtimes, e)])
            return False

    def client_send_recv_compare(self, connect_type, source_name, receive_file_name, runtimes):
        """
        TCP/UDP建立连接成功后，发送文件->接收文件->对比文件
        :param connect_type: 连接类型，TCP还是UDP
        :param source_name: 源文件的名称
        :param receive_file_name: 接收保存的文件的名称
        :param runtimes: 当前脚本的运行次数
        :return: True：发送接收对比都成功；False：接收失败；Timeout:接收超时。
        """
        try:
            # 1. 获取文件路径和大小信息
            base_path = os.path.dirname(os.getcwd())
            file_path = os.path.join(base_path, source_name)
            file_size = os.path.getsize(file_path)
            # 2. 发送数据
            self.log_queue.put(['at_log', '[{}] 开始发送文件'.format(datetime.datetime.now())])
            with open(file_path, 'rb') as f:
                if connect_type == 'TCP':
                    total_sent = 0
                    send_data = f.read()
                    while total_sent < file_size:
                        sent = self.client_tcp_udp.send(send_data[total_sent:])
                        if sent == 0:
                            raise RuntimeError("socket connection broken")
                        total_sent = total_sent + sent
                else:
                    send_size = 0
                    self.logger.info('UDP开始发送')
                    while True:
                        time.sleep(0.01)
                        buffer = self.client_tcp_udp.send(f.read(1024))
                        send_size += buffer
                        if send_size >= file_size:
                            break
                    self.logger.info('UDP发送完成')

            # 3. 接收数据
            self.log_queue.put(['at_log', '[{}] 开始接收文件'.format(datetime.datetime.now())])
            recv_data_start_timestamp = time.time()
            file_path_recv = os.path.join(base_path, receive_file_name)
            with open(file_path_recv, mode='wb') as f:
                recv_size = 0  # 单文件已接收字节数
                while True:
                    try:
                        buffer = self.client_tcp_udp.recv(8196)
                        recv_size += len(buffer)
                        f.write(buffer)
                        if recv_size >= file_size:
                            break
                    except BlockingIOError:
                        # 接收超时判断
                        if time.time() - recv_data_start_timestamp > 60:
                            self.log_queue.put(['all', '[{}] runtimes:{} {}接收文件超时'.format(datetime.datetime.now(), runtimes, connect_type)])
                            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
                            return False
            self.log_queue.put(['df', runtimes, 'recv_file_time', time.time() - recv_data_start_timestamp])  # runtimes_start_timestamp
            # 3. 对比文件
            if filecmp.cmp(file_path, file_path_recv, False):
                self.log_queue.put(['at_log', '[{}] 源文件和目标文件对比相同'.format(datetime.datetime.now())])
                return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} 源文件和目标文件对比不同'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'file_compare_fail_times', 1])  # file_compare_fail_times
                return False
        except Exception as e:
            self.log_queue.put(['all', '[{}] runtimes:{} {}'.format(datetime.datetime.now(), runtimes, e)])
            return False

    def client_disconnect(self, connect_type, runtimes):
        """
        断开TCP/UDP连接。
        :param connect_type: 连接类型，TCP还是UDP
        :param runtimes: 运行次数
        :return: True，连接成功；False：连接失败
        """
        try:
            disconnect_times = 10
            for i in range(disconnect_times):
                tcp_udp_disconnect_start_timestamp = time.time()
                self.client_tcp_udp.close()
                self.log_queue.put(['df', runtimes, 'tcp_udp_disconnect_time', time.time() - tcp_udp_disconnect_start_timestamp])  # tcp_udp_disconnect_time
                if 'closed' in repr(self.client_tcp_udp):
                    self.log_queue.put(['at_log', '[{}] {}断开连接成功'.format(datetime.datetime.now(), connect_type)])
                    self.log_queue.put(['df', runtimes, 'tcp_udp_disconnect_success_times', 1])  # runtimes_start_timestamp
                    return True
                else:
                    self.log_queue.put(['all', '[{}] runtimes: {} {}断开连接失败'.format(datetime.datetime.now(), runtimes, connect_type)])
                self.log_queue.put(['df', runtimes, 'tcp_udp_disconnect_fail_times', i])  # runtimes_start_timestamp
            else:  # 连续10次TCP/UDP断开失败返回False
                self.log_queue.put(['all', '[{}] runtimes: {} {}连续{}次断开连接失败'.format(datetime.datetime.now(), runtimes, connect_type, disconnect_times)])
                self.log_queue.put(['df', runtimes, 'tcp_udp_disconnect_fail_times', 10])  # runtimes_start_timestamp
                return False
        except Exception as e:
            self.log_queue.put(['all', '[{}] runtimes:{} {}'.format(datetime.datetime.now(), runtimes, e)])
            return False

    def ping(self, ping_url, ping_times, ping_4_6, ping_size, runtimes):
        ping = subprocess.Popen(['ping', '-4' if ping_4_6 == '-4' else '-6', '-l', str(ping_size), '-n', str(ping_times), ping_url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        ping_normal_list = []
        ping_abnormal_list = []
        while True:
            time.sleep(0.1)
            line = ping.stdout.readline().decode('GBK')
            if line != '' and line != '\r\n':
                self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), repr(line))])
                # 找不到主机错误
                if ping_url in line:
                    self.log_queue.put(['all', '[{}] runtimes: {} PING请求找不到主机'.format(datetime.datetime.now(), runtimes)])
                    self.log_queue.put(['df', runtimes, 'ping_fail_times', 1])  # shortest_time
                    ping.terminate()
                    return False
                # 连续10次没有正常返回值判定为False
                if ping_4_6 == '-4':
                    ping_status = re.findall(r'来自 (.*?) 的回复: 字节=(\d+) 时间=(\d+)ms TTL=(\d+)', line)
                else:
                    ping_status = re.findall(r'来自 (.*?) 的回复: 时间=(\d+)ms', line)
                if ping_status:
                    ping_normal_list.append(1)
                    ping_abnormal_list = []
                else:
                    ping_abnormal_list.append(1)
                    if len(ping_abnormal_list) == 10:
                        self.log_queue.put(['df', runtimes, 'send_package_number', int(len(ping_normal_list) + len(ping_abnormal_list))])  # send_package_number
                        self.log_queue.put(['df', runtimes, 'recv_package_number', int(len(ping_normal_list))])  # recv_package_number
                        self.log_queue.put(['df', runtimes, 'lost_package_number', int(len(ping_abnormal_list))])  # lost_package_number
                        self.log_queue.put(['df', runtimes, 'lost_package_percentage', '{}%'.format(int(len(ping_abnormal_list) * 100 / (len(ping_normal_list) + len(ping_abnormal_list))))])  # lost_package_percentage
                        self.log_queue.put(['all', '[{}] runtimes: {} PING丢包过高'.format(datetime.datetime.now(), runtimes)])
                        self.log_queue.put(['df', runtimes, 'ping_fail_times', 1])  # shortest_time
                        ping.terminate()
                        return False
                # 获取数据包的个数信息
                ping_data_package_status = re.findall(r'.*已发送 = (\d+)，已接收 = (\d+)，丢失 = (\d+) \((\d+%) 丢失\).*', line)
                if ping_data_package_status:
                    send_package_number, recv_package_number, lost_package_number, lost_package_percentage = ping_data_package_status.pop()
                    self.log_queue.put(['df', runtimes, 'send_package_number', int(send_package_number)])  # send_package_number
                    self.log_queue.put(['df', runtimes, 'recv_package_number', int(recv_package_number)])  # recv_package_number
                    self.log_queue.put(['df', runtimes, 'lost_package_number', int(lost_package_number)])  # lost_package_number
                    self.log_queue.put(['df', runtimes, 'lost_package_percentage', lost_package_percentage])  # lost_package_percentage
                # 获取数据包时间信息
                ping_delay_status = re.findall(r'最短 = (\d+)ms，最长 = (\d+)ms，平均 = (\d+)ms', line)
                if ping_delay_status:
                    shortest_time, longest_time, average_time = ping_delay_status.pop()
                    self.log_queue.put(['df', runtimes, 'shortest_time', int(shortest_time)])  # shortest_time
                    self.log_queue.put(['df', runtimes, 'longest_time', int(longest_time)])  # longest_time
                    self.log_queue.put(['df', runtimes, 'average_time', int(average_time)])  # average_time
                # 结束
                if '平均' in line:
                    ping.terminate()
                    break
        return True

    def ping_posix(self, ping_url, ping_times, ping_4_6, ping_size, network_card, runtimes):
        delay_time_list = []
        ping_command = ['ping' if ping_4_6 == '-4' else 'ping6', '-S', str(ping_size), '-c', str(ping_times), ping_url]
        if network_card:
            ping_command.extend(['-I', network_card])
        self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ' '.join(ping_command))])
        ping = subprocess.Popen(ping_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        ping_abnormal_list = []
        buffer = ''
        while True:
            time.sleep(0.1)
            line = ping.stdout.readline().decode('utf-8').strip()
            if line != '':
                buffer += line
                self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), repr(line))])
                # 找不到主机错误
                if 'unknown host' in line or 'unreachable' in line:
                    self.log_queue.put(['all', '[{}] runtimes: {} PING异常'.format(datetime.datetime.now(), runtimes)])
                    self.log_queue.put(['df', runtimes, 'ping_fail_times', 1])  # shortest_time
                    ping.terminate()
                    return False
                # 连续10次没有正常返回值判定为False
                ping_status = True if 'bytes from' in line else False
                if ping_status:
                    ping_abnormal_list = []
                else:
                    ping_abnormal_list.append(1)
                    if len(ping_abnormal_list) == 10:
                        self.log_queue.put(['all', '[{}] runtimes: {} PING丢包过高'.format(datetime.datetime.now(), runtimes)])
                        ping.send_signal(signal.SIGINT)
                # 统计延迟时间
                delay_time = ''.join((re.findall(r'time=(\d+\.\d+)\s+ms', line)))
                if delay_time:
                    delay_time_list.append(float(delay_time))
                if 'packets transmitted' in line:
                    ping.send_signal(signal.SIGINT)
                    break

        ping_status = re.search(r'(\d+)\s+packets\s+transmitted,\s+(\d+)\s+received.*\s+(\d+)%.*', buffer)
        send_package_number, recv_package_number, lost_package_percentage = ping_status.groups()
        self.log_queue.put(['df', runtimes, 'send_package_number', int(send_package_number)])  # send_package_number
        self.log_queue.put(['df', runtimes, 'recv_package_number', int(recv_package_number)])  # recv_package_number
        self.log_queue.put(['df', runtimes, 'lost_package_number', int(int(send_package_number) - int(recv_package_number))])  # lost_package_number
        self.log_queue.put(['df', runtimes, 'lost_package_percentage', lost_package_percentage])  # lost_package_percentage
        if len(delay_time_list) == 0:
            delay_time_list.append(999)
        self.log_queue.put(['df', runtimes, 'shortest_time', min(delay_time_list)])  # shortest_time
        self.log_queue.put(['df', runtimes, 'longest_time', max(delay_time_list)])  # longest_time
        self.log_queue.put(['df', runtimes, 'average_time', round(sum(delay_time_list) / len(delay_time_list), 2)])  # average_time

    def ftp_connect(self, connect_mode, connect_type, ftp_address, ftp_port, ftp_usr_name, ftp_password, runtimes):
        """
        建立FTP连接
        :param connect_mode: 长连还是短连 0：长连 1：短连
        :param connect_type: 拨号类型MBIM、NDIS
        :param ftp_address: ftp服务器地址
        :param ftp_port: ftp服务器端口
        :param ftp_usr_name: ftp服务器连接用户名
        :param ftp_password: ftp服务器连接密码
        :param runtimes: 当前脚本的运行次数
        :return: True：连接成功；False：连接失败
        """
        connect_times = 10
        try:
            for i in range(connect_times):
                ftp_start_time = time.time()
                self.ftp.set_debuglevel(0)
                self.ftp.connect(ftp_address, ftp_port)
                login = self.ftp.login(ftp_usr_name, ftp_password)
                if '230 Login successful' in login or '230 User logged in, proceed.' in login:
                    if connect_mode == 1:
                        self.log_queue.put(['df', runtimes, 'ftp_conn_time', time.time() - ftp_start_time])
                        self.log_queue.put(['df', runtimes, 'ftp_connect_success_times', 1])  # runtimes_start_timestamp
                    self.log_queue.put(['at_log', '[{}] FTP连接成功'.format(datetime.datetime.now())])
                    return True
                else:
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
                    self.log_queue.put(['all', '[{}] runtimes:{} {}连接异常'.format(datetime.datetime.now(), runtimes, connect_type)])
                    self.log_queue.put(['df', runtimes, 'ftp_connect_fail_times', i])  # runtimes_start_timestamp
            else:
                # 连续10次ftp失败,返回False
                self.log_queue.put(['all', '[{}] runtimes: {} {}连续{}次连接失败'.format(datetime.datetime.now(), runtimes, connect_type, connect_times)])
                self.log_queue.put(['df', runtimes, 'ftp_connect_fail_times', 10])
                return False
        except Exception as e:
            self.log_queue.put(['all', '[{}] runtimes:{} {}'.format(datetime.datetime.now(), runtimes, e)])
            return False

    def ftp_send_recv_compare(self, connect_type, local_file_path, local_file, ftp_file_path, ftp_path, local_target_file_path, runtimes):
        """
        FTP上传下载文件并对比文件大小
        :param connect_type : 连接类型，MBIM或者NDIS
        :param local_file: 本地文件名
        :param local_file_path: 本地源文件
        :param ftp_file_path: ftp文件路径
        :param ftp_path: ftp路径
        :param runtimes: 当前脚本的运行次数
        :param local_target_file_path: 本地下载目标文件路径
        :return: True：文件对比成功；False：文件对比失败
        """
        local_file_size = os.path.getsize(local_file_path)
        ftp_file_size = 0
        try:
            # 1、上传文件到ftp服务器
            self.log_queue.put(['at_log', '[{}] 开始上传{}byte文件至ftp服务器'.format(datetime.datetime.now(), local_file_size)])
            upload_start_time = time.time()  # 开始上传文件的时间
            buffer_size = 8192
            with open(local_file_path, 'rb') as fp:
                upload_status = self.ftp.storbinary('STOR ' + ftp_file_path, fp, buffer_size)
            upload_file_time = round(time.time() - upload_start_time, 3)
            if 'transfer complete' in upload_status.lower():
                self.log_queue.put(['at_log', '[{}] ftp文件上传成功'.format(datetime.datetime.now())])
                self.log_queue.put(['df', runtimes, 'ftp_upload_time', upload_file_time])
                self.log_queue.put(['df', runtimes, 'ftp_upload_speed', local_file_size / 1024 / 1024 / upload_file_time])
                # 检查ftp接收到的文件大小
                self.ftp.cwd(ftp_path)
                for ftp_file in self.ftp.nlst():
                    if ftp_file == local_file:
                        self.ftp.voidcmd('TYPE I')
                        ftp_file_size = self.ftp.size(ftp_file)
                if ftp_file_size != local_file_size:
                    self.logger.info(ftp_file_size)
                    self.log_queue.put(['all', '[{}] runtimes:{} ftp上传文件成功，但是文件大小不一致'.format(datetime.datetime.now(), runtimes)])
            else:
                self.log_queue.put(["all", '[{}] runtimes:{} ftp文件上传失败'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])

            # 2、从ftp下载文件
            self.log_queue.put(['at_log', '[{}] 开始从ftp服务器下载{}byte文件'.format(datetime.datetime.now(), local_file_size)])
            download_file_start_time = time.time()
            buffer_size = 8192
            with open(local_target_file_path, 'wb') as fp:
                download_status = self.ftp.retrbinary('RETR ' + ftp_file_path, fp.write, buffer_size)
            ftp_download_time = round(time.time() - download_file_start_time, 3)
            if 'transfer complete' in download_status.lower():
                self.log_queue.put(['df', runtimes, 'ftp_download_time', ftp_download_time])
                self.log_queue.put(['df', runtimes, 'ftp_download_speed', local_file_size / 1024 / 1024 / ftp_download_time])
                self.log_queue.put(['at_log', '[{}] FTP文件下载成功'.format(datetime.datetime.now())])
            else:
                self.log_queue.put(["all", '[{}] runtimes:{} ftp文件下载失败'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])

            # 3、对比文件
            if filecmp.cmp(local_file_path, local_target_file_path, False):
                self.log_queue.put(['at_log', '[{}] 源文件和目标文件对比相同'.format(datetime.datetime.now())])
                return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} 源文件和目标文件对比不同'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'file_compare_fail_times', 1])  # runtimes_start_timestamp
                return False
        except Exception as e:
            self.log_queue.put(['all', '[{}] runtimes:{} {}'.format(datetime.datetime.now(), runtimes, e)])
            return False

    def ftp_disconnect(self, runtimes):

        """
        断开ftp连接
        :param runtimes: 当前脚本的运行次数
        :return: True：断开ftp连接成功；False：断开ftp连接失败
        """
        try:
            disconnect_times = 10
            for i in range(disconnect_times):
                ftp_disconnect_start_timestamp = time.time()
                ftp_close = self.ftp.quit()
                self.log_queue.put(['df', runtimes, 'ftp_disconnect_time', time.time() - ftp_disconnect_start_timestamp])  # tcp_udp_disconnect_time
                if '221 Goodbye' in ftp_close:
                    self.log_queue.put(['at_log', '[{}] FTP断开连接成功'.format(datetime.datetime.now())])
                    self.log_queue.put(['df', runtimes, 'ftp_disconnect_success_times', 1])  # runtimes_start_timestamp
                    return True
                else:
                    self.log_queue.put(['all', '[{}] runtimes: {} FTP断开连接失败'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'ftp_disconnect_fail_times', i])  # runtimes_start_timestamp
            else:  # 连续10次TCP/UDP断开失败返回False
                self.log_queue.put(['all', '[{}] runtimes: {} FTP连续{}次断开连接失败'.format(datetime.datetime.now(), runtimes, disconnect_times)])
                self.log_queue.put(['df', runtimes, 'ftp_disconnect_fail_times', 10])  # runtimes_start_timestamp
                return False
        except Exception as e:
            self.log_queue.put(['all', '[{}] runtimes:{} {}'.format(datetime.datetime.now(), runtimes, e)])
            return False

    def http_post_get(self, server_url, server_remove_file_url, server_ip_port, source_name, receive_file_name, runtimes):
        """

        :param server_url:
        :param server_remove_file_url:
        :param server_port:
        :param source_name:
        :param receive_file_name:
        :param runtimes:
        :return:
        """
        try:
            response = requests.get(server_url)
            if response.status_code == 200:
                self.log_queue.put(['at_log', '[{}] get http服务器状态正常'.format(datetime.datetime.now())])
            else:
                test_response = requests.get("http://www.baidu.com")
                if test_response.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] get http服务器状态异常'.format(datetime.datetime.now())])
                    pause()
                else:
                    interface_name = self.get_interface_name(runtimes)
                    interface_status = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), interface_status)])
                    self.log_queue.put(['at_log', '[{}] 拨号连接异常, 请检查拨号连接状态'.format(datetime.datetime.now())])

            # post上传文件
            file_path = os.path.join(os.path.dirname(os.getcwd()), source_name)
            boundary_temp = '---------------------------7de1ae242c06ca'
            file_upload = MultipartEncoder(fields={'file': ('file', open(file_path, 'rb'))}, boundary=boundary_temp)
            req_headers = {'Content-Type': file_upload.content_type}
            self.log_queue.put(['at_log', '[{}] HTTP(s)开始上传文件'.format(datetime.datetime.now())])
            post_start_timestamp = time.time()
            post_data = requests.post(server_url, data=file_upload, headers=req_headers)
            if post_data.status_code != 200:
                self.log_queue.put(['df', runtimes, 'post_file_time', 999])
                self.log_queue.put(['df', runtimes, 'post_file_fail_times', 1])
            else:
                self.log_queue.put(['df', runtimes, 'post_file_time', time.time() - post_start_timestamp])
                self.log_queue.put(['df', runtimes, 'post_file_success_times', 1])
                self.log_queue.put(['at_log', '[{}] HTTP(s)文件上传完成'.format(datetime.datetime.now())])
            path_temp = ''.join(re.findall(r'path":"(.*?)"', post_data.content.decode('utf-8', 'ignore')))
            if not path_temp:
                self.log_queue.put(['all', '[{}] runtimes:{} 未获取到正确的http path'.format(datetime.datetime.now(), runtimes)])
                return False
            post_data.close()

            # get下载文件
            self.log_queue.put(['at_log', '[{}] HTTP(s)开始下载文件'.format(datetime.datetime.now())])
            get_start_timestamp = time.time()
            get_data = requests.get('%s://%s/%s' % ("http", server_ip_port, path_temp))
            if get_data.status_code != 200:
                self.log_queue.put(['df', runtimes, 'get_file_time', 999])
                self.log_queue.put(['df', runtimes, 'get_file_fail_times', 1])
            else:
                self.log_queue.put(['df', runtimes, 'get_file_time', time.time() - get_start_timestamp])
                self.log_queue.put(['df', runtimes, 'get_file_success_times', 1])
                self.log_queue.put(['at_log', '[{}] HTTP(S)下载文件完成'.format(datetime.datetime.now())])
            base_path = os.path.dirname(os.getcwd())
            with open(os.path.join(base_path, receive_file_name), 'wb') as f:
                for item in get_data.iter_content(chunk_size=8192):
                    f.write(item)

            file_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname('__file__'), os.path.pardir)), source_name)
            file_path_recv = os.path.join(os.path.abspath(os.path.join(os.path.dirname('__file__'), os.path.pardir)), receive_file_name)

            # 比较文件
            if filecmp.cmp(file_path, file_path_recv, False):
                self.log_queue.put(['at_log', '[{}] 源文件和目标文件对比相同'.format(datetime.datetime.now())])
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} 源文件和目标文件对比不同'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'file_compare_fail_times', 1])  # runtimes_start_timestamp
                return False
            file_temp = {'path': '%s' % path_temp}
            remove_file = requests.post(server_remove_file_url, data=file_temp)
            if int(remove_file.text) == 1:
                self.log_queue.put(['at_log', '[{}] 删除服务器文件成功'.format(datetime.datetime.now())])
            else:
                self.log_queue.put(['at_log', '[{}] 删除服务器文件失败'.format(datetime.datetime.now())])
        except Exception as e:
            self.logger.info(e)
            self.log_queue.put(['all', '[{}] runtimes:{} {}'.format(datetime.datetime.now(), runtimes, e)])
            return False

    def speed_test_old(self, runtimes):
        self.log_queue.put(['at_log', '[{}] 开始进行Speedtest测速'.format(datetime.datetime.now())])
        # speedtest_result dict
        # {latency': 8.1, 'server': 'China Telecom AnHui 5G-17145-speedtest1.ah163.com:8080-12.72km', 'download': 96.32,
        #     'download_total': 121.38, 'upload': 96.27, 'upload_speed': 142.08 }
        speedtest_result = Speedtest(self.log_queue, runtimes).speedtest()
        if speedtest_result is False:
            self.log_queue.put(['all', '[{}] runtimes:{} Speedtest测速失败'.format(datetime.datetime.now(), runtimes)])
            self.log_queue.put(['df', runtimes, 'speedtest_fail_times', 1])
            return False
        # 统计参数
        self.log_queue.put(['df', runtimes, 'download_speed', float(speedtest_result['download'])])
        self.log_queue.put(['df', runtimes, 'download_data', float(speedtest_result['download_total'])])
        self.log_queue.put(['df', runtimes, 'upload_speed', float(speedtest_result['upload'])])
        self.log_queue.put(['df', runtimes, 'upload_data', float(speedtest_result['upload_total'])])
        self.log_queue.put(['df', runtimes, 'server_info', speedtest_result['server']])
        self.log_queue.put(['df', runtimes, 'ping_delay', float(speedtest_result['latency'])])
        # AT log打印
        self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), '/' * 33)])
        self.log_queue.put(['at_log', '[{}] 下载速度: {} Mbps'.format(datetime.datetime.now(), float(speedtest_result['download']))])
        self.log_queue.put(['at_log', '[{}] 上传速度: {} Mbps'.format(datetime.datetime.now(), float(speedtest_result['upload']))])
        self.log_queue.put(['at_log', '[{}] 服务器: {} '.format(datetime.datetime.now(), speedtest_result['server'])])
        self.log_queue.put(['at_log', '[{}] ISP: {} '.format(datetime.datetime.now(), speedtest_result['isp'])])
        self.log_queue.put(['at_log', '[{}] 测速服务器延迟: {} ms'.format(datetime.datetime.now(), speedtest_result['latency'])])
        self.log_queue.put(['at_log', '[{}] 下载测试消耗数据量: {} MB'.format(datetime.datetime.now(), float(speedtest_result['download_total']))])
        self.log_queue.put(['at_log', '[{}] 上传测试消耗数据量: {} MB'.format(datetime.datetime.now(), float(speedtest_result['upload_total']))])
        self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), '/' * 33)])
        return True

    def speed_test_debug(self, runtimes):
        for i in range(1, 11):
            try:
                self.log_queue.put(['at_log', '[{}] 开始进行Speedtest测速'.format(datetime.datetime.now())])
                speedtest_result = Speedtest(self.log_queue, runtimes).speedtest(r'{}\speedtest.exe'.format(os.path.abspath('..')) if os.name == 'nt' else 'speedtest')
                if speedtest_result is False or 'error' in speedtest_result.lower():  # 如果有error
                    self.log_queue.put(['at_log', '[{}] 第{}次测速，speedtest应用返回数据异常'.format(datetime.datetime.now(), i)])
                    continue
                if "Result" in speedtest_result:
                    return_result = re.findall(r'Server:\s+(?P<server>.*?)\s+'
                                               r'ISP:\s+(?P<ISP>.*?)\s+'
                                               r'Latency:\s+(?P<latency>\d+\.\d+).*\((?P<jitter>\d+\.\d+).*\s+'
                                               r'Download:\s+(?P<download>\d+\.\d+).*used:\s(?P<download_MB>\d+\.\d+).*\s+'
                                               r'Upload:\s+(?P<upload>\d+\.\d+).*used:\s(?P<upload_MB>\d+\.\d+).*\s+'
                                               r'Packet\sLoss:\s+(?P<packet_loss>.*?)\s+'
                                               r'Result\sURL:\s(?P<result_url>.*?)\s', speedtest_result)
                    [(Server, ISP, Latency, jitter, Download, download_MB, Upload, upload_MB, Packet_Loss,
                      Result_URL)] = return_result  # 将信息解压
                    # 上传
                    self.log_queue.put(['df', runtimes, 'download_speed', float(Download)])
                    self.log_queue.put(['df', runtimes, 'download_data', float(download_MB)])
                    # 下载
                    self.log_queue.put(['df', runtimes, 'upload_speed', float(Upload)])
                    self.log_queue.put(['df', runtimes, 'upload_data', float(upload_MB)])
                    # 其他参数
                    self.log_queue.put(['df', runtimes, 'server_info', Server])
                    self.log_queue.put(['df', runtimes, 'ping_delay', float(Latency)])
                    self.log_queue.put(['df', runtimes, 'download_MB', download_MB])
                    self.log_queue.put(['df', runtimes, 'upload_MB', upload_MB])
                    self.log_queue.put(['df', runtimes, 'Packet_Loss', Packet_Loss])
                    self.log_queue.put(['df', runtimes, 'Result_URL', Result_URL])
                    return True
            except ValueError:
                self.log_queue.put(['df', runtimes, 'speedtest_fail_times', i])
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 连续十次Speedtest测速失败，重新启动'.format(datetime.datetime.now(), runtimes)])
            return False

    def speed_test(self, runtimes):
        codec = 'GBK' if os.name == 'nt' else 'utf-8'
        for i in range(1, 11):
            try:
                speedtest_start_timestamp = time.time()
                self.log_queue.put(['at_log', '[{}] 开始进行Speedtest测速'.format(datetime.datetime.now())])
                speedtest_command = r'{}\speedtest.exe --accept-license'.format(os.path.abspath('..')) if os.name == 'nt' else 'speedtest'  # Linux直接调用，Win下面需要指定文件位置
                s = subprocess.Popen(speedtest_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
                speed_test_cache = ''
                while True:
                    return_value = s.stdout.readline().decode(codec, 'replace')
                    if return_value != '':  # 如果有返回值
                        self.logger.info(return_value)
                        speed_test_cache += return_value
                    if 'error' in return_value.lower():  # 如果有error，则terminate
                        s.terminate()
                        self.log_queue.put(['at_log', '[{}] 第{}次测速，speedtest应用返回数据异常'.format(datetime.datetime.now(), i)])
                        break
                    if "Result" in return_value:  # 如果有Result在结果，则等待1S，然后break
                        time.sleep(1)
                        break
                    if time.time() - speedtest_start_timestamp > 60:  # 如果时间超过60S，立刻break
                        s.terminate()
                        self.log_queue.put(['at_log', '[{}] 第{}次测速，speedtest测速超时，60S内未返回完整结果'.format(datetime.datetime.now(), i)])
                        break
                return_result = re.findall(r'Server:\s+(?P<server>.*?)\s+'
                                           r'ISP:\s+(?P<ISP>.*?)\s+'
                                           r'Latency:\s+(?P<latency>\d+\.\d+).*\((?P<jitter>\d+\.\d+).*\s+'
                                           r'Download:\s+(?P<download>\d+\.\d+).*used:\s(?P<download_MB>\d+\.\d+).*\s+'
                                           r'Upload:\s+(?P<upload>\d+\.\d+).*used:\s(?P<upload_MB>\d+\.\d+).*\s+'
                                           r'Packet\sLoss:\s+(?P<packet_loss>.*?)\s+'
                                           r'Result\sURL:\s(?P<result_url>.*?)\s', speed_test_cache)
                [(Server, ISP, Latency, jitter, Download, download_MB, Upload, upload_MB, Packet_Loss,
                  Result_URL)] = return_result  # 将信息解压
                # 上传
                self.log_queue.put(['df', runtimes, 'download_speed', float(Download)])
                self.log_queue.put(['df', runtimes, 'download_data', float(download_MB)])
                self.log_queue.put(['at_log', '[{}] download: {} Mbps'.format(datetime.datetime.now(), float(Download))])
                # 下载
                self.log_queue.put(['df', runtimes, 'upload_speed', float(Upload)])
                self.log_queue.put(['df', runtimes, 'upload_data', float(upload_MB)])
                self.log_queue.put(['at_log', '[{}] Upload: {} Mbps'.format(datetime.datetime.now(), float(Upload))])
                # 其他参数
                self.log_queue.put(['df', runtimes, 'server_info', Server])
                self.log_queue.put(['df', runtimes, 'ping_delay', float(Latency)])
                self.log_queue.put(['df', runtimes, 'download_MB', download_MB])
                self.log_queue.put(['df', runtimes, 'upload_MB', upload_MB])
                self.log_queue.put(['df', runtimes, 'Packet_Loss', Packet_Loss])
                self.log_queue.put(['df', runtimes, 'Result_URL', Result_URL])
                self.log_queue.put(['at_log', '[{}] Server: {} '.format(datetime.datetime.now(), Server)])
                self.log_queue.put(['at_log', '[{}] ISP: {} '.format(datetime.datetime.now(), ISP)])
                self.log_queue.put(['at_log', '[{}] Latency: {} ms'.format(datetime.datetime.now(), Latency)])
                self.log_queue.put(['at_log', '[{}] jitter: {} ms'.format(datetime.datetime.now(), jitter)])
                self.log_queue.put(['at_log', '[{}] download_MB: {} MB'.format(datetime.datetime.now(), download_MB)])
                self.log_queue.put(['at_log', '[{}] upload_MB: {} MB'.format(datetime.datetime.now(), upload_MB)])
                self.log_queue.put(['at_log', '[{}] Packet_Loss: {}'.format(datetime.datetime.now(), Packet_Loss)])
                self.log_queue.put(['at_log', '[{}] Result_URL: {} '.format(datetime.datetime.now(), Result_URL)])
                return True
            except ValueError:
                self.log_queue.put(['df', runtimes, 'speedtest_fail_times', i])
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 连续十次Speedtest测速失败，重新启动'.format(datetime.datetime.now(), runtimes)])
            return False

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
        # 检查lsusb-t
        lsusb_value = os.popen('lsusb -t').read()
        self.logger.info(lsusb_value)
        if 'cdc_ether' not in lsusb_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), lsusb_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} lsusb -t指令未查询到cdc_ether网卡驱动'.format(datetime.datetime.now(), runtimes)])
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
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
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
        if 'wwan0' not in ifconfig_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ifconfig_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} ifconfig -a指令未查询到wwan0网卡'.format(datetime.datetime.now(), runtimes)])
            return False
        # 检查lsusb-t
        lsusb_value = os.popen('lsusb -t').read()
        self.logger.info(lsusb_value)
        if 'qmi_wwan' not in lsusb_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), lsusb_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} lsusb -t指令未查询到qmi_wwan网卡驱动'.format(datetime.datetime.now(), runtimes)])
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
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
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
        # 检查lsusb-t
        lsusb_value = os.popen('lsusb -t').read()
        self.logger.info(lsusb_value)
        if 'GobiNet' not in lsusb_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), lsusb_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} lsusb -t指令未查询到GobiNet网卡驱动'.format(datetime.datetime.now(), runtimes)])
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
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
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
        # 检查lsusb-t
        lsusb_value = os.popen('lsusb -t').read()
        self.logger.info(lsusb_value)
        if 'cdc_mbim' not in lsusb_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), lsusb_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} lsusb -t指令未查询到MBIM网卡驱动'.format(datetime.datetime.now(), runtimes)])
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
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，MBIM拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def wwan_connect_check_copy(self, runtimes):
        """
        相对于检查wwan_connect_check，删除了拨号，检查WWAN拨号的拨号状态：
        1. ifconfig -a查询值必须包含wwan0；
        2. lsusb -t查询值必须包含qmi_wwan
        :param runtimes: 当前脚本的运行次数
        :return:True，检查成功；False，检查失败
        """
        # 检查ifconfig
        ifconfig_value = os.popen('ifconfig -a').read()
        self.logger.info(ifconfig_value)
        if 'wwan0' not in ifconfig_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ifconfig_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} ifconfig -a指令未查询到wwan0网卡'.format(datetime.datetime.now(), runtimes)])
            return False
        # 检查lsusb-t
        lsusb_value = os.popen('lsusb -t').read()
        self.logger.info(lsusb_value)
        if 'qmi_wwan' not in lsusb_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), lsusb_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} lsusb -t指令未查询到qmi_wwan网卡驱动'.format(datetime.datetime.now(), runtimes)])
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            self.logger.info(subprocess.getoutput('cat /etc/resolv.conf'))
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getoutput('cat /etc/resolv.conf'))])
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] WWAN拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，WWAN拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def gobinet_connect_check_copy(self, runtimes):
        """
        相对于gobinet_connect_check， 删除了拨号，检查GobiNet拨号的拨号状态：
        1. ifconfig -a查询值必须包含usb0；
        2. lsusb -t查询值必须包含gobinet
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
        # 检查lsusb-t
        lsusb_value = os.popen('lsusb -t').read()
        self.logger.info(lsusb_value)
        if 'GobiNet' not in lsusb_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), lsusb_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} lsusb -t指令未查询到GobiNet网卡驱动'.format(datetime.datetime.now(), runtimes)])
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            self.logger.info(subprocess.getoutput('cat /etc/resolv.conf'))
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getoutput('cat /etc/resolv.conf'))])
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] GobiNet拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，GobiNet拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def mbim_connect_check_copy(self, runtimes):
        """
        相对mbim_connect_check删除了拨号，检查mbim拨号的拨号状态：
        1. ifconfig -a查询值必须包含usb0；
        2. lsusb -t查询值必须包含gobinet
        :param runtimes: 当前脚本的运行次数
        :return:True，检查成功；False，检查失败
        """
        # 检查ifconfig
        ifconfig_value = os.popen('ifconfig -a').read()
        self.logger.info(ifconfig_value)
        if 'wwan0' not in ifconfig_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ifconfig_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} ifconfig -a指令未查询到wwan0网卡'.format(datetime.datetime.now(), runtimes)])
            return False
        # 检查lsusb-t
        lsusb_value = os.popen('lsusb -t').read()
        self.logger.info(lsusb_value)
        if 'cdc_mbim' not in lsusb_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), lsusb_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} lsusb -t指令未查询到MBIM网卡驱动'.format(datetime.datetime.now(), runtimes)])
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            self.logger.info(subprocess.getoutput('cat /etc/resolv.conf'))
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getoutput('cat /etc/resolv.conf'))])
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] MBIM拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，MBIM拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def rgmii_connect_check(self, runtimes):
        """
        检测RGMII拨号当前的状态。
        :param runtimes: 当前脚本的运行次数
        :return: True，拨号检测成功；False，拨号检测失败
        """
        for _ in range(20):  # 开机后进行20次检查，每次1s
            connect_flag = False
            connection_dic = {}
            ipconfig = os.popen('ipconfig').read()  # 获取ipconfig的值
            ipconfig = re.sub('\n.*?\n\n\n', '', ipconfig)  # 去除\nWindows IP 配置\n\n\n
            ipconfig_list = ipconfig.split('\n\n')
            for i in range(0, len(ipconfig_list), 2):  # 步进2，i为key，i+1为value
                connection_dic[ipconfig_list[i]] = ipconfig_list[i + 1]
                self.logger.info(connection_dic)
            for _, value in connection_dic.items():
                ipv4 = ''.join(re.findall(r'.*IPv4.*?([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})', value))
                if '192.168.225.1' in value and ipv4:  # 如果网关为RGMII的默认网关，并且IP地址正常，则使用requests库进行连接测试
                    connect_flag = True
            if connect_flag:
                break
            else:
                self.log_queue.put(['at_log', '[{}] RGMII 暂未获取到正确IP，等待1S继续检测'.format(datetime.datetime.now())])
                time.sleep(1)  # 如果网络异常，等待1S继续
                continue
        else:
            self.logger.info(os.popen('ipconfig').read())
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} RGMII拨号异常，RGMII默认网关和IP异常'.format(datetime.datetime.now(), runtimes)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] RGMII拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，RGMII拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def rtl_connect_check(self, runtimes):
        """
        检测rtl拨号当前的状态。
        :param runtimes: 当前脚本的运行次数
        :return: True，拨号检测成功；False，拨号检测失败
        """
        for _ in range(20):  # 开机后进行20次检查，每次1s
            connect_flag = False
            connection_dic = {}
            ipconfig = os.popen('ipconfig').read()  # 获取ipconfig的值
            ipconfig = re.sub('\n.*?\n\n\n', '', ipconfig)  # 去除\nWindows IP 配置\n\n\n
            ipconfig_list = ipconfig.split('\n\n')
            for i in range(0, len(ipconfig_list), 2):  # 步进2，i为key，i+1为value
                connection_dic[ipconfig_list[i]] = ipconfig_list[i + 1]
                self.logger.info(connection_dic)
            for _, value in connection_dic.items():
                ipv4 = ''.join(re.findall(r'.*IPv4.*?([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})', value))
                if ipv4:  # 如果IP地址正常，则使用requests库进行连接测试
                    connect_flag = True
            if connect_flag:
                break
            else:
                self.log_queue.put(['at_log', '[{}] RTL 暂未获取到正确IP，等待1S继续检测'.format(datetime.datetime.now())])
                time.sleep(1)  # 如果网络异常，等待1S继续
                continue
        else:
            self.logger.info(os.popen('ipconfig').read())
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} RTL拨号异常，未获取到正确IP地址'.format(datetime.datetime.now(), runtimes)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 5
        num = 0
        for num in range(1, 11):
            try:
                request_status = requests.get(url, timeout=timeout)
                if request_status.status_code == 200:
                    self.log_queue.put(['at_log', '[{}] RTL拨号检测成功'.format(datetime.datetime.now())])
                    return True
            except Exception as e:
                self.logger.info(e)
            time.sleep(5)
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), subprocess.getstatusoutput(self.ping_cmd))])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，RTL拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def iperf(self, ip, user, passwd, port, mode, times, bandwidth, interval, bind, parallel, length, window, mtu, omit, runtimes):
        """
        iPerf3.9 wrapper.
        :param ip: iPerf3.9 server ip
        :param user: iPerf3.9 server ssh user
        :param passwd: iPerf3.9 server ssh passwd
        :param port: iPerf3.9 server ssh port
        :param mode: 参考函数transmit_mode_mapping内容
        :param times: 运行的时间，默认是10S
        :param bandwidth: 带宽，例如10M代表10Mbits/s
        :param interval: log每次返回的间隔，默认1S一次log
        :param bind: 是否绑定网卡，如果需要绑定，则输入对应网卡的IP
        :param parallel: 使用的线程数，默认为1
        :param length: The length of buffers to read or write. default 128 KB for TCP, dynamic or 1460 for UDP
        :param window: TCP/UDP window size
        :param mtu: The MTU(maximum segment size) - 40 bytes for the header. ethernet MSS is 1460 bytes (1500 byte MTU).
        :param omit: omit n, skip n seconds
        :param runtimes: runtimes
        :return: None
        """
        while True:
            try:
                iperf_server = IPerfServer(ip, user, passwd, port)
                break
            except Exception as e:
                self.log_queue.put(['at_log', '[{}] iPerf服务开启异常：{}，正在重试'.format(datetime.datetime.now(), e)])

        transmit_mode_mapping = {
            1: [],  # TCP上传，本地Server，远端Client
            2: ['-R'],  # TCP下载，本地client，远端Server
            3: ['--bidir'],  # TCP上下同传
            4: ['-u'],  # UDP上传，本地Server，远端Client
            5: ['-u', '-R'],  # UDP下载，本地client，远端Server
            6: ['-u', '--bidir']  # UDP上传同传
        }
        iperf_cmd = ['iperf3',
                     '-c', ip,
                     '-p', str(iperf_server.port),
                     '-f', 'm',
                     '-t', str(times),
                     '--forceflush',
                     ]

        iperf_cmd.extend(transmit_mode_mapping[mode])

        iperf_cmd_tail = []
        if interval:
            iperf_cmd_tail.extend(['-i', str(interval)])
        if bandwidth:
            iperf_cmd_tail.extend(['-b', str(bandwidth)])
        if bind:  # 绑定本机的IP，使用某个IP进行数据传输
            iperf_cmd_tail.extend(['-B', str(bind)])
        if parallel:  # 并行线程数
            iperf_cmd_tail.extend(['-P', str(parallel)])
        if length:  # The length of buffers to read or write. default 128 KB for TCP, dynamic or 1460 for UDP
            iperf_cmd_tail.extend(['-l', str(length)])
        if window:  # window
            iperf_cmd_tail.extend(['-w', str(window)])
        if mtu:  # TCP: maximum segment sizeThe MTU - 40 bytes for the header. ethernet MSS is 1460 bytes (1500 byte MTU).
            iperf_cmd_tail.extend(['-M', str(mtu)])
        if omit:  # omit n, skip n seconds
            iperf_cmd_tail.extend(['-O', str(omit)])

        iperf_cmd.extend(iperf_cmd_tail)

        self.log_queue.put(['at_log', '[{}] [iperf3 cmd] {}'.format(datetime.datetime.now(), ' '.join(iperf_cmd))])

        s = subprocess.Popen(iperf_cmd,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             text=True,
                             errors='ignore'
                             )

        speed_abnormal_times = 0
        result_cache = ''

        while s.poll() is None:
            data = s.stdout.readline().replace('\n', '')
            self.log_queue.put(['at_log', '[{}] [iPerf3] {}'.format(datetime.datetime.now(), data)]) if data else None
            self.log_queue.put(['all', '[{}] [iPerf3] 出现断流: {}'.format(datetime.datetime.now(), data)]) if '0.00 Mbits/sec' in data and 'sender' not in data and 'receiver' not in data else 0
            speed_abnormal_times += 1 if '0.00 Mbits/sec' in data and 'sender' not in data and 'receiver' not in data else 0
            result_cache += data if 'sender' in data or 'receiver' in data else ''
            if 'iperf3' in data:
                break

        out, _ = s.communicate()
        result_cache += out

        self.log_queue.put(['df', runtimes, 'speed_abnormal_times', speed_abnormal_times])

        iperf_server.shutdown()  # shutdown iperf3 service

        if s.returncode != 0:  # 如果异常，不进行参数统计
            return False

        # Used for mode 1, 2, 3
        result_regex = re.findall(r'{}(\d+[(.\d+)]*)\sM.*?(\d+[(.\d+)]*)\sMbits/sec'.format('SUM.*?' if parallel else ''),
                                  result_cache)  # .format('SUM.*?')为了指定-P参数返回正确的结果
        self.logger.info("iperf result log regex: {}".format(result_regex))

        if mode == 1 and len(result_regex) == 2:  # TCP upload and regex correct
            [(client_send, client_send_bandwidth), (server_receive, server_receive_bandwidth)] = result_regex
            self.log_queue.put(['at_log', '[{}] 模块TCP发送平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), client_send_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 服务器接收平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), server_receive_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 模块共发送 {} MBytes'.format(datetime.datetime.now(), client_send)])
            self.log_queue.put(['at_log', '[{}] 服务器共接收 {} MBytes'.format(datetime.datetime.now(), server_receive)])
            self.log_queue.put(['df', runtimes, 'client_send', float(client_send)])
            self.log_queue.put(['df', runtimes, 'client_send_bandwidth', float(client_send_bandwidth)])
            self.log_queue.put(['df', runtimes, 'server_receive', float(server_receive)])
            self.log_queue.put(['df', runtimes, 'server_receive_bandwidth', float(server_receive_bandwidth)])
            self.logger.info("统计完成")
        if mode == 2 and len(result_regex) == 2:  # TCP download and regex correct
            [(server_send, server_send_bandwidth), (client_receive, client_receive_bandwidth)] = result_regex
            self.log_queue.put(['at_log', '[{}] 服务器发送平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), server_send_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 模块TCP接收平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), client_receive_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 服务器共发送 {} MBytes'.format(datetime.datetime.now(), server_send)])
            self.log_queue.put(['at_log', '[{}] 模块共接收 {} MBytes'.format(datetime.datetime.now(), client_receive)])
            self.log_queue.put(['df', runtimes, 'server_send', float(server_send)])
            self.log_queue.put(['df', runtimes, 'server_send_bandwidth', float(server_send_bandwidth)])
            self.log_queue.put(['df', runtimes, 'client_receive', float(client_receive)])
            self.log_queue.put(['df', runtimes, 'client_receive_bandwidth', float(client_receive_bandwidth)])
            self.logger.info("统计完成")
        if mode == 3 and len(result_regex) == 4:  # TCP bi-direction
            [(client_send, client_send_bandwidth), (server_receive, server_receive_bandwidth),
             (server_send, server_send_bandwidth), (client_receive, client_receive_bandwidth)] = result_regex
            self.log_queue.put(['at_log', '[{}] 模块作为发送端，Server作为接收端时：'.format(datetime.datetime.now())])
            self.log_queue.put(['at_log', '[{}] 模块TCP发送平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), client_send_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 服务器接收平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), server_receive_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 模块共发送 {} MBytes'.format(datetime.datetime.now(), client_send)])
            self.log_queue.put(['at_log', '[{}] 服务器共接收 {} MBytes'.format(datetime.datetime.now(), server_receive)])
            self.log_queue.put(['at_log', '[{}] 模块作为接收端，Server作为发送端时：'.format(datetime.datetime.now())])
            self.log_queue.put(['at_log', '[{}] 服务器发送平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), server_send_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 模块TCP接收平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), client_receive_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 服务器共发送 {} MBytes'.format(datetime.datetime.now(), server_send)])
            self.log_queue.put(['at_log', '[{}] 模块共接收 {} MBytes'.format(datetime.datetime.now(), client_receive)])
            self.log_queue.put(['df', runtimes, 'client_send', float(client_send)])
            self.log_queue.put(['df', runtimes, 'client_send_bandwidth', float(client_send_bandwidth)])
            self.log_queue.put(['df', runtimes, 'server_receive', float(server_receive)])
            self.log_queue.put(['df', runtimes, 'server_receive_bandwidth', float(server_receive_bandwidth)])
            self.log_queue.put(['df', runtimes, 'server_send', float(server_send)])
            self.log_queue.put(['df', runtimes, 'server_send_bandwidth', float(server_send_bandwidth)])
            self.log_queue.put(['df', runtimes, 'client_receive', float(client_receive)])
            self.log_queue.put(['df', runtimes, 'client_receive_bandwidth', float(client_receive_bandwidth)])
            self.logger.info("统计完成")

        # Used for mode 4, 5, 6
        result_regex = re.findall(r'{}(\d+[(.\d+)]*)\sM.*?(\d+[(.\d+)]*)\sMbits/sec\s+(\d+[(.\d+)]*).*?(\d+)/(\d+)\s\((\d+|\d+\.\d+)%'.format('SUM.*?' if parallel else ''), result_cache)  # .format('SUM.*?')为了指定-P参数返回正确的结果
        self.log_queue.put("iperf result log regex: {}".format(result_regex))

        if mode == 4 and len(result_regex) == 2:  # UDP upload and regex correct
            [(client_send, client_send_bandwidth, client_send_jitter, client_send_loss, client_send_total, client_send_loss_percent),
             (server_receive, server_receive_bandwidth, server_receive_jitter, server_receive_loss, server_receive_total, server_receive_loss_percent)] = result_regex
            self.log_queue.put(['at_log', '[{}] 模块UDP发送平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), client_send_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 服务器接收平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), server_receive_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 模块共发送 {} MBytes，jitter {} ms'.format(datetime.datetime.now(), client_send, client_send_jitter)])
            self.log_queue.put(['at_log', '[{}] 服务器共接收 {} MBytes，jitter {} ms'.format(datetime.datetime.now(), server_receive, server_receive_jitter)])
            self.log_queue.put(['at_log', '[{}] 模块发送共丢失数据包 {} 个，共发送 {} 个，丢包率 {} %'.format(datetime.datetime.now(), client_send_loss, client_send_total, client_send_loss_percent)])
            self.log_queue.put(['at_log', '[{}] 服务器接收共丢失数据包 {} 个，共发送 {} 个，丢包率 {} %'.format(datetime.datetime.now(), server_receive_loss, server_receive_total, server_receive_loss_percent)])
            self.log_queue.put(['df', runtimes, 'client_send', float(client_send)])
            self.log_queue.put(['df', runtimes, 'client_send_bandwidth', float(client_send_bandwidth)])
            self.log_queue.put(['df', runtimes, 'client_send_jitter', float(client_send_jitter)])
            self.log_queue.put(['df', runtimes, 'client_send_loss', float(client_send_loss)])
            self.log_queue.put(['df', runtimes, 'client_send_total', float(client_send_total)])
            self.log_queue.put(['df', runtimes, 'client_send_loss_percent', float(client_send_loss_percent)])
            self.log_queue.put(['df', runtimes, 'server_receive', float(server_receive)])
            self.log_queue.put(['df', runtimes, 'server_receive_bandwidth', float(server_receive_bandwidth)])
            self.log_queue.put(['df', runtimes, 'server_receive_jitter', float(server_receive_jitter)])
            self.log_queue.put(['df', runtimes, 'server_receive_loss', float(server_receive_loss)])
            self.log_queue.put(['df', runtimes, 'server_receive_total', float(server_receive_total)])
            self.log_queue.put(['df', runtimes, 'server_receive_loss_percent', float(server_receive_loss_percent)])
            self.logger.info("统计完成")
        if mode == 5 and len(result_regex) == 2:  # UDP upload and regex correct
            [(server_send, server_send_bandwidth, server_send_jitter, server_send_loss, server_send_total, server_send_loss_percent),
             (client_receive, client_receive_bandwidth, client_receive_jitter, client_receive_loss, client_receive_total, client_receive_loss_percent)] = result_regex
            self.log_queue.put(['at_log', '[{}] 模块UDP接收平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), client_receive_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 服务器发送平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), server_send_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 模块共接收 {} MBytes，jitter {} ms'.format(datetime.datetime.now(), client_receive, client_receive_jitter)])
            self.log_queue.put(['at_log', '[{}] 服务器共发送 {} MBytes，jitter {} ms'.format(datetime.datetime.now(), server_send, server_send_jitter)])
            self.log_queue.put(['at_log', '[{}] 模块接收共丢失数据包 {} 个，共接收 {} 个，丢包率 {} %'.format(datetime.datetime.now(), client_receive_loss, client_receive_total, client_receive_loss_percent)])
            self.log_queue.put(['at_log', '[{}] 服务器发送共丢失数据包 {} 个，共发送 {} 个，丢包率 {} %'.format(datetime.datetime.now(), server_send_loss, server_send_total, server_send_loss_percent)])
            self.log_queue.put(['df', runtimes, 'server_send', float(server_send)])
            self.log_queue.put(['df', runtimes, 'server_send_bandwidth', float(server_send_bandwidth)])
            self.log_queue.put(['df', runtimes, 'server_send_jitter', float(server_send_jitter)])
            self.log_queue.put(['df', runtimes, 'server_send_loss', float(server_send_loss)])
            self.log_queue.put(['df', runtimes, 'server_send_total', float(server_send_total)])
            self.log_queue.put(['df', runtimes, 'server_send_loss_percent', float(server_send_loss_percent)])
            self.log_queue.put(['df', runtimes, 'client_receive', float(client_receive)])
            self.log_queue.put(['df', runtimes, 'client_receive_bandwidth', float(client_receive_bandwidth)])
            self.log_queue.put(['df', runtimes, 'client_receive_jitter', float(client_receive_jitter)])
            self.log_queue.put(['df', runtimes, 'client_receive_loss', float(client_receive_loss)])
            self.log_queue.put(['df', runtimes, 'client_receive_total', float(client_receive_total)])
            self.log_queue.put(['df', runtimes, 'client_receive_loss_percent', float(client_receive_loss_percent)])
            self.logger.info("统计完成")
        if mode == 6 and len(result_regex) == 4:  # UDP bi-direction
            [(client_send, client_send_bandwidth, client_send_jitter, client_send_loss, client_send_total, client_send_loss_percent),
             (server_receive, server_receive_bandwidth, server_receive_jitter, server_receive_loss, server_receive_total, server_receive_loss_percent),
             (server_send, server_send_bandwidth, server_send_jitter, server_send_loss, server_send_total, server_send_loss_percent),
             (client_receive, client_receive_bandwidth, client_receive_jitter, client_receive_loss, client_receive_total, client_receive_loss_percent)
             ] = result_regex
            self.log_queue.put(['at_log', '[{}] 模块作为发送端，Server作为接收端时：'.format(datetime.datetime.now())])
            self.log_queue.put(['at_log', '[{}] 模块UDP发送平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), client_send_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 服务器接收平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), server_receive_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 模块共发送 {} MBytes，jitter {} ms'.format(datetime.datetime.now(), client_send, client_send_jitter)])
            self.log_queue.put(['at_log', '[{}] 服务器共接收 {} MBytes，jitter {} ms'.format(datetime.datetime.now(), server_receive, server_receive_jitter)])
            self.log_queue.put(['at_log', '[{}] 模块发送共丢失数据包 {} 个，共发送 {} 个，丢包率 {} %'.format(datetime.datetime.now(), client_send_loss, client_send_total, client_send_loss_percent)])
            self.log_queue.put(['at_log', '[{}] 服务器接收共丢失数据包 {} 个，共发送 {} 个，丢包率 {} %'.format(datetime.datetime.now(), server_receive_loss, server_receive_total, server_receive_loss_percent)])
            self.log_queue.put(['at_log', '[{}] 模块作为接收端，Server作为发送端时：'.format(datetime.datetime.now())])
            self.log_queue.put(['at_log', '[{}] 模块UDP接收平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), client_receive_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 服务器发送平均带宽 {} Mbits/sec'.format(datetime.datetime.now(), server_send_bandwidth)])
            self.log_queue.put(['at_log', '[{}] 模块共接收 {} MBytes，jitter {} ms'.format(datetime.datetime.now(), client_receive, client_receive_jitter)])
            self.log_queue.put(['at_log', '[{}] 服务器共发送 {} MBytes，jitter {} ms'.format(datetime.datetime.now(), server_send, server_send_jitter)])
            self.log_queue.put(['at_log', '[{}] 模块接收共丢失数据包 {} 个，共接收 {} 个，丢包率 {} %'.format(datetime.datetime.now(), client_receive_loss, client_receive_total, client_receive_loss_percent)])
            self.log_queue.put(['at_log', '[{}] 服务器发送共丢失数据包 {} 个，共发送 {} 个，丢包率 {} %'.format(datetime.datetime.now(), server_send_loss, server_send_total, server_send_loss_percent)])
            self.log_queue.put(['df', runtimes, 'client_send', float(client_send)])
            self.log_queue.put(['df', runtimes, 'client_send_bandwidth', float(client_send_bandwidth)])
            self.log_queue.put(['df', runtimes, 'client_send_jitter', float(client_send_jitter)])
            self.log_queue.put(['df', runtimes, 'client_send_loss', float(client_send_loss)])
            self.log_queue.put(['df', runtimes, 'client_send_total', float(client_send_total)])
            self.log_queue.put(['df', runtimes, 'client_send_loss_percent', float(client_send_loss_percent)])
            self.log_queue.put(['df', runtimes, 'server_receive', float(server_receive)])
            self.log_queue.put(['df', runtimes, 'server_receive_bandwidth', float(server_receive_bandwidth)])
            self.log_queue.put(['df', runtimes, 'server_receive_jitter', float(server_receive_jitter)])
            self.log_queue.put(['df', runtimes, 'server_receive_loss', float(server_receive_loss)])
            self.log_queue.put(['df', runtimes, 'server_receive_total', float(server_receive_total)])
            self.log_queue.put(['df', runtimes, 'server_receive_loss_percent', float(server_receive_loss_percent)])
            self.log_queue.put(['df', runtimes, 'server_send', float(server_send)])
            self.log_queue.put(['df', runtimes, 'server_send_bandwidth', float(server_send_bandwidth)])
            self.log_queue.put(['df', runtimes, 'server_send_jitter', float(server_send_jitter)])
            self.log_queue.put(['df', runtimes, 'server_send_loss', float(server_send_loss)])
            self.log_queue.put(['df', runtimes, 'server_send_total', float(server_send_total)])
            self.log_queue.put(['df', runtimes, 'server_send_loss_percent', float(server_send_loss_percent)])
            self.log_queue.put(['df', runtimes, 'client_receive', float(client_receive)])
            self.log_queue.put(['df', runtimes, 'client_receive_bandwidth', float(client_receive_bandwidth)])
            self.log_queue.put(['df', runtimes, 'client_receive_jitter', float(client_receive_jitter)])
            self.log_queue.put(['df', runtimes, 'client_receive_loss', float(client_receive_loss)])
            self.log_queue.put(['df', runtimes, 'client_receive_total', float(client_receive_total)])
            self.log_queue.put(['df', runtimes, 'client_receive_loss_percent', float(client_receive_loss_percent)])
            self.logger.info("统计完成")

    def server_file_prepare(self, ip, port, user, password, file_name, file_path, ftp_path, max_parallel, runtimes):
        """
        服务器新建文件夹，并且将本地文件传输到服务器上。
        :param ip: 服务器IP
        :param port: 服务器端口
        :param user: 用户名
        :param password: 密码
        :param file_name: 本地源文件名称
        :param file_path: 本地源文件路径
        :param ftp_path: FTP的路径
        :param max_parallel: 最大同时几路FTP上传下载
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        self.log_queue.put(['at_log', '[{}] Server端准备源文件'.format(datetime.datetime.now())])
        self.unique_folder_head = time.strftime("%Y%m%d%H%M%S", time.localtime(time.time()))
        folder_name_upload = ['{}_{}_u'.format(self.unique_folder_head, num) for num in range(max_parallel)]
        folder_name_download = ['{}_{}_d'.format(self.unique_folder_head, num) for num in range(max_parallel)]
        self.folder_name_list = folder_name_upload + folder_name_download
        file_size = os.path.getsize(os.path.join(file_path, file_name))

        async def async_ftp_client(folder_name):
            self.logger.info('=' * 30 + 'async_ftp_client')
            async with aioftp.Client.context(ip, port=port, user=user, password=password) as client:
                # 判断是否有当前时间戳的目录并进入目录生成文件夹
                try:
                    await client.make_directory('{}/{}'.format(ftp_path, self.unique_folder_head))
                except aioftp.errors.StatusCodeError:
                    pass
                while True:
                    try:
                        await client.change_directory('{}/{}'.format(ftp_path, self.unique_folder_head))
                    except aioftp.errors.StatusCodeError:
                        continue
                    else:
                        break
                while True:
                    try:
                        await client.make_directory(folder_name)
                    except aioftp.errors.StatusCodeError:
                        continue
                    else:
                        break

        async def async_ftp_client_upload(path):
            self.logger.info('=' * 30 + 'async_ftp_client_upload')
            async with aioftp.Client.context(ip, port=port, user=user, password=password) as client:
                while True:
                    try:
                        await client.upload(os.path.join(file_path, file_name), '{}/{}/{}/{}'.format(ftp_path, self.unique_folder_head, path, file_name), write_into=True)
                        # file_state = await client.list('{}/{}'.format(self.unique_folder_head, path))
                        # if file_name not in str(file_state[0][0]) or file_state[0][1]['size'] != str(file_size):
                        #     continue
                        # 此方法公共FTP服务器不支持
                        file_state = await client.stat('{}/{}/{}/{}'.format(ftp_path, self.unique_folder_head, path, file_name))
                        if int(file_state['size']) != file_size:
                            continue
                    except aioftp.errors.StatusCodeError:
                        continue
                    except OSError:
                        self.log_queue.put(['all', '[{}] runtimes:{} 服务器可能不支持相关FTP命令'.format(datetime.datetime.now(), runtimes)])
                        pause()
                    else:
                        break

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tasks_mkdir = [
            asyncio.ensure_future(async_ftp_client(folder_name_tuple)) for folder_name_tuple in self.folder_name_list
        ]
        tasks_upload_origin_file = [
            asyncio.ensure_future(async_ftp_client_upload(folder_name)) for folder_name in folder_name_download
        ]
        loop.run_until_complete(asyncio.gather(*tasks_mkdir))
        loop.run_until_complete(asyncio.gather(*tasks_upload_origin_file))
        loop.close()

    def local_file_prepare(self, file_name, local_file_path, runtimes):
        """
        进行本地文件和文件夹的准备工作
        :param file_name: 源文件的名称
        :param local_file_path: 源文件的路径
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        self.log_queue.put(['at_log', '[{}] 本地准备源文件'.format(datetime.datetime.now())])
        if not os.path.exists(os.path.join(local_file_path, self.unique_folder_head)):  # 如果本地没有文件夹，则创建文件夹
            os.mkdir(os.path.join(local_file_path, self.unique_folder_head))
        for folder in self.folder_name_list:
            if not os.path.exists(os.path.join(local_file_path, self.unique_folder_head, folder)):  # 如果没有文件夹，创建文件夹
                os.mkdir(os.path.join(local_file_path, self.unique_folder_head, folder))
                if folder.endswith('_u'):  # 如果是_u结尾代表是需要上传的文件的文件夹，上传文件的文件夹要把源文件复制过去
                    shutil.copy(os.path.join(local_file_path, file_name),
                                os.path.join(local_file_path, self.unique_folder_head, folder, file_name))

    def async_ftp(self, ip, port, user, password, file_name, local_file_path, ftp_file_path, runtimes):
        """
        进行FTP连接，上传下载文件，断开FTP连接，支持上下同传，多线程同传
        :param ip: 服务器的IP
        :param port: 服务器的端口
        :param user: 用户名
        :param password: 密码
        :param file_name: 源文件名称
        :param local_file_path: 源文件的地址
        :param ftp_file_path: ftp服务器的地址
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        folder_list_upload = [name for name in self.folder_name_list if name.endswith('_u')]
        folder_list_download = [name for name in self.folder_name_list if name.endswith('_d')]
        file_size = os.path.getsize(os.path.join(local_file_path, file_name))
        connect_time_list = []
        disconnect_time_list = []
        upload_time_list = []
        download_time_list = []

        self.log_queue.put(['at_log', '[{}] 启动 {} 个协程同时进行上传下载'.format(datetime.datetime.now(), len(folder_list_upload))])

        async def async_ftp_client_upload(child_folder_name):
            self.logger.info('{}-async_ftp_client_upload'.format(child_folder_name))
            client = aioftp.Client()
            try:
                self.logger.info('{}-async_ftp_client_upload -> connect'.format(child_folder_name))
                # 进行FTP连接
                connect_start_time = time.time()
                await client.connect(host=ip, port=port)
                await client.login(user=user, password=password)
                connect_time_list.append(time.time() - connect_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} 模块建立FTP连接发生异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

            timeout = 1800
            # 上传
            try:
                self.logger.info('{}-async_ftp_client_upload -> upload'.format(child_folder_name))
                upload_start_time = time.time()
                local_file = os.path.join(local_file_path, self.unique_folder_head, child_folder_name, file_name)
                ftp_file = '{}/{}/{}/{}'.format(ftp_file_path, self.unique_folder_head, child_folder_name, file_name)
                await asyncio.wait_for(client.upload(local_file, ftp_file, write_into=True), timeout)
                upload_time_list.append(time.time() - upload_start_time)
            except asyncio.TimeoutError:
                print(['all', '[{}] runtimes:{} FTP上传超时({})，请检查AT Log URC信息是否有连接异常断开'.format(datetime.datetime.now(), runtimes, timeout)])
                return
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} FTP上传过程出现异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

            # 上传仅检查大小是否一致
            self.logger.info('{}-async_ftp_client_upload -> check_file'.format(child_folder_name))
            file_state = await client.stat(ftp_file)
            if int(file_state['size']) != file_size:
                self.file_compare_fail_times += 1
                self.log_queue.put(['all', '[{}] runtimes:{} FTP上传后文件大小检测不一致 {} -> {}'.format(datetime.datetime.now(), runtimes, file_size, file_state['size'])])

            # 断开连接
            try:
                self.logger.info('{}-async_ftp_client_upload -> disconnect'.format(child_folder_name))
                disconnect_start_time = time.time()
                await client.quit()
                disconnect_time_list.append(time.time() - disconnect_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} FTP上传后断开连接时发生异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

        async def async_ftp_client_download(child_folder_name):
            client = aioftp.Client()
            self.logger.info('{}-async_ftp_client_download'.format(child_folder_name))
            try:
                # 进行FTP连接
                self.logger.info('{}-async_ftp_client_download -> connect'.format(child_folder_name))
                connect_start_time = time.time()
                await client.connect(host=ip, port=port)
                await client.login(user=user, password=password)
                connect_time_list.append(time.time() - connect_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} 模块建立FTP连接发生异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

            timeout = 1800
            # 下载
            try:
                self.logger.info('{}-async_ftp_client_download -> download'.format(child_folder_name))
                download_start_time = time.time()
                local_file = os.path.join(local_file_path, self.unique_folder_head, child_folder_name, file_name)
                ftp_file = '{}/{}/{}/{}'.format(ftp_file_path, self.unique_folder_head, child_folder_name, file_name)
                await asyncio.wait_for(client.download(ftp_file, local_file, write_into=True), timeout)
                download_time_list.append(time.time() - download_start_time)
            except asyncio.TimeoutError:
                print(['all', '[{}] runtimes:{} FTP下载超时({})，请检查AT Log URC信息是否有连接异常断开'.format(datetime.datetime.now(), runtimes, timeout)])
                return
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} FTP下载过程出现异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

            # 下载后对比用filecmp
            self.logger.info('{}-async_ftp_client_download -> check_file'.format(child_folder_name))
            file_state = filecmp.cmp(local_file, os.path.join(local_file_path, file_name), shallow=False)
            if file_state is False:
                self.file_compare_fail_times += 1
                self.log_queue.put(['all', '[{}] runtimes:{} FTP上传后文件检测不一致'.format(datetime.datetime.now(), runtimes)])

            # 断开连接
            try:
                self.logger.info('{}-async_ftp_client_download -> disconnect'.format(child_folder_name))
                disconnect_start_time = time.time()
                await client.quit()
                disconnect_time_list.append(time.time() - disconnect_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} FTP下载后断开连接时发生异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

        self.logger.info('async_ftp -> set event loop')
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.logger.info('async_ftp -> create upload tasks')
        task_upload = [
            asyncio.ensure_future(async_ftp_client_upload(child_folder_name)) for child_folder_name in
            folder_list_upload
        ]
        self.logger.info('async_ftp -> create download tasks')
        task_download = [
            asyncio.ensure_future(async_ftp_client_download(child_folder_name)) for child_folder_name in
            folder_list_download
        ]
        tasks = task_upload + task_download
        self.logger.info('async_ftp -> run tasks')
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
        self.logger.info('async_ftp -> gather log')
        file_size_mb = file_size / 1024 / 1024
        upload_speed = sum(file_size_mb / each_time for each_time in upload_time_list)
        download_speed = sum(file_size_mb / each_time for each_time in download_time_list)
        self.log_queue.put(['df', runtimes, 'file_compare_fail_times', self.file_compare_fail_times])
        self.log_queue.put(['df', runtimes, 'ftp_upload_time', float(np.mean(upload_time_list))])
        self.log_queue.put(['df', runtimes, 'ftp_upload_speed', upload_speed])
        self.log_queue.put(['df', runtimes, 'ftp_download_time', float(np.mean(download_time_list))])
        self.log_queue.put(['df', runtimes, 'ftp_download_speed', download_speed])
        self.log_queue.put(['at_log', '[{}] 上传平均时间 {} s'.format(datetime.datetime.now(), np.round(np.mean(upload_time_list), 2))])
        self.log_queue.put(['at_log', '[{}] 上传平均速度 {} MB/s'.format(datetime.datetime.now(), round(upload_speed, 2))])
        self.log_queue.put(['at_log', '[{}] 下载平均时间 {} s'.format(datetime.datetime.now(), np.round(np.mean(download_time_list), 2))])
        self.log_queue.put(['at_log', '[{}] 下载平均速度 {} MB/s'.format(datetime.datetime.now(), round(download_speed, 2))])
        self.file_compare_fail_times = 0  # 重置次数
        return True  # 如果都是正常情况

    def disconnect_dial(self, dial_mode, runtimes):
        """
        linux下 wwan、Gobinet断开拨号（kill quectel-CM进程）
        :param dial_mode: 拨号方式
        :param runtimes:
        :return:
        """
        dis_timeout = 60
        kill_start_time = time.time()
        cmd = subprocess.Popen('killall quectel-CM', shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while True:
            time.sleep(0.001)
            line = cmd.stdout.readline().decode('GBK', 'ignore')
            if line != '':
                self.logger.info(repr(line))
                cmd.terminate()
                return False
            else:
                cmd.terminate()
                quectel_value = os.popen('ps -ef | grep quectel-CM').read()
                if './quectel-CM' in quectel_value:
                    continue
                if time.time() - kill_start_time > dis_timeout:
                    self.log_queue.put(['all', '[{}] runtimes:{} 超时{}S断开{}拨号失败！'.format(datetime.datetime.now(), runtimes, dis_timeout, dial_mode)])
                    self.log_queue.put(['df', runtimes, 'dial_disconnect_fail_times', 1])
                    return False
                else:
                    self.log_queue.put(['df', runtimes, 'dial_disconnect_time', time.time() - kill_start_time])  # dial_disconnect_time
                    self.log_queue.put(['at_log', '[{}]断开{}拨号成功'.format(datetime.datetime.now(), dial_mode)])
                    self.log_queue.put(['df', runtimes, 'dial_disconnect_success_times', 1])
                    return True

    def fusion_protocol_test(self, server_config, dial_mode, runtimes):
        # 生成UDP文件
        udp_file_name = 'udp_send.txt'
        udp_file_path = os.path.join(os.getcwd(), udp_file_name)
        udp_recv_file_name = 'udp_recv.txt'
        udp_recv_file_path = os.path.join(os.getcwd(), udp_recv_file_name)
        if not os.path.exists(udp_file_name):
            with open(udp_file_name, 'w', encoding='utf-8', buffering=1) as f:
                f.write(''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=1024)))

        # 生成TCP文件
        file_name = 'send.txt'
        file_path = os.path.join(os.getcwd(), file_name)
        recv_file_name = 'recv.txt'
        recv_file_path = os.path.join(os.getcwd(), recv_file_name)

        file_size = int(server_config['file_size'])
        if not os.path.exists(file_name):
            send_data = ''.join(
                random.choices(string.ascii_letters + string.digits + string.punctuation, k=1024 * file_size))
            with open(file_name, 'w', encoding='utf-8', buffering=1) as f:
                f.write(send_data + '\n')

        # 生成HTTP文件
        http_file_name = 'send.txt'
        http_file_path = os.path.join(os.path.dirname(os.getcwd()), file_name)
        http_recv_file_name = 'recv.txt'

        file_size = int(server_config['file_size'])
        if not os.path.exists(http_file_path):
            send_data = ''.join(
                random.choices(string.ascii_letters + string.digits + string.punctuation, k=1024 * file_size))
            with open(http_file_path, 'w', encoding='utf-8', buffering=1) as f:
                f.write(send_data + '\n')

        # TCP
        self.log_queue.put(['at_log', '[{}] -------------------进行TCP测试-------------------'.format(datetime.datetime.now())])
        # connect_status = self.client_connect('TCP', server_config['tcp_server'], server_config['tcp_port'], runtimes)
        # send_recv_status = self.client_send_recv_compare('TCP', file_path, recv_file_path, runtimes)
        # disconnect_status = self.client_disconnect('TCP', runtimes)
        # if connect_status is False or send_recv_status is False or disconnect_status is False:
        #     self.log_queue.put(['df', runtimes, 'tcp_fail_times', 1])
        tcp = self.socket_tcp(server_config, file_path, recv_file_path, runtimes)
        if tcp is False:
            self.log_queue.put(['df', runtimes, 'tcp_fail_times', 1])

        # UDP
        self.log_queue.put(['at_log', '[{}] -------------------进行UDP测试-------------------'.format(datetime.datetime.now())])
        # connect_status = self.client_connect('UDP', server_config['tcp_server'], server_config['tcp_port'], runtimes)
        # send_recv_status = self.client_send_recv_compare('UDP', udp_file_path, udp_recv_file_path, runtimes)
        # disconnect_status = self.client_disconnect('UDP', runtimes)
        # if connect_status is False or send_recv_status is False or disconnect_status is False:
        #     self.log_queue.put(['df', runtimes, 'udp_fail_times', 1])
        udp = self.socket_udp(server_config, udp_file_path, udp_recv_file_path, runtimes)
        if udp is False:
            self.log_queue.put(['df', runtimes, 'udp_fail_times', 1])

        # FTP
        self.log_queue.put(['at_log', '[{}] -------------------进行FTP测试-------------------'.format(datetime.datetime.now())])
        ftp_path = server_config['ftp_path']
        # connect_status = self.ftp_connect(1, dial_mode, server_config['ftp_server'],
        # server_config['ftp_port'], server_config['ftp_username'], server_config['ftp_password'], runtimes)
        # send_recv_status = self.ftp_send_recv_compare(dial_mode, file_path,
        # file_name, ftp_file_path, ftp_path, recv_file_path, runtimes)
        # disconnect_status = self.ftp_disconnect(runtimes)
        # if connect_status is False or send_recv_status is False or disconnect_status is False:
        #     self.log_queue.put(['df', runtimes, 'ftp_fail_times', 1])
        ftp = self.ftp_test(server_config, file_name, ftp_path, recv_file_path, runtimes)
        if ftp is False:
            self.log_queue.put(['df', runtimes, 'ftp_fail_times', 1])

        # HTTP
        self.log_queue.put(['at_log', '[{}] -------------------进行HTTP测试-------------------'.format(datetime.datetime.now())])
        send_recv_status = self.http_post_get(server_config['http_server_url'], server_config['http_server_remove_url'], server_config['http_server_ip_port'], http_file_name, http_recv_file_name, runtimes)
        if send_recv_status is False:
            self.log_queue.put(['df', runtimes, 'http_fail_times', 1])

    def socket_udp(self, server_config, orig_file, recv_file, runtimes):
        # 设置读取的size
        CHUNK_SIZE = 1024

        # 取出server config中的ip和port
        ip = server_config['udp_server']
        port = server_config['udp_port']

        def socket_read(socket_fd, recv_file):
            with open(recv_file, 'wb') as f:
                while True:
                    try:
                        recv, addr = socket_fd.recvfrom(CHUNK_SIZE)
                        f.write(recv)
                    except (socket.timeout, OSError):
                        break

        # 创建并连接socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.log_queue.put(['at_log', '[{}] 创建UDP socket'.format(datetime.datetime.now())])

        # 设置超时，防止卡死
        s.settimeout(5)

        # 创建读取端口线程、设置成守护线程并启动
        t = threading.Thread(target=socket_read, args=(s, recv_file))
        t.setDaemon(True)
        t.start()

        # write file in chunk
        try:
            with open(orig_file, 'rb') as fp:
                for block in iter(partial(fp.read, CHUNK_SIZE), b''):
                    s.sendto(block, (ip, port))
        except socket.error as e:
            s.close()
            self.log_queue.put(['all', '[{}] runtimes:{} UDP 发送文件异常: {}'.format(datetime.datetime.now(), runtimes, e)])
            return False
        self.log_queue.put(['at_log', '[{}] UDP 发送成功'.format(datetime.datetime.now())])

        # 判断读取线程是否超时死掉
        while t.is_alive():
            continue
        else:
            s.close()
        self.log_queue.put(['at_log', '[{}] UDP 接收完成'.format(datetime.datetime.now())])

        # 对比发送接收文件
        if not filecmp.cmp(orig_file, recv_file, shallow=False):
            self.log_queue.put(['all', '[{}] runtimes:{} UDP 文件对比异常，UDP 为非可靠连接，仅记录，不关注'.format(datetime.datetime.now(), runtimes)])
            return False
        self.log_queue.put(['at_log', '[{}] UDP 文件对比成功'.format(datetime.datetime.now())])

    def socket_tcp(self, server_config, orig_file, recv_file, runtimes):
        # 设置读取的size
        CHUNK_SIZE = 1024

        # 取出server config中的ip和port
        ip = server_config['tcp_server']
        port = server_config['tcp_port']

        def socket_read(socket_fd, recv_file):
            with open(recv_file, 'wb') as f:
                while True:
                    try:
                        recv = socket_fd.recv(CHUNK_SIZE)
                        f.write(recv)
                    except (socket.timeout, OSError):
                        break

        # 创建并连接socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn_flag = s.connect_ex((ip, port))  # connect_ex连接正常返回0，不会引发异常
        if conn_flag != 0:
            self.log_queue.put(['all', '[{}] runtimes:{} TCP 连接异常: conn_flag: {}'.format(datetime.datetime.now(), runtimes, conn_flag)])
            return False
        self.log_queue.put(['at_log', '[{}] TCP 连接成功'.format(datetime.datetime.now())])

        # 设置超时，防止卡死
        s.settimeout(5)

        # 创建读取端口线程、设置成守护线程并启动
        t = threading.Thread(target=socket_read, args=(s, recv_file))
        t.setDaemon(True)
        t.start()

        # write file in chunk
        try:
            with open(orig_file, 'rb') as fp:
                for block in iter(partial(fp.read, CHUNK_SIZE), b''):
                    s.sendall(block)
        except socket.error as e:
            s.close()
            self.log_queue.put(['all', '[{}] runtimes:{} TCP 发送文件异常: {}'.format(datetime.datetime.now(), runtimes, e)])
            return False
        self.log_queue.put(['at_log', '[{}] TCP 发送成功'.format(datetime.datetime.now())])

        # 判断读取线程是否超时死掉
        while t.is_alive():
            continue
        else:
            s.close()
        self.log_queue.put(['at_log', '[{}] TCP 接收完成'.format(datetime.datetime.now())])

        # 对比发送接收文件
        if not filecmp.cmp(orig_file, recv_file, shallow=False):
            self.log_queue.put(['all', '[{}] runtimes:{} TCP文件对比异常'.format(datetime.datetime.now(), runtimes)])
            return False
        self.log_queue.put(['at_log', '[{}] TCP 文件对比成功'.format(datetime.datetime.now())])

    def ftp_test(self, server_config, file_path, ftp_path, recv_file_path, runtimes):
        ip = server_config['ftp_server']
        port = server_config['ftp_port']
        user = server_config['ftp_username']
        passwd = server_config['ftp_password']

        # 进行 FTP连接
        try:
            ftp = FTP(timeout=30)
            ftp.connect(ip, port, timeout=30)
            ftp.login(user, passwd)
        except all_errors as e:
            self.log_queue.put(['all', '[{}] runtimes:{} FTP 登录异常: {}'.format(datetime.datetime.now(), runtimes, e)])
            return False
        self.log_queue.put(['at_log', '[{}] 登录FTP服务器成功'.format(datetime.datetime.now())])

        # 在5G目录下创建文件夹，创建失败可能是已经存在，忽略异常
        try:
            ftp.mkd('./5G/{}'.format(ftp_path))
        except all_errors:
            pass

        # 切换路径到设置的文件夹
        try:
            ftp.cwd('./5G/{}'.format(ftp_path))
        except all_errors as e:
            self.log_queue.put(['all', '[{}] runtimes:{} 更改 FTP 文件夹异常: {}'.format(datetime.datetime.now(), runtimes, e)])
            ftp.close()
            return False
        self.log_queue.put(['at_log', '[{}] 修改ftp文件夹到{}'.format(datetime.datetime.now(), ftp_path)])

        # 发送文件
        try:
            with open(file_path, 'rb') as fp:
                ftp.storbinary('STOR {}'.format(os.path.basename(file_path)), fp)
        except all_errors as e:
            self.log_queue.put(['all', '[{}] runtimes:{} FTP 发送文件异常: {}'.format(datetime.datetime.now(), runtimes, e)])
            ftp.close()
            return False
        self.log_queue.put(['at_log', '[{}] 已成功发送文件'.format(datetime.datetime.now())])

        # 接收文件
        try:
            with open(recv_file_path, 'wb') as fp:
                ftp.retrbinary('RETR {}'.format(os.path.basename(file_path)), fp.write)
        except all_errors as e:
            self.log_queue.put(['all', '[{}] runtimes:{} FTP 接收文件异常: {}'.format(datetime.datetime.now(), runtimes, e)])
            ftp.close()
            return False
        self.log_queue.put(['at_log', '[{}] 已成功接收文件'.format(datetime.datetime.now())])

        if getattr(ftp, 'close'):
            ftp.close()

        # 对比发送接收文件
        if not filecmp.cmp(file_path, recv_file_path, shallow=False):
            self.log_queue.put(['all', '[{}] runtimes:{} 接收的文件对比失败'.format(datetime.datetime.now(), runtimes)])
            return False
        self.log_queue.put(['at_log', '[{}] 文件对比成功'.format(datetime.datetime.now())])
