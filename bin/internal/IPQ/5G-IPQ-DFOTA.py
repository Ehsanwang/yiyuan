# -*- encoding=utf-8 -*-
from queue import Queue
from threading import Event
import time
import signal
import logging
from sys import path
import os
import datetime
path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'IPQ'))
from functions import environment_check
environment_check()  # 检查环境
from ipq_manager import IPQManager
from ipq_route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from ipq_dfota_log_thread import LogThread
from ipq_power_thread import PowerThread
from ipq_process_thread import IPQProcessThread
from functions import pause

"""
    脚本逻辑
    初始化检查是否开启adb和设备at+qcfg="data_interface",1,0
    本地升级方式逻辑（AT方式有问题，暂以adb方式上传差分包）
    1、check adb设备
    2、上传差分包
    3、at+qflst="*"校验版本包大小
    4、IPQ上校验版本
    5、查询和对比模块IMEI、CFUN、CPIN号
    6、进行FOTA升级(暂IPQ上捕获不到FOTA升级URC，模块usb直连电脑在AT口确认)
    7、重复4-6
    8、重复1-7

 """

"""
脚本准备

"""

# ======================================================================================================================
# 需要配置的参数
uart_port = 'COM8'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM15'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM16'  # 定义DM端口号,用于判断模块有无dump
power_port = 'COM14'  # 定义程控电源端口口,用于控制程控电源
ipq_port = 'COM11'  # 定义ipq的端口号，用于检测PCIE驱动加载情况
ipq_mode = 0       # ipq设备型号 0: 8074  1:4019
debug_port = 'COM19'  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RM502QAEAAR11A03M4G'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V03'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
after_upgrade_revision = "RM502QAEAAR11A02M4G"  # 设置升级后的Revision版本号，填写ATI+CSUB查询的Revision部分
after_upgrade_sub_edition = "V02"  # 设置升级后的SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
a_b_package_path = r'F:\\st-5g\\Python\\modify\\ipq\\f.zip'  # a到b版本的升级包路径，精确到包名，路径可以是本地电脑路径，也可是FTP/HTTP/HTTPS/
b_a_package_path = r'F:\\st-5g\\Python\\modify\\ipq\\z.zip'  # b到a版本的升级包路径，精确到包名，路径可以是本地电脑路径，也可是FTP/HTTP/HTTPS/
ufs_path = '/cache/ufs'  # UFS方式需要设置此参数：RG500设置/data/ufs, RM500设置/cache/ufs，具体根据版本确定
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0   # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
is_ufs = True    # 本地升级：True 在线升级：False
debug = False  # 设置脚本遇到异常是停止还是继续运行False：继续运行；True：停止脚本
# ======================================================================================================================
# 辅助参数
version = revision + sub_edition
after_upgrade_version = after_upgrade_revision + after_upgrade_sub_edition
lspci_check_value = ['17cb:1001', '17cb:0306'] if ipq_mode == 1 else ['17cb:1002', '17cb:0306']    # 不同的版本可能需要调整此参数，此参数参照pcie驱动加载成功后的lspci指令返回值
ipq_poweron_message = 'entered forwarding state' if ipq_mode == 1 else 'Enable bridge snooping'
ls_dev_mhi_check_value = ['/dev/mhi_BHI', '/dev/mhi_DUN', '/dev/mhi_QMI0', '/dev/mhi_DIAG', '/dev/mhi_LOOPBACK']
upgrade_error_list = ['520', '521', '522', '523', '524', '525', '526', '527', '528', '529', '530', '502', '540', '541', '542', '543', '544', '545', '546']  # 定义升级可能出现的错误代码
package_error_list = ['504', '505', '511']
a_b_package_name = os.path.basename(a_b_package_path)  # a_b升级的package_name
b_a_package_name = os.path.basename(b_a_package_path)  # b_a升级的package_name
package_path = ''
package_name = ''
a_b_version = ''
b_a_version = ''
runtimes = 0
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
ipq_info = 'IPQ-PCIE-DFOTA-Stress'  # 脚本详情字符串
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
process_thread = ProcessThread(at_port, dm_port, process_queue, main_queue, log_queue)
at_thread = ATThread(at_port, dm_port, at_queue, main_queue, log_queue)
log_thread = LogThread(version, ipq_info, log_queue, main_queue)
power_thread = PowerThread(power_port, power_queue, main_queue, log_queue)
ipq_process_thread = IPQProcessThread(ipq_port, ipq_queue, log_queue, main_queue)
threads = [route_thread, uart_thread, process_thread, at_thread, log_thread, power_thread, ipq_process_thread]
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
ipq_manager = IPQManager(main_queue, route_queue, uart_queue, at_queue, log_queue, power_queue, at_port, uart_port, evb, version, imei, lspci_check_value, ls_dev_mhi_check_value, debug, ipq_poweron_message, '', 0, '', runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
ipq_manager.ipq_pcie_dfota_init()  # IPQ初始化
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

    # 将最新的runtimes写入类中
    ipq_manager.runtimes = runtimes

    for mode in ('forward', 'backward'):
        if is_ufs:  # 如果是UFS方式
            if mode == 'forward':
                log_queue.put(['at_log', '[{}] 开始进行A-B升级'.format(datetime.datetime.now())])
                package_path = a_b_package_path  # 要升级的升级包的路径
                package_name = a_b_package_name  # 要升级的升级包的名称
                a_b_version = version  # 当前前版本号
                b_a_version = after_upgrade_version  # 升级后版本号
            elif mode == 'backward':
                log_queue.put(['at_log', '[{}] 开始进行B-A升级'.format(datetime.datetime.now())])
                package_path = b_a_package_path  # 要升级的升级包的路径
                package_name = b_a_package_name  # 要升级的升级包的名称
                a_b_version = after_upgrade_version  # 当前版本号
                b_a_version = version  # 升级后版本号

        if is_ufs:
            while True:
                ipq_manager.poweron_evb_ipq()  # 模块和ipq上电
                # 打开AT口
                main_queue_data = route_queue_put('AT', 'open', runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # checkURC
                main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # 开机检测ATFWD
                main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # 检查版本号
                main_queue_data = route_queue_put('AT', 'dfota_version_check', a_b_version, mode, runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # 检查模块信息
                main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # 检测adb devices是否有设备
                main_queue_data = route_queue_put('Process', 'check_adb_devices_connect', runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # 推送升级包
                main_queue_data = route_queue_put('Process', 'adb_push_package', package_path, ufs_path, runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # 检查升级包
                main_queue_data = route_queue_put('AT', 'check_file_size', package_path, runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # 开启pcie
                main_queue_data = route_queue_put('AT', 'data_interface', 1, debug, runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                # 关闭AT口
                main_queue_data = route_queue_put('AT', 'close', runtimes)
                if main_queue_data is False:
                    ipq_manager.poweroff_evb_ipq()
                    continue
                ipq_manager.poweroff_evb_ipq()   # 模块和ipq断电
                # 设备重启，IPQ上进行DFOTA升级
                log_queue.put(['df', runtimes, 'fota_a_b_start_timestamp' if mode == 'forward' else 'fota_b_a_start_timestamp', time.time()])
                qfotadl_status = ipq_manager.ipq_pcie_qfotadl(ufs_path, package_name)
                if qfotadl_status is False:
                    ipq_manager.ipq_pcie_re_init()
                    continue
                # 校验505错误
                main_queue_data = route_queue_put('AT', 'fota_urc_check', at_port, dm_port, runtimes)
                if main_queue_data is False:
                    ipq_manager.ipq_pcie_re_init()
                    continue
                # 检查驱动消失
                route_queue_put('Process', 'check_usb_driver_dis', True, runtimes)
                break  # 全部正常时退出该循环
        for i in range(1, 5):
            if i == 4:
                log_queue.put(['all', '[{}] runtimes:{} 连续三次升级异常'.format(datetime.datetime.now(), runtimes)])
                pause()
            main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                ipq_manager.poweron_evb_ipq()
                continue
            # 打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                ipq_manager.poweron_evb_ipq()
                continue
            # 检测DFOTA升级
            main_queue_data = route_queue_put('AT', 'check_dfota_status', [version, after_upgrade_version], package_error_list, upgrade_error_list, mode, False, runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                ipq_manager.poweron_evb_ipq()
                continue
            # 关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                ipq_manager.poweron_evb_ipq()
                continue
            # 检查驱动消失
            route_queue_put('Process', 'check_usb_driver_dis', True, runtimes)
            break  # DFOTA升级完成后break
        while True:
            """
            DFOTA全部升级成功后：
            1. 检测USB驱动加载
            2. 打开AT口
            3. 检测URC
            4. 检查版本号
            5. 检查模块信息
            6. 检查网络信息
            7. 关闭AT口
            """
            ipq_manager.poweron_evb_ipq()  # 模块和ipq上电
            # 打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                continue
            # 检查URC
            main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                continue
            # 开机检测ATFWD
            main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                continue
            # 检查版本号
            main_queue_data = route_queue_put('AT', 'dfota_version_check', b_a_version, mode, runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                continue
            # 5. 检查模块信息
            main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                continue
            # 6. 找网
            main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                continue

            # flash分区擦写量查询
            route_queue_put('AT', 'qftest_record', runtimes)

            # 查询统计还原次数
            main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                continue

            # 8. 关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                ipq_manager.poweroff_evb_ipq()
                continue
            break  # 退出升级成功后的循环

    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    if mode == 'backward':  # 只有反向升级完成时候才写入result_log
        log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
