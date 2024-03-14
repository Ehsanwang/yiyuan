# -*- encoding=utf-8 -*-
import datetime
from threading import Thread
import serial
import logging
from functions import pause


class PowerThread(Thread):
    def __init__(self, power_port, power_queue, main_queue, log_queue):
        super().__init__()
        self.power_port = power_port
        self.power_queue = power_queue
        self.main_queue = main_queue
        self.log_queue = log_queue
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.logger = logging.getLogger(__name__)

    def run(self):
        try:
            self.power_port = serial.Serial(self.power_port, baudrate=9600, timeout=0.1)  # 程控电源波特率9600
        except serial.serialutil.SerialException:
            pause("电源端口被占用或端口设置错误，请关闭脚本并重新运行！")
        self.power_port.write('syst:rem\r\n'.encode('utf-8'))
        self.power_port.write('Volt 0\r\n'.encode('utf-8'))

        while True:
            # 传入参数参考：['init_module', 5, 'M.2', 0.5, <threading.Event object at 0x...>]
            (func, *param), evt = self.power_queue.get()
            self.logger.info('{}->{}->{}'.format(func, param, evt))
            if func in self._methods_list:
                getattr(self.__class__, '{}'.format(func))(self, *param)
                self.main_queue.put(True)
                evt.set()

    def set_volt(self, volt):
        self.power_port.write('Volt {}\r\n'.format(volt).encode('utf-8'))
        self.log_queue.put(['at_log', "[{}] 程控电源电压设置为{}V".format(datetime.datetime.now(), volt)])


if __name__ == '__main__':
    # 电压从1到10测试
    from queue import Queue
    from threading import Event
    import time

    pq = Queue()
    exc_q = Queue()
    log_q = Queue()
    e = Event()

    pt = PowerThread('COM9', pq, exc_q, log_q)
    pt.start()
    for i in range(1, 11):
        pq.put([('set_volt', i), e])
        time.sleep(1)
