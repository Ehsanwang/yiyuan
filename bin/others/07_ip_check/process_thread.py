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
                    pause()
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
                    pause()
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
        start_time = time.time()
        random_off_time = round(random.uniform(15, 35), 2)
        upgrade = subprocess.Popen('QFirehose -f {}'.format(packagename), stdout=PIPE, stderr=STDOUT, shell=True)
        self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_starttimestamp' if mode == 'forward' else 'qfirehose_upgrade_b_a_starttimestamp', time.time()])
        while True:
            time.sleep(0.001)
            upgrade_content = upgrade.stdout.readline().decode("UTF-8")
            if upgrade_content != '':
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
            if vbat and time.time() - start_time > random_off_time:
                self.log_queue.put(['at_log', '[{}] 升级过程随机断电'.format(datetime.datetime.now())])
                return True
            if time.time() - start_time > 120:
                self.log_queue.put(['df', runtimes, 'upgrade_fail_times', 1])
                self.log_queue.put(['all', '[{}] runtimes:{} 120S内升级失败'.format(datetime.datetime.now(), runtimes)])
                return False

    def check_qfirehose_status(self, packagename, mode, runtimes):
        upgrade = subprocess.Popen('QFirehose -f {}'.format(packagename), stdout=PIPE, stderr=STDOUT, shell=True)
        self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_starttimestamp' if mode == 'forward' else 'qfirehose_upgrade_b_a_starttimestamp', time.time()])
        start_time = time.time()
        while True:
            time.sleep(0.001)
            upgrade_content = upgrade.stdout.readline().decode("UTF-8")
            if upgrade_content != '':
                self.log_queue.put(['qfirehose_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(upgrade_content).replace("'", ''))])
                if 'Upgrade module successfully' in upgrade_content:
                    self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_endtimestamp' if mode == 'forward' else 'qfirehose_upgrade_b_a_endtimestamp', time.time()])
                    self.log_queue.put(['at_log', '[{}] 升级成功'.format(datetime.datetime.now())])
                    upgrade.terminate()
                    upgrade.wait()
                    return True
            if time.time() - start_time > 120:
                self.log_queue.put(['df', runtimes, 'upgrade_fail_times', 1])
                self.log_queue.put(['all', '[{}] runtimes:{} 120S内升级失败'.format(datetime.datetime.now(), runtimes)])
                return False
