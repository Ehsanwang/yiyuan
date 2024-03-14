# -*- encoding=utf-8 -*-
import time
import signal
from sys import path
import logging
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'Dial'))
from dial_manager import DialManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from dial_process_thread import DialProcessThread
from queue import Queue
from threading import Event
from dial_log_thread_iperf import LogThread
from dial_ping_thread import PingThread
from dial_modem_thread import ModemThread

"""
注意事项：
1. 禁用本地连接
2. 下载配置iperf3路径到环境变量
3. 配置iperf3服务器和端口，如果上下同传则需要两个端口，不能与别人跑的脚本端口重复
4. iperf3的输出为单次输出log，所以每隔times参数设置的时间，才会写入一次at_log，非脚本卡死
5. iperf3的官方文档地址为 https://iperf.fr/iperf-doc.php，有各种参数的解释

iperf3获取和环境变量设置方法：
Windows10：
    1. 官网下载 https://iperf.fr/download/windows/iperf-3.1.3-win64.zip
    2. 解压后放到任何位置，然后配置环境变量
    3. 打开命令行，输入iperf3，不提示：'iperf3' 不是内部或外部命令，也不是可运行的程序则为配置成功。
Ubuntu 64 bits :
    1. sudo apt remove iperf3 libiperf0
    2. sudo apt install libsctp1
    3. wget https://iperf.fr/download/ubuntu/libiperf0_3.7-3_amd64.deb
    4. wget https://iperf.fr/download/ubuntu/iperf3_3.7-3_amd64.deb
    5. sudo dpkg -i libiperf0_3.7-3_amd64.deb iperf3_3.7-3_amd64.deb
    6. rm libiperf0_3.7-3_amd64.deb iperf3_3.7-3_amd64.deb
    7. 打开命令行，输入iperf3，不报错即为配置成功
"""

"""
脚本逻辑：
1. AT初始化（ATE1， ATI+CSUB，AT+EGMR=0,7等指令）
2. 进行iperf测速
3. 循环2
"""

"""
脚本有以下几种参数设置：

1. # 仅TCP上传
server = '118.25.146.158'
port = '5201'
bandwidth = '10M'  # 带宽根据需求设置
udp = False
reverse = False

2. # 仅TCP下载
server = '118.25.146.158'
port = '5201'
bandwidth = '10M'  # 带宽根据需求设置
udp = False
reverse = True

3. # TCP上下同传
server = '118.25.146.158'
port = '5201,5202'
bandwidth = '10M,20M'  # 带宽根据需求设置，逗号前为上传，逗号后为下载
udp = False
reverse = True  / reverse = False  ## False和True均可

4. # 仅UDP上传
server = '118.25.146.158'
port = '5201'
bandwidth = '10M'  # 带宽根据需求设置
udp = True
reverse = False

5. # 仅UDP下载
server = '118.25.146.158'
port = '5201'
bandwidth = '10M'  # 带宽根据需求设置
udp = True
reverse = True

3. # UDP上下同传
server = '118.25.146.158'
port = '5201,5202'
bandwidth = '10M,20M'  # 带宽根据需求设置，逗号前为上传，逗号后为下载
udp = True
reverse = True  / reverse = False  ## False和True均可
"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM10'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM14'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM13'  # 定义DM端口号,用于判断模块有无dump
debug_port = 'COM15'  # RG模块如果需要抓debug口log，则需要设置此参数，否则设为''
modem_port = 'COM16'  # 定义MODEM端口号,用于检测拨号过程中网络状态信息
revision = 'RG500QEAAAR01A01M4G_BETA_20200518H'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V01'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
dial_mode = 'NDIS'  # 设置当前拨号方式，仅用作log记录
server = '118.25.146.158'  # 设置iperf服务器的IP地址
port = '5201,5202'  # iperf端口:仅上传或下载，仅需配置一个端口，例如'5201'；上下同传需要配置两个端口，中间用英文逗号隔开 '5201,5202'
bandwidth = '20M,50M'  # 配置iperf TCP或UDP速率，速率为单位为Mbits/sec，例如'20M'，如果上下同传需要配置两个速率用英文逗号隔开 '20M,20M'
times = '100'  # 每次iperf运行时间，默认100，根据需求修改
reverse = False  # 进行上传还是下载测试，True：下载测试；False：上传测试，上下同传设置True/False均可
udp = False  # iperf是进行TCP还是UDP方式： True：UDP；False：TCP
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
runtimes = 0
version = revision + sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
u_d = '下载' if reverse else '上传'
info = '上下同传' if len(port.split(',')) == 2 else u_d
dial_info = 'iperf-{}-{}-{}-{}-长连'.format('UDP' if udp else 'TCP', info, bandwidth, dial_mode)  # 脚本详情字符串
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
modem_queue = Queue()
route_thread = RouteThread(route_queue, uart_queue, process_queue, at_queue)
uart_thread = UartThread(uart_port, debug_port, uart_queue, main_queue, log_queue)
process_thread = DialProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, dial_info, 0, log_queue, main_queue)
ping_thread = PingThread(runtimes, log_queue)
modem_thread = ModemThread(runtimes, log_queue, modem_port, modem_queue)
threads = [route_thread, uart_thread, process_thread, at_thread, log_thread, ping_thread, modem_thread]
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
    route_queue_put('end_script', udp, reverse, port, bandwidth, script_start_time, runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
dial_manager = DialManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, dial_mode, 0, '', '', '', '', '', '', runtimes)
input('请确认以太网连接断开后按Enter键继续...')
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
dial_init_iperf_only_status = dial_manager.dial_init_iperf_only()
if dial_init_iperf_only_status is False:  # 如果需要重新开始，运行re_init
    print('脚本初始化异常，请检查参数设置后重新运行脚本')
    exit()
# ======================================================================================================================
# 主流程
while True:
    # 脚本自动停止判断
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or (timing != 0 and time.time() - script_start_time > timing * 3600):  # 如果runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
        route_queue_put('end_script', udp, reverse, port, bandwidth, script_start_time, runtimes - 1, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    dial_manager.runtimes = runtimes

    ping_thread.runtimes = runtimes  # 连接成功后开始ping的标志
    modem_thread.runtimes = runtimes

    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        log_queue.put(['all', "检查网络异常"])
        input("保留现场，问题定位完成后请直接关闭脚本")
        exit()

    # 温度查询
    main_queue_data = route_queue_put('AT', 'check_qtemp', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        log_queue.put(['all', "温度查询异常"])
        input("保留现场，问题定位完成后请直接关闭脚本")
        exit()

    # 进行iperf3测试
    route_queue_put('Process', 'iperf', server, port, times, bandwidth, reverse, udp, runtimes)

    ping_thread.df_flag = True  # ping写入log
    time.sleep(1)  # 等待ping log
    modem_thread.modem_flag = True  # modem口停止网络状态check

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', udp, reverse, port, runtimes])  # 每个runtimes往result_log文件写入log
