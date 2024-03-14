# -*- encoding=utf-8 -*-
import datetime
import os
from queue import Queue
from threading import Event
import time
import signal
import logging
from sys import path
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'Flash'))
from functions import environment_check
environment_check()  # 检查环境
from flash_manager import FlashManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from flash_life_log_thread import LogThread
from collections import defaultdict

# VBAT接线方式  注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
# 需要插入SIM卡防止CPIN: NOT INSERT

# 脚本逻辑：
# 1. 模块初始化
# 2. 执行VBAT方式关机后开机
# 3. 执行Flash擦写命令。
# 4. 循环读取擦写状态，直到擦写报错
# 5. 统计当前BLOCK循环擦写指定次数
# 6. 重复2-5

# ======================================================================================================================
# 必选参数
uart_port = 'COM3'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM20'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM17'  # 定义DM端口号,用于判断模块有无dump
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RM500QGLABR11A01M4G_BETA_20210526H'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
qftest_partition = ['recovery', 'recoveryfs']  # 配置需要擦写的分区
qftest_block_id = [56, 79]  # 配置分区的block id
flash_test_times = 10  # 每个分区(block)擦写的次数
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
# ======================================================================================================================
# 可选参数
# AT+QFTEST="FlashStrTest","sys_rev",1,1,300000,85,30
# AT+QFTEST="FlashStrTest","PartitionName",<State>,<BlockId>,<EraseWriteTimes>,<Data>,<Timer>
# "PartitionName"：指定擦写nand分区名称
# <State> : 控制指令运行状态；0：停止；1：执行；2：查询。
# <BlockID>: 指定擦写第几个blcok，范围从1到整个分区的block个数
# <EraseWriteTimes>： 该次AT命令总共要执行的擦写次数。
# <Data>：写入的数据，一个字节。整个block都写这个值，建议写数字85（十六进制0x55）。
# <Timer> : 擦除一次BlockCnt间隔时间间隔，为0时软件会有一个默认值。
qftest_erase_write_times = 300000
qftest_data = 85
qftest_timer = 30
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 其他参数
runtimes = 0
logger = logging.getLogger(__name__)
version = revision + sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
info = 'flash_life'
result_dict = defaultdict(list)
# ======================================================================================================================
# 定义queue并启动线程
main_queue, route_queue, uart_queue, process_queue, at_queue, log_queue = (Queue() for i in range(6))
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
process_thread = ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, info, log_queue, main_queue)
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
    log_queue.put(['df', runtimes, 'error', 1]) if _main_queue_data is False else ''
    return _main_queue_data


# 脚本结束，进行结果统计
def handler(signal_num, frame=None):  # noqa
    """
    脚本结束参数统计。
    """
    result = ''
    for k, v in result_dict.items():
        result += "{}: {}次\n".format(k, sum(v))
    route_queue_put('end_script', result, script_start_time, runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
flash_manager = FlashManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei,
                             is_5g_m2_evb, runtimes)
flash_manager.flash_init()  # 开关机各种方式初始化
# ======================================================================================================================
# DataFrame的统一格式['df', runtimes, column_name, content]
# log内容不需要使用route_queue_put，因为写入log的时候不需要Event()
# 主流程
while True:
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致

    # 脚本自动停止判断:
    # runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or \
            (timing != 0 and time.time() - script_start_time > timing * 3600):
        result = ''
        for k, v in result_dict.items():
            result += "{}: {}次\n".format(k, sum(v))
        route_queue_put('end_script', result, script_start_time, runtimes - 1, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符

    # 将最新的runtimes写入类中
    flash_manager.runtimes = runtimes

    for partition, block_id in dict(zip(qftest_partition, qftest_block_id)).items():

        for num in range(1, flash_test_times + 1):
            log_queue.put(['at_log', '[{}]正在擦写{}，id:{}，times:{}-{}'.format(datetime.datetime.now(), partition, block_id, num, flash_test_times)])

            log_queue.put(['df', runtimes, 'partition', partition])  # runtimes
            log_queue.put(['df', runtimes, 'block_id', block_id])  # runtimes

            # 重启
            flash_manager.flash_init()

            # 打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                continue

            time.sleep(5)

            # 开机检测ATFWD
            main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
            if main_queue_data is False:
                continue

            # flash test
            main_queue_data = route_queue_put('AT', 'block_test', partition, block_id, qftest_erase_write_times,
                                              qftest_data, qftest_timer, runtimes)
            if main_queue_data is False:
                continue

            # 关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                continue

        # LOG相关
        log_queue.put(['to_csv'])  # 所有LOG写入CSV
        log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log

        result_dict[partition].append(at_thread.block_erase_times)

        at_thread.block_erase_times = 0  # 每个block重复擦写前将block的擦写次数置为0
