# -*- encoding=utf-8 -*-
import datetime
import os
import re
import subprocess
import time
import serial.tools.list_ports
from threading import Thread
from ftplib import FTP
import logging
import glob
import signal
from functions import pause, IPerfServer


class RgmiiRtl8125ProcessThread(Thread):
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

    def check_ip(self, runtimes):
        for _ in range(20):  # 开机后进行20次检查，每次2s
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
                if ipv4 and '192.168' in ipv4:  # 如果网关为RGMII的默认网关，并且IP地址正常，则使用requests库进行连接测试
                    self.log_queue.put(['at_log', '[{}] 获取到正确IP {}'.format(datetime.datetime.now(), ipv4)])
                    connect_flag = True
            if connect_flag:
                break
            else:
                self.log_queue.put(['at_log', '[{}] 暂未获取到正确IP，等待2S继续检测'.format(datetime.datetime.now())])
                time.sleep(3)  # 如果网络异常，等待3S继续
                continue
        else:
            self.logger.info(os.popen('ipconfig').read())
            self.log_queue.put(['all', '[{}] runtimes:{} IP异常'.format(datetime.datetime.now(), runtimes)])
            return False

    def check_outnet_ip(self, runtimes):
        for _ in range(20):  # 开机后进行20次检查，每次2s
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
                if ipv4 and (ipv4.startswith('10') or ipv4.startswith('100')):
                    self.log_queue.put(['at_log', '[{}] 获取到外网IP {}'.format(datetime.datetime.now(), ipv4)])
                    connect_flag = True
            if connect_flag:
                break
            else:
                self.log_queue.put(['at_log', '[{}] 暂未获取到正确IP，等待2S继续检测'.format(datetime.datetime.now())])
                time.sleep(3)  # 如果网络异常，等待3S继续
                continue
        else:
            self.logger.info(os.popen('ipconfig').read())
            self.log_queue.put(['all', '[{}] runtimes:{} IP异常'.format(datetime.datetime.now(), runtimes)])
            pause()
            return False

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

    def ping(self, ping_url, ping_times, ping_4_6, ping_size, runtimes):
        ping = subprocess.Popen(['ping', '-4' if ping_4_6 == '-4' else '-6', '-l', str(ping_size), '-n', str(ping_times), ping_url], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        ping_normal_list = []
        ping_abnormal_list = []
        while True:
            time.sleep(0.1)
            line = ping.stdout.readline().decode('GBK')
            if line != '' and line != '\r\n':
                self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), repr(line))])
                # 连续10次没有正常返回值判定为False
                if ping_4_6 == '-4':
                    ping_status = re.findall(r'来自 (.*?) 的回复: 字节=(\d+) 时间[<|=](\d+)ms TTL=(\d+)', line)
                else:
                    ping_status = re.findall(r'来自 (.*?) 的回复: 时间[<|=](\d+)ms', line)
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

    def adb_close_netcard(self, runtimes):
        """
        禁用rgmii/rtl8125网卡
        """
        self.log_queue.put(['at_log', '[{}] 开始进行down模块内部网卡'.format(datetime.datetime.now())])
        s = subprocess.Popen("powershell adb shell", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.PIPE)
        s.stdin.write(b'ifconfig\r\n')
        s.stdin.write(b'exit\r\n')
        s.stdin.close()
        value = s.stdout.read().decode('GBK', 'ignore')
        self.log_queue.put(['at_log', '[{}] 执行ifconfig查询: {}'.format(datetime.datetime.now(), value)])
        if 'eth0' in value:
            self.log_queue.put(['at_log', '[{}] 已检测到模块内部网卡'.format(datetime.datetime.now())])
            self.log_queue.put(['at_log', '[{}] 使用ifconfig eth0 down 禁用网卡'.format(datetime.datetime.now())])
            s = subprocess.Popen("powershell adb shell", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.PIPE)
            s.stdin.write(b'ethtool -r eth0\r\n')
            s.stdin.write(b'exit\r\n')
            s.stdin.close()
            down_value = s.stdout.read().decode('GBK', 'ignore')
            self.log_queue.put(['at_log', '[{}] 执行ifconfig eth0 down 返回: {}'.format(datetime.datetime.now(), down_value)])
            self.log_queue.put(['at_log', '[{}] 成功禁用网卡'.format(datetime.datetime.now())])
            self.log_queue.put(['at_log', '[{}] 等待30s自动启用网卡'.format(datetime.datetime.now())])
        else:
            self.log_queue.put(['at_log', '[{}] 当前未检测到模块内部网卡,请检测RGMII/RTL8125连接设置'.format(datetime.datetime.now())])
            pause('请手动验证当前rgmii/rtl8125是否正常')

    def adb_onoff_consensus(self, runtimes):
        """
        开关自协商
        """
        s = subprocess.Popen("powershell adb shell", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.PIPE)
        s.stdin.write(b'ethtool -s eth0 autoneg off speed 100\r\n')
        s.stdin.write(b'exit\r\n')
        s.stdin.close()
        value = s.stdout.read().decode('GBK', 'ignore')
        self.log_queue.put(['at_log', '[{}] 执行ethtool -s eth0 autoneg off speed 100 返回: {}'.format(datetime.datetime.now(), value)])
        time.sleep(2)
        s = subprocess.Popen("powershell adb shell", stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.PIPE)
        s.stdin.write(b'ethtool -s eth0 autoneg on\r\n')
        s.stdin.write(b'exit\r\n')
        s.stdin.close()
        value = s.stdout.read().decode('GBK', 'ignore')
        self.log_queue.put(
            ['at_log', '[{}] 执行ethtool -s eth0 autoneg on 返回: {}'.format(datetime.datetime.now(), value)])

    def modprobe_vlan(self, runtimes):
        """
        加载Vlan模块
        """
        self.log_queue.put(['at_log', '[{}] 执行modprobe 8021q加载Vlan模块:'.format(datetime.datetime.now())])
        vlaue_out = os.popen('modprobe 8021q').read()
        self.log_queue.put(['at_log', '[{}] 执行返回 : {} '.format(datetime.datetime.now(), vlaue_out)])

    def add_threeVlan(self, net_card_name, runtimes):
        """
        新增其它三路拨号网卡名
        """
        self.log_queue.put(['at_log', '[{}] 开始添加3路vlan网卡:'.format(datetime.datetime.now())])
        eth_value1 = os.popen('vconfig add {} 2'.format(net_card_name)).read()
        self.log_queue.put(['at_log', '[{}] 执行添加第二路网卡 : {} '.format(datetime.datetime.now(), eth_value1)])
        eth_value2 = os.popen('vconfig add {} 3'.format(net_card_name)).read()
        self.log_queue.put(['at_log', '[{}] 执行添加第三路网卡 : {} '.format(datetime.datetime.now(), eth_value2)])
        eth_value3 = os.popen('vconfig add {} 4'.format(net_card_name)).read()
        self.log_queue.put(['at_log', '[{}] 执行添加第四路网卡 : {} '.format(datetime.datetime.now(), eth_value3)])

    def set_netcard(self, net_card1, net_card2, net_card3, net_card4, runtimes):
        """
        重新拉起四路网卡
        """
        self.log_queue.put(['at_log', '[{}] 重新拉起四路拨号网卡:'.format(datetime.datetime.now())])
        eth1_down = os.popen('ifconfig {} down'.format(net_card1)).read()
        self.log_queue.put(['at_log', '[{}] 关闭{}网卡返回 : {}'.format(datetime.datetime.now(), net_card1, eth1_down)])
        eth1_up = os.popen('ifconfig {} hw ether 00:0e:c6:67:78:01 up'.format(net_card1)).read()
        self.log_queue.put(['at_log''[{}] 启用网卡: ifconfig {} hw ether 00:0e:c6:67:78:01 up 返回: {}'
                           .format(datetime.datetime.now(), net_card1, eth1_up)])
        eth2_up = os.popen('ifconfig {} hw ether 00:0e:c6:67:78:02 up'.format(net_card2)).read()
        self.log_queue.put(['at_log', '[{}] 启用网卡: {}'.format(datetime.datetime.now(), eth2_up)])
        self.log_queue.put(['at_log', '[{}] 启用网卡: ifconfig {} hw ether 00:0e:c6:67:78:02 up'.
                           format(datetime.datetime.now(), net_card2)])
        eth3_up = os.popen('ifconfig {} up'.format(net_card3)).read()
        self.log_queue.put(['at_log', '[{}] 启用网卡: {}'.format(datetime.datetime.now(), eth3_up)])
        self.log_queue.put(['at_log', '[{}] 启用网卡: ifconfig {} up'.format(datetime.datetime.now(), net_card3)])
        eth4_up = os.popen('ifconfig {} up'.format(net_card4)).read()
        self.log_queue.put(['at_log', '[{}] 启用网卡: {}'.format(datetime.datetime.now(), eth4_up)])
        self.log_queue.put(['at_log', '[{}] 启用网卡: ifconfig {} up'.format(datetime.datetime.now(), net_card4)])

    def check_netcard(self, net_card1, net_card2, net_card3, net_card4, runtimes):
        """
        执行ifconfig查询网卡,并使用udhcpc获取ip
        """
        if_value = os.popen('ifconfig -a').read()
        if net_card1 in if_value and net_card2 in if_value and net_card3 in if_value and net_card4 in if_value:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), if_value)])
            self.log_queue.put(['all', '[{}] runtimes:{} ifconfig -a指令查询四路网卡'.format(datetime.datetime.now(), runtimes)])
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), if_value)])
            self.log_queue.put(
                ['all', '[{}] runtimes:{} ifconfig -a指令未查询到指定网卡'.format(datetime.datetime.now(), runtimes)])
            return False

        self.log_queue.put(['at_log', '[{}] 执行udhcpc 获取ip地址'.format(datetime.datetime.now())])
        cpc_value = os.popen('udhcpc -i {}'.format(net_card1)).read()
        self.log_queue.put(['at_log', '[{}]执行udhcpc -i {}返回: {}'.format(datetime.datetime.now(), net_card1, cpc_value)])
        cpc_value = os.popen('udhcpc -i {}'.format(net_card2)).read()
        self.log_queue.put(['at_log', '[{}]执行udhcpc -i {}返回: {}'.format(datetime.datetime.now(), net_card2, cpc_value)])
        cpc_value = os.popen('udhcpc -i {}'.format(net_card3)).read()
        self.log_queue.put(['at_log', '[{}]执行udhcpc -i {}返回: {}'.format(datetime.datetime.now(), net_card3, cpc_value)])
        cpc_value = os.popen('udhcpc -i {}'.format(net_card4)).read()
        self.log_queue.put(['at_log', '[{}]执行udhcpc -i {}返回: {}'.format(datetime.datetime.now(), net_card4, cpc_value)])

    def check_linux_ip(self, network_card_name, runtimes):
        """
        检测路由模式获取到的ip
        """
        for i in range(30):
            ifconfig_value = os.popen('ifconfig -a').read()
            re_ifconfig = re.findall(r'{}.*\n(.*)'.format(network_card_name), ifconfig_value)[0].strip()
            ip = re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', re_ifconfig)[0]
            self.log_queue.put(['at_log', '[{}] 获取到正确IP {}'.format(datetime.datetime.now(), ip)])
            if ip and '192.168' in ip:
                self.log_queue.put(['at_log', '[{}] 获取到正确的内网IP {}'.format(datetime.datetime.now(), ip)])
                break
            else:
                self.log_queue.put(['at_log', '[{}] 暂未获取到正确的内网IP，等待3S继续检测'.format(datetime.datetime.now())])
                time.sleep(3)  # 如果网络异常，等待3S继续
                continue
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} IP异常'.format(datetime.datetime.now(), runtimes)])
            return False

    def check_linux_outip(self, network_card_name, runtimes):
        """
        检查桥模式获取的外网ip
        """
        for i in range(30):
            ifconfig_value = os.popen('ifconfig -a').read()
            re_ifconfig = re.findall(r'{}.*\n(.*)'.format(network_card_name), ifconfig_value)[0].strip()
            ip = re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', re_ifconfig)[0]
            self.log_queue.put(['at_log', '[{}] 获取到正确IP {}'.format(datetime.datetime.now(), ip)])
            if ip and ('10' in ip or '100' in ip):
                self.log_queue.put(['at_log', '[{}] 获取到正确的外网IP {}'.format(datetime.datetime.now(), ip)])
                break
            else:
                self.log_queue.put(['at_log', '[{}] 暂未获取到正确外网IP，等待3S继续检测'.format(datetime.datetime.now())])
                time.sleep(3)  # 如果网络异常，等待3S继续
                continue
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} IP异常'.format(datetime.datetime.now(), runtimes)])
            return False

    def ping_posix(self, ping_url, ping_times, ping_4_6, ping_size, network_card_name, runtimes):
        delay_time_list = []
        ping_command = ['ping' if ping_4_6 == '-4' else 'ping6', '-S', str(ping_size), '-c', str(ping_times), ping_url]
        if network_card_name:
            ping_command.extend(['-I', network_card_name])
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

        ping_status = re.search(r'(\d+)\s+packets\s+transmitted,\s+(\d+)\s+received.*\s+(\d+\.\d+|\d+)%.*', buffer)
        send_package_number, recv_package_number, lost_package_percentage = ping_status.groups()
        self.log_queue.put(['df', runtimes, 'send_package_number', int(send_package_number)])  # send_package_number
        self.log_queue.put(['df', runtimes, 'recv_package_number', int(recv_package_number)])  # recv_package_number
        self.log_queue.put(['df', runtimes, 'lost_package_number', int(int(send_package_number) - int(recv_package_number))])  # lost_package_number
        self.log_queue.put(['df', runtimes, 'lost_package_percentage', lost_package_percentage])
        if len(delay_time_list) == 0:
            delay_time_list.append(999)
        self.log_queue.put(['df', runtimes, 'shortest_time', min(delay_time_list)])  # shortest_time
        self.log_queue.put(['df', runtimes, 'longest_time', max(delay_time_list)])  # longest_time
        self.log_queue.put(['df', runtimes, 'average_time', round(sum(delay_time_list) / len(delay_time_list), 2)])
