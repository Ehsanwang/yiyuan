# -*- encoding=utf-8 -*-
import time
import signal
import logging
from sys import path
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'TCPUDP'))
from functions import environment_check
environment_check()  # 检查环境
from tcp_udp_manager import TcpUdpManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from queue import Queue
from threading import Event
from tcp_many_send_recv_log import LogThread

"""
脚本逻辑：
1. 初始化开机，AT初始化。
2. 检查模块基本信息，注网信息及模块温度等；
3. 建立多路TCP连接；
4. 发送数据；
5. 检查所发送数据是否正常；
5. 重复4-5；
"""

"""
环境准备：
1. EVB跳线连接；
    PCIE-CARD: PWRKEY置高，飞线连接P_EN和DTR引脚；
    5G-EVB: 短接PWRKEY_3.3V和RTS，3.8V_EN和DTR。
    注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
    打开QserverTCP连接，IP填写本机IP，端口填写自己的端口，服务开启成功后Default Auto Reply置Enable
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM26'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM4'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM6'  # 定义DM端口号,用于判断模块有无dump
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RG500QEAAAR11A03M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
server_ip = '220.180.239.212'  # Server地址
server_port = 9161  # TCP或UDP端口
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 24   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
version = revision + sub_edition
is_continue = 1     # 设置是否某一模式完成直接进行下一模式，0否1是，若设置1则必须设置运行时间，若设置24H则两种模式分别运行12H
runtimes = 0
connection_type = "TCP"
connection_mode = 0  # 0代表长连,1代表短连
access_mode = 0    # 0:非透传 Buffer 模式, 1:非透传 Push 模式
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
tcp_info = '{}-{}-{}'.format(connection_type, '短连' if connection_mode == 1 else '长连', '非透传Buffer模式' if access_mode == 0 else '非透传push模式')  # 脚本详情字符串
logger = logging.getLogger(__name__)
# ======================================================================================================================
# 定义queue并启动线程
main_queue = Queue()
route_queue = Queue()
uart_queue = Queue()
process_queue = Queue()
at_queue = Queue()
log_queue = Queue()
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
process_thread = ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, tcp_info, log_queue, connection_mode, False, main_queue)
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
dial_manager = TcpUdpManager(main_queue, route_queue, uart_queue, log_queue, uart_port, version, imei, connection_mode,
                             access_mode, connection_type, server_ip, server_port, 0, 0, '', 0, is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
dial_init_status = dial_manager.dial_init_tcp()
if dial_init_status is False:  # 如果需要重新开始，运行re_init
    exit()
start_transfer_time = time.time()
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

    # 打开AT口->进行网络检测->关闭AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_many_tcp_reboot()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_many_tcp_reboot()
        continue

    # 检测模块信息 IMEI、CFUN、CPIN
    main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_many_tcp_reboot()
        continue

    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_many_tcp_reboot()
        continue

    # 温度查询
    main_queue_data = route_queue_put('AT', 'check_qtemp', runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_many_tcp_reboot()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 查询统计还原次数
    main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_many_tcp_reboot()
        continue

    # AT+QDMEM?分区内存泄露查询
    if runtimes % 50 == 0:
        time.sleep(2)
        route_queue_put('AT', 'memory_leak_monitoring', runtimes)

    if runtimes == 1 and connection_mode == 0:    # 长连只在第一次进行连接，连接后无需执行QICLOSE
        # 进行TCP非透传buffer连接
        if access_mode == 0:
            main_queue_data = route_queue_put('AT', 'many_client_connect', connection_type, server_ip, server_port, access_mode, runtimes)
            if main_queue_data is False:
                dial_manager.dial_init_many_tcp_reboot()
                continue
        elif access_mode == 1:  # 进行非透传push连接
            main_queue_data = route_queue_put('AT', 'many_client_connect', connection_type, server_ip, server_port, access_mode, runtimes)
            if main_queue_data is False:
                dial_manager.dial_init_many_tcp_reboot()
                continue
    if connection_mode == 1:    # 短连，每次都需要重新连接，每次需要执行QICLOSE
        if access_mode == 0:    # 进行TCP非透传buffer连接
            main_queue_data = route_queue_put('AT', 'many_client_connect', connection_type, server_ip, server_port, access_mode, runtimes)
            if main_queue_data is False:
                dial_manager.dial_init_many_tcp_reboot()
                continue
        if access_mode == 1:    # 进行TCP非透传push连接
            main_queue_data = route_queue_put('AT', 'many_client_connect', connection_type, server_ip, server_port, access_mode, runtimes)
            if main_queue_data is False:
                dial_manager.dial_init_many_tcp_reboot()
                continue

    # 发送接收对比数据
    main_queue_data = route_queue_put('AT', 'many_client_send_recv_compare', connection_mode, runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_many_tcp_reboot()
        continue

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_many_tcp_reboot()
        continue

    time.sleep(60)  # 参考LTE每次之间等待一段时间（60秒）

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
