# -*- encoding=utf-8 -*-
import re
import subprocess
import serial.tools.list_ports
from threading import Thread
import datetime
import time
import os
import logging
from functions import pause
import glob


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
        self.time = 0.0

    def run(self):
        while True:
            (func, *param), evt = self.process_queue.get()  # ['check_usb_driver', 0] <threading.Event object at 0x...>
            self.logger.info('{}->{}->{}'.format(func, param, evt))
            runtimes = param[-1]
            if func in self._methods_list:
                process_status = getattr(self.__class__, '{}'.format(func))(self, *param)
                if process_status is not False:
                    if type(process_status) == str:
                        self.main_queue.put(process_status)
                    else:
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
            self.logger.info('get_port_list')
            port_name_list = []
            ports = serial.tools.list_ports.comports()
            for port, _, _ in sorted(ports):
                port_name_list.append(port)
            self.logger.info(port_name_list)
            return port_name_list
        else:
            return glob.glob('/dev/ttyUSB*')

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

    def adb_push_rw_file(self, rwfile_path, rwfile, flag, rwfile_index, runtimes):
        """
        adb push文件到UFS分区
        :param rwfile_path:
        :param rwfile:
        :param runtimes:
        :return:
        """
        split_suffix = os.path.splitext(rwfile_path + rwfile)[1]
        path = os.path.join(rwfile_path, rwfile)
        command_adbpush_rwfile = 'adb push {} /usrdata/rwfile/{}{}'.format(path, rwfile_index, split_suffix)
        if flag is True:
            self.log_queue.put(['at_log', '[{}] adb开始push文件到模块：{}'.format(datetime.datetime.now(), command_adbpush_rwfile)])
            cmd = subprocess.Popen(command_adbpush_rwfile, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            time.sleep(2)
            while True:
                time.sleep(0.01)
                os.popen('adb shell mount -o remount,rw /')
                data = cmd.stdout.readline().decode('GBK')
                if data != '':
                    self.logger.info(repr(data))
                    if re.search('device offline', str(data)):  # adb device offline
                        os.popen('adb kill-server')
                        self.log_queue.put(['at_log', '[{}] adb kill-server'.format(datetime.datetime.now())])
                        time.sleep(2)
                        os.popen('adb start-server')
                        self.log_queue.put(['at_log', '[{}] adb start-server'.format(datetime.datetime.now())])
                        time.sleep(10)
                        self.check_adb_devices_connect(runtimes)
                        cmd.terminate()
                        return True
                    if re.search('remote Read-only file system', str(data)):  # 文件系统只读
                        self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), repr(data))])  # 写入log
                        self.log_queue.put(['all', '[{}] runtimes:{} adb push 异常 remote Read-only file system'.format(datetime.datetime.now(), runtimes)])
                        cmd.terminate()
                        continue
                    if '1 file pushed' in data:  # 如果推送成功
                        self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), repr(data))])  # 写入log
                        time.sleep(0.05)
                        cmd.terminate()
                        return True
                    if 'closed' in data:
                        os.popen('adb shell mount -o remount,rw /')
                        cmd.terminate()
                        continue
                    if re.search('No space left on device', str(data)):
                        self.log_queue.put(['at_log', '[{}]写入成功,分区已满'.format(datetime.datetime.now())])
                        self.log_queue.put(['df', runtimes, 'cp_ufs_full_time', time.time() - self.time])  # u写满ufs分区时间
                        cmd.terminate()
                        return str(data)
                    if re.search('RESET', str(data).upper()):
                        self.log_queue.put(['at_log', '[{}]runtimes:{}系统发生重启.'.format(datetime.datetime.now(), runtimes)])
                        time.sleep(20)
        else:
            os.popen('adb shell mount -o remount,rw /')
            self.log_queue.put(['at_log', '[{}] adb开始push文件到模块：{}'.format(datetime.datetime.now(), command_adbpush_rwfile)])
            subprocess.Popen(command_adbpush_rwfile, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
            time.sleep(2)
            return True

    def delete_ufs_file(self, cmd, runtimes):
        # check待删除文件
        delete_start_time = time.time()
        delete_timeout = 60
        while True:
            time.sleep(0.001)
            out = os.popen('adb shell find /usrdata/rwfile -name "*.txt"')
            out_read = out.read()
            if re.search('/usrdata/rwfile', str(out_read)):
                # 删除文件
                self.log_queue.put(['at_log', '[{}]删除UFS分区已写入的文件'.format(datetime.datetime.now())])
                self.log_queue.put(['at_log', '[{}]{}'.format(datetime.datetime.now(), cmd)])
                os.popen(cmd)
                time.sleep(10)  # ufs写满删除文件需要较长时间
                continue
            elif time.time() - delete_start_time > delete_timeout:
                self.log_queue.put(['all', '[{}]文件删除超时{}s'.format(datetime.datetime.now(), delete_timeout)])
                self.log_queue.put(['df', runtimes, 'rw_delete_fail_times', 1])  # 删除文件失败次数统计
                return False
            else:
                delete_file_time = time.time() - delete_start_time
                self.log_queue.put(['at_log', '[{}]删除UFS文件成功'.format(datetime.datetime.now())])
                self.log_queue.put(['df', runtimes, 'rw_delete_time', delete_file_time])  # 删除文件时间
                return True

    def kill_adb(self, runtimes):
        """
        kill adb 进程
        :param runtimes:
        :return:
        """
        self.log_queue.put(['at_log', '[{}]kill adb 进程 taskkill /f /t /im adb.exe'.format(datetime.datetime.now())])
        kill = os.popen('taskkill /f /t /im adb.exe')
        kill_read = kill.read()
        if re.search('PID', str(kill_read)):
            self.log_queue.put(['at_log', '[{}]kill adb 成功'.format(datetime.datetime.now())])
            return True
        else:
            self.log_queue.put(['at_log', '[{}]kill adb 失败'.format(datetime.datetime.now())])
            self.log_queue.put(['df', runtimes, 'kill_adb_fail_times', 1])  # kill adb失败次数
            return False
