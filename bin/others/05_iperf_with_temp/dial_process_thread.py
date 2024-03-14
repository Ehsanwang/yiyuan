# -*- encoding=utf-8 -*-
import datetime
import filecmp
import os
import re
import socket
import subprocess
import time
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
                    time.sleep(0.1)  # 延迟0.1秒避免端口打开异常
                    return True
                elif self.dm_port in port_list and self.at_port not in port_list:  # 发现仅有DM口并且没有AT口
                    time.sleep(3)  # 等待3S口还是只有AT口没有DM口判断为DUMP，RG502QEAAAR01A01M4G出现两个口相差1秒
                    port_list = self.get_port_list()
                    if self.dm_port in port_list and self.at_port not in port_list:
                        self.log_queue.put(['all', '[{}] runtimes:{} 模块DUMP'.format(datetime.datetime.now(), runtimes)])
                        self.check_usb_driver(True, runtimes)
                else:
                    time.sleep(0.1)  # 降低检测频率，减少CPU占用
            else:  # timeout秒驱动未加载
                if debug:
                    self.log_queue.put(['all', "[{}] runtimes:{} 模块开机{}秒内USB驱动{}加载失败".format(datetime.datetime.now(), runtimes, timeout, self.at_port)])
                    input("保留现场，问题定位完成后请直接关闭脚本")
                else:
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
                    input("保留现场，问题定位完成后请直接关闭脚本")
                else:
                    return False

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
                input("保留现场，问题定位完成后请直接关闭脚本")

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
            if '没有' in interface_status:
                time.sleep(1)
            elif time.time() - stat_timestamp > timeout:
                self.log_queue.put(['all', "[{}] runtimes: {} 开机成功后{}秒内PC拨号功能未加载成功，请确定原因".format(datetime.datetime.now(), runtimes, timeout)])
                input("保留现场，问题定位完成后请直接关闭脚本")
            else:
                self.log_queue.put(['at_log', "[{}] PC拨号功能加载成功".format(datetime.datetime.now())])
                time.sleep(10)  # 等待稳定
                # 获取本机移动宽带数量和移动宽带名称
                mobile_broadband_info = os.popen('netsh mbn show interface').read()
                mobile_broadband_num = ''.join(re.findall(r'系统上有 (\d+) 个接口', mobile_broadband_info))  # 手机宽带数量
                if mobile_broadband_num and int(mobile_broadband_num) > 1:
                    self.log_queue.put(['all', "[{}] runtimes: {} 系统上移动宽带有{}个，多于一个".format(datetime.datetime.now(), runtimes, mobile_broadband_num)])
                    input("保留现场，问题定位完成后请直接关闭脚本")
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
                    '46003': 'ctnet',  # 电信
                    '46005': 'ctnet',  # 电信
                    '46011': 'ctnet',  # 电信
                }
                # 写入XML文件
                mbn_profile = ET.Element('MBNProfileExt', xmlns='http://www.microsoft.com/networking/WWAN/profile/v4')
                ET.SubElement(mbn_profile, "Name").text = str(time.time())
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
            input("保留现场，问题定位完成后请直接关闭脚本")
        mobile_broadband_name = ''.join(re.findall(r'\s+名称\s+:\s(.*)', mobile_broadband_info))
        return mobile_broadband_name

    def reset_connect(self, runtimes):
        """
        如果MBIM/NDIS为连接状态，则关闭连接。
        :param runtimes: 当前脚本的运行次数
        :return: True:执行成功；False:执行失败
        """
        interface_name = self.get_interface_name(runtimes)
        os.popen('netsh mbn disconnect interface="{}"'.format(interface_name)).read()
        time.sleep(5)
        interface_data = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
        if '未连接' in interface_data:
            self.log_queue.put(['at_log', '[{}] 连接重置成功'.format(datetime.datetime.now())])
            return True
        else:
            self.logger.info(interface_data)
            self.log_queue.put(['all', '[{}] runtimes:{} 连接重置失败'.format(datetime.datetime.now(), runtimes)])
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
            input("保留现场，问题定位完成后请直接关闭脚本")
        elif dial_mode.upper() == 'MBIM' and 'Generic Mobile Broadband Adapter' not in repr(driver_name):
            self.log_queue.put(['all', '[{}] runtimes:{} 拨号驱动加载异常，MBIM拨号加载非MBIM驱动'.format(datetime.datetime.now(), runtimes)])
            input("保留现场，问题定位完成后请直接关闭脚本")

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

    def connect(self, dial_mode, runtimes):
        """
        进行MBIM或者NDIS的拨号连接
        :param dial_mode: 拨号模式，MBIM还是NDIS
        :param runtimes: 脚本运行次数
        :return: True:连接成功；False：连接失败
        """
        interface_name = self.get_interface_name(runtimes)
        dial_connect_start_timestamp = time.time()
        os.popen('netsh mbn connect interface="{}" connmode=tmp name=_profile.xml'.format(interface_name))
        self.log_queue.put(['df', runtimes, 'dial_connect_time', time.time() - dial_connect_start_timestamp])  # dial_connect_time
        time.sleep(10)  # 等待10秒稳定
        interface_data = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
        if '已连接' in interface_data:
            self.log_queue.put(['at_log', '[{}] {}连接成功'.format(datetime.datetime.now(), dial_mode)])
            self.log_queue.put(['df', runtimes, 'dial_success_times', 1])  # runtimes_start_timestamp
            return True
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败'.format(datetime.datetime.now(), runtimes, dial_mode)])
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
            os.popen('netsh mbn disconnect interface="{}"'.format(interface_name))
            self.log_queue.put(['df', runtimes, 'dial_disconnect_time', time.time() - dial_disconnect_start_timestamp])  # dial_disconnect_time
            time.sleep(5)
            interface_status = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
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
                self.log_queue.put(['df', runtimes, 'tcp_udp_connect_time', time.time() - tcp_udp_connect_start_timestamp])  # tcp_udp_connect_time
                # 发送接收数据验证连接是否正常
                self.client_tcp_udp.sendall(b"hello world!")
                data_recv = self.client_tcp_udp.recv(1024).decode('GBK')
                if conn == 0 and data_recv == 'hello world!':  # 正常情况
                    self.log_queue.put(['at_log', '[{}] {}连接成功'.format(datetime.datetime.now(), connect_type)])
                    self.log_queue.put(['df', runtimes, 'tcp_udp_connect_success_times', 1])  # runtimes_start_timestamp
                    return True  # 连接成功
                else:  # 异常情况
                    interface_name = self.get_interface_name(runtimes)
                    interface_status = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
                    if '已连接' in interface_status:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败，拨号状态正常'.format(datetime.datetime.now(), runtimes, connect_type)])
                    else:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败，拨号状态异常'.format(datetime.datetime.now(), runtimes, connect_type)])
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
                send_data = f.read()
            self.client_tcp_udp.sendall(send_data)
            # 3. 接收数据
            self.log_queue.put(['at_log', '[{}] 开始接收文件'.format(datetime.datetime.now())])
            recv_data_start_timestamp = time.time()
            file_path_recv = os.path.join(base_path, receive_file_name)
            with open(file_path_recv, mode='wb') as f:
                recv_size = 0  # 单文件已接收字节数
                while True:
                    buffer = self.client_tcp_udp.recv(8196)
                    recv_size += len(buffer)
                    f.write(buffer)
                    if recv_size >= file_size:
                        break
                    # 接收超时判断
                    if time.time() - recv_data_start_timestamp > 360:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}接收文件超时'.format(datetime.datetime.now(), runtimes, connect_type)])
                        return False
            self.log_queue.put(['df', runtimes, 'recv_file_time', time.time() - recv_data_start_timestamp])  # runtimes_start_timestamp
            # 3. 对比文件
            if filecmp.cmp(file_path, file_path_recv, False):
                self.log_queue.put(['at_log', '[{}] 源文件和目标文件对比相同'.format(datetime.datetime.now())])
                return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} 源文件和目标文件对比不同'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'file_compare_fail_times', 1])  # file_compare_fail_times
                return True
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
                    interface_name = self.get_interface_name(runtimes)
                    interface_status = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
                    if '已连接' in interface_status:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败，拨号状态正常'.format(datetime.datetime.now(), runtimes, connect_type)])
                    else:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败，拨号状态异常'.format(datetime.datetime.now(), runtimes, connect_type)])
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
                        ftp_file_size = self.ftp.size(ftp_file)
                if ftp_file_size != local_file_size:
                    self.logger.info(ftp_file_size)
                    self.log_queue.put(['all', '[{}] runtimes:{} ftp上传文件成功，但是文件大小不一致'.format(datetime.datetime.now(), runtimes)])
            else:
                self.log_queue.put(["all", '[{}] runtimes:{} ftp文件上传失败'.format(datetime.datetime.now(), runtimes)])
                interface_name = self.get_interface_name(runtimes)
                interface_status = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
                if '已连接' in interface_status:
                    self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败，{}拨号状态正常'.format(datetime.datetime.now(), runtimes, "FTP", connect_type)])
                else:
                    self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败，{}拨号状态异常'.format(datetime.datetime.now(), runtimes, "FTP", connect_type)])

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
                interface_name = self.get_interface_name(runtimes)
                interface_status = os.popen('netsh mbn show connection interface="{}"'.format(interface_name)).read()
                if '已连接' in interface_status:
                    self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败，{}拨号状态正常'.format(datetime.datetime.now(), runtimes, "FTP", connect_type)])
                else:
                    self.log_queue.put(['all', '[{}] runtimes:{} {}连接失败，{}拨号状态异常'.format(datetime.datetime.now(), runtimes, "FTP", connect_type)])

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
                    input("保留现场，问题定位完成后请直接关闭脚本")
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
            self.log_queue.put(['at_log', '[{}] HTTP(s)上传文件中，请稍等'.format(datetime.datetime.now())])
            post_start_timestamp = time.time()
            post_data = requests.post(server_url, data=file_upload, headers=req_headers)
            if post_data.status_code != 200:
                self.log_queue.put(['df', runtimes, 'post_file_time', 999])
                self.log_queue.put(['df', runtimes, 'post_file_fail_times', 1])
            else:
                self.log_queue.put(['df', runtimes, 'post_file_time', time.time() - post_start_timestamp])
                self.log_queue.put(['df', runtimes, 'post_file_success_times', 1])
                self.log_queue.put(['at_log', '[{}] HTTP(s)文件上传完成'.format(datetime.datetime.now())])
            post_data_dict = post_data.json()
            path_temp = post_data_dict["path"]
            post_data.close()

            # get下载文件
            self.log_queue.put(['at_log', '[{}] HTTP(s)文件下载中，请稍等'.format(datetime.datetime.now())])
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

            file_path = os.path.abspath(os.path.join(os.path.dirname('__file__'), os.path.pardir)) + "\\" + source_name
            file_path_recv = os.path.abspath(os.path.join(os.path.dirname('__file__'), os.path.pardir)) + "\\" + receive_file_name

            # 比较文件
            if filecmp.cmp(file_path, file_path_recv, False):
                self.log_queue.put(['at_log', '[{}] 源文件和目标文件对比相同'.format(datetime.datetime.now())])
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} 源文件和目标文件对比不同'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'file_compare_fail_times', 1])  # runtimes_start_timestamp
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
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，GobiNet拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def rgmii_connect_check(self, runtimes):
        """
        检测RGMII拨号当前的状态。
        :param runtimes: 当前脚本的运行次数
        :return: True，拨号检测成功；False，拨号检测失败
        """
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
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
                    self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，RGMII拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
                    self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
                    return False
        else:
            self.logger.info(os.popen('ipconfig').read())
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.qq.com').read())])
            self.log_queue.put(['all', '[{}] runtimes:{} RGMII拨号异常，RGMII默认网关和IP异常'.format(datetime.datetime.now(), runtimes)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
            return False

    def iperf(self, server, port, times, bandwidth, reverse, udp, runtimes):
        speed_abnormal_times = 0
        names = locals()
        ports = port.split(',')  # 切分列表
        bandwidths = bandwidth.split(',')  # 切分bandwidth
        iperf_tests = []  # 用于存放iperf测试实例
        for num, port in enumerate(ports):  # 根据端口数量，创建n个iperf
            iperf_command = ['iperf3', '-c', server, '-f', 'm', '-p', port, '-i', '1', '-t', times]
            if len(bandwidths) == 1:
                iperf_command.extend(['-b', bandwidths.pop()])
            elif len(bandwidths) == 2:
                iperf_command.extend(['-b', '{}'.format(bandwidths[0] if num == 0 else bandwidths[1])])
            iperf_command.append('-R') if (len(ports) == 2 and num == 1) or (reverse and len(ports) == 1) else None
            iperf_command.append('-u') if udp else None  # 是否是UDP模式，True：UDP，False TCP
            names['s_{}'.format(num)] = subprocess.Popen(iperf_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            iperf_tests.append([iperf_command, names['s_{}'.format(num)]])
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), ' '.join(iperf_command))])
        for iperf_command, single_test in iperf_tests:  # 获取iperf3测试的返回结果
            return_value = single_test.communicate()[0].decode('utf-8', 'replace')
            if 'error' in return_value:
                self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), return_value)])
                self.log_queue.put(['all', "[{}] runtimes:{} iperf3测试返回error，请在AT log中检查iperf返回值".format(datetime.datetime.now(), runtimes)])
            else:
                try:
                    self.log_queue.put(['at_log', '[{}] \n {}'.format(datetime.datetime.now(), return_value)])
                    self.logger.info(return_value)
                    return_value_regex = ''.join(re.findall(r'[\s|\S]*- - - -', return_value))
                    speed_abnormal_regex = re.findall(r'0\.0\d+\sMbits/sec.*', return_value_regex)
                    if len(speed_abnormal_regex) != 0:
                        self.log_queue.put(['df', runtimes, 'speed_abnormal_times', len(speed_abnormal_regex)])
                        self.log_queue.put(['all', "[{}] runtimes:{} iperf3测速出现断流".format(datetime.datetime.now(), runtimes)])
                    else:
                        self.log_queue.put(['df', runtimes, 'speed_abnormal_times', 0])
                    if '-u' not in iperf_command and '-R' not in iperf_command:  # TCP上传
                        sender_value = ''.join(re.findall('.*sender', return_value))
                        receiver_value = ''.join(re.findall('.*receiver', return_value))
                        sender_value_regex = re.search(r'\w+\s+(?P<size>\d+\.*\d*)\s+(?P<size_unit>\w+)\s+(?P<speed>\d+\.*\d*)\s+(?P<speed_unit>\w+/\w+).*se', sender_value)
                        receiver_value_regex = re.search(r'\w+\s+(?P<size>\d+\.*\d*)\s+(?P<size_unit>\w+)\s+(?P<speed>\d+\.*\d*)\s+(?P<speed_unit>\w+/\w+).*re', receiver_value)
                        sender_size, sender_size_unit, sender_speed, sender_speed_unit = sender_value_regex.groups()
                        receiver_size, receiver_size_unit, receiver_speed, receiver_speed_unit = receiver_value_regex.groups()
                        self.log_queue.put(['at_log', '[{}] 模块TCP上传平均带宽 {} {}'.format(datetime.datetime.now(), sender_speed, sender_speed_unit)])
                        self.log_queue.put(['at_log', '[{}] 模块上传 {} {}'.format(datetime.datetime.now(), sender_size, sender_size_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器接收平均带宽 {} {}'.format(datetime.datetime.now(), receiver_speed, receiver_speed_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器接收 {} {}'.format(datetime.datetime.now(), receiver_size, receiver_size_unit)])
                        # 单位转换和格式转换
                        sender_speed = float(sender_speed)
                        receiver_speed = float(receiver_speed)
                        sender_size = float(sender_size)
                        sender_size = sender_size / 1024 if sender_size_unit == 'KBytes' else sender_size
                        sender_size = sender_size / 1024 / 1024 if sender_size_unit == 'Bytes' else sender_size
                        receiver_size = float(receiver_size)
                        receiver_size = receiver_size / 1024 if receiver_size_unit == 'KBytes' else receiver_size
                        receiver_size = receiver_size / 1024 / 1024 if receiver_size_unit == 'Bytes' else receiver_size
                        self.log_queue.put(['df', runtimes, 'tcp_upload_speed', sender_speed])
                        self.log_queue.put(['df', runtimes, 'tcp_upload_size', sender_size])
                        self.log_queue.put(['df', runtimes, 'tcp_upload_server_speed', receiver_speed])
                        self.log_queue.put(['df', runtimes, 'tcp_upload_server_size', receiver_size])
                    elif '-u' not in iperf_command and '-R' in iperf_command:  # TCP下载
                        sender_value = ''.join(re.findall('.*sender', return_value))
                        receiver_value = ''.join(re.findall('.*receiver', return_value))
                        sender_value_regex = re.search(r'\w+\s+(?P<size>\d+\.*\d*)\s+(?P<size_unit>\w+)\s+(?P<speed>\d+\.*\d*)\s+(?P<speed_unit>\w+/\w+)\s+(?P<retr>\d*)\s+se', sender_value)
                        receiver_value_regex = re.search(r'\w+\s+(?P<size>\d+\.*\d*)\s+(?P<size_unit>\w+)\s+(?P<speed>\d+\.*\d*)\s+(?P<speed_unit>\w+/\w+).*re', receiver_value)
                        sender_size, sender_size_unit, sender_speed, sender_speed_unit, retransmitted = sender_value_regex.groups()
                        receiver_size, receiver_size_unit, receiver_speed, receiver_speed_unit = receiver_value_regex.groups()
                        self.log_queue.put(['at_log', '[{}] 模块TCP下载平均带宽 {} {}'.format(datetime.datetime.now(), receiver_speed, receiver_speed_unit)])
                        self.log_queue.put(['at_log', '[{}] 模块共下载 {} {}'.format(datetime.datetime.now(), receiver_size, receiver_size_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器发送平均带宽 {} {}'.format(datetime.datetime.now(), sender_speed, sender_speed_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器共发送 {} {}'.format(datetime.datetime.now(), sender_size, sender_size_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器重发 {} 次'.format(datetime.datetime.now(), retransmitted)])
                        # 单位转换和格式转换
                        sender_speed = float(sender_speed)
                        receiver_speed = float(receiver_speed)
                        sender_size = float(sender_size)
                        sender_size = sender_size / 1024 if sender_size_unit == 'KBytes' else sender_size
                        sender_size = sender_size / 1024 / 1024 if sender_size_unit == 'Bytes' else sender_size
                        receiver_size = float(receiver_size)
                        receiver_size = receiver_size / 1024 if receiver_size_unit == 'KBytes' else receiver_size
                        receiver_size = receiver_size / 1024 / 1024 if receiver_size_unit == 'Bytes' else receiver_size
                        self.log_queue.put(['df', runtimes, 'tcp_download_speed', receiver_speed])
                        self.log_queue.put(['df', runtimes, 'tcp_download_size', receiver_size])
                        self.log_queue.put(['df', runtimes, 'tcp_download_server_speed', sender_speed])
                        self.log_queue.put(['df', runtimes, 'tcp_download_server_size', sender_size])
                        retransmitted = int(retransmitted) if retransmitted != '' else 0
                        self.log_queue.put(['df', runtimes, 'tcp_download_server_retransmitted', retransmitted])
                    elif '-u' in iperf_command and '-R' not in iperf_command:  # UDP上传
                        # 客户端
                        sender_size_list = []
                        sender_speed_list = []
                        sender_packet_all_sum = 0
                        sender_speed_unit = ''
                        sender_speed = ''
                        seconds = ''.join(re.findall(r'[\s|\S]*- - - -', return_value))
                        seconds = re.findall(r'\w+\s+(?P<size>\d+\.*\d*)\s(?P<size_unit>\w+)\s+(?P<speed>\d+\.*\d*)\s(?P<speed_unit>\w+/\w+)\s+(?P<packet_send>\d+)', seconds)
                        for per_second in seconds:
                            sender_size, sender_size_unit, sender_speed, sender_speed_unit, sender_packet_all = per_second
                            sender_size = float(sender_size)
                            sender_size = sender_size / 1024 if sender_size_unit == 'KBytes' else sender_size
                            sender_size = sender_size / 1024 / 1024 if sender_size_unit == 'Bytes' else sender_size
                            sender_size_list.append(float(sender_size))
                            sender_speed_list.append(float(sender_speed))
                            sender_packet_all_sum += int(sender_packet_all)
                        self.log_queue.put(['at_log', '[{}] 模块UDP上传平均带宽 {} {}'.format(datetime.datetime.now(), round(sum(sender_speed_list) / len(sender_speed_list), 2), sender_speed_unit)])
                        self.log_queue.put(['at_log', '[{}] 模块共上传 {} MBytes'.format(datetime.datetime.now(), round(sum(sender_size_list), 2))])
                        self.log_queue.put(['at_log', '[{}] 模块共发送数据包 {} 个'.format(datetime.datetime.now(), sender_packet_all_sum)])
                        # 服务端
                        receiver_value = ''.join(re.findall(r'(.*)\s+\[\s+\d+]\s\Sent', return_value))
                        receiver_value_regex = re.search(r'\w+\s+(?P<size>\d+\.*\d*)\s(?P<size_unit>\w+)\s+(?P<speed>\d+\.*\d*)\s(?P<speed_unit>\w+/\w+)\s+(?P<jitter>\d+\.*\d+)\s+\w+\s+(?P<packet_lost>\d+)/(?P<packet_all>\d+)\s+\((?P<packet_loss_percent>[\d\w\+]+)', receiver_value)
                        receiver_size, receiver_size_unit, receiver_speed, receiver_speed_unit, receiver_jitter, receiver_packet_lost, receiver_packet_all, receiver_packet_loss_percent = receiver_value_regex.groups()
                        self.log_queue.put(['at_log', '[{}] 服务器接收平均带宽 {} {}'.format(datetime.datetime.now(), receiver_speed, receiver_speed_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器共接收 {} {}'.format(datetime.datetime.now(), receiver_size, receiver_size_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器平均抖动 {} ms'.format(datetime.datetime.now(), receiver_jitter)])
                        self.log_queue.put(['at_log', '[{}] 服务器共接收数据包 {} 个'.format(datetime.datetime.now(), receiver_packet_all)])
                        self.log_queue.put(['at_log', '[{}] 服务器共丢失数据包 {} 个'.format(datetime.datetime.now(), receiver_packet_lost)])
                        self.log_queue.put(['at_log', '[{}] 服务器丢包率 {} %'.format(datetime.datetime.now(), receiver_packet_loss_percent)])
                        # DataFrame
                        self.log_queue.put(['df', runtimes, 'udp_upload_speed', round(sum(sender_speed_list) / len(sender_speed_list), 2)])
                        self.log_queue.put(['df', runtimes, 'udp_upload_size', round(sum(sender_size_list), 2)])
                        self.log_queue.put(['df', runtimes, 'udp_upload_packet', sender_packet_all_sum])
                        self.log_queue.put(['df', runtimes, 'udp_server_upload_speed', float(receiver_speed)])
                        self.log_queue.put(['df', runtimes, 'udp_server_upload_size', float(receiver_size)])
                        self.log_queue.put(['df', runtimes, 'udp_server_upload_jitter', float(receiver_jitter)])
                        self.log_queue.put(['df', runtimes, 'udp_server_upload_packet', int(receiver_packet_all)])
                        self.log_queue.put(['df', runtimes, 'udp_server_upload_packet_lost', int(receiver_packet_lost)])
                        self.log_queue.put(['df', runtimes, 'udp_server_upload_packet_lost_percent', float(receiver_packet_loss_percent)])
                    elif '-u' in iperf_command and '-R' in iperf_command:  # UDP下载
                        # 客户端
                        sender_size_list = []
                        sender_speed_list = []
                        sender_jitter_list = []
                        sender_packet_lost_sum = 0
                        sender_packet_all_sum = 0
                        sender_speed_unit = ''
                        sender_speed = ''
                        seconds = ''.join(re.findall(r'[\s|\S]*- - - -', return_value))
                        seconds = re.findall(r'\w+\s+(?P<size>\d+\.*\d*)\s(?P<size_unit>\w+)\s+(?P<speed>\d+\.*\d*)\s(?P<speed_unit>\w+/\w+)\s+(?P<jitter>\d+\.*\d+)\s+\w+\s+(?P<packet_lost>\d+)/(?P<packet_all>\d+)\s+\((?P<packet_loss_percent>\d+)', seconds)
                        for per_second in seconds:
                            sender_size, sender_size_unit, sender_speed, sender_speed_unit, sender_jitter, sender_packet_lost, sender_packet_all, sender_packet_loss_percent = per_second
                            sender_size = float(sender_size)
                            sender_size = sender_size / 1024 if sender_size_unit == 'KBytes' else sender_size
                            sender_size = sender_size / 1024 / 1024 if sender_size_unit == 'Bytes' else sender_size
                            sender_size_list.append(float(sender_size))
                            sender_speed_list.append(float(sender_speed))
                            sender_packet_lost_sum += int(sender_packet_lost)
                            sender_packet_all_sum += int(sender_packet_all)
                            sender_jitter_list.append(float(sender_jitter))
                        self.log_queue.put(['at_log', '[{}] 模块UDP下载平均带宽 {} {}'.format(datetime.datetime.now(), round(sum(sender_speed_list) / len(sender_speed_list), 2), sender_speed_unit)])
                        self.log_queue.put(['at_log', '[{}] 模块共下载 {} MBytes'.format(datetime.datetime.now(), round(sum(sender_size_list), 2))])
                        self.log_queue.put(['at_log', '[{}] 模块平均抖动 {} ms'.format(datetime.datetime.now(), round(sum(sender_jitter_list) / len(sender_jitter_list), 2))])
                        self.log_queue.put(['at_log', '[{}] 模块共接收数据包 {} 个'.format(datetime.datetime.now(), sender_packet_all_sum)])
                        self.log_queue.put(['at_log', '[{}] 模块共丢失数据包 {} 个'.format(datetime.datetime.now(), sender_packet_lost_sum)])
                        self.log_queue.put(['at_log', '[{}] 模块UDP下载丢包率 {} %'.format(datetime.datetime.now(), round(sender_packet_lost_sum / sender_packet_all_sum * 100, 2))])
                        # 服务端
                        receiver_value = ''.join(re.findall(r'(.*)\s+\[\s+\d+]\s\Sent', return_value))
                        receiver_value_regex = re.search(r'\w+\s+(?P<size>\d+\.*\d*)\s(?P<size_unit>\w+)\s+(?P<speed>\d+\.*\d*)\s(?P<speed_unit>\w+/\w+)\s+(?P<jitter>\d+\.*\d+)\s+\w+\s+(?P<packet_lost>\d+)/(?P<packet_all>\d+)\s+\((?P<packet_loss_percent>[\d\w\+]+)', receiver_value)
                        receiver_size, receiver_size_unit, receiver_speed, receiver_speed_unit, receiver_jitter, receiver_packet_lost, receiver_packet_all, receiver_packet_loss_percent = receiver_value_regex.groups()
                        self.log_queue.put(['at_log', '[{}] 服务器发送平均带宽 {} {}'.format(datetime.datetime.now(), receiver_speed, receiver_speed_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器共发送 {} {}'.format(datetime.datetime.now(), receiver_size, receiver_size_unit)])
                        self.log_queue.put(['at_log', '[{}] 服务器平均抖动 {} ms'.format(datetime.datetime.now(), receiver_jitter)])
                        self.log_queue.put(['at_log', '[{}] 服务器共发送数据包 {} 个'.format(datetime.datetime.now(), receiver_packet_all)])
                        self.log_queue.put(['at_log', '[{}] 服务器共丢失数据包 {} 个'.format(datetime.datetime.now(), receiver_packet_lost)])
                        self.log_queue.put(['at_log', '[{}] 服务器丢包率 {} %'.format(datetime.datetime.now(), float(receiver_packet_loss_percent))])
                        # DataFrame
                        self.log_queue.put(['df', runtimes, 'udp_download_speed', round(sum(sender_speed_list) / len(sender_speed_list), 2)])
                        self.log_queue.put(['df', runtimes, 'udp_download_size', round(sum(sender_size_list), 2)])
                        self.log_queue.put(['df', runtimes, 'udp_download_jitter', round(sum(sender_jitter_list) / len(sender_jitter_list), 2)])
                        self.log_queue.put(['df', runtimes, 'udp_download_packet', sender_packet_all_sum])
                        self.log_queue.put(['df', runtimes, 'udp_download_packet_lost', sender_packet_lost_sum])
                        self.log_queue.put(['df', runtimes, 'udp_download_packet_lost_percent', round(sender_packet_lost_sum / sender_packet_all_sum * 100)])
                        self.log_queue.put(['df', runtimes, 'udp_server_download_speed', float(receiver_speed)])
                        self.log_queue.put(['df', runtimes, 'udp_server_download_size', float(receiver_size)])
                        self.log_queue.put(['df', runtimes, 'udp_server_download_jitter', float(receiver_jitter)])
                        self.log_queue.put(['df', runtimes, 'udp_server_download_packet', int(receiver_packet_all)])
                        self.log_queue.put(['df', runtimes, 'udp_server_download_packet_lost', int(receiver_packet_lost)])
                        self.log_queue.put(['df', runtimes, 'udp_server_download_packet_lost_percent', float(receiver_packet_loss_percent)])
                except Exception as e:
                    self.logger.info(e)
                    self.log_queue.put(['all', "[{}] runtimes:{} 数据解析异常".format(datetime.datetime.now(), runtimes)])

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
                        input("保留现场，问题定位完成后请直接关闭脚本")
                    else:
                        break

        loop = asyncio.ProactorEventLoop()
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
            client = aioftp.Client()
            try:
                # 进行FTP连接
                connect_start_time = time.time()
                await client.connect(host=ip, port=port)
                await client.login(user=user, password=password)
                connect_time_list.append(time.time() - connect_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} 模块建立FTP连接发生异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

            # 上传
            try:
                upload_start_time = time.time()
                local_file = os.path.join(local_file_path, self.unique_folder_head, child_folder_name, file_name)
                ftp_file = '{}/{}/{}/{}'.format(ftp_file_path, self.unique_folder_head, child_folder_name, file_name)
                await client.upload(local_file, ftp_file, write_into=True)
                upload_time_list.append(time.time() - upload_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} FTP上传过程出现异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

            # 上传仅检查大小是否一致
            file_state = await client.stat(ftp_file)
            if int(file_state['size']) != file_size:
                self.file_compare_fail_times += 1
                self.log_queue.put(['all', '[{}] runtimes:{} FTP上传后文件大小检测不一致 {} -> {}'.format(datetime.datetime.now(), runtimes, file_size, file_state['size'])])

            # 断开连接
            try:
                disconnect_start_time = time.time()
                await client.quit()
                disconnect_time_list.append(time.time() - disconnect_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} FTP上传后断开连接时发生异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

        async def async_ftp_client_download(child_folder_name):
            client = aioftp.Client()
            try:
                # 进行FTP连接
                connect_start_time = time.time()
                await client.connect(host=ip, port=port)
                await client.login(user=user, password=password)
                connect_time_list.append(time.time() - connect_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} 模块建立FTP连接发生异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

            # 下载
            try:
                download_start_time = time.time()
                local_file = os.path.join(local_file_path, self.unique_folder_head, child_folder_name, file_name)
                ftp_file = '{}/{}/{}/{}'.format(ftp_file_path, self.unique_folder_head, child_folder_name, file_name)
                await client.download(ftp_file, local_file, write_into=True)
                download_time_list.append(time.time() - download_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} FTP下载过程出现异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

            # 下载后对比用filecmp
            file_state = filecmp.cmp(local_file, os.path.join(local_file_path, file_name), shallow=False)
            if file_state is False:
                self.file_compare_fail_times += 1
                self.log_queue.put(['all', '[{}] runtimes:{} FTP上传后文件检测不一致'.format(datetime.datetime.now(), runtimes)])

            # 断开连接
            try:
                disconnect_start_time = time.time()
                await client.quit()
                disconnect_time_list.append(time.time() - disconnect_start_time)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} FTP下载后断开连接时发生异常 {}'.format(datetime.datetime.now(), runtimes, e)])
                return

        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        task_upload = [
            asyncio.ensure_future(async_ftp_client_upload(child_folder_name)) for child_folder_name in
            folder_list_upload
        ]
        task_download = [
            asyncio.ensure_future(async_ftp_client_download(child_folder_name)) for child_folder_name in
            folder_list_download
        ]
        tasks = task_upload + task_download
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
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
