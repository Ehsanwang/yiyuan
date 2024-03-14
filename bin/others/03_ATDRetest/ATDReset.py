# -*- encoding=utf-8 -*-
from queue import Queue
from threading import Event
import time
import signal
import logging
from manger import Manger
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from atd_log_thread import LogThread

"""
脚本逻辑
1、模块开机，确认注网OK
2、ATD拨打电话(注意不能使用联通卡，会存在频繁拨打电话导致电话卡被停用)
3、AT+CLCC确认当前通话状态(拨打10086，at+clcc返回的参数stat为0即可)
4、ATH挂断电话
5、在DEBUG串口输入：cat /run/ql_voice_server.log，匹配msg_id=0x2E和msg_id=0x1F,若匹配不到，则暂停脚本，若匹配正常，则断电重启模块
6、循环步骤1~5
"""


# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM19'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM5'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM3'  # 定义DM端口号,用于判断模块有无dump
debug_port = 'COM15'  # RG模块如果需要抓debug口log，则需要设置此参数，否则设为''
revision = 'RG500QEABETA072116'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '866897040005150'  # 模块测试前配置IMEI号
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
cpin_flag = False  # 如果要锁PIN找网时间设置为 True ，如果要开机到找网的时间设置为 False
debug_port_pwd = 'angrTJ3hNhDFMmyDgKYIo1'  # 此处填写debug口登录密码
# ======================================================================================================================
# 辅助参数
runtimes = 0
version = revision+sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
logger = logging.getLogger(__name__)
atd_info = 'ATD复测'
# ======================================================================================================================
# 定义queue并启动线程
main_queue = Queue()
route_queue = Queue()
uart_queue = Queue()
process_queue = Queue()
at_queue = Queue()
log_queue = Queue()
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue, debug_port_pwd)
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
manger = Manger(main_queue, route_queue, uart_queue, at_queue, log_queue, at_port, uart_port, version, imei,
                         runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('='*35, '='*35)])
print("\rinitialize", end="")
# manger.init()  # 开关机各种方式初始化
cfun_init_status = manger.init()
if cfun_init_status is False:
    exit()
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
    manger.runtimes = runtimes

    main_queue_data = route_queue_put('Process', 'check_usb_driver', False, runtimes)
    if main_queue_data is False:
        manger.init()  # 开机失败初始化
        continue

    # 打开AT口
    main_queue_data = route_queue_put('AT', 'open', runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # 检查注网
    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # 拨打电话及查询状态
    main_queue_data = route_queue_put('AT', 'check_atd', runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # debug查询
    main_queue_data = route_queue_put('AT', 'debug_check', debug_port, debug_port_pwd, runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    # 关闭AT口
    main_queue_data = route_queue_put('AT', 'close', runtimes)
    if main_queue_data is False:
        manger.init()
        continue

    time.sleep(300)

    manger.vbat()

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
