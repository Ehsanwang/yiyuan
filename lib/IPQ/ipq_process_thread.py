# -*- encoding=utf-8 -*-
import datetime
import random
import time
import serial
import logging
from functions import pause
import re
from threading import Thread


class IPQProcessThread(Thread):

    def __init__(self, ipq_port, ipq_queue, log_queue, main_queue):
        super().__init__()
        self.ipq_queue = ipq_queue
        self.log_queue = log_queue
        self.main_queue = main_queue
        self.ipq_port = ipq_port
        self.rts_flag = False  # 决定QFirehose是否需要拉低powerkey进行升级
        self.port_flag = True
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        try:
            self.ipq_port = serial.Serial(self.ipq_port, baudrate=115200, timeout=0)
        except serial.serialutil.SerialException:
            pause("IPQ UART端口被占用或设置错误，请关闭脚本并重新运行！")
        self.logger = logging.getLogger(__name__)

    def run(self):
        while True:
            time.sleep(0.001)  # 减小CPU开销
            # 检查外部是否有信息传入
            # 1. 有信息传入，则运行对应函数
            (func, *param), evt = ['0', '0'] if self.ipq_queue.empty() else self.ipq_queue.get()  # 如果ipq_queue有内容读，无内容[0,0]
            self.logger.info('{}->{}->{}'.format(func, param, evt)) if func != '0' else ''
            if func in self._methods_list:
                runtimes = param[-1]  # 注意最后一个元素必须是runtimes
                ipq_status = getattr(self.__class__, '{}'.format(func))(self, *param)
                if ipq_status is not False:
                    self.main_queue.put(True)
                else:
                    self.log_queue.put(['write_result_log', runtimes])
                    self.main_queue.put(False)
                evt.set()
            # 2. 没有信息传入则读一行
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['ipq_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])

    def ipq_usb_pcie_check(self, command, checked_info, debug, runtimes):
        """
        USB切换到PCIE后检测是否切换成功，发送一个命令，并且检查返回值中是否包含需要检查的内容
        :param command: 需要发送的命令，例如lspci/ls /dev/mhi*
        :param checked_info: *列表类型! 需要检查的信息，例如ls /dev/mhi*检查['/dev/mhi_BHI', '/dev/mhi_DUN', '/dev/mhi_QMI0', '/dev/mhi_DIAG', '/dev/mhi_LOOPBACK']
        :param debug: 设置脚本遇到异常是停止还是继续运行False：继续运行；True：停止脚本
        :param runtimes: 当前的运行次数
        :return: True：发送命令后，返回值包含需要检查的信息；发送命令后，返回值不包含需要检查的信息
        """
        return_value_cache = ''
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('\n'.encode('utf-8'))
        # 写入命令
        self.ipq_port.write('{}\r\n'.format(command).encode('utf-8'))
        # 读取1S内返回的内容
        recv_start_timestamp = time.time()
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['ipq_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                return_value_cache += return_value
            if time.time() - recv_start_timestamp > 1:
                break
        # 检查命令
        for info in checked_info:
            if info not in return_value_cache:
                self.log_queue.put(['all', '[{}] runtimes:{} USB切换PCIE失败，发送{}后返回值中未包含检测内容{}'.format(datetime.datetime.now(), runtimes, command, checked_info)])
                self.log_queue.put(['df', runtimes, 'ipq_pcie_check_fail_times', 1])
                if debug:
                    pause()
                else:
                    return False
        else:
            self.log_queue.put(['at_log', '[{}] USB切换PCIE后，{}命令检测成功，返回值包含{}'.format(datetime.datetime.now(), command, checked_info)])
            return True

    def ipq_pcie_usb_check(self, command, checked_info, debug, runtimes):
        """
        PCIE切换到USB后检测是否切换成功，发送一个命令，并且检查返回值中是否不包含需要检查的内容
        :param command: 需要发送的命令，例如lspci/ls /dev/mhi*
        :param checked_info: *列表类型! 需要检查的信息，例如ls /dev/mhi*检查['/dev/mhi_BHI', '/dev/mhi_DUN', '/dev/mhi_QMI0', '/dev/mhi_DIAG', '/dev/mhi_LOOPBACK']
        :param debug: 设置脚本遇到异常是停止还是继续运行False：继续运行；True：停止脚本
        :param runtimes: 当前的运行次数
        :return: True：发送命令后，返回值包含需要检查的信息；发送命令后，返回值不包含需要检查的信息
        """
        return_value_cache = ''
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('\n'.encode('utf-8'))
        # 写入命令
        self.ipq_port.write('{}\r\n'.format(command).encode('utf-8'))
        # 读取1S内返回的内容
        recv_start_timestamp = time.time()
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['ipq_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                return_value_cache += return_value
            if time.time() - recv_start_timestamp > 1:
                break
        # 检查命令
        for info in checked_info:
            if info in return_value_cache:
                self.log_queue.put(['all', '[{}] runtimes:{} PCIE切换USB失败，发送{}后返回值中包含检测内容{}'.format(datetime.datetime.now(), runtimes, command, checked_info)])
                self.log_queue.put(['df', runtimes, 'ipq_pcie_check_fail_times', 1])
                if debug:
                    pause()
                else:
                    return False
        else:
            self.log_queue.put(['at_log', '[{}] PCIE切换USB后，{}命令检测成功，返回值不包含{}'.format(datetime.datetime.now(), command, checked_info)])
            return True

    def get_message(self, message, debug, runtimes):
        """
        获取信息，如果获取到信息，发送'\r\n'，如果超时，返回False
        :param message: 需要检查的信息
        :param debug: 设置脚本遇到异常是停止还是继续运行False：继续运行；True：停止脚本
        :param runtimes: 当前脚本的运行次数
        :return: True：获取到了需要检查的信息；False：指定超时时间内没有获取到需要检查的信息
        """
        get_message_start_timestamp = time.time()
        get_message_timeout = 120
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['ipq_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                if message in return_value:
                    self.log_queue.put(['at_log', '[{}] 已检测到{}'.format(datetime.datetime.now(), message)])
                    self.ipq_port.write('\n'.encode('utf-8'))
                    self.ipq_port.write('\n'.encode('utf-8'))
                    return True
            if time.time() - get_message_start_timestamp > get_message_timeout:
                self.log_queue.put(['all', '[{}] runtimes:{} {}内未检测到{}'.format(datetime.datetime.now(), runtimes, get_message_timeout, message)])
                self.log_queue.put(['df', runtimes, 'ipq_start_fail_times', 1])
                if debug:
                    pause()
                else:
                    return False

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
                    buf += port.read(1).decode('utf-8', 'ignore')
                    if buf.endswith('\n'):
                        self.logger.info(repr(buf))
                        return buf
                    elif time.time() - start_time > 1:
                        self.logger.info('异常 {}'.format(repr(buf)))
                        return buf
            else:
                return buf
        except OSError as error:
            self.logger.info('Fatal ERROR: {}'.format(error))
            return buf

    def at(self, at_command, runtimes):
        timeout = 3
        return_value_cache = ''
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('busybox microcom /dev/mhi_DUN\n'.encode('utf-8'))
        time.sleep(0.1)
        at_start_timestamp = time.time()
        self.ipq_port.write('{}\r\n'.format(at_command).encode('utf-8'))
        self.log_queue.put(['at_log', '[{} DUN Send] {}'.format(datetime.datetime.now(), '{}\\r\\n'.format(at_command))])
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['at_log', '[{} DUN Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                return_value_cache += return_value
                if 'OK' in return_value or 'ERROR' in return_value:
                    self.ipq_port.write(chr(0x18).encode())
                    return return_value_cache
            if time.time() - at_start_timestamp > timeout:
                self.log_queue.put(['all', '[{}] runtimes:{} busybox{}命令执行{}S未返回OK或ERROR'.format(datetime.datetime.now(), runtimes, at_command, timeout)])
                self.ipq_port.write(chr(0x18).encode())
                return ''

    def data_interface(self, mode, debug, runtimes):
        """
        data_interface指令相关操作
        :param mode: 0：设置0,0；1：设置1,1；2，检查0，0；3，检查1，1
        :param debug: 设置脚本遇到异常是停止还是继续运行False：继续运行；True：停止脚本
        :param runtimes: 当前runtimes
        :return:
        """
        if mode == 0 or mode == 1:
            command_string = '0,0' if mode == 0 else '1,0'
            self.at('at+qcfg="data_interface",{}'.format(command_string), runtimes)
            for i in range(10):
                time.sleep(1)
                data_interface = self.at('at+qcfg="data_interface"', runtimes)
                if ',{}'.format(command_string) in data_interface:
                    return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} atfwd异常，at+qcfg="data_interface"设置为{}后，查询仅返回OK'.format(datetime.datetime.now(), runtimes, command_string)])
                self.log_queue.put(['df', runtimes, 'data_interface_value_error_times', 1])
                if debug:
                    pause()
        elif mode == 2 or mode == 3:
            command_string = '0,0' if mode == 2 else '1,0'
            for i in range(10):
                time.sleep(1)
                data_interface = self.at('at+qcfg="data_interface"', runtimes)
                if ',{}'.format(command_string) in data_interface:
                    return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} atfwd异常，at+qcfg="data_interface"查询预期{}失败，仅返回OK'.format(datetime.datetime.now(), runtimes, command_string)])
                self.log_queue.put(['df', runtimes, 'data_interface_value_error_times', 1])
                if debug:
                    pause()

    def insmod(self, command):
        return_value_cache = ''
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('\n'.encode('utf-8'))
        # 写入命令
        self.ipq_port.write('{}\r\n'.format(command).encode('utf-8'))
        # 读取2S内返回的内容
        recv_start_timestamp = time.time()
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['ipq_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                return_value_cache += return_value
            if time.time() - recv_start_timestamp > 2:
                return return_value_cache

    def qmi_connect(self, runtimes):
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('\n'.encode('utf-8'))
        # 执行拨号指令
        self.ipq_port.write('quectel-CM &\r\n'.encode('utf-8'))
        self.log_queue.put(['at_log', '[{}] quectel-CM &'.format(datetime.datetime.now())])
        qmi_start_time = time.time()
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['ipq_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                if 'Adding DNS server' in return_value or 'udhcpc: setting default routers' in return_value:
                    self.log_queue.put(['at_log', '[{}] QMI拨号成功'.format(datetime.datetime.now())])  # 写入log
                    self.log_queue.put(['df', runtimes, 'qmi_dial_success_times', 1])
                    break
            if time.time() - qmi_start_time > 60:
                self.log_queue.put(['all', '[{}] runtimes:{} 60S内QMI拨号失败'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'qmi_dial_fail_times', 1])
                return False
        self.ipq_port.write('\r\n'.encode('utf-8'))
        self.ipq_port.write('\r\n'.encode('utf-8'))
        self.ipq_port.write('ping -w 60 8.8.8.8\r\n'.encode('utf-8'))
        ping_start_time = time.time()
        while True:
            time.sleep(0.01)
            return_ping_value = self.readline(self.ipq_port)
            if return_ping_value != '':
                self.log_queue.put(['at_log', '[{} Ping Recv] {}'.format(datetime.datetime.now(), repr(return_ping_value).replace("'", ''))])
            if time.time() - ping_start_time > 60:  # ping 60s
                time.sleep(3)
                self.ipq_port.write('\n'.encode('utf-8'))
                self.ipq_port.write('\n'.encode('utf-8'))
                time.sleep(3)
                return True

    def qmi_disconnect(self, runtimes):
        kill_start_time = time.time()
        self.ipq_port.write('killall quectel-CM\r\n'.encode('utf-8'))
        while True:
            time.sleep(0.01)
            return_ping_value = self.readline(self.ipq_port)
            if return_ping_value != '':
                self.log_queue.put(['at_log', '[{} Ping Recv] {}'.format(datetime.datetime.now(), repr(return_ping_value).replace("'", ''))])
                if 'QmiWwanThread exit' in return_ping_value:
                    self.log_queue.put(['at_log', '[{}] {}QMI拨号断开成功'.format(datetime.datetime.now(), runtimes)])
                    return True
            if time.time() - kill_start_time > 60:
                self.log_queue.put(['at_log', '[{}] {}超时60sQMI断开失败'.format(datetime.datetime.now(), runtimes)])
                return False

    def send_at(self, at_command, runtimes):
        timeout = 3
        return_value_cache = ''
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('busybox microcom /dev/ttyUSB2\n'.encode('utf-8'))
        time.sleep(0.1)
        at_start_timestamp = time.time()
        self.ipq_port.write('{}\r\n'.format(at_command).encode('utf-8'))
        self.log_queue.put(['at_log', '[{} AT Send] {}'.format(datetime.datetime.now(), '{}\\r\\n'.format(at_command))])
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['at_log', '[{} AT Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                return_value_cache += return_value
                if 'OK' in return_value or 'ERROR' in return_value:
                    self.ipq_port.write(chr(0x18).encode())
                    return return_value_cache
            if time.time() - at_start_timestamp > timeout:
                self.log_queue.put(['all', '[{}] runtimes:{} busybox{}命令执行{}S未返回OK或ERROR'.format(datetime.datetime.now(), runtimes, at_command, timeout)])
                self.ipq_port.write(chr(0x18).encode())
                return ''

    def ipq_qfirehose(self, command, vbat, runtimes):
        time.sleep(3)   # 实际测试出现之前未完全退出busybox，导致升级指令未正确发送，等待一段时间后再发送
        return_value_cache = ''
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('\n'.encode('utf-8'))
        random_off_time = round(random.uniform(1, 75))
        if vbat:
            self.log_queue.put(['at_log', '[{}] 升级进行{}S后断电'.format(datetime.datetime.now(), random_off_time)])
        # 写入命令
        self.log_queue.put(['at_log', '[{}] 开始升级'.format(datetime.datetime.now())])
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('{}\r\n'.format(command).encode('utf-8'))
        self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_starttimestamp', time.time()])
        start_time = time.time()
        # 读取返回的内容
        recv_start_timestamp = time.time()
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['qfirehose_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                return_value_cache += return_value
            if vbat and time.time() - start_time > random_off_time:
                self.log_queue.put(['at_log', '[{}] 升级过程随机断电'.format(datetime.datetime.now())])
                return True
            if 'Upgrade module successfull' in return_value:
                if vbat:
                    self.log_queue.put(['at_log', '[{}] 上报升级完成后断电'.format(datetime.datetime.now())])
                    return True
                self.log_queue.put(['df', runtimes, 'qfirehose_upgrade_a_b_endtimestamp', time.time()])
                self.log_queue.put(['at_log', '[{}] 升级成功'.format(datetime.datetime.now())])
                return True
            if 'Upgrade module failed' in return_value:
                self.log_queue.put(['all', '[{}] runtimes:{}] 升级失败'.format(datetime.datetime.now(), runtimes)])
                return False
            if time.time() - recv_start_timestamp > 120:
                self.log_queue.put(['df', runtimes, 'upgrade_fail_times', 1])
                self.log_queue.put(['all', '[{}] runtimes:{} 120S内升级失败'.format(datetime.datetime.now(), runtimes)])
                return False

    def at_init(self, runtimes):
        self.at('ATE', runtimes)
        time.sleep(1)
        self.at('AT+EGMR=0,7', runtimes)
        time.sleep(1)
        self.at('AT+QTEMP', runtimes)
        time.sleep(1)
        self.at('AT+QEFSVER', runtimes)

    def check_usb_at(self, runtimes):
        """
        检查AT口通信是否正常
        :param runtimes:
        :return:
        """
        self.ipq_port.write('ls /dev/ttyUSB*\r\n'.encode('utf-8'))
        start_time = time.time()
        while True:
            time.sleep(0.001)
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['ipq_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
            if time.time() - start_time > 2:
                break
        self.send_at('AT+QGMR', runtimes)
        time.sleep(1)
        self.send_at('AT+QTEMP', runtimes)

    def qfirehose_module_info_check(self, version, imei, runtimes):
        """
        查询和对比模块信息
        :param version: 当前模块的版本号
        :param imei: 当前模块imei号
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        # IMEI
        imei_value = self.at('AT+EGMR=0,7', runtimes)
        imei_re = ''.join(re.findall(r'EGMR: "(\d{15})"', imei_value))
        if imei_re != imei and 'OK' in imei_value:
            self.log_queue.put(['all', '[{}] runtimes:{} 模块IMEI号发生改变'.format(datetime.datetime.now(), runtimes)])
            pause()
        time.sleep(1)
        return_value = self.at('ATI+CSUB', runtimes)
        revision = ''.join(re.findall(r'Revision: (.*)', return_value))
        sub_edition = ''.join(re.findall('SubEdition: (.*)', return_value))
        version_r = revision + sub_edition
        version_r = re.sub(r'[\r|\n]', '', version_r)
        if version != version_r:
            self.log_queue.put(['df', runtimes, 'qfirehose_version_fail_times', 1])
            self.log_queue.put(['all', '[{}] runtimes:{} 模块版本号检查失败,当前版本为{}'.format(datetime.datetime.now(), runtimes, version_r)])
            return False
        # CFUN  刚开机可能需要等待几秒CFUN才会变成1
        return_value_re = ''
        for _ in range(20):  # 等待10S
            time.sleep(1)
            cfun_value = self.at('AT+CFUN?', runtimes)
            return_value_re = ''.join(re.findall(r'CFUN:\s(\d+)', cfun_value))
            if '1' in return_value_re and 'OK' in cfun_value:
                break
            time.sleep(0.5)
        else:
            self.log_queue.put(['df', runtimes, 'cfun_fail_times', 1])
            self.log_queue.put(['all', "[{}] runtimes:{} CFUN值错误，当前CFUN={}".format(datetime.datetime.now(), runtimes, return_value_re)])
            return False
        # CPIN
        for _ in range(20):  # 等待10S
            time.sleep(1)
            cpin_value = self.at('AT+CPIN?', runtimes)
            cpin_value_re = ''.join(re.findall(r"\+(.*ERROR.*)", cpin_value))
            if cpin_value_re != '':
                time.sleep(0.5)
                continue
            if 'READY' in cpin_value and "OK" in cpin_value:
                break
        else:
            time.sleep(1)
            cpin_value = self.at('AT+CPIN?', runtimes)
            cpin_value_re = ''.join(re.findall(r"\+(.*ERROR.*)", cpin_value))
            self.log_queue.put(['all', "[{}] runtimes:{} CPIN值异常 {}".format(datetime.datetime.now(), runtimes, cpin_value_re)])
            return False

    def qfirehose_again_check(self, lspci_check_value, ls_dev_mhi_check_value, debug, runtimes):
        """
        首先lsusb查询模块状态，处于紧急下载模式，则挂载U盘，加载驱动，进行升级并拉低powerkey；
        处于正常模式首先lspci，加载驱动，ls /dev指令查询，挂载U盘，进行升级。
        :param lspci_check_value:
        :param ls_dev_mhi_check_value:
        :param debug:
        :param runtimes:
        :return:
        """
        lsusb_val = self.insmod('lsusb')
        if '9008' in lsusb_val:     # 如果处于紧急下载模式
            self.log_queue.put(['at_log', '[{}] 模块已进入紧急下载模式'.format(datetime.datetime.now())])
            self.insmod('mount /dev/sda1 /mnt')
            self.insmod('insmod pcie_mhi.ko')
            self.rts_flag = True
        elif '2c7c' in lsusb_val:   # 如果处于正常模式
            self.ipq_usb_pcie_check('lspci', lspci_check_value, debug, runtimes)
            self.insmod('insmod pcie_mhi.ko')
            self.ipq_usb_pcie_check('ls /dev/mhi*', ls_dev_mhi_check_value, debug, runtimes)
            self.insmod('mount /dev/sda1 /mnt')
            self.rts_flag = False
        else:
            self.log_queue.put(['all', "[{}] runtimes:{} 开机lsusb查询未识别到模块".format(datetime.datetime.now(), runtimes)])
            return False

    def get_rts_state(self, runtimes):
        """
        获取rts_flag的值
        :param runtimes:
        :return:
        """
        if not self.rts_flag:   # 如果为False，代表无需拉低rts
            return False
        else:
            return True   # 为True代表需要拉低升级

    def qmi_mbim_connect(self, dial_mode, ipq_mode, dial_check_message, runtimes):
        """
        IPQ上进行QMI或者MBIM长拨
        :param server_config:
        :param dial_mode:
        :param runtimes:
        :return:
        """
        self.ipq_port.write('\n'.encode('utf-8'))
        self.ipq_port.write('\n'.encode('utf-8'))
        # 执行拨号指令
        if ipq_mode == 0:
            # 8074型号使用copy外部拨号工具 拨号指令用./quectel-CM
            self.ipq_port.write('./quectel-CM &\r\n'.encode('utf-8'))
            self.log_queue.put(['at_log', '[{}] ./quectel-CM &'.format(datetime.datetime.now())])
        else:
            # 4019型号ipq使用自带拨号工具，拨号指令用quectel-CM
            self.ipq_port.write('quectel-CM &\r\n'.encode('utf-8'))
            self.log_queue.put(['at_log', '[{}] quectel-CM &'.format(datetime.datetime.now())])
        qmi_start_time = time.time()
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.ipq_port)
            if return_value != '':
                self.log_queue.put(['ipq_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                if dial_check_message in return_value:
                    self.ipq_port.write('\r\n'.encode('utf-8'))
                    self.ipq_port.write('\r\n'.encode('utf-8'))
                    self.ipq_port.write('ping -w 60 8.8.8.8\r\n'.encode('utf-8'))
                    ping_start_time = time.time()
                    while True:
                        time.sleep(0.01)
                        return_ping_value = self.readline(self.ipq_port)
                        if return_ping_value != '':
                            self.log_queue.put(['at_log', '[{} Ping Recv] {}'.format(datetime.datetime.now(), repr(return_ping_value).replace("'", ''))])
                            self.log_queue.put(['at_log', '[{}] {}拨号成功'.format(datetime.datetime.now(), dial_mode)])  # 写入log
                        if time.time() - ping_start_time > 60:  # ping 60s
                            return True
            if time.time() - qmi_start_time > 60:
                self.log_queue.put(['all', '[{}] runtimes:{} 60S内{}拨号失败'.format(datetime.datetime.now(), runtimes, dial_mode)])
                return False


if __name__ == '__main__':
    from queue import Queue
    from threading import Event

    iq = Queue()
    lq = Queue()
    eq = Queue()
    e = Event()

    ipd_thread = IPQProcessThread('COM19', iq, lq, eq)
    ipd_thread.start()

    # iq.put([('get_message', 'Enable bridge snooping', 1), e])
    # iq.put([('ipq_usb_pcie_check', 'lspci', ['17cb', '0306'], 1), e])
    # iq.put([('ipq_usb_pcie_check', 'ls /dev/mhi*', ['/dev/mhi_BHI', '/dev/mhi_DUN', '/dev/mhi_QMI0', '/dev/mhi_DIAG', '/dev/mhi_LOOPBACK'], 1), e])
    iq.put([('data_interface', 2, False, 1), e])
