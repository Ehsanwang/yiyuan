# -*- encoding=utf-8 -*-
from queue import Queue
from threading import Event
import time
import signal
import logging
import datetime
from sys import path
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'ABSYSTEM'))
from functions import environment_check
environment_check()  # 检查环境
from ab_boot_manager import AB_Boot_Manager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from ab_boot_log_thread import LogThread

"""
脚本接线方式参考VBAT。
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM18'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM15'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM11'  # 定义DM端口号,用于判断模块有无dump
debug_port = 'COM17'  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'SG520TMDAR01A02M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
Partition_Type = 'system'  #分区类型，boot,modem,system
Partition_rangea = 1     #擦除分区范围下限
Partition_rangeb = 2     #擦除分区范围上限
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
runtimes_temp = 5  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
runtimes = 0
version = revision + sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
logger = logging.getLogger(__name__)
abboot_info = '顺序依次破坏AB分区'
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
log_thread = LogThread(version, abboot_info, log_queue, main_queue)
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
ab_boot_manager = AB_Boot_Manager(main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port, version, imei,
                                  is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
ab_boot_manager.ab_boot_init()  # 开关机各种方式初始化
# ======================================================================================================================
# DataFrame的统一格式['df', runtimes, column_name, content]
# log内容不需要使用route_queue_put，因为写入log的时候不需要Event()
# 主流程

while True:
    # 脚本自动停止判断
    time.sleep(5)
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
    log_queue.put(['ab_bootfail_log', "{}runtimes:{}{}\n".format('=' * 60, runtimes, '=' * 60)])  # at_log写入分隔符

    # 将最新的runtimes写入类中
    ab_boot_manager.runtimes = runtimes

    for i in range(Partition_rangea, Partition_rangeb+1):  # forward代表正向升级，backward代表逆向升级

        while True:
            # 打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            time.sleep(6)

            # 开机检测ATFWD
            main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue
            #检查state
            main_queue_data = route_queue_put('AT', 'check_addoot_state', runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            #擦除A分区BOOT分区
            main_queue_data = route_queue_put('AT', 'orderA_break_ab_boot', i, Partition_Type, runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            #重启模块
            main_queue_data = ab_boot_manager.ab_boot_vbat()
            if main_queue_data is False:
                continue

            #检查擦除后分区
            main_queue_data = route_queue_put('AT', 'orderA_check_abboot', i, Partition_Type, runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            time.sleep(6)
            # 检查state
            main_queue_data = route_queue_put('AT', 'check_addoot_state', runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            # 擦除B分区BOOT分区
            main_queue_data = route_queue_put('AT', 'orderB_break_ab_boot', i, Partition_Type, runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            # 重启模块
            main_queue_data = ab_boot_manager.ab_boot_vbat()
            if main_queue_data is False:
                continue

            # 检查擦除后分区
            main_queue_data = route_queue_put('AT', 'orderB_check_abboot', i, Partition_Type, runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            # flash分区擦写量查询
            route_queue_put('AT', 'qftest_record', runtimes)

            # 查询统计还原次数
            main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            # 关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                ab_boot_manager.ab_boot_init()
                continue

            break

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
