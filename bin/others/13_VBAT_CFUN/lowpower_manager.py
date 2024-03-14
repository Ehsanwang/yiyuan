# -*- encoding=utf-8 -*-
import time
from threading import Event
import logging


class LowPower:
    def __init__(self, main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, vbat, runtimes):
        self.main_queue = main_queue
        self.route_queue = route_queue
        self.uart_queue = uart_queue
        self.uart_port = uart_port
        self.evb = evb
        self.imei = imei
        self.version = version
        self.runtimes = runtimes
        self.log_queue = log_queue
        self.vbat = vbat
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

    def low_power_vbat(self):
        """
        M.2 EVB：拉高DTR断电->检测驱动消失->拉低DTR上电；
        5G-EVB_V2.1：拉高RTS->拉高DTR断电->检测驱动消失->拉低DTR上电。
        :return: None
        """
        # 关口防止端口变化
        None if self.runtimes == 0 else self.route_queue_put('AT', 'close', self.runtimes)
        self.route_queue_put('Power', 'set_volt', 0)
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        # 等待3S上电
        time.sleep(3)
        # 上电
        self.route_queue_put('Power', 'set_volt', 3.8)
        self.log_queue.put(['df', self.runtimes, 'power_on_timestamp', time.time()])  # 写入power_on_timestamp
        # 检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:  # 端口异常
            return False
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            return False
        # check 开机urc
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            return False
        time.sleep(10)

    def lp_init(self):
        self.log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
        print("\rinitialize", end="")
        # 1.初始化引脚
        self.route_queue_put('Power', 'set_volt', 0)
        # 检测驱动消失
        self.route_queue_put('Process', 'check_usb_driver_dis', True, self.runtimes)
        # 上电
        self.route_queue_put('Power', 'set_volt', 3.8)
        # 2. 初始化检测USB驱动
        main_queue_data = self.route_queue_put('Process', 'check_usb_driver', True, self.runtimes)
        if main_queue_data is False:
            print('初始化模块时USB驱动加载失败，请重新运行脚本')
            exit()
        # 3. 打开AT口
        main_queue_data = self.route_queue_put('AT', 'open', self.runtimes)
        if main_queue_data is False:
            print('初始化模块时USB驱动加载失败，请重新运行脚本')
            exit()
        # 4. 检测开机URC
        main_queue_data = self.route_queue_put('AT', 'check_urc', self.runtimes)
        if main_queue_data is False:
            print('初始化模块时USB驱动加载失败，请重新运行脚本')
            exit()
        time.sleep(5)
        # 5. 普通AT初始化
        main_queue_data = self.route_queue_put('AT', 'prepare_at', self.version, self.imei, False, self.runtimes)
        if main_queue_data is False:
            print('初始化模块时USB驱动加载失败，请重新运行脚本')
            exit()
        # 6. 检查网络
        main_queue_data = self.route_queue_put('AT', 'check_network', False, self.runtimes)
        if main_queue_data is False:
            print('初始化模块时USB驱动加载失败，请重新运行脚本')
            exit()
        # 7. 关闭AT口
        main_queue_data = self.route_queue_put('AT', 'close', self.runtimes)
        if main_queue_data is False:
            print('初始化模块时USB驱动加载失败，请重新运行脚本')
            exit()
