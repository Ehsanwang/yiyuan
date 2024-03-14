# -*- encoding=utf-8 -*-
import time
import signal
from sys import path
import logging
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'Dial'))
from functions import environment_check
environment_check()  # 检查环境
from dial_manager import DialManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from dial_process_thread import DialProcessThread
from queue import Queue
from threading import Event
from dial_log_thread_speedtest import LogThread
from dial_ping_thread import PingThread
from dial_modem_thread import ModemThread
"""
脚本准备
Windows:
*手动禁止本地以太网，或者直接拔掉网线

脚本有以下参数配置
Windows:
    1. 使用MBIM或者NDIS拨号进行speedtest短连测试
        dial_mode = 'NDIS' / dial_mode = 'MBIM'
        restart_mode = None
        connection_mode = 1
    2. 使用MBIM或者NDIS拨号进行speedtest长连测试
        dial_mode = 'NDIS' / dial_mode = 'MBIM'
        restart_mode = None
        connection_mode = 0
    3. 使用RGMII拨号进行speedtest长连测试，RGMII拨号前需要配置好对应的RGMII拨号参数
        dial_mode = 'RGMII'
        restart_mode = None
        connection_mode = 0
    4. 使用MBIM、NDIS或RGMII拨号，每个runtimes重启进行speedtest短连测试
        dial_mode = 'NDIS' / dial_mode = 'MBIM'
        restart_mode = 1  # 1: 使用vbat进行关机，飞线按照开关机VBAT方式，2：使用AT+QPOWD=1进行关机，飞线按照开关机QPOWD1方式
        connection_mode = 1
Linux：
    1. 进行ECM或者WWAN或者GOBINET拨号长连测试：
        dial_mode = 'ECM' / dial_mode = 'WWAN' / dial_mode = 'GOBINET'
        restart_mode = None
        connection_mode = 0
    2. 使用ECM或者WWAN或者GOBINET拨号，每个runtimes重启进行speedtest测试
        dial_mode = 'ECM' / dial_mode = 'WWAN' / dial_mode = 'GOBINET'
        restart_mode = 1  # 1: 使用vbat进行关机，飞线按照开关机VBAT方式，2：使用AT+QPOWD=1进行关机，飞线按照开关机QPOWD1方式
        connection_mode = 0
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = ''  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = ''  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = ''  # 定义DM端口号,用于判断模块有无dump
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
modem_port = ''  # 定义MODEM端口号,用于检测拨号过程中网络状态信息
restart_mode = None  # 设置是否开关机，None：每个runtimes不进行开关机，1：每个runtimes进行VBAT开关机， 2：每个runtimes进行qpowd=1开关机
revision = 'RM502QGLAAR11A01M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V05'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '355878110021656'  # 模块测试前配置IMEI号
dial_mode = 'WWAN'  # 设置拨号方式 Windows: NDIS/MBIM/RGMII  LINUX: WWAN/MBIM/GOBINET/ECM
connection_mode = 1  # 0代表长连,1代表短连
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
interval = 10800  # 设置speedtest运行的间隔时间，单位为秒，speedtest停止运行的时候ping依然会继续
# ======================================================================================================================
# 辅助参数
runtimes = 0
version = revision + sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
dial_info = 'Speedtest-{}-{}'.format(dial_mode, '短连' if connection_mode == 1 else '长连')  # 脚本详情字符串
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
logger = logging.getLogger(__name__)
# ======================================================================================================================
# 定义queue并启动线程
main_queue = Queue()
route_queue = Queue()
uart_queue = Queue()
process_queue = Queue()
at_queue = Queue()
log_queue = Queue()
modem_queue = Queue()
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
process_thread = DialProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, dial_info, connection_mode, log_queue, main_queue)
ping_thread = PingThread(runtimes, log_queue)
modem_thread = ModemThread(runtimes, log_queue, modem_port, modem_queue)
threads = [route_thread, uart_thread, process_thread, at_thread, log_thread, ping_thread, modem_thread]
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
dial_manager = DialManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, dial_mode, connection_mode, '', '', '', '', '', restart_mode, runtimes)
# log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
# print("\rinitialize", end="")
# dial_init_speedtest_status = dial_manager.dial_init_speedtest()
# if dial_init_speedtest_status is False:  # 如果需要重新开始，运行re_init
#     print('请手动关闭拨号自动连接，并检查AT+QCFG="USBNET"的返回值与脚本配置的dial_mode是否匹配(0: NDIS, 1: MBIM)，然后重新运行脚本')
#     exit()
# ======================================================================================================================
# 主流程
while True:
    # 脚本自动停止判断
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or (timing != 0 and time.time() - script_start_time > timing * 3600):  # 如果runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
        route_queue_put('end_script', script_start_time, runtimes - 1, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    dial_manager.runtimes = runtimes

    if connection_mode == 1:
        if os.name == 'nt':
            # 用win api进行连接
            main_queue_data = route_queue_put('Process', 'connect', dial_mode, runtimes)
            if main_queue_data is False:
                continue
            # 检查和电脑IP的情况
            main_queue_data = route_queue_put('Process', 'check_ip_connect_status', dial_mode, runtimes)
            if main_queue_data is False:
                continue
        elif os.name == 'posix':
            if dial_mode.upper() == 'WWAN':
                main_queue_data = route_queue_put('Process', 'wwan_connect_check', runtimes)
                if main_queue_data is False:
                    continue
            elif dial_mode.upper() == 'GOBINET':
                main_queue_data = route_queue_put('Process', 'gobinet_connect_check', runtimes)
                if main_queue_data is False:
                    continue
            elif dial_mode.upper() == 'MBIM':
                main_queue_data = route_queue_put('Process', 'mbim_connect_check', runtimes)
                if main_queue_data is False:
                    continue
    elif connection_mode == 0 and runtimes == 1:
        if os.name == 'posix':
            if dial_mode.upper() == 'WWAN':
                main_queue_data = route_queue_put('Process', 'wwan_connect_check', runtimes)
                if main_queue_data is False:
                    continue
            elif dial_mode.upper() == 'GOBINET':
                main_queue_data = route_queue_put('Process', 'gobinet_connect_check', runtimes)
                if main_queue_data is False:
                    continue
            elif dial_mode.upper() == 'MBIM':
                main_queue_data = route_queue_put('Process', 'mbim_connect_check', runtimes)
                if main_queue_data is False:
                    continue

    ping_thread.runtimes = runtimes  # 连接成功后开始ping的标志
    modem_thread.runtimes = runtimes

    # 进行Speedtest测速
    main_queue_data = route_queue_put('Process', 'speed_test', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_init_speedtest()
        continue

    time.sleep(interval)  # 设置每个runtimes的间隔
    ping_thread.df_flag = True  # ping写入log
    time.sleep(1)  # 等待ping log
    modem_thread.modem_flag = True  # modem口停止网络状态check

    # 短连断开连接
    if connection_mode == 1:
        if os.name == 'nt':   # windows下短拨断开拨号
            main_queue_data = route_queue_put('Process', 'disconnect', runtimes)
            if main_queue_data is False:
                dial_manager.dial_init_speedtest()
                continue
        elif os.name == 'posix':  # linux下短拨断开拨号
            main_queue_data = route_queue_put('Process', 'disconnect_dial', dial_mode, runtimes)
            if main_queue_data is False:
                dial_manager.dial_init_speedtest()
                continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
