# -*- encoding=utf-8 -*-
from queue import Queue
from threading import Event
import time
import signal
import logging
from sys import path
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'ATD'))
from atd_manger import Manger
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from atd_log_thread import LogThread


"""
脚本逻辑：
1、模块开机，确认注网OK
2、ATD拨打电话
3、AT+CLCC确认当前通话状态
4、ATH挂断电话
5、在DEBUG串口输入：cat /run/ql_voice_server.log，匹配msg_id=0x2E和msg_id=0x1F,若匹配不到，则暂停脚本，若匹配正常，则断电重启模块
6、循环步骤1~5

脚本准备:
PCIE-CARD: PWRKEY置高，飞线连接P_EN和DTR引脚；
5G-EVB: 短接PWRKEY_3.3V和RTS,3.8V_EN和DTR。
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
不要拨打三大运营商号码，自己使用另一模块插卡开机并指令配置响铃多少声后自动接听，ATS0=*,*填几则代表上报几次RING后自动接听
如果需要MBIM拨号再拨打电话的话压力前手动设置AT+QCFG="USBNET",2
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM7'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM4'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM6'  # 定义DM端口号,用于判断模块有无dump
debug_port = 'COM28'  # RG模块如果需要抓debug口log，则需要设置此参数，否则设为''
revision = 'RG500QEAAAR11A05M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V02'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
number = '13275863160'     # 配置要拨打的号码
debug_port_pwd = 'ccX2cjIT/kJY.cqC7BFSV0'  # 此处填写debug口登录密码
interval = 300  # 每次拨号的间隔时间，默认300S
ATS_time = 3    # ATS0=*指令设置值为多少就填多少
MBIM = False     # 是否MBIM拨号后再进行通话测试 True:需要，Fals: 不需要
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
runtimes = 0
VBAT = False
version = revision + sub_edition
cpin_flag = False  # 如果要锁PIN找网时间设置为 True ，如果要开机到找网的时间设置为 False
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
logger = logging.getLogger(__name__)
atd_info = '通话稳定性'
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
log_thread = LogThread(version, atd_info, log_queue, False, main_queue)
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
manger = Manger(main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port, version, imei, MBIM,
                is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
atd_init_status = manger.init()
if atd_init_status is False:
    print("拨号脚本初始化异常，请检查AT log并重新运行脚本。")
    exit()
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

    # 将最新的runtimes写入类中
    manger.runtimes = runtimes

    if VBAT:
        manger.init()

    if MBIM:
        # MBIM拨号后PING百度
        main_queue_data = route_queue_put('Process', 'connect', 'MBIM', runtimes)
        if main_queue_data is False:
            manger.init()
            continue
        main_queue_data = route_queue_put('Process', 'request_baidu', runtimes)
        if main_queue_data is False:
            manger.init()
            continue

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # 开机检测ATFWD
    main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # 检查注网
    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # 等待10S
    time.sleep(10)

    # 拨打电话及查询状态
    main_queue_data = route_queue_put('AT', 'check_atd', number, ATS_time, runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # debug查询
    main_queue_data = route_queue_put('Uart', 'debug_check', debug_port_pwd, runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # 防止频繁拨打电话
    time.sleep(interval)

    # 查询统计还原次数
    main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # AT+QDMEM?分区内存泄露查询
    if VBAT is False and runtimes % 50 == 0:
        time.sleep(2)
        route_queue_put('AT', 'memory_leak_monitoring', runtimes)

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    if MBIM:
        main_queue_data = route_queue_put('Process', 'disconnect', runtimes)
        if main_queue_data is False:
            manger.init()
            continue

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
