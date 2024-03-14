# -*- encoding=utf-8 -*-
from queue import Queue
from threading import Event
import time
import signal
import logging
from sys import path
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'Cefs'))
from functions import environment_check
environment_check()  # 检查环境
from cefs_block_manger import CefsBlockManger
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from cefs_block_log_thread import LogThread

"""
脚本逻辑
1.查询cefs总还原次数上限(默认值2000)
2.设置cefs总还原次数上限(设置5000)
3.查询cefs分区各block累计触发还原次数上限(默认值)
4.设置cefs分区各block累计触发还原次数上限(设置50)
5.模组备份
6.检查模块30s内是否自动重启,若不自动重启则设置主动还原
7.模组VBAT随机断电上电,如果模组主动重启，则不需要再进行断电，
查询指令执行下at+qcefscfg=”block_restore_count”;at+qprtpara=4;at+qcefscfg=”get_bad_blocks_id”;at+qcefscfg="block_consecutive_restore_count"，做好记录
8.查询cefs分区所有block坏块id
9.重复6-9
脚本准备：
1.脚本接线方式参考VBAT。
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线  
2.每次执行该脚本前都需要全擦烧录工厂版本,之后开机后手动执行一次AT+QPRTPARA=1备份指令
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM17'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM10'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM12'  # 定义DM端口号,用于判断模块有无dump
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RM500QGLABR13A01M4G_BETA_20221215H'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
runtimes_temp = 10000  # 设置脚本运行次数，需要设置成与参数total_restore_count值一致
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
block_restore_count = 3  # 设置cefs各分区累计还原次数上限,设置成50则cefs还原到达51次时被标记为坏块
total_restore_count = 10000  # 设置模块总还原次数,当还原次数到达该数值后，再次执行还原指令则会报错
is_5g_m2_evb = True  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
# ======================================================================================================================
# 辅助参数
runtimes = 0
version = revision + sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
logger = logging.getLogger(__name__)
cefsblock_info = 'cefs各分区累计擦除上限标记坏块功能验证'
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
log_thread = LogThread(version, cefsblock_info, log_queue, main_queue)
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
cefsblock_manger = CefsBlockManger(main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port,
                                   version, imei, is_5g_m2_evb, block_restore_count, total_restore_count, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
cefsblock_manger.block_init()
# ======================================================================================================================
# DataFrame的统一格式['df', runtimes, column_name, content]
# log内容不需要使用route_queue_put，因为写入log的时候不需要Event()
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
    log_queue.put(['cefsblock_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符

    # 将最新的runtimes写入类中
    cefsblock_manger.runtimes = runtimes

    # 持续1分钟检测模块是否会自动重启,若没有自动重启,则进行vbat随机断电
    main_queue_data = route_queue_put('Process', 'check_usb_driver_always', runtimes)
    if main_queue_data is False:  # 模块自动重启
        main_queue_data = route_queue_put('Process', 'check_usb_driver', False, runtimes)
        if main_queue_data is False:
            cefsblock_manger.block_init()  # 开机失败初始化
            continue
    else:  # 模块没有自动重启,需手动vbat随机断电
        cefsblock_manger.blockinit()

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        cefsblock_manger.block_init()
        continue

    time.sleep(12)
    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        cefsblock_manger.block_init()
        continue
    # 查询相关block并进行对比
    main_queue_data = route_queue_put('AT', 'check_cefsblock', block_restore_count, runtimes)
    if main_queue_data is False:
        cefsblock_manger.block_init()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        cefsblock_manger.block_init()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
