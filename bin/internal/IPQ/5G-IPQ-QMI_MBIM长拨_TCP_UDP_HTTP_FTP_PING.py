# -*- encoding=utf-8 -*-
from queue import Queue
from threading import Event
import time
import signal
import logging
from sys import path
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'IPQ'))
path.append(os.path.join('..', '..', '..', 'lib', 'Dial'))
from functions import environment_check
environment_check()  # 检查环境
from ipq_manager import IPQManager
from ipq_route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from ipq_qmi_log_thread import LogThread
from ipq_power_thread import PowerThread
from ipq_process_thread import IPQProcessThread
from dial_ping_thread import PingThread

"""
脚本逻辑
PCIE-QMI/MBIM长拨+TCP+UDP+HTTP+FTP+PING
初始化：
1、at+qcfg="data_interface",1,0 IPQ和模块整机重启
2、QMI或者MBIM长拨
3、等待1000s,人手动登录192.168.1.1网站设置wan和wan6的physical Settings
主流程：
1、注网和温度检查
2、进行多种协议测试
3、循环step1-2

"""

"""
脚本准备：
vbat短接

备注：脚本拨号成功后需人手动登录192.168.1.1网站设置wan和wan6的physical Settings
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM41'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM23'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM24'  # 定义DM端口号,用于判断模块有无dump
power_port = 'COM47'  # 定义程控电源端口口,用于控制程控电源
ipq_port = 'COM40'  # 定义ipq的端口号，用于检测PCIE驱动加载情况
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RG500QEAAAR11A05M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V02'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
ipq_mode = 0       # ipq设备型号 0: 8074  1:4019
imei = '869710030002905'  # 模块测试前配置IMEI号
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
debug = False  # 设置脚本遇到异常是停止还是继续运行False：继续运行；True：停止脚本
dial_mode = 'QMI'  # QMI:QMI拨号 MBIM：MBIM拨号
config = {
    # 自动创建的文件大小(K)
    'file_size': 1000,
    # TCP
    'tcp_server': '220.180.239.212',
    'tcp_port': 8305,
    # UDP
    'udp_server': '220.180.239.212',
    'udp_port': 8305,
    # FTP
    'ftp_server': '58.40.120.14',
    'ftp_port': 21,
    'ftp_username': 'test',
    'ftp_password': 'test',
    'ftp_path': 'flynn',
    # HTTP
    'http_server_url': 'http://220.180.239.212:8300/upload.php',
    'http_server_remove_url': 'http://220.180.239.212:8300/remove_file.php',
    'http_server_ip_port': '220.180.239.212:8300'
}
# ======================================================================================================================
# 辅助参数
version = revision + sub_edition
lspci_check_value = ['17cb:1001', '17cb:0306'] if ipq_mode == 1 else ['17cb:1002', '17cb:0306']    # 不同的版本可能需要调整此参数，此参数参照pcie驱动加载成功后的lspci指令返回值
ipq_poweron_message = 'entered forwarding state' if ipq_mode == 1 else 'IPQCM Quitting'
dial_check_message = 'udhcpc: setting default routers' if dial_mode == 'QMI' else 'system(ip -4 link'
ls_dev_mhi_check_value = ['/dev/mhi_BHI', '/dev/mhi_DUN', '/dev/mhi_QMI0', '/dev/mhi_DIAG', '/dev/mhi_LOOPBACK'] if dial_mode == 'QMI' else ['/dev/mhi_BHI', '/dev/mhi_DUN', '/dev/mhi_MBIM', '/dev/mhi_DIAG', '/dev/mhi_LOOPBACK']
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
ipq_info = '5G-IPQ-QMI(MBIM)长拨_TCP_UDP_HTTP_FTP_PING'   # 脚本详情字符串
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
power_queue = Queue()
ipq_queue = Queue()
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue, power_queue, ipq_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
process_thread = ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, ipq_info, log_queue, main_queue)
power_thread = PowerThread(power_port, power_queue, main_queue, log_queue)
ipq_process_thread = IPQProcessThread(ipq_port, ipq_queue, log_queue, main_queue)
ping_thread = PingThread(runtimes, log_queue)
threads = [route_thread, uart_thread, process_thread, at_thread, log_thread, power_thread, ipq_process_thread,
           ping_thread]
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
ipq_manager = IPQManager(main_queue, route_queue, uart_queue, at_queue, log_queue, power_queue, at_port, uart_port, evb, version, imei, lspci_check_value, ls_dev_mhi_check_value, debug, ipq_poweron_message, dial_mode, ipq_mode, dial_check_message, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
ipq_manager.ipq_pcie_qmi_MBIM_init()  # IPQ初始化
ipq_manager.ipq_pcie_qmi_mbim()  # qmi或者MBIm拨号
print("等待1000s人工登录192.168.1.1网站设置wan和wan6的physical Settings")
time.sleep(00)  # 给1000s等待人工登录192.168.1.1网站设置wan和wan6的physical Settings
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
    log_queue.put(['ipq_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # ipq_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符

    # 将最新的runtimes写入类中
    ipq_manager.runtimes = runtimes
    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        ipq_manager.ipq_qmi_mbim_re_init()
        continue
    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        ipq_manager.ipq_qmi_mbim_re_init()
        continue
    # 网络检查
    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        ipq_manager.ipq_qmi_mbim_re_init()
        continue

    # 温度查询
    main_queue_data = route_queue_put('AT', 'check_qtemp', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        ipq_manager.ipq_qmi_mbim_re_init()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 查询统计还原次数
    main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
    if main_queue_data is False:
        ipq_manager.ipq_qmi_mbim_re_init()
        continue

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        ipq_manager.ipq_qmi_mbim_re_init()
        continue

    # 进行多种协议测试
    main_queue_data = route_queue_put('Process', 'fusion_protocol_test', config, dial_mode, runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        ipq_manager.ipq_qmi_mbim_re_init()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
