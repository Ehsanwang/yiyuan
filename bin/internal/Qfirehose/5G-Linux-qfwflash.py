# -*- encoding=utf-8 -*-
import time
import signal
import datetime
import logging
from sys import path
import os
import re
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
from qfwflash_log_thread import LogThread
from qfwflash_manager import Qfwflash
from functions import pause

'''
脚本逻辑：
相同版本升级：
1、进行初始化;
2、检测版本号信息是否正确;
3、进行升级，可配置是否随机断电;
4、升级完成后检查版本号是否正确;
5、检查注网情况;
6、循环2-5。
不同版本升级：
1、进行初始化;
2、检测号信息是否正确;
3、进行A-B版本升级(先进行全擦工厂升级再进行标准版本升级);
4、升级完成后检查版本号是否正确;
5、检查注网情况;
6、进行B-A升级;
7、升级完成后检查版本号是否正确;
8、检查注网情况;
9、循环2-8。
'''
"""
脚本准备:
1、配置qfwflash环境变量：
    1、gedit ~/.bashrc；
    2、在文档中最后一行添加qfwflash，例：export PATH=/home/dell/Tools/qfwflash:$PATH
    3、source ~/.bashrc
    4、chmod 777 你的qfwflash路径
2、RG的模块接线方式参考VBAT开关机方式。RM的模块若正常升级，只需短接P_EN和DTR，若断电升级，则还需短接P_OFF和RTS。
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
3、如果是不同版本升级，需要将两个版本的工厂包及标准包分别放到两个文件夹下
"""
# ======================================================================================================================
# 需要配置的参数
uart_port = '/dev/ttyUSB0'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = '/dev/ttyUSB3'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = '/dev/ttyUSB1'   # 定义DM端口号,用于判断模块有无DUMP
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RG500QEAAAR11A05M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V02'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
after_upgrade_revision = "RG500QEAAAR11A05M4G"  # 设置升级后的Revision版本号，填写ATI+CSUB查询的Revision部分，如果是同版本升级则不填
after_upgrade_sub_edition = "V01"  # 设置升级后的SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
VBAT = True       # 升级过程是否断电 True：升级过程中断电  False: 升级过程中不断电
A_B_package_name = '/home/cris/standard/RG500QEAAAR11A05M4G_01.001V01.01.001V01/RG500QEAAAR11A05M4G_01.001V01.01.001V01' # 若是同版本升级，只在此处填写当前版本包路径名称，不同版本填写升级后标准版本包路径名称
B_A_package_name = '/home/cris/standard/RG500QEAAAR11A05M4G_01.001V02.01.001V02/RG500QEAAAR11A05M4G_01.001V02.01.001V02' # 若是不同版本升级，则此处填写升级前版本包名称 ,否则不填
is_calibration = 0  # 模块是否经过校准，0：未校准，1：已校准
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 12   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
is_factory = False
is_same_upgrade = False if B_A_package_name != '' else True  # 为True时为相同版本升级，False为不同版本
if not is_same_upgrade:     # 只有在不同版本升级时候才判断是否需要全擦升级
    is_factory = False if int(''.join(re.findall(r'R(\d+)', revision))) == int(''.join(re.findall(r'R(\d+)', after_upgrade_revision))) else True    # 判断是否同一基线决定是否升级工厂版本
A_B_factory_package_name = A_B_package_name + '_factory'    # 拼接工厂包名称
B_A_factory_package_name = B_A_package_name + '_factory'
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
version = revision + sub_edition
after_version = after_upgrade_revision + after_upgrade_sub_edition if after_upgrade_revision != '' else version
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
qfwflash_info = 'Qfwflash-{}-{}'.format('相同版本升级' if is_same_upgrade else '不同版本升级', '升级断电' if VBAT else '正常升级')  # 脚本详情字符串
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
log_thread = LogThread(version, qfwflash_info, log_queue, main_queue, is_same_upgrade)
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
qfwflash_manager = Qfwflash(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei,
                             is_calibration, VBAT, is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
qfwflash_manager.qfwflash_init()
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
    log_queue.put(['qfwflash_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    qfwflash_manager.runtimes = runtimes

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        qfwflash_manager.qfwflash_normal_exception_init()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        qfwflash_manager.qfwflash_normal_exception_init()
        continue

    # 检测版本号
    main_queue_data = route_queue_put('AT', 'qfirehose_version_check', version, runtimes)
    if main_queue_data is False:
        qfwflash_manager.qfwflash_normal_exception_init()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 查询统计还原次数
    main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
    if main_queue_data is False:
        qfwflash_manager.qfwflash_normal_exception_init()
        continue

    # AT+QDMEM?分区内存泄露查询
    if not VBAT and runtimes % 50 == 0:
        time.sleep(2)
        route_queue_put('AT', 'memory_leak_monitoring', runtimes)

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        qfwflash_manager.qfwflash_normal_exception_init()
        continue
    # 进行qfwflash升级，如果是相同版本升级，则只升级一次,否则进行正反向升级，先升级工厂再升级标准
    if is_same_upgrade:     # 同版本升级
        log_queue.put(['at_log', '[{}] 开始进行同版本升级,当前版本为{}'.format(datetime.datetime.now(), version)])
        for i in range(1, 5):
            if i == 4:
                log_queue.put(['all', '[{}] runtimes:{} 连续三次升级异常'.format(datetime.datetime.now(), runtimes)])
                pause()
            main_queue_data = route_queue_put('Process', 'qfwflash_upgrade', A_B_package_name, VBAT, 'forward', dm_port,
                                              runtimes)
            if main_queue_data is False:
                qfwflash_manager.upgrade_fail_init(runtimes)
                continue
            if VBAT:
                qfwflash_status = qfwflash_manager.qfwflash_upgrade_vbat(A_B_package_name, 'forward', dm_port, runtimes)
                if qfwflash_status is False:
                    qfwflash_manager.upgrade_fail_init(runtimes)
                    continue
            # 检测驱动加载
            route_queue_put('Uart', 'set_rts_false')
            log_queue.put(['at_log', "[{}] Set RTS False".format(datetime.datetime.now())])
            main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
            if main_queue_data is False:
                qfwflash_manager.qfwflash_normal_exception_init()
                continue
            # 打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                qfwflash_manager.qfwflash_normal_exception_init()
                continue
            # 检测开机URC
            main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
            if main_queue_data is False:
                qfwflash_manager.qfwflash_normal_exception_init()
                continue
            # 开机检测ATFWD
            main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
            if main_queue_data is False:
                qfwflash_manager.qfwflash_normal_exception_init()
                continue
            # 检测版本号
            main_queue_data = route_queue_put('AT', 'qfirehose_version_check', after_version, runtimes)
            if main_queue_data is False:
                qfwflash_manager.qfwflash_normal_exception_init()
                continue
            break
    else:    # 不同版本升级，首先升级工厂，再升级标准
        for mode in ('forward', 'backward'):
            if mode == 'forward':
                for i in range(1, 5):
                    if i == 4:
                        log_queue.put(['all', '[{}] runtimes:{} 连续三次升级异常'.format(datetime.datetime.now(), runtimes)])
                        pause()
                    if is_factory:
                        log_queue.put(['at_log', '[{}] 开始进行A-B工厂版本升级,当前版本为{}'.format(datetime.datetime.now(), version)])
                        main_queue_data = route_queue_put('Process', 'qfwflash_upgrade', A_B_factory_package_name, VBAT,
                                                          mode, dm_port, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.upgrade_fail_init(runtimes)
                            continue
                        if VBAT:
                            qfwflash_status = qfwflash_manager.qfwflash_upgrade_vbat(A_B_factory_package_name, mode,
                                                                                     dm_port, runtimes)
                            if qfwflash_status is False:
                                qfwflash_manager.upgrade_fail_init(runtimes)
                                continue
                        # 检测驱动加载
                        main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 打开AT口
                        main_queue_data = route_queue_put('AT', 'open', runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 检测开机URC
                        main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 开机检测ATFWD
                        main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 检测版本号
                        main_queue_data = route_queue_put('AT', 'qfirehose_version_check', after_version, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 检测注网
                        main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 关闭AT口
                        main_queue_data = route_queue_put('AT', 'close', runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                    log_queue.put(['at_log', '[{}] 开始进行B标准版本升级'.format(datetime.datetime.now())])
                    # 升级标准版本
                    main_queue_data = route_queue_put('Process', 'qfwflash_upgrade', A_B_package_name, VBAT, mode,
                                                      dm_port, runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.upgrade_fail_init(runtimes)
                        continue
                    if VBAT:
                        qfwflash_status = qfwflash_manager.qfwflash_upgrade_vbat(A_B_package_name, mode, dm_port,
                                                                                 runtimes)
                        if qfwflash_status is False:
                            qfwflash_manager.upgrade_fail_init(runtimes)
                            continue
                    # 检测驱动加载
                    main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 打开AT口
                    main_queue_data = route_queue_put('AT', 'open', runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 检测开机URC
                    main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 开机检测ATFWD
                    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 检测版本号
                    main_queue_data = route_queue_put('AT', 'qfirehose_version_check', after_version, runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    if not is_factory:      # 只在同基线下升级后检查模块信息
                        main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                    # 检测注网
                    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 关闭AT口
                    main_queue_data = route_queue_put('AT', 'close', runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    break
            elif mode == 'backward':
                for i in range(1, 5):
                    if i == 4:
                        log_queue.put(['all', '[{}] runtimes:{} 连续三次升级异常'.format(datetime.datetime.now(), runtimes)])
                        pause()
                    if is_factory:
                        log_queue.put(['at_log', '[{}] 开始进行B-A工厂版本升级,当前版本为{}'.format(datetime.datetime.now(), after_version)])
                        main_queue_data = route_queue_put('Process', 'qfwflash_upgrade', B_A_factory_package_name, VBAT,
                                                          mode, dm_port, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.upgrade_fail_init(runtimes)
                            continue
                        if VBAT:
                            qfwflash_status = qfwflash_manager.qfwflash_upgrade_vbat(B_A_factory_package_name, mode,
                                                                                     dm_port, runtimes)
                            if qfwflash_status is False:
                                qfwflash_manager.upgrade_fail_init(runtimes)
                                continue
                        # 检测驱动加载
                        main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 打开AT口
                        main_queue_data = route_queue_put('AT', 'open', runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 检测开机URC
                        main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 开机检测ATFWD
                        main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 检测版本号
                        main_queue_data = route_queue_put('AT', 'qfirehose_version_check', version, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 检测注网
                        main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                        # 关闭AT口
                        main_queue_data = route_queue_put('AT', 'close', runtimes)
                        if main_queue_data is False:
                            qfwflash_manager.qfwflash_normal_exception_init()
                            continue
                    # 升级标准版本
                    log_queue.put(['at_log', '[{}] 开始进行A标准版本升级'.format(datetime.datetime.now())])
                    main_queue_data = route_queue_put('Process', 'qfwflash_upgrade', B_A_package_name, VBAT, mode,
                                                      dm_port, runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.upgrade_fail_init(runtimes)
                        continue
                    if VBAT:
                        qfwflash_status = qfwflash_manager.qfwflash_upgrade_vbat(B_A_package_name, mode, dm_port,
                                                                                 runtimes)
                        if qfwflash_status is False:
                            qfwflash_manager.upgrade_fail_init(runtimes)
                            continue
                    # 检测驱动加载
                    main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 打开AT口
                    main_queue_data = route_queue_put('AT', 'open', runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 检测开机URC
                    main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 开机检测ATFWD
                    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    # 检测版本号
                    main_queue_data = route_queue_put('AT', 'qfirehose_version_check', version, runtimes)
                    if main_queue_data is False:
                        qfwflash_manager.qfwflash_normal_exception_init()
                        continue
                    break

    # 检测注网
    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        qfwflash_manager.qfwflash_normal_exception_init()
        continue
    if not is_factory:  # 只在同基线下升级后检查模块信息
        # 检测模块信息 IMEI、CFUN、CPIN
        main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
        if main_queue_data is False:
            qfwflash_manager.qfwflash_normal_exception_init()
            continue
    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        qfwflash_manager.qfwflash_normal_exception_init()
        continue
    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
