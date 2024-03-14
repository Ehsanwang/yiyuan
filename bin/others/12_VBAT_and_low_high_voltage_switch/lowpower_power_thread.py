# -*- encoding=utf-8 -*-
import datetime
from threading import Thread
import serial
import numpy as np
import logging
import time
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
            pause("电源端口被占用或者端口设置错误，请关闭脚本并重新运行！")
        self.power_port.write('syst:rem\r\n'.encode('utf-8'))
        while True:
            # 传入参数参考：['init_module', 5, 'M.2', 0.5, <threading.Event object at 0x...>]
            (func, *param), evt = self.power_queue.get()
            self.logger.info('{}->{}->{}'.format(func, param, evt))
            if func in self._methods_list:
                getattr(self.__class__, '{}'.format(func))(self, *param)
                self.main_queue.put(True)
                evt.set()

    def get_current_volt(self, max_electric, max_rate, check_time, check_frequency, mode, runtimes):
        get_volt_start_timestamp = time.time()
        volt_list = []
        while True:
            time.sleep(0.001)
            self.power_port.write('meas:curr?\r\n'.encode('UTF-8'))
            return_value = self.power_port.readline().decode('utf-8', 'ignore')
            if time.time() - get_volt_start_timestamp > check_time:  # 到达检测时间
                upset_list = [volt for volt in volt_list if volt > max_electric]  # 电流大于设定值时加入此列表
                curr_avg = np.round(np.mean(volt_list), 2)  # 计算电流平均值
                real_rate = round(len(upset_list) / len(volt_list), 2)  # 大于设定值的比率
                if mode == 0:
                    if real_rate > max_rate:
                        self.log_queue.put(['all', '[{}] runtimes:{} 休眠耗流值偏高频率为{}%'.format(datetime.datetime.now(), runtimes, real_rate * 100)])
                    else:
                        self.log_queue.put(['at_log', '[{}] 休眠耗流值偏高频率为{}%\n'.format(datetime.datetime.now(), real_rate * 100)])
                    if curr_avg > max_electric:
                        self.log_queue.put(['all', '[{}] runtimes:{} 休眠耗流平均值实测为{}mA'.format(datetime.datetime.now(), runtimes, curr_avg)])
                    else:
                        self.log_queue.put(['at_log', '[{}] 休眠耗流平均值实测为{}mA'.format(datetime.datetime.now(), curr_avg)])
                    if curr_avg > max_electric or real_rate > max_rate:
                        self.log_queue.put(['df', runtimes, 'sleep_upset_times', 1])
                    self.log_queue.put(['df', runtimes, 'sleep_curr_avg', curr_avg])
                    self.log_queue.put(['df', runtimes, 'sleep_real_rate', real_rate])
                elif mode == 1:
                    if real_rate > max_rate:
                        self.log_queue.put(['all', '[{}] runtimes:{} 唤醒耗流值偏高实测为{}%'.format(datetime.datetime.now(), runtimes, real_rate * 100)])
                    else:
                        self.log_queue.put(['at_log', '[{}] 休眠耗流值偏高频率为{}%'.format(datetime.datetime.now(), real_rate * 100)])
                    if curr_avg > max_electric:
                        self.log_queue.put(['all', '[{}] runtimes:{} 唤醒耗流平均值实测为{}mA'.format(datetime.datetime.now(), runtimes, curr_avg)])
                    else:
                        self.log_queue.put(['at_log', '[{}] 唤醒耗流平均值实测为{}mA'.format(datetime.datetime.now(), curr_avg)])
                    if curr_avg > max_electric or real_rate > max_rate:
                        self.log_queue.put(['df', runtimes, 'wake_upset_times', 1])
                    self.log_queue.put(['df', runtimes, 'wake_curr_avg', curr_avg])
                    self.log_queue.put(['df', runtimes, 'wake_real_rate', real_rate])
                break
            if return_value != '':
                current_voltage = float(return_value) * 1000
                self.log_queue.put(['at_log', '[{} power] {} mA'.format(datetime.datetime.now(), round(current_voltage, 4))])
                volt_list.append(current_voltage)
            time.sleep(check_frequency)

    def set_volt(self, volt):
        self.power_port.write('Volt {}\r\n'.format(volt).encode('utf-8'))
        self.log_queue.put(['at_log', "[{}] 程控电源电压设置为{}V".format(datetime.datetime.now(), volt)])


if __name__ == '__main__':
    from queue import Queue
    from threading import Event

    pq = Queue()
    mq = Queue()
    exc_q = Queue()
    log_q = Queue()
    e = Event()

    pt = PowerThread('COM18', pq, exc_q, mq)
    pt.start()
    pq.put([('get_current_volt', 20, 10, 10, 1, 1, 1), e])

    time.sleep(100)
