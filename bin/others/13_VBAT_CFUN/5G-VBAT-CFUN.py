# -*- encoding=utf-8 -*-
import json
import datetime
import time
import signal
from sys import path
import logging
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'LowPower'))
from functions import environment_check
environment_check()  # 检查环境
from lowpower_route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from queue import Queue
from threading import Event
from lowpower_log_thread import LowLogThread
from lowpower_power_thread import PowerThread
from functions import pause

"""
注意事项：
1. 脚本需要使用程控电源
2. 电脑需要设置usb suspend
"""

with open('config.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# ======================================================================================================================
# 需要配置的参数
at_port = data['at_port']  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = data['dm_port']  # 定义DM端口号,用于判断模块有无dump
power_port = data['power_port']  # 程控电源端口号,用于电流的输入和输出
evb = data['evb']  # RG默认evb参数为EVB，RM默认evb参数为M.2
voltage = data['voltage']  # 基准的电压
curr = data['curr']  # 基准电流
# ======================================================================================================================

uart_port = None
debug_port = None
voltage = float(voltage)
runtimes_temp = 0
timing = 0


# 辅助参数
sleep_curr_max = 6  # 设置进入休眠后的平均耗流标准，实测不得超过该标准，单位为毫安
wake_curr_max = 40  # 设置退出休眠后的平均耗流标准，实测不得超过该标准，单位为毫安
tolerance_rate = 0.08  # 在采样数据中出现的高于设定标准的峰值频率
sleep_time = 60  # 检测休眠耗流时长，单位为秒
wake_time = 30  # 检测唤醒耗流时长，单位为秒
wait_sleep_time = 120  # 设置静置等待进入睡眠时间，单位为秒
check_freq = 1  # 检测频率，单位为秒
pid_vid = '2c7c:0800'  # Linux下需要配置pid和vid用于Linux检测，值为lsusb返回的值
cfun_0 = True  # True时候会休眠前会发送AT+CFUN=0，False默认
wait_time = 0  # 开机后多久执行睡眠命令
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
info = 'VBAT-CFUN'  # 脚本详情字符串
logger = logging.getLogger(__name__)
# ======================================================================================================================
# 定义queue并启动线程
main_queue = Queue()
route_queue = Queue()
uart_queue = Queue()
process_queue = Queue()
at_queue = Queue()
log_queue = Queue()
power_queue = Queue()
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue, power_queue)
process_thread = ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LowLogThread('test', info, False, log_queue, main_queue)
power_thread = PowerThread(power_port, power_queue, main_queue, log_queue)
threads = [route_thread, process_thread, at_thread, log_thread, power_thread]
if uart_port and debug_port:
    uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
    threads.extend([uart_thread])
for thread in threads:
    thread.setDaemon(True)
    thread.start()


def route_queue_put(*args, queue=route_queue):
    """
    往某个queue队列put内容，默认为route_queue，并且接收main_queue队列如果有内容，就接收。
    :param args: 需要往queue中发送的内容
    :param queue: 指定queue发送，默认route_queue
    :return: main_queue内容
    """
    logger.info('{}->{}'.format(queue, args))
    evt = Event()
    queue.put([*args, evt])
    evt.wait()
    _main_queue_data = main_queue.get(timeout=0.1)
    return _main_queue_data


# 脚本结束，进行结果统计
def handler(signal_num, frame=None):
    """
    脚本结束参数统计。
    """
    route_queue_put('end_script', script_start_time, runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
# ======================================================================================================================
# 主流程
while True:
    # 脚本自动停止判断
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or (timing != 0 and time.time() - script_start_time > timing * 3600):  # 如果runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
        # route_queue_put('end_script', script_start_time, runtimes - 1, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符

    # 上电
    route_queue_put('Power', 'set_volt', voltage, curr)

    # 检测驱动
    main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
    if main_queue_data is False:
        print('检测驱动失败，开机失败，暂停脚本')
        pause()

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        print("打开AT口失败，暂停脚本")
        pause()

    # 检测URC
    main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
    if main_queue_data is False:
        print('检测驱动失败，开机失败，暂停脚本')
        pause()

    # 等待3S
    time.sleep(3)

    # 检测CFUN
    main_queue_data = route_queue_put('AT', 'check_cfun', runtimes)
    if main_queue_data is False:
        print('检测CFUN值异常，暂停脚本')
        pause()

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        print("关闭AT口失败，暂停脚本")
        pause()

    # 断电
    route_queue_put('Power', 'set_volt', 0, 0)

    # 检测驱动消失
    main_queue_data = route_queue_put('Process', 'check_usb_driver_dis', True, runtimes)
    if main_queue_data is False:
        print("关闭AT口失败，暂停脚本")
        pause()

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
