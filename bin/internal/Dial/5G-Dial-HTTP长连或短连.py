# -*- encoding=utf-8 -*-
import random
import string
import time
import signal
import logging
from sys import path
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
from dial_log_thread_http import LogThread
from dial_ping_thread import PingThread
from dial_modem_thread import ModemThread

"""
脚本逻辑：
1. 初始化开机，AT初始化，检查拨号模式和网络情况，等待网卡拨号功能加载成功后断开网络连接；
2. 进行NDIS/MBIM连接
3. HTTP_Post上传文件,HTTP_Get下载文件(目前浏览器协议都默认发起Keep_Alive连接请求，所以不考虑协议短连)
4. 断开TCP连接后断开NDIS/MBIM连接。
5. 长连循环执行3;
6. 短连循环执行2-4。
"""

"""
脚本准备
M.2: PWRKEY置高，飞线连接P_EN和DTR
5G_EVB_V2.2: 短接PWRKEY_3.3V和RTS，短接3.8V_EN和DTR
*手动禁止本地以太网
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM10'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM14'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM13'  # 定义DM端口号,用于判断模块有无dump
modem_port = 'COM16'  # 定义MODEM端口号,用于检测拨号过程中网络状态信息
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RG500QEAAAR01A01M4G_BETA_20200518H'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号ct
dial_mode = 'MBIM'  # 设置当前是MBIM拨号还是NDIS拨号
network_driver_name = 'RG500Q-EA'  # 如果拨号模式是NDIS，设置网卡名称'Quectel Generic'，如果MBIM，设置'Generic Mobile Broadband Adapter' 因为版本BUG的原因，MBIM拨号时候通常要设置为"RG500Q-EA"，根据实际加载情况设置
server_url = 'http://220.180.239.212:8300/upload.php'  # HTTP上传文件URL
server_remove_file_url = 'http://220.180.239.212:8300/remove_file.php'  # HTTP删除文件URL
server_ip_port = "220.180.239.212:8300"  # HTTP(s)套接字
connection_mode = 1  # 0代表长连,1代表短连
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
file_size = 100  # 文件大小，以K为单位
# ======================================================================================================================
# 辅助参数
version = revision + sub_edition
# 生成文件
send_data = ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation, k=1024 * file_size))
with open('send.txt', 'w', encoding='utf-8', buffering=1) as f:
    f.write(send_data + '\n')
source_name = 'send.txt'
receive_file_name = 'recv.txt'
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
dial_info = '{}-{}-{}'.format(dial_mode, "HTTP", '短连' if connection_mode == 1 else '长连')  # 脚本详情字符串
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
    route_queue_put('end_script', script_start_time, 'http', runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
dial_manager = DialManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, dial_mode,
                           connection_mode, '_', '_', '_', '', '', '', network_driver_name, '', runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
dial_http_init_status = dial_manager.dial_http_init()
if dial_http_init_status is False:
    print("脚本初始化失败，请检查后重新运行脚本")
    exit()
# ======================================================================================================================
# 主流程
while True:
    # 脚本自动停止判断
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or (timing != 0 and time.time() - script_start_time > timing * 3600):  # 如果runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
        route_queue_put('end_script', script_start_time, 'http', runtimes - 1, queue=log_queue)  # 结束脚本统计log
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
            dial_manager.dial_http_init()
            continue

    # 检查和电脑IP的情况
    main_queue_data = route_queue_put('Process', 'check_ip_connect_status', dial_mode, network_driver_name, runtimes)
    if main_queue_data is False:
        dial_manager.dial_http_init()
        continue

    ping_thread.runtimes = runtimes  # 连接成功后开始ping的标志
    modem_thread.runtimes = runtimes

    # 打开AT口->进行网络检测->关闭AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_http_init()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_http_init()
        continue

    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_http_init()
        continue

    # 温度查询
    main_queue_data = route_queue_put('AT', 'check_qtemp', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_http_init()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_http_init()
        continue

    # 进行HTTP_Get_Post文件操作
    main_queue_data = route_queue_put('Process', 'http_post_get', server_url,
                                      server_remove_file_url,
                                      server_ip_port,
                                      source_name,
                                      receive_file_name,
                                      runtimes)

    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        dial_manager.dial_http_init()
        continue

    ping_thread.df_flag = True  # ping写入log
    time.sleep(1)  # 等待ping log
    modem_thread.modem_flag = True  # modem口停止网络状态check

    # 断开拨号连接
    if connection_mode == 1:
        main_queue_data = route_queue_put('Process', 'disconnect', runtimes)
        if main_queue_data is False:
            dial_manager.dial_http_init()
            continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
