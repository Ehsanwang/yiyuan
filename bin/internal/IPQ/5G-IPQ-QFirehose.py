# -*- encoding=utf-8 -*-
from queue import Queue
from threading import Event
import time
import datetime
import signal
import logging
from sys import path
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'IPQ'))
from functions import environment_check
environment_check()  # 检查环境
from ipq_manager import IPQManager
from ipq_route_thread import RouteThread
from uart_thread import UartThread
from ipq_qfirehose_log_thread import LogThread
from ipq_power_thread import PowerThread
from ipq_process_thread import IPQProcessThread
from functions import pause

"""
脚本逻辑
1. 初始化：模块上电2S后IPQ上电，检查能否正常识别模块；
2. 模块上电2S后IPQ上电，检查模块信息，挂载U盘；
3. 执行升级指令进行升级；
4. 如果是断电升级，则升级过程中随机断电，之后重启IPQ及模块再发送升级指令进行升级；
5. IPQ断电模块断电；
6. 模块上电2S后IPQ上电，查询模块信息是否正常；
7. 循环2-6。
"""

"""
脚本准备
1. 需要在脚本运行前确保at+qcfg="data_interface"返回值为1,0
2. 需要外接工业HUB，将版本包放入U盘中插在工业HUB上，EVB板上USB线也接入工业HUB中。
3. 初始状态为程控电源关闭，模块处于Vbat断电状态
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM28'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
power_port = 'COM26'  # 定义程控电源端口口,用于控制程控电源
ipq_port = 'COM29'  # 定义ipq的端口号，用于检测PCIE驱动加载情况
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RM500QGLABR11A04M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
VBAT = True       # 升级过程是否断电 True：升级过程中断电  False: 升级过程中不断电,目前只关注同版本断电升级
package_name = 'RM500QGLABR11A04M4G_01.001V01.01.001V01'   # 填写版本包在U盘中路径名称
ipq_number = '4019'     # 填写IPQ编号，4019或8074
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
debug = False  # 设置脚本遇到异常是停止还是继续运行False：继续运行；True：停止脚本
# ======================================================================================================================
# 辅助参数
ipq_poweron_message = 'Enable bridge snooping' if ipq_number == '8074' else 'entered forwarding state'
version = revision + sub_edition
lspci_check_value = ['17cb:1001', '17cb:0306']  # 不同的版本可能需要调整此参数，此参数参照pcie驱动加载成功后的lspci指令返回值
ls_dev_mhi_check_value = ['/dev/mhi_BHI', '/dev/mhi_DUN', '/dev/mhi_QMI0', '/dev/mhi_DIAG', '/dev/mhi_LOOPBACK']
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
ipq_info = 'IPQ{}-QFirehose-{}'.format(ipq_number, '升级断电' if VBAT else '正常升级')  # 脚本详情字符串
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
ipq_queue = Queue()
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue, power_queue, ipq_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
log_thread = LogThread(version, ipq_info, log_queue, main_queue)
power_thread = PowerThread(power_port, power_queue, main_queue, log_queue)
ipq_process_thread = IPQProcessThread(ipq_port, ipq_queue, log_queue, main_queue)
threads = [route_thread, uart_thread, log_thread, power_thread, ipq_process_thread]
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
ipq_manager = IPQManager(main_queue, route_queue, uart_queue, at_queue, log_queue, power_queue, '', uart_port, evb, version, imei, lspci_check_value, ls_dev_mhi_check_value, debug, ipq_poweron_message, '', 0, '', runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
ipq_manager.ipq_qfirehose_pcie_init()  # IPQ初始化
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
    log_queue.put(['ipq_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # ipq_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['qfirehose_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符

    # 将最新的runtimes写入类中
    ipq_manager.runtimes = runtimes

    # 查询PCIE驱动情况,挂载U盘
    check_pcie_driver_status = ipq_manager.check_qfirehose_pcie_driver_status()
    if check_pcie_driver_status is False:
        ipq_manager.ipq_qfirehose_pcie_re_init()
        continue

    # 检测模块信息
    main_queue_data = ipq_manager.module_info_check()
    if main_queue_data is False:
        ipq_manager.ipq_qfirehose_pcie_re_init()
        continue

    # 检测AT口是否正常
    check_at_status = ipq_manager.check_at()
    if check_at_status is False:
        ipq_manager.ipq_qfirehose_pcie_re_init()
        continue

    # 进行QFirehose升级
    for i in range(3):
        main_queue_data = ipq_manager.qfirehose(package_name, VBAT, runtimes)
        if main_queue_data is False:
            if i == 2:
                log_queue.put(['all', '[{}] runtimes:{} 连续三次升级异常'.format(datetime.datetime.now(), runtimes)])
                pause()
            ipq_manager.qfirehose_again(package_name, runtimes, False)
            continue
        if VBAT:
            main_queue_data = ipq_manager.qfirehose_again(package_name, runtimes)
            if main_queue_data is False:
                if i == 2:
                    log_queue.put(['all', '[{}] runtimes:{} 连续三次升级异常'.format(datetime.datetime.now(), runtimes)])
                    pause()
                ipq_manager.qfirehose_again(package_name, runtimes, False)
                continue
        # 重启检查版本号是否正常
        main_queue_data = ipq_manager.qfirehose_check()
        if main_queue_data is False:
            ipq_manager.qfirehose_again(package_name, runtimes)
            continue
        break

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
