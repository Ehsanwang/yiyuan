# -*- encoding=utf-8 -*-
import random
import string
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
from dial_log_thread_ftp import LogThread
from dial_ping_thread import PingThread
from dial_modem_thread import ModemThread


"""
脚本准备
M.2: PWRKEY置高，飞线连接P_EN和DTR
5G_EVB_V2.2: 短接PWRKEY_3.3V和RTS，短接3.8V_EN和DTR
*手动禁止本地以太网
"""

"""
关于服务器：
1. 跑FTP先上传后下载的脚本，需要使用  58.40.120.14 服务器，用户名 test、密码test
2. 跑FTP上下同传的脚本，需要使用 \\Standard\\bin\\others\\01_ftp_server下的ftp.py脚本搭建的服务器运行。
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM3'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM14'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM15'  # 定义DM端口号,用于判断模块有无dump
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
modem_port = 'COM12'  # 定义MODEM端口号,用于检测拨号过程中网络状态信息
revision = 'RM502QGLAAR05A03M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V02'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
dial_mode = 'NDIS'  # 设置当前是MBIM拨号还是NDIS拨号  0:NDIS 1:MBIM
network_driver_name = 'RG500Q-EA'  # 如果拨号模式是NDIS，设置网卡名称'Quectel Generic'，如果MBIM，设置'Generic Mobile Broadband Adapter' 因为版本BUG的原因，MBIM拨号时候通常要设置为"RG500Q-EA"，根据实际加载情况设置
ftp_addr = '58.40.120.14'  # ftp服务器地址
server_port = 21  # FTP端口
ftp_usr_name = "test"  # FTP服务器用户名
ftp_password = "test"  # FTP服务器密码
ftp_path = "."  # 要上传或下载的文件对应的FTP目录，！路径最右不能有右斜杠
connection_mode = 0  # 0代表长连,1代表短连
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
file_size = 1000  # 自动创建的文件大小，以K为单位
# !!!公司 58.40.120.14 FTP服务器版本过老，不支持max_parallel参数，请设置为0
# 使用max_parallel参数的时候connection_mode参数需要设置为0
max_parallel = 0  # 最大并行数，设置为0：先上传后下载; 设置为1：上传的同时进行下载；设置为>1：n路同时进行上传下载
# ======================================================================================================================
# 辅助参数
os.mkdir(os.path.join(os.getcwd(), 'cache')) if not os.path.exists(os.path.join(os.getcwd(), 'cache')) else None
os.mkdir(os.path.join(os.getcwd(), 'cache', 'download')) if not os.path.exists(os.path.join(os.getcwd(), 'cache', 'download')) else None
send_data = ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=1024 * file_size))
local_file = "data.txt"  # 本地源文件名称
with open(os.path.join(os.path.join(os.getcwd(), 'cache'), local_file), 'w', encoding='utf-8', buffering=1) as f:
    f.write(send_data + '\n')
version = revision + sub_edition
local_file_path = os.path.join(os.getcwd(), 'cache', local_file)  # 本地源文件路径
local_base_path = os.path.dirname(local_file_path)  # 本地不带文件名的路径名称
ftp_file_path = '{}/{}'.format(ftp_path, local_file) if not ftp_path.endswith('/') else '{}{}'.format(ftp_path, local_file)  # FTP文件路径
local_target_file_path = os.path.join(os.getcwd(), 'cache', 'download', local_file)  # 本地目标文件路径
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
dial_info = '{}-FTP-{}'.format(dial_mode, '短连' if connection_mode == 1 else '长连')  # 脚本详情字符串
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
runtimes = 0
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
    route_queue_put('end_script', script_start_time, 'FTP', runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
dial_manager = DialManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, dial_mode,
                           connection_mode, "FTP", ftp_addr, server_port, ftp_usr_name, ftp_password, '',
                           network_driver_name, '', runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
dial_init_ftp_status = dial_manager.dial_init_ftp()
if dial_init_ftp_status is False:  # 如果需要重新开始，运行re_init
    print('请手动关闭拨号自动连接，并检查AT+QCFG="USBNET"的返回值与脚本配置的dial_mode是否匹配(0: NDIS, 1: MBIM)，然后重新运行脚本')
    exit()
# ======================================================================================================================
# 主流程
while True:
    # 脚本自动停止判断
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or (timing != 0 and time.time() - script_start_time > timing * 3600):  # 如果runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
        route_queue_put('end_script', script_start_time, 'FTP', runtimes, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    dial_manager.runtimes = runtimes

    if connection_mode == 1:
        # 用win api进行连接
        main_queue_data = route_queue_put('Process', 'connect', dial_mode, runtimes)
        if main_queue_data is False:
            dial_manager.dial_init_ftp()
            continue

    # 检查和电脑IP的情况
    main_queue_data = route_queue_put('Process', 'check_ip_connect_status', dial_mode, network_driver_name, runtimes)
    if main_queue_data is False:
        dial_manager.dial_init_ftp()
        continue

    # 连接成功后开始ping的标志
    ping_thread.runtimes = runtimes
    modem_thread.runtimes = runtimes

    # 打开AT口->进行网络检测->关闭AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_init_ftp()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_init_ftp()
        continue

    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_init_ftp()
        continue

    # 温度查询
    main_queue_data = route_queue_put('AT', 'check_qtemp', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_init_ftp()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_init_ftp()
        continue

    if max_parallel == 0:  # 普通的FTP
        # 进行FTP连接
        if connection_mode == 1:
            main_queue_data = route_queue_put('Process', 'ftp_connect', connection_mode, dial_mode, ftp_addr, server_port, ftp_usr_name, ftp_password, runtimes)
            if main_queue_data is False:
                ping_thread.df_flag = True  # ping写入log
                modem_thread.modem_flag = True
                dial_manager.dial_init_ftp()
                continue

        # ftp文件上传下载,对比数据
        main_queue_data = route_queue_put('Process', 'ftp_send_recv_compare', dial_mode, local_file_path, local_file, ftp_file_path, ftp_path, local_target_file_path, runtimes)
        if main_queue_data is False:
            ping_thread.df_flag = True  # ping写入log
            modem_thread.modem_flag = True
            dial_manager.dial_init_ftp()
            continue
    else:  # 协程FTP
        if runtimes == 1:  # runtimes = 1的时候需要在服务器和本地准备文件
            route_queue_put('Process', 'server_file_prepare', ftp_addr, server_port, ftp_usr_name, ftp_password, local_file, local_base_path, ftp_path, max_parallel, runtimes)
            route_queue_put('Process', 'local_file_prepare', local_file, local_base_path, runtimes)

        main_queue_data = route_queue_put('Process', 'async_ftp', ftp_addr, server_port, ftp_usr_name, ftp_password, local_file, local_base_path, ftp_path, runtimes)
        if main_queue_data is False:
            ping_thread.df_flag = True  # ping写入log
            modem_thread.modem_flag = True
            dial_manager.dial_init_ftp()
            continue

    ping_thread.df_flag = True  # ping写入log
    time.sleep(1)  # 等待ping log
    modem_thread.modem_flag = True  # modem口停止网络状态check

    if connection_mode == 1 and max_parallel == 0:  # 短连并且是普通的FTP非协程FTP
        # 断开ftp连接
        main_queue_data = route_queue_put('Process', 'ftp_disconnect', runtimes)
        if main_queue_data is False:
            dial_manager.dial_init_ftp()
            continue

    if connection_mode == 1:  # 如果是短连
        # 断开拨号连接
        main_queue_data = route_queue_put('Process', 'disconnect', runtimes)
        if main_queue_data is False:
            dial_manager.dial_init_ftp()
            continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
