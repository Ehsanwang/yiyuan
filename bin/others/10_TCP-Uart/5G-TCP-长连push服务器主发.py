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
from process_thread import ProcessThread
from queue import Queue
from threading import Event
from tcp_log_recv_thread import LogThread

"""
脚本逻辑：
1. 初始化开机，AT初始化。
2. 检查模块基本信息，注网信息及模块温度等；
3. 建立TCP透传连接；
4. 发送数据；
5. 检查所发送数据是否正常；
5. 长连重复4-5；
6. 短连重复3-5。
"""

"""
环境准备：
1. EVB跳线连接；
    PCIE-CARD: PWRKEY置高，飞线连接P_EN和DTR引脚；
    5G-EVB: 短接PWRKEY_3.3V和RTS，3.8V_EN和DTR。
    打开QserverTCP连接，IP填写本机IP，端口填写自己的端口，服务开启成功后Default Auto Reply置Enable,Auto Send中Target选择Broadcast设置时间及次数后点击Auto Send
    运行前设置上报口为uart口，设置指令AT+QURCCFG="URCPORT","uart1"并重启模块
"""

# ======================================================================================================================
# 需要配置的参数
at_port = 'COM22'  # 定义AT端口号,用于发送AT指令或检测URC信息
revision = 'RG502QEAAAR11A02M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V05'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
server_ip = '220.180.239.212'  # Server地址
server_port = 9161  # TCP或UDP端口
wait_time = 10  # 设置一次接收完后等待多久进行下一次接受服务器下发数据，与Qserver中Interval设置时间保持一致。
send_data = '01234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789'  # 定义服务器所下发数据，与Qserver发送框中内容保持一致。
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 24   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
version = revision + sub_edition
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
dm_port = ''  # 定义DM端口号,用于判断模块有无dump
uart_port = ''  # 定义串口号,用于控制DTR引脚电平或检测URC信息
access_mode = 1    # 1：非透传Push模式
runtimes = 0
connection_mode = 0  # 0代表长连,1代表短连
connection_type = "TCP"
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
tcp_info = '{}-{}-服务器主发非透传Push'.format(connection_type, '短连' if connection_mode == 1 else '长连')  # 脚本详情字符串
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
logger = logging.getLogger(__name__)
# ======================================================================================================================
# 定义queue并启动线程
main_queue = Queue()
route_queue = Queue()
process_queue = Queue()
at_queue = Queue()
log_queue = Queue()
route_thread = RouteThread(route_queue, process_queue, at_queue)
process_thread = ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, tcp_info, log_queue, connection_mode, False, main_queue)
threads = [route_thread, process_thread, at_thread, log_thread]
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
dial_manager = TcpUdpManager(main_queue, route_queue, log_queue, uart_port, version, imei, connection_mode, access_mode, connection_type, server_ip, server_port, '', '', '', '', runtimes)
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
        # dial_manager.dial_init_tcp_reboot()
        continue

    # 检测模块信息 IMEI、CFUN、CPIN
    main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
    if main_queue_data is False:
        # dial_manager.dial_init_tcp_reboot()
        continue

    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        # dial_manager.dial_init_tcp_reboot()
        continue

    # 温度查询
    main_queue_data = route_queue_put('AT', 'check_qtemp', runtimes)
    if main_queue_data is False:
        # dial_manager.dial_init_tcp_reboot()
        continue

    # 长连第一次连接服务器
    if runtimes == 1:
        main_queue_data = route_queue_put('AT', 'client_connect', connection_type, server_ip, server_port, access_mode, runtimes)
        if main_queue_data is False:
            # dial_manager.dial_init_tcp_reboot()
            continue

    # 确认数据是否正常
    main_queue_data = route_queue_put('AT', 'recvdata_compare', access_mode, send_data, connection_mode, wait_time, runtimes)
    if main_queue_data is False:
        # dial_manager.dial_init_tcp_reboot()
        continue

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        # dial_manager.dial_init_tcp_reboot()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
