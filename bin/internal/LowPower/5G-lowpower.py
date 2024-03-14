# -*- encoding=utf-8 -*-
import time
import signal
from sys import path
import logging
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'LowPower'))
from functions import environment_check
environment_check()  # 检查环境
from lowpower_manager import LowPower
from lowpower_route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from queue import Queue
from threading import Event
from lowpower_log_thread import LowLogThread
from lowpower_power_thread import PowerThread

"""
注意事项：
1. 脚本需要使用程控电源,RG模块需要短接Powerkey及RTS引脚
2. 电脑需要设置usb suspend
3. 如果需要MBIM拨号，运行前先手动设置AT+QCFG="USBNET",2
"""


# ======================================================================================================================
# 需要配置的参数
uart_port = '/dev/ttyUSB1'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = '/dev/ttyUSB5'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = '/dev/ttyUSB4'  # 定义DM端口号,用于判断模块有无dump
power_port = '/dev/ttyUSB2'  # 程控电源端口号,用于电流的输入和输出
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RM502QGLAAR05A03M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V02'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
VBAT = False  # 每个Runtimes是否关机重启  True：重启，False：不重启
MBIM = False  # 是否需要MBIM和PING  True：需要，False：不需要
network_driver_name = 'RG500Q-EA'  # 如果MBIM，设置'Generic Mobile Broadband Adapter' 因为版本BUG的原因，MBIM拨号时候通常要设置为"RG500Q-EA"，根据实际加载情况设置
sleep_curr_max = 6  # 设置进入休眠后的平均耗流标准，实测不得超过该标准，单位为毫安
wake_curr_max = 40  # 设置退出休眠后的平均耗流标准，实测不得超过该标准，单位为毫安
tolerance_rate = 0.08  # 在采样数据中出现的高于设定标准的峰值频率
sleep_time = 60  # 检测休眠耗流时长，单位为秒,若需要检测连续24H耗流，则此处可以填写86400
wake_time = 30  # 检测唤醒耗流时长，单位为秒
wait_sleep_time = 120  # 设置静置等待进入睡眠时间，单位为秒
check_freq = 1  # 检测频率，单位为秒
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
pid_vid = '2c7c:0800'  # Linux下需要配置pid和vid用于Linux检测，值为lsusb返回的值
cfun_0 = True  # True时候会休眠前会发送AT+CFUN=0，False默认
is_debug = False    # 是否需要进入debug口输入指令以开启慢时钟，针对Yacto版本
wait_time = 0  # 开机后多久执行睡眠命令
runtimes = 0
version = revision + sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
info = 'USB慢时钟LowPower'  # 脚本详情字符串
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
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue, power_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
process_thread = ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LowLogThread(version, info, VBAT, log_queue, main_queue)
power_thread = PowerThread(power_port, power_queue, main_queue, log_queue)
threads = [route_thread, uart_thread, process_thread, at_thread, log_thread, power_thread]
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
lowpower_manager = LowPower(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, VBAT, is_debug, runtimes)
lowpower_manager.lp_init()
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

    # 更新lowpower.manager类runtimes
    lowpower_manager.runtimes = runtimes

    # 是否进行开关机动作
    if VBAT:  # 需要关机，首先进行关机
        while True:
            low_power_vbat_status = lowpower_manager.low_power_vbat()
            if low_power_vbat_status is False:
                continue
            break

    if VBAT:
        time.sleep(wait_time)

    if MBIM:  # 如果MBIM拨号
        if os.name == 'nt':  # 如果是Windows
            main_queue_data = route_queue_put('Process', 'wait_dial_init', runtimes)
            if main_queue_data is False:
                lowpower_manager.low_power_vbat()
                continue

            main_queue_data = route_queue_put('Process', 'reset_connect', runtimes)
            if main_queue_data is False:
                lowpower_manager.low_power_vbat()
                continue

            main_queue_data = route_queue_put('Process', 'connect', 'MBIM', runtimes)
            if main_queue_data is False:
                lowpower_manager.low_power_vbat()
                continue

            main_queue_data = route_queue_put('Process', 'check_ip_connect_status', 'MBIM', network_driver_name, runtimes)
            if main_queue_data is False:
                lowpower_manager.low_power_vbat()
                continue

            main_queue_data = route_queue_put('Process', 'request_baidu', runtimes)
            if main_queue_data is False:
                lowpower_manager.low_power_vbat()
                continue

            main_queue_data = route_queue_put('Process', 'disconnect', runtimes)
            if main_queue_data is False:
                lowpower_manager.low_power_vbat()
                continue

        else:  # 如果是Linux
            # MBIM拨号后PING百度
            main_queue_data = route_queue_put('Process', 'mbim_connect_check', runtimes)
            if main_queue_data is False:
                lowpower_manager.low_power_vbat()
                continue
            # 断开拨号连接
            main_queue_data = route_queue_put('Process', 'disconnect_dial', 'MBIM', runtimes)
            if main_queue_data is False:
                lowpower_manager.low_power_vbat()
                continue

    # 打开AT口
    if VBAT is False:  # 如果不需要关机，首先打开AT口
        main_queue_data = route_queue_put('AT', 'open', runtimes)
        if main_queue_data is False:
            lowpower_manager.low_power_vbat()
            continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        lowpower_manager.low_power_vbat()
        continue

    # 进入慢时钟
    main_queue_data = route_queue_put('AT', 'AT+QSCLK=1,1', 6, 1, runtimes)
    if main_queue_data is False:
        lowpower_manager.low_power_vbat()
        continue

    if cfun_0:
        main_queue_data = route_queue_put('AT', 'AT+CFUN=0', 6, 1, runtimes)
        if main_queue_data is False:
            lowpower_manager.low_power_vbat()
            continue

    if os.name != 'nt':  # Linux下需要设置参数
        route_queue_put('Process', 'linux_enter_low_power', runtimes)
        route_queue_put('Process', 'get_usb_enumerate_status', pid_vid, runtimes)

    if runtimes == 1:  # 第一次的时候多等待，进入休眠，之后不再
        time.sleep(30)

    # 静置等待一段时间待模块进入慢时钟后再检测耗流值
    time.sleep(wait_sleep_time)

    # 模块进入慢时钟后开始获取耗流值
    route_queue_put('Power', 'get_current_volt', sleep_curr_max, tolerance_rate, sleep_time, check_freq, 0, runtimes)

    # 退出慢时钟
    main_queue_data = route_queue_put('AT', 'AT+QSCLK=0,0', 6, 1, runtimes)
    if main_queue_data is False:
        lowpower_manager.low_power_vbat()
        continue

    # 原则3s之后就可以,最长时间为20s
    time.sleep(10)

    if cfun_0:
        main_queue_data = route_queue_put('AT', 'AT+CFUN=1', 6, 1, runtimes)
        if main_queue_data is False:
            lowpower_manager.low_power_vbat()
            continue

    # 模块退出慢时钟后开始获取耗流值
    if os.name != 'nt':  # Linux退出休眠检测usb枚举情况
        route_queue_put('Process', 'get_usb_enumerate_status', pid_vid, runtimes)
    route_queue_put('Power', 'get_current_volt', wake_curr_max, tolerance_rate, wake_time, check_freq, 1, runtimes)

    if cfun_0 and MBIM:
        main_queue_data = route_queue_put('AT', 'AT+CFUN=1', 6, 1, runtimes)
        if main_queue_data is False:
            lowpower_manager.low_power_vbat()
            continue
        # 检测注网
        main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
        if main_queue_data is False:
            lowpower_manager.low_power_vbat()
            continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 查询统计还原次数
    main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
    if main_queue_data is False:
        lowpower_manager.low_power_vbat()
        continue

    # AT+QDMEM?分区内存泄露查询
    if VBAT is False and runtimes % 50 == 0:
        time.sleep(2)
        route_queue_put('AT', 'memory_leak_monitoring', runtimes)

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        lowpower_manager.low_power_vbat()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
