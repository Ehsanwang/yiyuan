# -*- encoding=utf-8 -*-
import subprocess
import time
import signal
from sys import path
import logging
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'Rgmii_Rtl8125'))
from functions import environment_check, pause, QuectelCMThread
environment_check()  # 检查环境
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from queue import Queue
from threading import Event
from rgmii_rtl8125_log_thread import LogThread
from rgmii_rtl8125_manager import Rgmii_Rtl8125Manager
from rgmii_rtl8125_process_thread import RgmiiRtl8125ProcessThread

"""
脚本准备:
1. 接线方式:
    VBAT :5G_EVB_V2.2: 短接PWRKEY_3.3V和RTS，短接3.8V_EN和DTR
    注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
    
2. 手动禁用本地以太网,WIFI网络,或者拔掉网线
3. 手动配置开启rgmii或rtl8125模式 (该压力不涉及拨号,只需开启) 开启后手动验证是否获取到ip:如果获取不到正确的ip请手动执行：at+qeth="delay_mode",13
    【RGMII】at+qeth="rgmii","enable",1
    【PCIE】at+qcfg="pcie/mode",1   at+qeth="eth_driver","r8125"/"r8168"
    开启后手动验证是否获取到ip:如果获取不到正确的ip请手动执行：at+qeth="delay_mode",13，之后重新打开rgmii功能
4. 需手动开启adb功能
5. Python版本大于3.8
脚本逻辑:
1. 模块初始化(版本号/IMEI/CPIN/其他特殊指令)；
2. 如果选择VBAT则关机->开机->找网->等待拨号加载；
3. 检查网络；
4. flash分区擦写量查询
5. 检查是否获取到ip;
6. 进行自协商设置
7. ping连接测试
8. 重复2-7.
"""

# ======================================================================================================================
# 必选参数
uart_port = 'COM16'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM30'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM29'  # 定义DM端口号,用于判断模块有无dump
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RG500QEAAAR11A05M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V02'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
dial_mode = 'RGMII'  # 设置拨号方式 RGMII或者RTL8125 用于log名称
ping_times = 300  # 默认每个runtimes ping 100次
ping_url = '192.168.225.1'  # 默认ping的网址
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
# ======================================================================================================================
# 可选参数
ping_4_6 = '-4'  # 设置是ping ipv4还是ipv6，取值'-4'，'-6'
ping_size = 32  # 设置每次ping的大小
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 其他参数
restart_mode = None  # 此脚本为不开关机脚本
runtimes = 0
version = revision + sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
dial_info = '{}_开关自协商PING连接稳定性'.format(dial_mode)  # 脚本详情字符串
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
process_thread = RgmiiRtl8125ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, restart_mode, dial_info, log_queue, main_queue)
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
def handler(signal_num, frame=None):  # noqa
    """
    脚本结束参数统计。
    """
    route_queue_put('end_script', script_start_time, runtimes, queue=log_queue)  # 结束脚本统计log
    exit()

# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)
Rgmii_Rtl8125Manager = Rgmii_Rtl8125Manager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version,
                                            imei, dial_mode, is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
dial_init_fusion_status = Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
if dial_init_fusion_status is False:  # 如果需要重新开始，运行re_init
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
    if os.name != 'nt':
        log_queue.put(['quectel_cm_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符

    Rgmii_Rtl8125Manager.runtimes = runtimes

    time.sleep(10)
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 查询统计还原次数
    main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    time.sleep(10)
    main_queue_data = route_queue_put('Process', 'check_ip', runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    # adb shell中开关自协商
    main_queue_data = route_queue_put('Process', 'adb_onoff_consensus', runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    time.sleep(30)

    main_queue_data = route_queue_put('Process', 'check_ip', runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    # 等待拨号稳定
    time.sleep(10)

    # 进行PING连接
    main_queue_data = route_queue_put('Process', 'ping', ping_url, ping_times, ping_4_6, ping_size, runtimes)
    if main_queue_data is False:
        Rgmii_Rtl8125Manager.rgmii_rtl8125_init_fusion()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
