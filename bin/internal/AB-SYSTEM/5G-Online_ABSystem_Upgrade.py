# -*- encoding=utf-8 -*-
import re
import time
import signal
import datetime
import logging
from sys import path
import os

path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'ABSYSTEM'))
from functions import environment_check

environment_check()  # 检查环境
from ab_dfota_manager import DfotaManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from queue import Queue
from threading import Event
from ab_dfota_log_thread import LogThread

"""
环境准备：
1. 确认Python环境(python>3.6, 64位, 安装好requirements.txt的所有依赖)；
2. 使用VBAT接线方式，接线参考开关机脚本VBAT开关机方式
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
3. 准备DFOTA升级的版本号
4. 需要打开adb

脚本逻辑:
脚本逻辑:
1. A-B升级
   a. 打开AT口
   b. 检查版本号
   c. 检查模块信息
   d. 查询升级前系统状态
   e. 下载差分包
   f. 验证ufs
   g. 命名版本包
   h. 查询UFS
   i. 执行升级指令
   j. 查询升级时系统状态
   k. 检测fota升级过程
   l. 关闭AT口
   m. 检查驱动消失
   n. 检查驱动加载
   o. 打开AT口
   p. 检查URC
   q. 检查升级后版本是否正确
   r. 检查模块信息
   s. 模块进行找网
   t. 查询ufs  
   u. 检测AB系统同步状态
   v. 检查flash使用状态
   w. 查询ufs
   x. 关闭AT口
2. 进行B-A升级
3. 重复1-2。
"""

# ======================================================================================================================
# 必选参数
uart_port = 'COM18'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM15'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM11'  # 定义DM端口号,用于判断模块有无DUMP
debug_port = 'COM17'  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'SG520TMDAR01A01M4G_BETA_20220128A'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V03'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
after_upgrade_revision = "SG520TMDAR01A02M4G"  # 设置升级后的Revision版本号，填写ATI+CSUB查询的Revision部分
after_upgrade_sub_edition = "V01"  # 设置升级后的SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
a_b_package_path = r'http://112.31.84.164:8302/jaime/SG520TMDA_BETA_TO_A02.zip'  # a到b版本的升级包路径
b_a_package_path = r'http://112.31.84.164:8302/jaime/SG520TMDA_A02_TO_BETA.zip'  # b到a版本的升级包路径
a_b_packagename = 'SG520TMDA_BETA_TO_A02.zip'  # a到b的差分包名称，用于后面的指令命名
b_a_packagename = 'SG520TMDA_A02_TO_BETA.zip'  # b到a的差分包名称，用于后面的指令命名
imei = '869710030002905'  # 模块测试前配置IMEI号
VBAT = False  # 升级过程是否断电 True：升级过程中断电  False: 升级过程中不断电
adb_or_at = 0  # adb方式上传差分包 0：adb 目前只支持adb方式
backup_vbat = False  # 升级完成后AB系统同步是否断电 True：同步过程中断电  False: 同步过程中不断电
download_vbat = True  # 下载差分包时是否断电  True:断电  False:不断电
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
# ======================================================================================================================
# 可选参数
runtimes_temp = 1  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 0  # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
version = revision + sub_edition
after_upgrade_version = after_upgrade_revision + after_upgrade_sub_edition
upgrade_error_list = ['520', '521', '522', '523', '524', '525', '526', '527', '528', '529', '530',
                      '540', '541', '542', '543', '544', '545', '546']  # 定义升级可能出现的错误代码
package_error_list = ['502', '504', '505', '510', '511']
online_error_list = ['601', '602', '701', '702']
a_b_package_name = os.path.basename(a_b_package_path)  # a_b升级的package_name
b_a_package_name = os.path.basename(b_a_package_path)  # b_a升级的package_name
abpackagename = os.path.basename(a_b_packagename)
bapackagename = os.path.basename(b_a_packagename)
package_path = ''
package_name = ''
a_b_version = ''
b_a_version = ''
runtimes = 0
info = 'UFS' if len(re.split(r'[\\|/]', a_b_package_path)[0]) < 3 else re.split(r'[\\|/]', a_b_package_path)[0][:-1]
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
dfota_info = 'Online_DFOTA-{}-{}-{}'.format(info, '升级断电' if VBAT else '正常升级',
                                            '同步时断电' if backup_vbat else '正常同步')  # 脚本详情字符串
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
log_thread = LogThread(version, dfota_info, adb_or_at, log_queue, main_queue)
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
def handler(signal_num, frame=None):  # noqa
    """
    脚本结束参数统计。
    """
    route_queue_put('end_script', script_start_time, runtimes, queue=log_queue)  # 结束脚本统计log
    exit()


# ======================================================================================================================
# 初始化
signal.signal(signal.SIGINT, handler)  # 捕获Ctrl+C，当前方法可能有延迟
dfota_manager = DfotaManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version,
                             after_upgrade_version, imei, package_error_list, upgrade_error_list, '', adb_or_at,
                             is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
dfota_manager.abdfota_init()
# ======================================================================================================================
# 主流程
while True:
    # 脚本自动停止判断
    runtimes += 1
    time.sleep(0.1)  # 此处停止0.1为了防止先打印runtimes然后才打印异常造成的不一致
    if (runtimes_temp != 0 and runtimes > runtimes_temp) or (
            timing != 0 and time.time() - script_start_time > timing * 3600):  # 如果runtimes到达runtimes_temp参数设定次数或者当前runtimes时间超过timing设置时间，则停止脚本
        route_queue_put('end_script', script_start_time, runtimes - 1, queue=log_queue)  # 结束脚本统计log
        break

    # 打印当前runtimes，写入csv
    print("\rruntimes: {} ".format(runtimes), end="")
    log_queue.put(['df', runtimes, 'runtimes', str(runtimes)])  # runtimes
    log_queue.put(['df', runtimes, 'runtimes_start_timestamp', time.time()])  # runtimes_start_timestamp
    log_queue.put(['at_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['debug_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    log_queue.put(['memory_log', "{}runtimes:{}{}\n".format('=' * 60, runtimes, '=' * 60)])  # at_log写入分隔符
    dfota_manager.runtimes = runtimes

    # 进行正向或逆向升级
    for mode in ('forward', 'backward'):  # forward代表正向升级，backward代表逆向升级
        # 参数赋值
        if mode == 'forward':
            log_queue.put(['at_log', '[{}] 开始进行A-B升级'.format(datetime.datetime.now())])
            package_path = a_b_package_path  # 要升级的升级包的路径
            package_name = a_b_packagename  # 要升级的升级包的名称
            a_b_version = version  # 当前前版本号
            b_a_version = after_upgrade_version  # 升级后版本号

        elif mode == 'backward':
            log_queue.put(['at_log', '[{}] 开始进行B-A升级'.format(datetime.datetime.now())])
            package_path = b_a_package_path  # 要升级的升级包的路径
            package_name = b_a_packagename  # 要升级的升级包的名称
            a_b_version = after_upgrade_version  # 当前版本号
            b_a_version = version  # 升级后版本号

        dfota_manager.mode = mode

        while True:
            """
            流程：
            1. 打开AT口
            2. 检查版本号
            3. 检查模块信息
            4. 查询升级前系统状态
            5. 下载差分包
            6. 验证ufs
            7. 差分包命名
            8. 查询UFS
            9. 发送升级指令
            10. 查询升级时系统状态
            11. 检测fota升级
            12. 关闭AT口
            """
            # 1.打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 开机检测ATFWD
            main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_normal_exception_init()
                continue

            # 2.检查版本号
            main_queue_data = route_queue_put('AT', 'dfota_version_check', a_b_version, mode, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            time.sleep(4)
            # 3.检查模块信息
            main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 进行找网
            main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 4.查询升级前系统状态
            main_queue_data = route_queue_put('AT', 'check_fotastate', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 检测adb devices是否有设备
            main_queue_data = route_queue_put('Process', 'check_adb_devices_connect', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 5.下载差分包
            main_queue_data = route_queue_put('AT', 'download_ab_package', package_path, online_error_list,
                                              download_vbat, package_name, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            if download_vbat:  # 下载差分包过程中断电重启
                dfota_status = dfota_manager.online_abfota_download_vbat()
                if dfota_status is False:
                    continue

                time.sleep(10)  # 刚下载完差分包名称可能不为update，需等待一段时间查询为准
                # 检查ufs是否存在残留
                main_queue_data = route_queue_put('AT', 'download_vbat_ufscheck', package_name, runtimes)
                if main_queue_data is False:
                    dfota_manager.dfota_ab_exception_init()
                    continue

                # 重新下载差分包
                main_queue_data = route_queue_put('AT', 'download_ab_package', package_path, online_error_list, False,
                                                  package_name, runtimes)
                if main_queue_data is False:
                    dfota_manager.dfota_ab_exception_init()
                    continue

            # 查下差分包下载成功
            main_queue_data = route_queue_put('AT', 'check_download_ufs', package_name, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 差分包命名
            main_queue_data = route_queue_put('AT', 'set_package_name', package_name, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            time.sleep(2)
            # 下载差分包后查询UFS
            time.sleep(2)
            main_queue_data = route_queue_put('AT', 'check_ufs_package', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            time.sleep(2)
            # 8.发送DFota升级指令
            log_queue.put(
                ['df', runtimes, 'fota_a_b_start_timestamp' if mode == 'forward' else 'fota_b_a_start_timestamp',
                 time.time()])
            main_queue_data = route_queue_put('AT', 'at+qabfota="update"', 10, 1, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 9.检测DFOTA升级
            main_queue_data = route_queue_put('AT', 'check_adbfota_status', [version, after_upgrade_version],
                                              package_error_list, upgrade_error_list, mode, VBAT, runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            if VBAT:  # 如果VBAT，则需要VBAT，重新检查驱动
                dfota_status = dfota_manager.dfota_upgradeAB_vbat()
                if dfota_status is False:
                    continue

            # 10.关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            break  # 全部正常时退出该循环

        while True:
            """
            DFOTA全部升级成功后：
            1. 检测USB驱动加载
            2. 打开AT口
            3. 检测URC
            4. 检查版本号

            5. 检查模块信息
            6. 检查网络信息
            7. 查询ufs
            8. 检查AB系统同步
            9.查询flash分区
            10.查询ufs
            11. 关闭AT口
            """
            # 检测驱动消失
            main_queue_data = route_queue_put('Process', 'check_usb_driver_dis', True, runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            # 1. 检测驱动
            main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            # 2. 打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            # 3. 检查URC
            main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            # 开机检测ATFWD
            main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_normal_exception_init()
                continue

            # 4. 检查版本号
            main_queue_data = route_queue_put('AT', 'dfota_version_check', b_a_version, mode, runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            # 6. 检查模块信息
            main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            # 7. 找网
            main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            # 升级成功后查询UFS
            time.sleep(2)
            main_queue_data = route_queue_put('AT', 'check_ufs_package', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 8.检查系统同步 同步时间估计为10分钟，30秒检查一次同步状态
            main_queue_data = route_queue_put('AT', 'check_twosystem_synchronization', backup_vbat, mode, runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            # 同步断电
            if backup_vbat:
                dfota_status = dfota_manager.dfota_backupAB_vbat()
                if dfota_status is False:
                    continue

            # 9.flash分区擦写量查询
            route_queue_put('AT', 'qftest_record', runtimes)

            # 查询统计还原次数
            main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 同步成功后后查询UFS
            time.sleep(2)
            main_queue_data = route_queue_put('AT', 'check_ufs_package', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_ab_exception_init()
                continue

            # 10. 关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                dfota_manager.abfota_upgrade_exception_init()
                continue

            break  # 退出升级成功后的循环

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    if mode == 'backward':  # 只有反向升级完成时候才写入result_log
        log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
