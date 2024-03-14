# -*- encoding=utf-8 -*-
import time
import signal
from sys import path
import logging
import os
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'Dial'))
from functions import environment_check, pause, iperf39_check
environment_check()  # 检查环境
iperf39_check()  # 检查iperf版本
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
1. Ubuntu必须更新iperf3.9，更新方法见下
2. 禁用本地连接
3. iperf3的官方文档地址为 https://iperf.fr/iperf-doc.php，有各种参数的解释

iperf3获取和环境变量设置方法：
Windows10：
    1. 把脚本目录下的iperf3.exe和cygwin1.dll放到任何位置，然后配置环境变量
    2. 如果之前配置过iperf3的老版本环境变量，删除之前环境变量配置的iperf3老版本
    3. 打开新的命令行，输入iperf3 -v 显示 iperf 3.9即配置成功
Ubuntu 64 bits :
    1. sudo apt remove iperf3 libiperf0
    2. sudo apt install libsctp1
    3. wget https://iperf.fr/download/ubuntu/libiperf0_3.9-1_amd64.deb
    4. wget https://iperf.fr/download/ubuntu/iperf3_3.9-1_amd64.deb
    5. sudo dpkg -i libiperf0_3.9-1_amd64.deb iperf3_3.9-1_amd64.deb
    6. rm libiperf0_3.9-1_amd64.deb iperf3_3.9-1_amd64.deb

    如果提示libssl1.1缺失，操作如下步骤安装libssl1.1后重新运行上面1-6命令行
    1. wget http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.0g-2ubuntu4_amd64.deb
    2. sudo dpkg -i libssl1.1_1.1.0g-2ubuntu4_amd64.deb
QSS：
1. 如果需要使用QSS进行打流，需要保证 "iperf3 --version"返回3.9版本号，安装方法见上。
2. 需要下载安装ssh service，然后脚本server、user、password需要填写为QSS实际内容：
    a. sudo apt-get update
    b. sudo apt-get install openssh-server
    c. service sshd start
    d. ps -ef | grep sshd  （需要查询到sshd服务在后台正常运行）
"""

"""
脚本逻辑：
1. AT初始化（ATE1， ATI+CSUB，AT+EGMR=0,7等指令）
2. 进行iperf测速
3. 循环2
"""

"""
mode参数的设置
1: TCP上传-client发送-server接收
2: TCP下载-client接收-server发送
3: TCP上下同传-client-server同时发送并接收
4: UDP上传-client发送-server接收
5: UDP下载-client接收-server发送
6: UDP上下同传-client-server同时发送并接收
"""

# ======================================================================================================================
# 必选参数
uart_port = 'COM3'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
debug_port = 'COM4'  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
at_port = 'COM14'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM12'  # 定义DM端口号,用于判断模块有无dump
modem_port = 'COM15'  # 定义MODEM端口号,用于检测拨号过程中网络状态信息
revision = 'RG500QEAAAR11A03M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V03'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
mode = 3  # 配置iperf模式  1：TCP发送; 2：TCP接收; 3：TCP上下同传; 4: UDP发送; 5: UDP接收; 6: UDP上下同传
server = '112.31.84.164'  # 设置iperf服务器的IP地址
user = 'Q'  # 配置iperf服务器的ssh用户名
password = 'st'  # 配置iperf服务器的ssh密码
port = 19999  # 配饰iperf服务器的ssh端口
bandwidth = '10M'  # 配置iperf TCP或UDP的带宽，速率为单位为Mbits/sec，例如'20M'
times = '100'  # 每次iperf运行时间，默认100，根据需求修改
dial_mode = "NDIS"  # 拨号模式字符串，仅用于记录
# ======================================================================================================================
# 可选参数
# ip, user, passwd, mode, times, bandwidth, interval, bind, parallel, length, window, mtu, omit, runtimes
interval = None  # log每次返回的间隔，默认1S一次log
bind = None  # 是否绑定网卡，如果需要绑定，则输入对应网卡的IP
parallel = None  # 使用的线程数，默认为None(1个线程)
length = None  # The length of buffers to read or write. default 128 KB for TCP, dynamic or 1460 for UDP
window = None  # TCP/UDP window size
mtu = None  # The MTU(maximum segment size) - 40 bytes for the header. ethernet MSS is 1460 bytes (1500 byte MTU).
omit = None  # omit n, skip n seconds
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 其他参数
runtimes = 0
version = revision + sub_edition
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
mode_mapping = {
    1: 'TCP上传-client发送-server接收',
    2: 'TCP下载-client接收-server发送',
    3: 'TCP上下同传-client-server同时发送并接收',
    4: 'UDP上传-client发送-server接收',
    5: 'UDP下载-client接收-server发送',
    6: 'UDP上下同传-client-server同时发送并接收',
}
dial_info = 'iperf-{}-{}-长连'.format(dial_mode, mode_mapping[mode])  # 脚本详情字符串
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
log_thread = LogThread(mode, version, dial_info, 0, log_queue, main_queue)
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
def handler(signal_num, frame=None):  # noqa
    """
    脚本结束参数统计。
    """
    route_queue_put('end_script', script_start_time, runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
dial_manager = DialManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version, imei, dial_mode, 0,
                           '', '', '', '', '', '', '', '', runtimes)
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
        route_queue_put('end_script', script_start_time, runtimes, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    logger.info("{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35))  # _.log写入分隔符号
    dial_manager.runtimes = runtimes

    ping_thread.runtimes = runtimes  # 连接成功后开始ping的标志
    modem_thread.runtimes = runtimes

    main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        pause()

    # flash分区擦写量查询
    route_queue_put('AT', 'qftest_record', runtimes)

    # AT+QDMEM?分区内存泄露查询
    if runtimes % 50 == 0:
        time.sleep(2)
        route_queue_put('AT', 'memory_leak_monitoring', runtimes)

    main_queue_data = route_queue_put('AT', 'check_qtemp', runtimes)
    if main_queue_data is False:
        ping_thread.df_flag = True  # ping写入log
        modem_thread.modem_flag = True
        pause()

    # 进行iperf3测试
    # ip, user, passwd, mode, times, bandwidth, interval, bind, parallel, length, window, mtu, omit, runtimes
    route_queue_put('Process', 'iperf', server, user, password, port, mode, times,
                    bandwidth, interval, bind, parallel, length, window, mtu, omit, runtimes)

    ping_thread.df_flag = True  # ping写入log
    time.sleep(1)  # 等待ping log
    modem_thread.modem_flag = True  # modem口停止网络状态check

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
