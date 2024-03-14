# -*- encoding=utf-8 -*-
import time
import signal
import datetime
import logging
from sys import path
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'Qfirehose'))
from functions import environment_check
environment_check()  # 检查环境
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from queue import Queue
from threading import Event
from Qfirehose_log_thread import LogThread
from Qfirehose_manager import Qfirehose
from functions import pause

'''
脚本逻辑：
相同版本升级：
1、进行初始化;
2、检测版本号信息是否正确;
3、进行升级;
4、升级完成后检查版本号是否正确;
5、使用Qfwflash升级工具进行升级;
6、升级完成后检查版本号是否正确。
7、检查MBN是否有重复加载的情况
8、循环2-7
'''
"""
脚本准备:
1、配置Qfirehose及Qfwflash环境变量：
    1、gedit ~/.bashrc；
    2、在文档中最后一行添加Qfirehose，例：export PATH=/home/dell/Tools/Qfirehose:$PATH
    3、source ~/.bashrc
    4、chmod 777 你的Qfirehose路径
2、接线方式参考VBAT开关机方式
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = '/dev/ttyUSB0'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = '/dev/ttyUSB4'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = '/dev/ttyUSB2'   # 定义DM端口号,用于判断模块有无DUMP
debug_port = '/dev/ttyUSB1'  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RG502QEAAAR01A02M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V02'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
after_upgrade_revision = ""  # 设置Qfwflash升级后的Revision版本号，填写ATI+CSUB查询的Revision部分，如果是同版本升级则不填
after_upgrade_sub_edition = ""  # 设置Qfwflash升级后的SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '860736040004978'  # 模块测试前配置IMEI号
ori_package_path = '/home/q/RG502QEAAAR01A02M4G_01.001V02.01.001V02'   # 初始版本的版本包路径,先使用QFirehose升级到这个版本
check_package_path = ''   # 填写Qfwflash升级的版本包路径，这个版本进行MBN检查
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
VBAT = False       # 升级过程是否断电 True：升级过程中断电  False: 升级过程中不断电,目前只关注同版本断电升级
is_same_upgrade = False
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
version = revision + sub_edition
after_version = after_upgrade_revision + after_upgrade_sub_edition
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
Qfirehose_info = 'Qfirehose-Qfwflash单包-MBN检查'
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
log_thread = LogThread(version, Qfirehose_info, log_queue, main_queue, is_same_upgrade)
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
qfirehose_manager = Qfirehose(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
qfirehose_manager.qfirehose_init()
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
    log_queue.put(['qfirehose_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    qfirehose_manager.runtimes = runtimes

    # 进行Qfirehose升级，如果是相同版本升级，则只升级一次,否则进行正反向升级
    log_queue.put(['at_log', '[{}] 开始进行QFirehose升级,当前版本为{}'.format(datetime.datetime.now(), version)])
    for i in range(1, 5):
        if i == 4:
            log_queue.put(['all', '[{}] runtimes:{} 连续三次升级异常'.format(datetime.datetime.now(), runtimes)])
            pause()
        main_queue_data = route_queue_put('Process', 'qfirehose_upgrade', ori_package_path, VBAT, 'forward', runtimes)
        if main_queue_data is False:
            qfirehose_manager.qfirehose_normal_exception_init()
            continue
        if VBAT:
            qfirehose_status = qfirehose_manager.qfirehose_upgrade_vbat(ori_package_path, runtimes)
            if qfirehose_status is False:
                continue

        time.sleep(50)      # efuse模块升级过程中DM口一直在，直接检查端口消失或加载，会导致误报端口异常

        # 检测驱动加载
        main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
        if main_queue_data is False:
            qfirehose_manager.qfirehose_normal_exception_init()
            continue
        # 打开AT口
        main_queue_data = route_queue_put('AT', 'open', runtimes)
        if main_queue_data is False:
            qfirehose_manager.qfirehose_normal_exception_init()
            continue
        # 检测版本号
        main_queue_data = route_queue_put('AT', 'qfirehose_version_check', version, runtimes)
        if main_queue_data is False:
            qfirehose_manager.qfirehose_normal_exception_init()
            continue
        break

    # 检测模块信息 IMEI、CFUN、CPIN
    main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
    if main_queue_data is False:
        qfirehose_manager.qfirehose_normal_exception_init()
        continue

    # 进行单包升级，使用Qfwflash升级工具进行升级
    main_queue_data = route_queue_put('Process', 'qfwflash_upgrade', check_package_path, False, runtimes)
    if main_queue_data is False:
        qfirehose_manager.qfirehose_normal_exception_init()
        continue

    time.sleep(30)      # efuse模块升级过程中DM口一直在，直接检查端口消失或加载，会导致误报端口异常

    # 检测驱动加载
    main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
    if main_queue_data is False:
        qfirehose_manager.qfirehose_normal_exception_init()
        continue

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        qfirehose_manager.qfirehose_normal_exception_init()
        continue

    qfirehose_manager.qfirehose_normal_exception_init()

    # 检测版本号
    main_queue_data = route_queue_put('AT', 'qfirehose_version_check', after_version, runtimes)
    if main_queue_data is False:
        qfirehose_manager.qfirehose_normal_exception_init()
        continue

    # 检测模块信息 IMEI、CFUN、CPIN
    main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
    if main_queue_data is False:
        qfirehose_manager.qfirehose_normal_exception_init()
        continue

    # 检测MBN是否出现重复
    route_queue_put('AT', 'check_mbnlist', runtimes)

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        qfirehose_manager.qfirehose_normal_exception_init()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
