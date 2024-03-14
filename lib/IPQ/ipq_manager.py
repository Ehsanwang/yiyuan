# -*- encoding=utf-8 -*-
import time
from threading import Event
import datetime
import logging


class IPQManager:
    def __init__(self, main_queue, route_queue, uart_queue, at_queue, log_queue, power_queue, at_port, uart_port, evb, version, imei, lspci_check_value, ls_dev_mhi_check_value, debug, ipq_poweron_message, dial_mode, ipq_mode, dial_check_message, runtimes):
        self.route_queue = route_queue
        self.uart_queue = uart_queue
        self.at_queue = at_queue
        self.log_queue = log_queue
        self.power_queue = power_queue
        self.at_port = at_port
        self.uart_port = uart_port
        self.evb = evb
        self.runtimes = runtimes
        self.version = version
        self.imei = imei
        self.main_queue = main_queue
        self.lspci_check_value = lspci_check_value
        self.ls_dev_mhi_check_value = ls_dev_mhi_check_value
        self.debug = debug
        self.ipq_poweron_message = ipq_poweron_message
        self.dial_mode = dial_mode
        self.ipq_mode = ipq_mode
        self.dial_check_message = dial_check_message
        # 使用insmod pcie_mhi.ko加载pcie驱动
        self.insmod_driver = 'insmod pcie_mhi.ko' if self.dial_mode == 'QMI' else 'insmod pcie_mhi.ko mhi_mbim_enabled=1'
        self.logger = logging.getLogger(__name__)

    def route_queue_put(self, *args, queue=None):
        """
        往某个queue队列put内容，默认为None时向route_queue发送内容，并且接收main_queue队列如果有内容，就接收。
        :param args: 需要往queue中发送的内容
        :param queue: 指定queue发送，默认route_queue
        :return: main_queue内容
        """
        self.logger.info('{}->{}'.format(queue, args))
        if queue is None:
            evt = Event()
            self.route_queue.put([*args, evt])
            evt.wait()
        else:
            evt = Event()
            queue.put([*args, evt])
            evt.wait()
        _main_queue_data = self.main_queue.get(timeout=0.1)
        return _main_queue_data

    def ipq_pcie_init(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        # 设置data_interface为0,0
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'data_interface', 2, self.debug, self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def ipq_pcie_re_init(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        # 设置data_interface为0,0re
        self.route_queue_put('AT', 'open', self.runtimes)
        self.route_queue_put('AT', 'check_urc', self.runtimes)
        self.route_queue_put('AT', 'data_interface', 0, self.debug, self.runtimes)
        self.route_queue_put('AT', 'close', self.runtimes)
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def set_data_interface_1_1(self):
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 读取IPQ上报Enable bridge snooping
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 发送lspci查看是否不包含17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_pcie_usb_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 发送ls /dev/mhi*查看是否不包含指定驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_pcie_usb_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 设置data_interface为1,1
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'data_interface', 1, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def get_data_interface_0_0(self):
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 读取IPQ上报Enable bridge snooping
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 发送lspci查看是否不包含17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_pcie_usb_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 发送ls /dev/mhi*查看是否不包含指定驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_pcie_usb_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 设置data_interface为1,1
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'data_interface', 2, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            return False
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def check_pcie_driver_status(self):
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 读取IPQ上报Enable bridge snooping
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lspci查看是否返回17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 使用insmod pcie_mhi.ko加载pcie驱动
        main_queue_data = self.route_queue_put('IPQ', 'insmod', 'insmod pcie_mhi.ko')
        if main_queue_data is False:
            return False
        # 发送ls /dev/mhi*查看是否返回所有的驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('IPQ', 'data_interface', 3, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 进行qmi拨号及Ping操作
        main_queue_data = self.route_queue_put('IPQ', 'qmi_connect', self.runtimes)
        if main_queue_data is False:
            return False
        # 设置data_interface为0,0
        main_queue_data = self.route_queue_put('IPQ', 'data_interface', 0, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def ipq_pcie_dfota_init(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        # data_interface 设置0,0
        main_queue_data = self.route_queue_put('AT', 'data_interface', 0, self.debug, self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        # 开启adb
        main_queue_data = self.route_queue_put('AT', 'qcfg_usbcfg', True, self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def poweron_evb_ipq(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)

    def poweroff_evb_ipq(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)

    def ipq_pcie_qfotadl(self, ufs_path, package_name):
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 读取IPQ上报Enable bridge snooping
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lspci
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 使用insmod pcie_mhi.ko加载pcie驱动
        main_queue_data = self.route_queue_put('IPQ', 'insmod', 'insmod pcie_mhi.ko')
        if main_queue_data is False:
            return False
        # 发送ls /dev/mhi*查看是否返回所有的驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 使DFOTA升级
        main_queue_data = self.route_queue_put('IPQ', 'at', 'at+qfotadl="{}/{}"'.format(ufs_path, package_name), self.runtimes)
        if main_queue_data is False:
            return False

    def ipq_qfirehose_pcie_init(self):
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            exit()
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lspci查看是否返回17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            exit()
        # 使用insmod pcie_mhi.ko加载pcie驱动
        self.route_queue_put('IPQ', 'insmod', 'insmod pcie_mhi.ko')
        # 发送ls /dev/mhi*查看是否返回所有的驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            exit()
        self.route_queue_put('IPQ', 'at_init', self.runtimes)
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def ipq_qfirehose_pcie_re_init(self):
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def check_at(self):
        main_queue_data = self.route_queue_put('IPQ', 'check_usb_at', self.runtimes)
        if main_queue_data is False:
            return False

    def check_qfirehose_pcie_driver_status(self):
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 读取IPQ上报Enable bridge snooping
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lspci查看是否返回17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 使用insmod pcie_mhi.ko加载pcie驱动
        main_queue_data = self.route_queue_put('IPQ', 'insmod', 'insmod pcie_mhi.ko')
        if main_queue_data is False:
            return False
        # 发送ls /dev/mhi*查看是否返回所有的驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 发送指令挂载U盘
        main_queue_data = self.route_queue_put('IPQ', 'insmod', 'mount /dev/sda1 /mnt')
        if main_queue_data is False:
            return False

    def qfirehose_again(self, package_name, runtimes, flag=True):
        """
        断电升级或者升级异常后使用
        :param package_name:升级包名
        :param runtimes:运行次数
        :param flag:True:断电升级时使用，IPQ重启后直接升级；False:升级异常时使用，IPQ重启后不升级
        :return:
        """
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_rts_false')
        self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 读取IPQ上报Enable bridge snooping
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lsusb检查模块处于紧急下载模式还是正常模式，再决定后续流程
        main_queue_data = self.route_queue_put('IPQ', 'qfirehose_again_check', self.lspci_check_value, self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('IPQ', 'get_rts_state', self.runtimes)
        if main_queue_data:  # 代表需要拉低rts
            self.route_queue_put('Uart', 'set_rts_true')
            self.log_queue.put(['at_log', "[{}] Set RTS True".format(datetime.datetime.now())])
        if flag:
            is_success = self.qfirehose(package_name, False, runtimes)
            self.log_queue.put(['at_log', "[{}] 模块升级完成后，拉高powerkey".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_rts_false')
            if not is_success:
                self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
                self.route_queue_put('Uart', 'set_rts_false')
                return False

    def module_info_check(self):
        main_queue_data = self.route_queue_put('IPQ', 'qfirehose_module_info_check', self.version, self.imei, self.runtimes)
        if main_queue_data is False:
            return False

    def qfirehose(self, package_name, vbat, runtimes):
        main_queue_data = self.route_queue_put('IPQ', 'ipq_qfirehose', 'QFirehose -f /mnt/{}'.format(package_name), vbat, runtimes)
        if main_queue_data is False:
            return False

    def qfirehose_check(self):
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_rts_false')
        self.log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lspci查看是否返回17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 使用insmod pcie_mhi.ko加载pcie驱动
        main_queue_data = self.route_queue_put('IPQ', 'insmod', 'insmod pcie_mhi.ko')
        if main_queue_data is False:
            return False
        # 发送ls /dev/mhi*查看是否返回所有的驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('IPQ', 'qfirehose_module_info_check', self.version, self.imei, self.runtimes)
        if main_queue_data is False:
            return False
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def ipq_pcie_qmi_init(self):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        # 设置data_interface为0,0
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'data_interface', 1, self.debug, self.runtimes)  # 设置1,0
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def ipq_qmi_ping_restart(self):
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 读取IPQ上报Enable bridge snooping
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lspci查看是否返回17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 使用insmod pcie_mhi.ko加载pcie驱动
        main_queue_data = self.route_queue_put('IPQ', 'insmod', 'insmod pcie_mhi.ko')
        if main_queue_data is False:
            return False
        # 发送ls /dev/mhi*查看是否返回所有的驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        main_queue_data = self.route_queue_put('IPQ', 'data_interface', 3, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        # 进行qmi拨号及Ping操作
        main_queue_data = self.route_queue_put('IPQ', 'qmi_connect', self.runtimes)
        if main_queue_data is False:
            return False
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def ipq_qmi_ping_norestart(self):
        # 非开关机方式需要ipq开机、验证IPQ信息等
        if self.runtimes == 1:
            # 模块上电
            self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            # 等待2S
            time.sleep(2)
            # IPQ上电
            self.route_queue_put('Power', 'set_volt', 12)
            # 读取IPQ上报Enable bridge snooping
            main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
            if main_queue_data is False:
                return False
            time.sleep(3)  # 等3秒让多余的log吐完
            # 发送lspci查看是否返回17cb:0306，根据版本设置值？
            main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
            if main_queue_data is False:
                return False
            # 使用insmod pcie_mhi.ko加载pcie驱动
            main_queue_data = self.route_queue_put('IPQ', 'insmod', 'insmod pcie_mhi.ko')
            if main_queue_data is False:
                return False
            # 发送ls /dev/mhi*查看是否返回所有的驱动
            main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
            if main_queue_data is False:
                return False
            main_queue_data = self.route_queue_put('IPQ', 'data_interface', 3, self.debug, self.runtimes)
            if main_queue_data is False:
                return False
        self.log_queue.put(['at_log', "[{}] 进行QMI拨号".format(datetime.datetime.now())])
        # qmi拨号和ping
        main_queue_data = self.route_queue_put('IPQ', 'qmi_connect', self.runtimes)
        if main_queue_data is False:
            return False
        # 断开QMI拨号
        main_queue_data = self.route_queue_put('IPQ', 'qmi_disconnect', self.runtimes)
        if main_queue_data is False:
            return False

    def ipq_qmi_re_init(self, flag=True):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        # 设置data_interface为0,0re
        self.route_queue_put('AT', 'open', self.runtimes)
        self.route_queue_put('AT', 'check_urc', self.runtimes)
        self.route_queue_put('AT', 'close', self.runtimes)
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)
        if flag is False:
            # 模块上电
            self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
            self.route_queue_put('Uart', 'set_dtr_true')
            self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
            # 等待2S
            time.sleep(2)
            # IPQ上电
            self.route_queue_put('Power', 'set_volt', 12)
            # 读取IPQ上报Enable bridge snooping
            main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug,
                                                   self.runtimes)
            if main_queue_data is False:
                return False
            time.sleep(3)  # 等3秒让多余的log吐完
            # 发送lspci查看是否返回17cb:0306，根据版本设置值？
            main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
            if main_queue_data is False:
                return False
            # 使用insmod pcie_mhi.ko加载pcie驱动
            main_queue_data = self.route_queue_put('IPQ', 'insmod', 'insmod pcie_mhi.ko')
            if main_queue_data is False:
                return False
            # 发送ls /dev/mhi*查看是否返回所有的驱动
            main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
            if main_queue_data is False:
                return False

    def ipq_pcie_qmi_MBIM_init(self):
        """
        qmi/mbim 长拨初始化
        :return:
        """
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        # 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        # 检查开机URC
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        # 设置at+qcfg="data_interface",1,0
        main_queue_data = self.route_queue_put('AT', 'data_interface', 1, self.debug, self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            print('初始化打开AT口失败，请重新运行脚本')
            exit()
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)

    def ipq_pcie_qmi_mbim(self):
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        # 读取IPQ上报
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            print('初始化IPQ开机失败，请重新运行脚本')
            exit()
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lspci查看是否返回17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            print('初始化lspci失败，请重新运行脚本')
            exit()
        if self.dial_mode.upper() == 'MBIM':    # 如果是MBIM拨号的话，首先卸载QMI驱动，再进行MBIM驱动加载
            main_queue_data = self.route_queue_put('IPQ', 'insmod', 'rmmod pcie_mhi.ko')
            if main_queue_data is False:
                return False
        # 加载qmi或者mbim驱动
        main_queue_data = self.route_queue_put('IPQ', 'insmod', self.insmod_driver)
        if main_queue_data is False:
            return False
        time.sleep(5)   # 加载完后，等待一会才能查到
        # 发送ls /dev/mhi*查看是否返回所有的驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            print('初始化ls /dev/mhi*失败，请重新运行脚本')
            exit()
        main_queue_data = self.route_queue_put('IPQ', 'data_interface', 3, self.debug, self.runtimes)
        if main_queue_data is False:
            print('初始化查询data_interface非1,0，请重新运行脚本')
            exit()
        time.sleep(5)
        self.log_queue.put(['at_log', "[{}] 进行{}拨号".format(datetime.datetime.now(), self.dial_mode)])
        # qmi、mbim拨号--长拨
        main_queue_data = self.route_queue_put('IPQ', 'qmi_mbim_connect', self.dial_mode, self.ipq_mode, self.dial_check_message, self.runtimes)
        if main_queue_data is False:
            print('初始化{}拨号失败，请重新运行脚本'.format(self.dial_mode))
            exit()

    def ipq_qmi_mbim_re_init(self, flag=True):
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        # 模块断电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块断电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_false')
        self.log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ断电
        self.route_queue_put('Power', 'set_volt', 0)
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        # 模块上电
        self.log_queue.put(['at_log', "[{}] 拉动DTR控制模块上电".format(datetime.datetime.now())])
        self.route_queue_put('Uart', 'set_dtr_true')
        self.log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 等待2S
        time.sleep(2)
        # IPQ上电
        self.route_queue_put('Power', 'set_volt', 12)
        # 检测驱动
        self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        self.route_queue_put('AT', 'open', self.runtimes)
        self.route_queue_put('AT', 'check_urc', self.runtimes)
        self.route_queue_put('AT', 'close', self.runtimes)
        # 读取IPQ上报Enable bridge snooping
        main_queue_data = self.route_queue_put('IPQ', 'get_message', self.ipq_poweron_message, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(3)  # 等3秒让多余的log吐完
        # 发送lspci查看是否返回17cb:0306，根据版本设置值？
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'lspci', self.lspci_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        if self.dial_mode.upper() == 'MBIM':    # 如果是MBIM拨号的话，首先卸载QMI驱动，再进行MBIM驱动加载
            main_queue_data = self.route_queue_put('IPQ', 'insmod', 'rmmod pcie_mhi.ko')
            if main_queue_data is False:
                return False
        # 加载qmi或者mbim驱动
        main_queue_data = self.route_queue_put('IPQ', 'insmod', self.insmod_driver)
        if main_queue_data is False:
            return False
        time.sleep(5)
        # 发送ls /dev/mhi*查看是否返回所有的驱动
        main_queue_data = self.route_queue_put('IPQ', 'ipq_usb_pcie_check', 'ls /dev/mhi*', self.ls_dev_mhi_check_value, self.debug, self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(5)
        self.log_queue.put(['at_log', "[{}] 进行{}拨号".format(datetime.datetime.now(), self.dial_mode)])
        # qmi、mbim拨号--长拨
        main_queue_data = self.route_queue_put('IPQ', 'qmi_mbim_connect', self.dial_mode, self.ipq_mode, self.dial_check_message, self.runtimes)
        if main_queue_data is False:
            return False
