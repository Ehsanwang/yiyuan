# -*- encoding=utf-8 -*-
import time
import signal
import datetime
import logging
from sys import path
import os
import random
import re
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'FILE'))
from functions import environment_check
environment_check()  # 检查环境
from rw_manager import RWManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from rw_process_thread import ProcessThread
from queue import Queue
from threading import Event
from rw_log_thread import LogThread

"""
脚本准备
1、at+qadbkey? 查询出adb秘钥后 并配置
2、at+qcfg="usbcfg",0x2C7C,0x0800,1,1,1,1,1,1
3. 脚本需要连接跳线，同VBAT方式
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线

备注： 建议上传50M以上文件、关闭防火墙和360等杀毒软件

脚本逻辑
1.模块开机后查询EFSBLOCKEC
2、adb push 文件至/bin/origin路径下  注：origin为自定义文件夹  
3、adb push文件至UFS分区到存储空间满为止，RW过程中vbat随机断电，随机断电之前查询EFSBLOCKEC
4、删除UFS空间文件
5、kill adb进程
6、循环step2-5

"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM8'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM6'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM4'   # 定义DM端口号,用于判断模块有无DUMP
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RG500QEAAAR11A01M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
rwfile_path = 'F:\\st-5g\\Python\\modify\\File\\新建文件夹\\'  # 文件原路径
rwfile = 'a.txt'  # 待推送文件
imei = '869710030002905'  # 模块测试前配置IMEI号
vbat = False  # 是否需要vbat随机断电
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
version = revision + sub_edition
runtimes = 0
info = 'RW_UFS分区_VBAT'
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
rwfile_info = 'File-{}'.format(info)  # 脚本详情字符串
logger = logging.getLogger(__name__)
file_path = rwfile_path + rwfile
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
log_thread = LogThread(version, rwfile_info, vbat, log_queue, main_queue)
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


def random_poweroff_vbat(is_5g_m2_evb, runtimes):
    """
    M.2 EVB：拉高DTR断电->检测驱动消失->拉低DTR上电；
    5G-EVB_V2.1：拉高RTS->拉高DTR断电->检测驱动消失->拉低DTR上电。
    :return: None
    """
    log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电\n".format(datetime.datetime.now())])
    time.sleep(random.uniform(3.5, 5.5))
    if is_5g_m2_evb is True:
        log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电\n".format(datetime.datetime.now())])
        # 断电
        route_queue_put('Uart', 'set_dtr_true')
        log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
        # 检测驱动消失
        route_queue_put('Process', 'check_usb_driver_dis', True, runtimes)
        time.sleep(3)
        # 上电
        route_queue_put('Uart', 'set_dtr_false')
        log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
    else:
        log_queue.put(['at_log', "[{}] 拉动DTR控制VBAT断电上电\n".format(datetime.datetime.now())])
        # 断电
        route_queue_put('Uart', 'set_dtr_false')
        log_queue.put(['at_log', "[{}] Set DTR False".format(datetime.datetime.now())])
        # 检测驱动消失
        route_queue_put('Process', 'check_usb_driver_dis', True, runtimes)
        time.sleep(3)
        # 上电
        route_queue_put('Uart', 'set_dtr_true')
        log_queue.put(['at_log', "[{}] Set DTR True".format(datetime.datetime.now())])
    # 检测驱动加载
    route_queue_put('Process', 'check_usb_driver', False, runtimes)


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
rw_manager = RWManager(main_queue, route_queue, uart_queue, log_queue, uart_port, version, imei, rwfile_path,
                       rwfile, is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
rw_manager.rw_init()
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
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # debug_log写入分隔符
    log_queue.put(['efsec_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # efsec_log写入分隔符
    rw_manager.runtimes = runtimes

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    # # 检查模块信息
    main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    #  检测注网
    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    # 开机之后进行AT+QFTEST="EFSBlockEC"查询
    main_queue_data = route_queue_put('AT', 'check_efsec', runtimes, False)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 查询统计还原次数
    main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    # AT+QDMEM?分区内存泄露查询
    if vbat is False and runtimes % 50 == 0:
        time.sleep(2)
        route_queue_put('AT', 'memory_leak_monitoring', runtimes)

    # 检测adb devices是否有设备
    main_queue_data = route_queue_put('Process', 'check_adb_devices_connect', runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    rwfile_index = 0
    while True:
        time.sleep(0.001)
        rwfile_index = rwfile_index + 1
        # 读写ufs分区过程中vbat随机断电
        if vbat:
            choice = random.choice([1, 2, 3, 4])
            if choice == 3:
                route_queue_put('Process', 'adb_push_rw_file', rwfile_path, rwfile, False, rwfile_index, runtimes)
                # 随机断电之前进行AT+QFTEST="EFSBlockEC"查询
                main_queue_data = route_queue_put('AT', 'check_efsec', runtimes, True)
                if main_queue_data is False:
                    rw_manager.rw_exception_reinit()
                    continue
                random_poweroff_vbat(is_5g_m2_evb, runtimes)  # 随机vbat断电
                main_queue_data = route_queue_put('Process', 'check_adb_devices_connect', runtimes)  # 开机后检测adb设备
                if main_queue_data is False:
                    rw_manager.rw_exception_reinit()
                    continue
            else:
                main_queue_data = route_queue_put('Process', 'adb_push_rw_file', rwfile_path, rwfile, True, rwfile_index, runtimes)
                if re.search('No space left on device', str(main_queue_data)):
                    break
                else:
                    continue
        # 读写ufs分区不进行vbat
        else:
            main_queue_data = route_queue_put('Process', 'adb_push_rw_file', rwfile_path, rwfile, True, rwfile_index, runtimes)
            if re.search('No space left on device', str(main_queue_data)):
                break
            else:
                continue

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    # 删除UFS分区文件
    route_queue_put('Process', 'delete_ufs_file', 'adb shell rm -rf /usrdata/rwfile/*', runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    # kill adb进程
    route_queue_put('Process', 'kill_adb', runtimes)
    if main_queue_data is False:
        rw_manager.rw_exception_reinit()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
