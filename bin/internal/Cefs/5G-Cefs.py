# -*- encoding=utf-8 -*-
import time
import signal
import datetime
import logging
from sys import path
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'Cefs'))
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from queue import Queue
from threading import Event
from Cefs_manger import CefsManger
from Cefs_log_thread import LogThread

'''
脚本逻辑:
1、开机后使用AT指令随机擦除cefs分区Bolck；
2、模块重启；
3、检查模块是否正常还原。

脚本准备:
1、接线方式参考VBAT开关机方式。
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
2、进行压力时不要QPST不要打开DM口抓取DUMPlog。
脚本注:
擦除方式参考SDX24，可擦除分区:Cefs，Usrdata；
目前不关注使用fastboot全擦方式，只使用AT指令随机擦除分区Bolck。
'''

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM16'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM23'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM22'   # 定义DM端口号,用于判断模块有无DUMP
debug_port = ''  # RG模块如果需要抓debug口log，则需要设置此参数，否则设为''
revision = 'RG500QEAAAR11A04M4G_BETA_20211103_ACY'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V05'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
mode = 'cefs'     # 此处配置擦除方式，cefs表示只随机擦除cefs分区，usrdata代表fastboot方式全擦usrdata，all代表每次擦除cefs及usrdata
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
version = revision + sub_edition
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
cefs_info = 'Cefs随机擦除'  # 脚本详情字符串
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
log_thread = LogThread(version, cefs_info, log_queue, main_queue)
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
    route_queue_put('end_script', script_start_time, mode, runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
cefs_manager = CefsManger(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei,
                          is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
cefs_manager.init()
# ======================================================================================================================
# 主流程
while True:
    # 脚本自动停止判断
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or (timing != 0 and time.time() - script_start_time > timing * 3600):  # 如果runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
        route_queue_put('end_script', script_start_time, mode, runtimes - 1, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    cefs_manager.runtimes = runtimes

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        cefs_manager.init()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        cefs_manager.init()
        continue

    # 检查模块是否正常还原
    main_queue_data = route_queue_put('AT', 'cefs_restore', mode, runtimes)
    if main_queue_data is False:
        cefs_manager.init()
        continue

    if mode == 'cefs':
        log_queue.put(['at_log', '[{}] 开始随机擦除Cefs分区Block'.format(datetime.datetime.now())])
        main_queue_data = route_queue_put('AT', 'cefs_random', runtimes, mode)
        if main_queue_data is False:
            cefs_manager.init()
            continue

        main_queue_data = route_queue_put('AT', 'close', runtimes)
        if main_queue_data is False:
            cefs_manager.init()
            continue

        time.sleep(2)
        cefs_manager.init()

        main_queue_data = route_queue_put('AT', 'open', runtimes)
        if main_queue_data is False:
            cefs_manager.init()
            continue

        # 开机检测ATFWD
        main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
        if main_queue_data is False:
            cefs_manager.init()
            continue

        # 检测模块信息 IMEI、CFUN、CPIN
        main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
        if main_queue_data is False:
            cefs_manager.init()
            continue

        # 检查模块是否正常还原
        main_queue_data = route_queue_put('AT', 'cefs_restore', mode, runtimes)
        if main_queue_data is False:
            cefs_manager.init()
            continue

    if mode == 'usrdata':
        log_queue.put(['at_log', '[{}] fastboot全擦usrdata分区Block'.format(datetime.datetime.now())])
        # 使用fastboot方式全擦usrdata分区
        main_queue_data = route_queue_put('AT', 'cefs_random', runtimes, mode)
        if main_queue_data is False:
            cefs_manager.init()
            continue
        time.sleep(50)
        # 检测模块信息 IMEI、CFUN、CPIN
        main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
        if main_queue_data is False:
            cefs_manager.init()
            continue
        # 检查模块是否正常还原
        main_queue_data = route_queue_put('AT', 'cefs_restore', mode, runtimes)
        if main_queue_data is False:
            cefs_manager.init()
            continue
    if mode.upper() == 'ALL':
        # 随机擦除分区Block
        for mo in ("usrdata", "cefs"):
            if mo == "cefs":
                log_queue.put(['at_log', '[{}] 开始随机擦除Cefs分区Block'.format(datetime.datetime.now())])
                main_queue_data = route_queue_put('AT', 'cefs_random', runtimes, mo)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue
                # 关闭AT口
                main_queue_data = route_queue_put('AT', 'close', runtimes)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue
                # 模块重启
                cefs_manager.cefs_vbat()
                time.sleep(45)
                cefs_manager.init()
                # 打开AT口
                main_queue_data = route_queue_put('AT', 'open', runtimes)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue
                # 开机检测ATFWD
                main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue
                # 检测模块信息 IMEI、CFUN、CPIN
                main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue
                # 检查模块是否正常还原
                main_queue_data = route_queue_put('AT', 'cefs_restore', mo, runtimes)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue
            if mo == "usrdata":
                log_queue.put(['at_log', '[{}] fastboot全擦usrdata分区Block'.format(datetime.datetime.now())])
                # 使用fastboot方式全擦usrdata分区
                main_queue_data = route_queue_put('AT', 'cefs_random', runtimes, mo)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue
                time.sleep(50)
                # 检测模块信息 IMEI、CFUN、CPIN
                main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue
                # 检查模块是否正常还原
                main_queue_data = route_queue_put('AT', 'cefs_restore', mo, runtimes)
                if main_queue_data is False:
                    cefs_manager.init()
                    continue

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        cefs_manager.init()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
