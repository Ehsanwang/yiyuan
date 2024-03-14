# -*- encoding=utf-8 -*-
import os
from queue import Queue
from threading import Event
import time
import signal
import logging
from sys import path
from types import coroutine
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'PowerOnOff'))
from functions import environment_check, VOICEAPPThread
environment_check()  # 检查环境
from restart_manager import RestartManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from power_on_off_log_thread import LogThread
import datetime

## 注意试项
# 1. Python3.8或以上环境运行
# 2. 用语音多的套餐,避免欠费
# 3. loopback_test重新编译
#       a. 修改loopback_test.c文件中/dev/ttyUSB1为NEMA口，NEMA口为驱动加载后第二个口，不清晰的查询，注意修改下面的ttyUSB3为加载的口，返回值应改为01 ATTRS{bInterfaceNumber}=="01"
#        udevadm info --attribute-walk --path=$(udevadm info --query=path --name=/dev/ttyUSB3) | grep ATTRS{bInterfaceNumber}
#       b. sudo make clean
#       c. sudo make
# 4. 需要辅助机器，辅助机器用作接听电话，开启自动接听，本机用作拨打电话

## 逻辑
# 发送AT+QPCMV=1,0
# 启动开发提供APP
# 开启电话URC上报，打电话，检测通话接通，接通后检查DUMP20S
# 未DUMP，跳转4
# DUMP，kill开发提供程序，Qlog抓取log后模块重启继续第二步

# ======================================================================================================================
# 必选参数
uart_port = '/dev/ttyUSB0'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = '/dev/ttyUSBAT'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = '/dev/ttyUSBDM'  # 定义DM端口号,用于判断模块有无dump
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
assist_phone = r'17884496969'  # 设置辅助机的手机号，用来接收电话
qlog_path = r'/home/flynn/Downloads/Quectel_QLog_Linux&Android_V1.4.17/QLog'  # 填写机器Qlog的安装路径，QLog需要编译首先编译，然后chmod 777 loopback_test
loopback_path = r'/home/flynn/Downloads/voice_over_usb_pcie'  # 填写开发提供的voice_over_usb_pcieAPP的路径，需要事先编译，然后chmod 777 loopback_test
evb = 'EVB'  # RG默认evb参数为EVB，RM默认evb参数为M.2
# ======================================================================================================================
# 可选参数
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 其他参数
runtimes = 0
logger = logging.getLogger(__name__)
version = "TEST"
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
# ======================================================================================================================
# 定义queue并启动线程
main_queue, route_queue, uart_queue, process_queue, at_queue, log_queue = (Queue() for i in range(6))
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
process_thread = ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, 'voice_over_usb', log_queue, main_queue)
threads = [route_thread, uart_thread, process_thread, at_thread, log_thread]
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
    log_queue.put(['df', runtimes, 'error', 1]) if _main_queue_data is False else ''
    return _main_queue_data


# 脚本结束，进行结果统计
def handler(signal_num, frame=None):  # noqa
    """
    脚本结束参数统计。
    """
    route_queue_put('end_script', script_start_time, runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
restart_manager = RestartManager(main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port, evb, version, runtimes)
restart_manager.init()  # 开关机各种方式初始化
# ======================================================================================================================
# DataFrame的统一格式['df', runtimes, column_name, content]
# log内容不需要使用route_queue_put，因为写入log的时候不需要Event()
# 主流程
while True:
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致

    # 脚本自动停止判断:
    # runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or \
            (timing != 0 and time.time() - script_start_time > timing * 3600):
        route_queue_put('end_script', script_start_time, runtimes - 1, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['loopback_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符

    # 将最新的runtimes写入类中
    restart_manager.runtimes = runtimes

    # 启动voice_over_usb_pcie
    voice_app = VOICEAPPThread(loopback_path, log_queue)

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        restart_manager.init()
        continue

    # 开启电话URC上报 -> 打电话 -> 检测通话接通 -> 接通后20S
    route_queue_put('AT', 'dial_assist', assist_phone, runtimes)

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        restart_manager.init()
        continue

    # 检查DUMP
    dump = route_queue_put('Process', 'check_dump_voice', runtimes)

    # DUMP -> kill开发提供程序 -> Qlog抓取log -> 检测模块开机 -> 检测URC -> 检测找网 —> 发送AT+QPCMV=1,0 -> 启动开发提供的APP
    if dump:
        voice_app.terminate()
        route_queue_put('Process', 'qlog_catch_dump', qlog_path, runtimes)
        restart_manager.init()

    else:
        log_queue.put(['at_log', '[{}] 等待5S进行下一轮测试'.format(datetime.datetime.now())])
        time.sleep(5)

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
