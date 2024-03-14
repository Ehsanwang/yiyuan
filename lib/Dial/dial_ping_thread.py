# -*- encoding=utf-8 -*-
import datetime
import subprocess
import time
import re
from threading import Thread
import os


class PingThread(Thread):
    def __init__(self, runtimes, log_queue):
        super().__init__()
        self.runtimes = runtimes
        self.log_queue = log_queue
        self.df_flag = False

    def run(self):
        runtimes_cache = 0
        while True:

            while True:
                time.sleep(0.1)
                if runtimes_cache != self.runtimes:  # 拨号成功时开始
                    runtimes_cache = self.runtimes
                    self.log_queue.put(['ping_log', '[{}] {}runtimes:{}{}'.format(datetime.datetime.now(), '=' * 30, self.runtimes, '=' * 30)])
                    ping_result_list = []
                    break
            if os.name == 'nt':
                s = subprocess.Popen(['ping', '-4', '-t', 'www.qq.com'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                while True:
                    time.sleep(0.1)
                    ping_data = s.stdout.readline().decode('GBK', 'ignore')
                    self.log_queue.put(['ping_log', '[{}] {}'.format(datetime.datetime.now(), repr(ping_data))]) if ping_data != '' else ''
                    ping_status = re.findall(r'来自 (.*?) 的回复: 字节=(\d+) 时间=(\d+)ms TTL=(\d+)', ping_data)
                    ping_result_list.append(ping_status)
                    if self.df_flag is True:  # df_flag为True时结束
                        self.df_flag = False
                        if len(ping_result_list) >= 3:
                            ping_result_list = ping_result_list[2:]  # 取消ping前两行无效值
                            package_loss_rate = ping_result_list.count([]) / len(ping_result_list) * 100
                            self.log_queue.put(['df', self.runtimes, 'ping_package_loss_rate', package_loss_rate])
                        else:
                            self.log_queue.put(['df', self.runtimes, 'ping_package_loss_rate', 0])
                        s.terminate()
                        break
            else:
                s = subprocess.Popen(['ping', 'www.qq.com'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                while True:
                    time.sleep(0.1)
                    ping_data = s.stdout.readline().decode('utf-8', 'ignore')
                    self.log_queue.put(['ping_log', '[{}] {}'.format(datetime.datetime.now(), repr(ping_data))]) if ping_data != '' else ''
                    ping_status = re.findall(r'(time|时间)=(\d+)', ping_data)
                    ping_result_list.append(ping_status)
                    if self.df_flag is True:  # df_flag为True时结束
                        self.df_flag = False
                        if len(ping_result_list) >= 2:
                            ping_result_list = ping_result_list[2:]  # 取消ping前两行无效值
                            package_loss_rate = ping_result_list.count([]) / len(ping_result_list) * 100
                            self.log_queue.put(['df', self.runtimes, 'ping_package_loss_rate', package_loss_rate])
                        else:
                            self.log_queue.put(['df', self.runtimes, 'ping_package_loss_rate', 0])
                        s.terminate()
                        break
