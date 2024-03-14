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
from lowpower_manager import LowPower
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
mode = data['mode']  # 1：通电断电测试  0：高低电压测试
uart_port = data['uart_port']  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = data['at_port']  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = data['dm_port']  # 定义DM端口号,用于判断模块有无dump
power_port = data['power_port']  # 程控电源端口号,用于电流的输入和输出
debug_port = data['debug_port']  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
evb = data['evb']  # RG默认evb参数为EVB，RM默认evb参数为M.2
voltage = data['voltage']  # 基准的电压
# 程控电源断电设置参数
power_on_time = data['power_on_time']  # 从通电到断电的时间
power_off_time = data['power_off_time'] # 断电后到下次上电的时间
# 高低电压脚本设置参数
voltage_offset = data['voltage_offset']  # 电压偏移量，0.1则为10%
high_low_volt_last_time = data['high_low_volt_last_time']
# 程序运行时间次数设置参数
runtimes_temp = data['runtimes_temp']  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = data['timing']   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
voltage = float(voltage)
power_on_time = int(power_on_time)
power_off_time = int(power_off_time)
runtimes_temp = int(runtimes_temp)
timing = int(timing)
mode = int(mode)
voltage_offset = float(voltage_offset)
high_low_volt_last_time = int(high_low_volt_last_time)

if voltage > 3.8:
    input("模块基准电压为3.8V，确认设置{}V?".format(voltage))
    input("你真的要设置{}V?".format(voltage))
    input("最后一次确认：你真的要设置{}V?".format(voltage))

if voltage_offset > 0.2:
    input("模块基准电压为{}V，偏移{}%，确认设置?".format(voltage, voltage_offset*100))

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
info = 'VBAT-{}'.format('通电断电测试' if mode else '高低电压测试')  # 脚本详情字符串
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
lowpower_manager = LowPower(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, 'test', 'None', False, runtimes)
if mode == 0:
    # 上电
    route_queue_put('Power', 'set_volt', voltage)

    log_queue.put(['at_log', '[{}] 检测驱动'.format(datetime.datetime.now())])
    # # 检测驱动
    # main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
    # if main_queue_data is False:
    #     print('检测驱动失败，开机失败，暂停脚本')
    #     pause()
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

    # 更新lowpower.manager类runtimes
    lowpower_manager.runtimes = runtimes

    if mode == 1:
        # 上电
        route_queue_put('Power', 'set_volt', voltage)
        start_time = time.time()

        log_queue.put(['at_log', '[{}] 检测驱动'.format(datetime.datetime.now())])
        # # 检测驱动
        # main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
        # if main_queue_data is False:
        #     print('检测驱动失败，开机失败，暂停脚本')
        #     pause()
        sleeping_time = time.time() - start_time

        # 等待100秒（通电之后100S）
        log_queue.put(['at_log', '[{}] 等待{}S'.format(datetime.datetime.now(), power_on_time)])
        time.sleep(power_on_time - sleeping_time)

        # 断电
        route_queue_put('Power', 'set_volt', 0)

        # 等待
        log_queue.put(['at_log', '[{}] 等待{}S'.format(datetime.datetime.now(), power_off_time)])
        time.sleep(power_off_time)
    else:
        high_volt = round(voltage * (1 + voltage_offset), 2)
        low_volt = round(voltage * (1 - voltage_offset), 2)

        # 高电压
        log_queue.put(['at_log', '[{}] 设置高电压'.format(datetime.datetime.now())])
        route_queue_put('Power', 'set_volt', high_volt)

        # 等待300S
        log_queue.put(['at_log', '[{}] 等待{}S'.format(datetime.datetime.now(), high_low_volt_last_time)])
        time.sleep(high_low_volt_last_time)

        log_queue.put(['at_log', '[{}] 检测驱动'.format(datetime.datetime.now())])
        # # 检测驱动
        # main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
        # if main_queue_data is False:
        #     print('检测驱动失败，开机失败，暂停脚本')
        #     pause()

        # 低电压
        log_queue.put(['at_log', '[{}] 设置低电压'.format(datetime.datetime.now())])
        route_queue_put('Power', 'set_volt', low_volt)

        # 等待300S
        log_queue.put(['at_log', '[{}] 等待{}S'.format(datetime.datetime.now(), high_low_volt_last_time)])
        time.sleep(high_low_volt_last_time)

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
