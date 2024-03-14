# -*- encoding=utf-8 -*-
import asyncio
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
from functions import pause
import glob
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
                    time.sleep(0.1)  # 降低检测频率，减少CPU占用
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
            self.logger.info('serial_tools_port_list')
            port_name_list = []
            ports = serial.tools.list_ports.comports()
            for port, _, _ in sorted(ports):
                port_name_list.append(port)
            self.logger.info('serial_tools_port_list:{}'.format(port_name_list))
            return port_name_list
        else:
            return glob.glob('/dev/ttyUSB*')

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

    def check_adb_devices_connect(self, runtimes):
        """
        检查adb devices是否有设备连接
        :param runtimes: 当前脚本的运行次数
        :return: True:adb devices已经发现设备
        """
        adb_check_start_time = time.time()
        while True:
            # 发送adb devices
            adb_value = repr(os.popen('adb devices').read())
            self.logger.info(adb_value)
            devices_online = ''.join(re.findall(r'\\n(.*)\\tdevice', adb_value))
            devices_offline = ''.join(re.findall(r'\\n(.*)\\toffline', adb_value))
            if devices_online != '' or devices_offline != '':  # 如果检测到设备
                self.log_queue.put(['at_log', '[{}] 已检测到adb设备'.format(datetime.datetime.now())])  # 写入log
                return True
            elif time.time() - adb_check_start_time > 100:  # 如果超时
                self.log_queue.put(['all', '[{}] runtimes:{} adb未加载，请确认是否发送AT+QCFG="USBCFG",0x2C7C,0x0800,1,1,1,1,1,1'.format(datetime.datetime.now(), runtimes)])
                pause()
            else:  # 既没有检测到设备，也没有超时，等1S
                time.sleep(1)

    def adb_push_package(self, package_path, ufs_path, runtimes):
        """
        用adb将版本升级包push上去
        :param package_path: 版本包在PC上的存放路径
        :param ufs_path: UFS路径
        :param runtimes: 当前脚本的运行次数
        :return: True:adb push成功；False：adb push失败
        """
        self.log_queue.put(['at_log', '[{}] adb开始push版本包到模块'.format(datetime.datetime.now())])  # 写入log
        adb_error_list = ['offline', 'no devices', 'failed to read stat response', 'fail', 'reset', 'error', 'closed']
        adb_push_start_timestamp = time.time()
        command = 'adb push {} {}'.format(package_path, ufs_path)
        cmd = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while True:
            time.sleep(0.01)
            if time.time() - adb_push_start_timestamp > 120:  # adb 超时判断
                self.log_queue.put(['all', '[{}] runtimes:{} adb push超时'.format(datetime.datetime.now(), runtimes)])
                cmd.terminate()
                return False
            line = cmd.stdout.readline().decode('GBK')
            if line != '':
                self.logger.info(repr(line))
                err_list = [i for i in adb_error_list if i in line]  # 对每一句和adb_err_list进行匹配
                if err_list:  # 如果出现了异常
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), repr(line))])  # 写入log
                    self.log_queue.put(['all', '[{}] runtimes:{} adb push 异常'.format(datetime.datetime.now(), runtimes)])
                    cmd.terminate()
                    return False
                if '1 file pushed' in line:  # 如果推送成功
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), repr(line))])  # 写入log
                    cmd.terminate()
                    return True

    def linux_enter_low_power(self, runtimes):
        """
        Linux需要休眠首先dmesg查询USB节点，然后设置节点的autosuspend值为1，level值为auto，wakeup值为enabled
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        dmesg_data = os.popen('dmesg').read()
        dmesg_data_regex = re.findall(r'usb\s(\d+-\d+):.*Quectel.*', dmesg_data)
        if dmesg_data_regex:
            node_list = list(set(dmesg_data_regex))
            for node in node_list:
                node_path = os.path.join('/sys/bus/usb/devices/', node, 'power')
                autosuspend = 'cd {} && echo 1 > {}'.format(node_path, 'autosuspend')
                level = 'cd {} && echo auto > {}'.format(node_path, 'level')
                wakeup = 'cd {} && echo enabled > {}'.format(node_path, 'wakeup')
                commands = [autosuspend, level, wakeup]
                for command in commands:
                    try:
                        self.logger.info(command)
                        s = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
                        out, error = s.communicate()
                        self.logger.info([out, error])
                    except Exception as e:
                        self.logger.info(e)
        self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), '已更改autosuspend 、levle、wakeup默认值')])

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

    def qfirehose_upgrade(self, packagename, vbat, mode, runtimes):
        lsusb_content_cache = ''
        for i in range(3):
            lsusb = subprocess.Popen('lsusb', stdout=PIPE, stderr=STDOUT, shell=True)
            ls_start_time = time.time()
            self.log_queue.put(['at_log', '[{} Recv] lsusb:\n'.format(datetime.datetime.now())])
            while True:
                time.sleep(0.001)
                lsusb_content = lsusb.stdout.readline().decode("UTF-8")
                if lsusb_content != '':
                    self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(lsusb_content).replace("'", ''))])
                    lsusb_content_cache += lsusb_content
                if time.time() - ls_start_time > 2:
                    break
            if '9008' in lsusb_content_cache:
                self.log_queue.put(['at_log', '[{}] 模块已转QDL口，直接升级'.format(datetime.datetime.now())])
                break
            if '2c7c' in lsusb_content_cache:
                self.log_queue.put(['at_log', '[{}] 模块未转QDL口，等待10S升级'.format(datetime.datetime.now())])
                time.sleep(10)
                break
            time.sleep(8)
        else:
            self.log_queue.put(['at_log', '[{}] lsusb未识别到模块'.format(datetime.datetime.now())])
        start_time = time.time()
        random_off_time = round(random.uniform(0, 60))
        if vbat:
            self.log_queue.put(['at_log', '[{}] 升级进行{}S后断电'.format(datetime.datetime.now(), random_off_time)])
        upgrade = subprocess.Popen('QFirehose -f {}'.format(packagename), stdout=PIPE, stderr=STDOUT, shell=True)
        os.set_blocking(upgrade.stdout.fileno(), False)
        self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_starttimestamp' if mode == 'forward' else 'qfirehose_upgrade_b_a_starttimestamp', time.time()])
        while True:
            time.sleep(0.001)
            upgrade_content = upgrade.stdout.readline().decode('utf-8')
            if upgrade_content != '':
                if vbat and time.time() - start_time > random_off_time:
                    self.log_queue.put(['at_log', '[{}] 升级过程断电'.format(datetime.datetime.now())])
                    upgrade.terminate()
                    upgrade.wait()
                    return True
                if upgrade_content == '.':
                    continue
                self.log_queue.put(['qfirehose_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(upgrade_content).replace("'", ''))])
                if 'Upgrade module successfully' in upgrade_content:
                    self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_endtimestamp' if mode == 'forward' else 'qfirehose_upgrade_b_a_endtimestamp', time.time()])
                    self.log_queue.put(['at_log', '[{}] 升级成功'.format(datetime.datetime.now())])
                    upgrade.terminate()
                    upgrade.wait()
                    return True
                if 'fail to access {}'.format(packagename) in upgrade_content:
                    self.log_queue.put(['all', "[{}] runtimes:{} 请检查版本包路径是否填写正确".format(datetime.datetime.now(), runtimes)])
                    pause()
                if 'Upgrade module failed' in upgrade_content:
                    self.log_queue.put(['all', '[{}] 升级失败'.format(datetime.datetime.now())])
                    upgrade.terminate()
                    upgrade.wait()
                    return False
            if vbat and time.time() - start_time > random_off_time:
                self.log_queue.put(['at_log', '[{}] 升级过程随机断电'.format(datetime.datetime.now())])
                return True
            if time.time() - start_time > 120:
                self.log_queue.put(['df', runtimes, 'upgrade_fail_times', 1])
                self.log_queue.put(['all', '[{}] runtimes:{} 120S内升级失败'.format(datetime.datetime.now(), runtimes)])
                upgrade.terminate()
                upgrade.wait()
                return False

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
