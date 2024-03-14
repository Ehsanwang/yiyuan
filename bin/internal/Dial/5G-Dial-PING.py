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
from dial_log_thread_ping import LogThread
from dial_modem_thread import ModemThread

"""
脚本逻辑：
1. 初始化开机，AT初始化，检查拨号模式和网络情况，等待网卡拨号功能加载成功后进行网络连接；
2. 检查电脑网络情况，模块找网；
3. PING网100次，记录发送的数据包，丢失的数据包，数据包时间等参数；
4. 重复2-3。
"""

"""
脚本准备
*手动禁止本地以太网
脚本接线方式参考VBAT。
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM47'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM14'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM12'  # 定义DM端口号,用于判断模块有无dump
modem_port = 'COM35'  # 定义MODEM端口号,用于检测拨号过程中网络状态信息
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
restart_mode = None  # 设置是否开关机，None：每个runtimes不进行开关机，1：每个runtimes进行VBAT开关机， 2：每个runtimes进行qpowd=1开关机
revision = 'RG502QEAAAR01A02M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V03'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
dial_mode = 'NDIS'  # 设置当前是MBIM拨号还是NDIS拨号
network_driver_name = 'RG500Q-EA'  # 如果拨号模式是NDIS，设置网卡名称'Quectel Generic'，如果MBIM，设置'Generic Mobile Broadband Adapter' 因为版本BUG的原因，MBIM拨号时候通常要设置为"RG500Q-EA"，根据实际加载情况设置
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
version = revision + sub_edition
ping_times = 100  # 默认每个runtimes ping 100次
ping_url = 'www.qq.com'  # 默认ping的网址
ping_4_6 = '-4'  # 设置是ping ipv4还是ipv6，取值'-4'，'-6'
ping_size = 1024  # 设置每次ping的大小
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
dial_info = '{}-{}'.format(dial_mode, 'PING')  # 脚本详情字符串
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
log_thread = LogThread(version, restart_mode, dial_info, log_queue, main_queue)
modem_thread = ModemThread(runtimes, log_queue, modem_port, modem_queue)
threads = [route_thread, uart_thread, process_thread, at_thread, log_thread, modem_thread]
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
dial_manager = DialManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, dial_mode, '',
                           '', '', '', '', '', restart_mode, network_driver_name, is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
dial_init_ping_status = dial_manager.dial_init_ping()
if dial_init_ping_status is False:  # 如果需要重新开始，运行re_init
    print('请手动关闭拨号自动连接，并检查AT+QCFG="USBNET"的返回值与脚本配置的dial_mode是否匹配(0: NDIS, 1: MBIM)，然后重新运行脚本')
    exit()
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

    # 进行各种开关机
    if restart_mode is not None:
        dial_init_ping_info = dial_manager.dial_init_ping()
        if dial_init_ping_info is False:
            dial_manager.dial_init_ping()
            continue

    # 检查和电脑IP的情况
    main_queue_data = route_queue_put('Process', 'check_ip_connect_status', dial_mode, network_driver_name, runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_ping()
        continue

    modem_thread.runtimes = runtimes

    # 打开AT口->进行网络检测->关闭AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        modem_thread.modem_flag = True
        dial_manager.dial_init_ping()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        modem_thread.modem_flag = True
        dial_manager.dial_init_ping()
        continue

    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        modem_thread.modem_flag = True
        dial_manager.dial_init_ping()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 查询统计还原次数
    main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_ping()
        continue

    # AT+QDMEM?分区内存泄露查询
    if restart_mode is None and runtimes % 50 == 0:
        time.sleep(2)
        route_queue_put('AT', 'memory_leak_monitoring', runtimes)

    # 温度查询
    main_queue_data = route_queue_put('AT', 'check_qtemp', runtimes)
    if main_queue_data is False:
        modem_thread.modem_flag = True
        dial_manager.dial_init_ping()
        continue

    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        modem_thread.modem_flag = True
        dial_manager.dial_init_ping()
        continue

    # 进行PING连接
    main_queue_data = route_queue_put('Process', 'ping', ping_url, ping_times, ping_4_6, ping_size, runtimes)
    if main_queue_data is False:
        modem_thread.modem_flag = True
        dial_manager.dial_init_ping()
        continue

    modem_thread.modem_flag = True  # modem口停止网络状态check
    time.sleep(1)

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
