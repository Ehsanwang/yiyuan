# -*- encoding=utf-8 -*-
import re
import subprocess
import serial.tools.list_ports
import datetime
import time
from subprocess import PIPE, STDOUT
import random
import logging
from functions import pause
import glob
import xml.etree.ElementTree as ET
import os
import string
import filecmp
from ftplib import all_errors
import socket
from threading import Thread
from ftplib import FTP
from functools import partial
import requests
from requests_toolbelt import MultipartEncoder  # 用于流式上传文件
import threading
# tts


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
        self.rts_flag = False   # QFirehose升级所用变量，True代表需要拉低rts升级，False代表不需要
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
            self.logger.info('serial_tools_port_list')
            port_name_list = []
            ports = serial.tools.list_ports.comports()
            for port, _, _ in sorted(ports):
                port_name_list.append(port)
            self.logger.info('serial_tools_port_list:{}'.format(port_name_list))
            return port_name_list
        else:
            self.logger.info("glob.glob('/dev/ttyUSB*')")
            ports = glob.glob('/dev/ttyUSB*')
            self.logger.info(ports)
            return ports

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
        self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), '已更改autosuspend 、level、wakeup默认值')])

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

    def rts_check(self, runtimes):
        """
        检查QFirehose升级是否需要拉低RTS
        :return:
        """
        for i in range(5):
            lsusb = os.popen('lsusb').read()
            self.logger.info(lsusb)
            if '9008' in lsusb:     # 如果处于紧急下载模式
                self.log_queue.put(['at_log', '[{}] 模块已进入紧急下载模式，需要拉低powerkey'.format(datetime.datetime.now())])
                self.rts_flag = True
                return
            elif '2c7c' in lsusb:   # 如果处于正常模式
                self.log_queue.put(['at_log', '[{}] 模块未进入紧急下载模式，无需拉低powerkey'.format(datetime.datetime.now())])
                self.rts_flag = False
                time.sleep(15)
                return
            time.sleep(5)
        else:
            self.log_queue.put(['all', "[{}] runtimes:{} 开机lsusb查询未识别到模块".format(datetime.datetime.now(), runtimes)])
            return False

    def get_rts_state(self, runtimes):
        """
        获取rts_flag的值
        :return:
        """
        if not self.rts_flag:   # 如果为False，代表无需拉低rts
            return False
        else:
            return True   # 为True代表需要拉低升级

    def qfirehose_upgrade(self, packagename, vbat, mode, runtimes):
        is_factory = True if 'factory' in packagename else False    # 是否是工厂包升级，是的话指令需要加-e
        val = os.popen('ps -ef | grep QFirehose').read()
        if 'QFirehose -f {}'.format(packagename) in val:
            self.log_queue.put(['at_log', '[{}] 升级前存在残留升级进程:\n{}'.format(datetime.datetime.now(), val)])
            try:
                kill_qf = subprocess.run('killall QFirehose', shell=True, timeout=10)
                if kill_qf.returncode == 0 or kill_qf.returncode == 1:
                    self.log_queue.put(['at_log', '[{}] 已关闭升级进程'.format(datetime.datetime.now())])
                    time.sleep(1)
                    val_after = os.popen('ps -ef | grep QFirehose').read()
                    self.log_queue.put(['at_log', '[{}] 关闭升级进程后升级进程情况\n:{}'.format(datetime.datetime.now(), val_after)])
            except subprocess.TimeoutExpired:
                self.log_queue.put(['all', '[{}] 关闭升级进程失败'.format(datetime.datetime.now())])
        start_time = time.time()
        random_off_time = round(random.uniform(1, 60))
        if vbat:
            self.log_queue.put(['at_log', '[{}] 升级进行{}S后断电'.format(datetime.datetime.now(), random_off_time)])
        upgrade = subprocess.Popen('QFirehose -f {} {}'.format(packagename, '-e' if is_factory else ''), stdout=PIPE, stderr=STDOUT, shell=True)
        self.log_queue.put(['qfirehose_log', '[{} Recv] QFirehose -f {} {}'.format(datetime.datetime.now(), packagename, '-e' if is_factory else '')])
        os.set_blocking(upgrade.stdout.fileno(), False)
        if is_factory:
            self.log_queue.put(['df', runtimes, 'qfirehose_factory_upgrade_a_b_starttimestamp' if mode == 'forward' else 'qfirehose_factory_upgrade_b_a_starttimestamp', time.time()])
        else:
            self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_starttimestamp' if mode == 'forward' else 'qfirehose_upgrade_b_a_starttimestamp', time.time()])
        while True:
            time.sleep(0.001)
            upgrade_content = upgrade.stdout.readline().decode('utf-8')
            if upgrade_content != '':
                if vbat and time.time() - start_time > random_off_time:
                    self.log_queue.put(['at_log', '[{}] 升级过程断电'.format(datetime.datetime.now())])
                    return True
                if upgrade_content == '.':
                    continue
                self.log_queue.put(['qfirehose_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(upgrade_content).replace("'", ''))])
                if 'Upgrade module successfully' in upgrade_content:
                    if is_factory:
                        self.log_queue.put(['df', runtimes, 'qfirehose_factory_upgrade_a_b_endtimestamp' if mode == 'forward' else 'qfirehose_factory_upgrade_b_a_endtimestamp', time.time()])
                    else:
                        self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_endtimestamp' if mode == 'forward' else 'qfirehose_upgrade_b_a_endtimestamp', time.time()])
                    self.log_queue.put(['at_log', '[{}] 升级成功'.format(datetime.datetime.now())])
                    upgrade.terminate()
                    upgrade.wait()
                    return True
                if 'fail to access {}'.format(packagename) in upgrade_content:
                    self.log_queue.put(['all', "[{}] runtimes:{} 请检查版本包路径是否填写正确".format(datetime.datetime.now(), runtimes)])
                    pause()
                if 'Upgrade module failed' in upgrade_content:
                    if is_factory:
                        self.log_queue.put(['df', runtimes, 'factory_upgrade_fail_times', 1])
                    else:
                        self.log_queue.put(['df', runtimes, 'upgrade_fail_times', 1])
                    self.log_queue.put(['all', '[{}] runtimes:{} 升级失败'.format(datetime.datetime.now(), runtimes)])
                    upgrade.terminate()
                    upgrade.wait()
                    return False
            if vbat and time.time() - start_time > random_off_time:
                self.log_queue.put(['at_log', '[{}] 升级过程随机断电'.format(datetime.datetime.now())])
                return True
            if time.time() - start_time > 120:
                if is_factory:
                    self.log_queue.put(['df', runtimes, 'factory_upgrade_fail_times', 1])
                else:
                    self.log_queue.put(['df', runtimes, 'upgrade_fail_times', 1])
                upgrade_val = os.popen('ps -ef | grep QFirehose').read()
                ls_val = os.popen('ls /dev/ttyUSB*').read()
                lsusb_val = os.popen('lsusb |grep 9008').read()
                self.log_queue.put(['at_log', '[{}] 120S内升级失败后进程情况:{}'.format(datetime.datetime.now(), upgrade_val)])
                self.log_queue.put(['at_log', '[{}] 120S内升级失败后ls /dev/ttyUSB*查询端口枚举情况:{}'.format(datetime.datetime.now(), ls_val)])
                self.log_queue.put(['at_log', '[{}] 120S内升级失败后lsusb |grep 9008查询是否存在紧急下载口:{}'.format(datetime.datetime.now(), lsusb_val)])
                self.log_queue.put(['all', '[{}] runtimes:{} 120S内升级失败'.format(datetime.datetime.now(), runtimes)])
                upgrade.terminate()
                upgrade.wait()
                return False

    def get_interface_name(self, runtimes):
        """
        获取连接的名称
        :param runtimes: 当前运行次数
        :return: 当前连接名称
        """
        for i in range(10):
            time.sleep(5)
            mobile_broadband_info = os.popen('netsh mbn show interface').read()
            mobile_broadband_num = ''.join(re.findall(r'系统上有 (\d+) 个接口', mobile_broadband_info))  # 手机宽带数量
            if mobile_broadband_num and int(mobile_broadband_num) > 1:
                self.log_queue.put(['all', "[{}] runtimes: {} 系统上移动宽带有{}个，多于一个".format(datetime.datetime.now(), runtimes, mobile_broadband_num)])
                pause()
            mobile_broadband_name = ''.join(re.findall(r'\s+名称\s+:\s(.*)', mobile_broadband_info))
            if mobile_broadband_name != '':
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

    def mbim_connect_check(self, runtimes):
        """
        检查Linux下mbim拨号的拨号状态：
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
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen(self.ping_cmd).read())])
            self.log_queue.put(['all', '[{}] runtimes:{} 请求{}次{}均异常，MBIM拨号异常'.format(datetime.datetime.now(), runtimes, num, url)])
            self.log_queue.put(['df', runtimes, 'dial_fail_times', 1])  # ip_error_times
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
                pause()
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
                    except KeyError:
                        time.sleep(1)
                        pass
                else:
                    self.log_queue.put(['all', "[{}] runtimes: {} 连续10次生成拨号配置文件失败".format(datetime.datetime.now(), runtimes)])
                    pause()

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
            time.sleep(5)
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

    def request_baidu(self, runtimes):
        # requests库获取网页并判断
        url = "http://www.baidu.com"
        timeout = 10
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        for num in range(1, 11):
            try:
                self.log_queue.put(['at_log', '[{}] 第 {} 次打开 {}'.format(datetime.datetime.now(), num, url)])
                request_status = requests.get(url, timeout=timeout, headers=headers)
                if request_status.status_code != 200:
                    self.log_queue.put(['all', '[{}] runtimes:{} 请求{}时状态码异常: {}'.format(datetime.datetime.now(), runtimes, url, request_status.status_code)])
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{} 请求{}时异常：{}'.format(datetime.datetime.now(), runtimes, url, e)])
            time.sleep(1)

    def fusion_protocol_test(self, server_config, dial_mode, runtimes):
        """

        :param server_config:
        :param dial_mode:
        :param runtimes:
        :return:
        """
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
        tcp = self.socket_tcp(server_config, file_path, recv_file_path, runtimes)
        if tcp is False:
            self.log_queue.put(['df', runtimes, 'tcp_fail_times', 1])

        # UDP
        self.log_queue.put(['at_log', '[{}] -------------------进行UDP测试-------------------'.format(datetime.datetime.now())])
        udp = self.socket_udp(server_config, udp_file_path, udp_recv_file_path, runtimes)
        if udp is False:
            self.log_queue.put(['df', runtimes, 'udp_fail_times', 1])

        # FTP
        self.log_queue.put(['at_log', '[{}] -------------------进行FTP测试-------------------'.format(datetime.datetime.now())])
        ftp_path = server_config['ftp_path']
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
