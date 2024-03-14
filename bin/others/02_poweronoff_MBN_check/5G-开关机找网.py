# -*- encoding=utf-8 -*-
from queue import Queue
from threading import Event
import time
import signal
import logging
from sys import path
path.append(r'..\..\..\lib\Communal')
path.append(r'..\..\..\lib\PowerOnOff')
from restart_manager import RestartManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from power_on_off_log_thread import LogThread

"""
脚本逻辑
1．  at+qnvfd="/nv/item_files/mcfg/mcfg_rfs_sw_digest_version"

2．  VBAT断电重启模块抓开机log，(由于其他的开关机方式会出现开关机失败的现象故此处用vbat来测试)

3．  at+qmbncfg=”list” 查询mbn list是否正确，若正确继续步骤1，如不正确，保存log

脚本中需要对QMBNCFG: "List",26,0,0,"",0, 返回值的“MBN Name”进行匹配，为空则异常

"""

"""
脚本准备

*打开QPST抓DUMP，并设置抓完DUMP重启

M.2的EVB(M.2_EVB_V2.2)各开关机方式准备如下：
0  -> PWRKEY：             PWRKEY置高，飞线连接P_OFF和DTR引脚，模块开机关机状态均可
1  -> QPOWD0：             PWRKEY置高，无需飞线，模块开机状态运行脚本
2  -> QPOWD1：             PWRKEY置高，无需飞线，模块开机状态运行脚本
3  -> RESET：              PWRKEY置高，飞线连接reset和DTR引脚，模块开机关机状态均可
4  -> CFUN1,1：            PWRKEY置高，无需飞线，模块开机状态运行脚本
5  -> VBAT：               PWRKEY置高，飞线连接P_EN和DTR，模块处于关机状态
6  -> QPOWD1+PWRKEY：      PWRKEY置高，飞线连接P_OFF和DTR，模块开机状态运行脚本
7  -> CFUN0/1：            PWRKEY置高，无需飞线，模块开机状态运行脚本
8  -> QPOWD1+VBAT：        PWRKEY置高，飞线连接P_EN和DTR，模块处于关机状态
9  -> QPOWD1+RESET：       PWRKEY置高，飞线连接RESET和DTR，模块开机关机状态均可
10 -> QPOWD1+PWRKEY+VBAT： M.2无RTS引脚，暂时无法测试
11 -> PWRKEY+VBAT：        M.2无RTS引脚，暂时无法测试
12 -> VBAT_RANDOM：        PWRKEY置高，飞线连接P_EN和DTR，模块处于关机状态
13  -> CFUN0/1/4：         PWRKEY置高，无需飞线，模块开机状态运行脚本

普通EVB(5G_EVB_V2.2)各开关机方式准备如下： 
0  => PWRKEY:              短接PWRKEY_3.3V和RTS，模块开机关机状态均可
1  => QPOWD0:              短接PWRKEY_3.3V和RTS，模块开机状态运行脚本
2  => QPOWD1:              短接PWRKEY_3.3V和RTS，模块开机状态运行脚本
3  => RESET:               短接PWRKEY_3.3V和RTS，短接RESET_3.3V和DTR，模块开机关机状态均可
4  => CFUN1,1:             短接PWRKEY_3.3V和RTS，模块开机状态运行脚本
5  => VBAT:                短接PWRKEY_3.3V和RTS，短接3.8V_EN和DTR，模块处于关机状态
6  => QPOWD1+PWRKEY:       短接PWRKEY_3.3V和RTS，模块开机状态运行脚本
7  => CFUN0_1:             无需飞线，模块开机状态运行脚本
8  => QPOWD1+VBAT:         短接PWRKEY_3.3V和RTS，短接3.8V_EN和DTR，模块处于关机状态
9  => QPOWD1+RESET:        短接PWRKEY_3.3V和RTS，短接RESET_3.3V和DTR，模块开机关机状态均可
10 => QPOWD1+PWRKEY+VBAT:  短接PWRKEY_3.3V和RTS，短接3.8V_EN和DTR，模块处于关机状态
11 => PWRKEY+VBAT:         短接PWRKEY_3.3V和RTS，短接3.8V_EN和DTR，模块处于关机状态
12 => VBAT_RANDOM:         短接PWRKEY_3.3V和RTS，短接3.8V_EN和DTR，模块处于关机状态
13  => CFUN0_1_4:          无需飞线，模块开机状态运行脚本

脚本逻辑见：
http://192.168.21.135/5G-SDX55/Standard/wikis/开关机脚本
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM47'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM14'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM12'  # 定义DM端口号,用于判断模块有无dump
debug_port = ''  # RG模块如果需要抓debug口log，则需要设置此参数，否则设为''
revision = 'RG502QEAAAR01A02M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V03'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
restart_mode = 5  # 设置开关机类型
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
cpin_flag = False  # 如果要锁PIN找网时间设置为 True ，如果要开机到找网的时间设置为 False
# ======================================================================================================================
# 辅助参数
runtimes = 0
version = revision+sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
dtr_on_time = 0.5  # 定义POWERKEY开机脉冲时间，默认0.5S(500ms)
dtr_off_time = 0.8  # 定义POWERKEY关机脉冲时间，默认0.8S(800ms)
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
restart_mode_dict = {0: "powerkey", 1: "qpowd0", 2: "qpowd1", 3: "reset", 4: "cfun1_1",
                     5: "vbat", 6: "qpowd1_powerkey", 7: "cfun0_1", 8: "qpowd1_vbat", 9: "qpowd1_reset",
                     10: "qpowd1_powerkey_vbat", 11: "powerkey_vbat", 12: "vbat_random", 13: "cfun0_1_4"}
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
log_thread = LogThread(version, restart_mode_dict[restart_mode], log_queue, restart_mode, cpin_flag, main_queue)
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
restart_manager = RestartManager(main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port, dtr_on_time, dtr_off_time, evb, restart_mode, version, imei, cpin_flag, runtimes)
restart_manager.init()  # 开关机各种方式初始化
# ======================================================================================================================
# DataFrame的统一格式['df', runtimes, column_name, content]
# log内容不需要使用route_queue_put，因为写入log的时候不需要Event()
# 主流程
while True:
    # 脚本自动停止判断
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or (timing != 0 and time.time()-script_start_time > timing*3600):  # 如果runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
        route_queue_put('end_script', script_start_time, runtimes-1, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('='*35, runtimes, '='*35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('='*35, runtimes, '='*35)])  # at_log写入分隔符

    # 将最新的runtimes写入类中
    restart_manager.runtimes = runtimes


    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        restart_manager.re_init()
        continue

    # 开关机前执行at+qnvfd="/nv/item_files/mcfg/mcfg_rfs_sw_digest_version"
    main_queue_data = route_queue_put('AT', 'qnvfd_mbn', runtimes)
    if main_queue_data is False:
        restart_manager.re_init()
        continue

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        restart_manager.re_init()
        continue

    # 根据restart_mode_dict的编号获取对应restart_manager中的方法并调用
    restart_status = getattr(restart_manager, restart_mode_dict[restart_mode])()
    log_queue.put(['df', runtimes, 'power_on_timestamp', time.time()])  # 写入power_on_timestamp
    if restart_status is False:
        restart_manager.re_init()
        continue

    if restart_mode == 0:  # Powerkey方式开关机检测驱动没有出现会进入restart_manager的re_init方法
        main_queue_data = route_queue_put('Process', 'check_usb_driver', False, runtimes)
        if main_queue_data is False:
            restart_manager.re_init()  # 开机失败初始化
            continue
    elif restart_mode != 7 and restart_mode != 13:  # 除Powerkey方式检测驱动没有出现直接暂停脚本
        # 检测USB驱动
        route_queue_put('Process', 'check_usb_driver', True, runtimes)

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        restart_manager.re_init()
        continue

    # 检测开机URC
    main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
    if main_queue_data is False:
        restart_manager.re_init()
        continue

    # 防止MBN查询只返回OK，开机后增加20s延迟等待
    time.sleep(20)

    # 检测模块信息 IMEI、CFUN、CPIN
    main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
    if main_queue_data is False:
        restart_manager.re_init()
        continue

    # 检查mbn
    main_queue_data = route_queue_put('AT', 'check_mbnlist', runtimes)
    if main_queue_data is False:
        restart_manager.re_init()
        continue

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        restart_manager.re_init()
        continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
