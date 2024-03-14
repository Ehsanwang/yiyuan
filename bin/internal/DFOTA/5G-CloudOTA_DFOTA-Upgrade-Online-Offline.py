# -*- encoding=utf-8 -*-
import re
import time
import signal
import datetime
import logging
from sys import path
import os

path.append(os.path.join('..', '..', '..', 'lib', 'Communal'))
path.append(os.path.join('..', '..', '..', 'lib', 'DFOTA'))
from functions import environment_check

environment_check()  # 检查环境
from CloudOta_dfota_manager import OtaDfotaManager
from route_thread import RouteThread
from at_thread import ATThread
from uart_thread import UartThread
from process_thread import ProcessThread
from queue import Queue
from threading import Event
from CloudOta_dfota_log_thread import LogThread
from functions import pause

"""
环境准备：
1. 确认Python环境(python>3.6, 64位, 安装好requirements.txt的所有依赖)；
2. 使用VBAT接线方式，接线参考开关机脚本VBAT开关机方式
注意:新5G_M.2_EVB  DTR置为DTR_ON 无需跳线
3. 准备DFOTA升级的版本号
4. 需要将版本包放入服务器

脚本逻辑:
1. A-B升级
   1. 打开AT口
   2. 检查版本号
   3. 检查模块信息
   4. 配置网址和升级码
   5. 检查flash读写次数
   6. 发送DFOTA升级指令
   7. 检查升级包下载状态
   8. 再次检查flash读写次数
   9  检查驱动消失
   10. 检查驱动加载
   11. 打开AT口
   12. 检查DFOTA升级过程
   13. 关闭AT口
   14. 检查驱动消失
   16. 检查驱动加载
   17. 打开AT口
   18. 检查URC
   19. 检查升级后版本是否正确
   20. 检查模块信息
   21. 模块进行找网
   22. 关闭AT口
2. 进行B-A升级
3. 重复1-2。
"""

# ======================================================================================================================
# 必选参数
uart_port = 'COM18'  # 定义串口号,用于控制DTR引脚电平或检测URC信息
at_port = 'COM15'  # 定义AT端口号,用于发送AT指令或检测URC信息
dm_port = 'COM13'  # 定义DM端口号,用于判断模块有无DUMP
debug_port = ''  # RM模块参数设置为''，但是需要连接跳线读取debug log，RG需要设置为DEBUG UART串口号
revision = 'RG502QEUAAR12A02M4G_Yctopen_BL'  # 设置Revision版本号，填写ATI+CSUB查询的Revision部分
sub_edition = 'V06'  # 设置SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
after_upgrade_revision = "RG502QEUAAR12A02M4G_YctOpen_BL_BETA_20211116A"  # 设置升级后的Revision版本号，填写ATI+CSUB查询的Revision部分
after_upgrade_sub_edition = "V01"  # 设置升级后的SubEdition版本号，填写ATI+CSUB查询的SubEdition部分
imei = '869710030002905'  # 模块测试前配置IMEI号
# VBAT = False  # 升级过程是否断电 True：升级过程中断电  False: 升级过程中不断电
http_or_https = 1  # 在线升级方式 0：http 1: https 
server_address = 'https://iot-gateway.quectel.com'  # 云平台服务器地址
config_username = 'Y256NnBCYXc2bnRv'  # 配置项目识别码
config_password = 'p111G4'  # 配置项目识别码
is_5g_m2_evb = False  # 适配RM新EVB压力挂测,True: 当前使用EVB为5G_M.2_EVB ,False:当前使用为M.2_EVB_V2.2或普通EVB(5G_EVB_V2.2)
# ======================================================================================================================
# 可选参数
runtimes_temp = 0  # 设置脚本运行次数，默认0是不限次数，如果设置1000则脚本运行1000个runtimes后自动结束
timing = 12  # 设置脚本的运行时间，单位为h，默认0是不限制时间，如果设置12则脚本运行12小时后自动结束
# ======================================================================================================================
# 辅助参数
evb = 'EVB' if revision.upper().startswith('RG') else 'M.2'  # RG默认evb参数为EVB，RM默认evb参数为M.2
version = revision + sub_edition
after_upgrade_version = after_upgrade_revision + after_upgrade_sub_edition
#is_ufs = os.path.isfile(a_b_package_path)  # 如果是UFS方式，会返回True，HTTP/HTTPS/FTP方式返回False
online_error_list = ['10700', '10701', '10703', '10704', '10705', '10706', '10707', '10708', '10709', '10710',
                     '10713', '10714', '10715', '10600', '10601', '10602', '10603', '10604', '10605', '10606',
                     '10607', '10608', '10609', '10610', '10611', '10612']
package_path = ''
package_name = ''
a_b_version = ''
b_a_version = ''
runtimes = 0
info='OTA'
script_start_time = time.time()  # 脚本开始的时间，用作最后log统计
dfota_info = 'DFOTA-{}-正常升级'.format(info)  # 脚本详情字符串
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
log_thread = LogThread(version, dfota_info, http_or_https, log_queue, main_queue)
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
dfota_manager = OtaDfotaManager(main_queue, route_queue, uart_queue, log_queue, uart_port, evb, version,
                                after_upgrade_version, imei, '', http_or_https, is_5g_m2_evb, runtimes)
log_queue.put(['at_log', '{}initialize{}'.format('=' * 35, '=' * 35)])
print("\rinitialize", end="")
dfota_manager.dfota_init()
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
    log_queue.put(['flash_log', "{}runtimes:{}{}\n".format('=' * 35, runtimes, '=' * 35)])  # at_log写入分隔符
    dfota_manager.runtimes = runtimes

    # 进行正向或逆向升级
    for mode in ('forward', 'backward'):  # forward代表正向升级，backward代表逆向升级
        # 参数赋值
        if mode == 'forward':
            log_queue.put(['at_log', '[{}] 开始进行A-B升级'.format(datetime.datetime.now())])
            a_b_version = version  # 当前前版本号
            b_a_version = after_upgrade_version  # 升级后版本号

        elif mode == 'backward':
            log_queue.put(['at_log', '[{}] 开始进行B-A升级'.format(datetime.datetime.now())])
            a_b_version = after_upgrade_version  # 当前版本号
            b_a_version = version  # 升级后版本号

        dfota_manager.mode = mode

        while True:
            """
            OTA升级差分包下载流程：
            1. 打开AT口
            2. 检查版本号
            3. 检查模块信息
            4. 配置差分包网址,识别码,时延,及升级方式
            5. flash分区擦写量查询
            6. 执行升级指令
            7. 检查差分包下载状态
            8. flash分区擦写量查询
            9. 关闭AT口
            10. 检测驱动消失
            """
            # 1.打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 开机检测ATFWD
            main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 2.检查版本号
            main_queue_data = route_queue_put('AT', 'dfota_version_check', a_b_version, mode, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            time.sleep(4)
            # 3.检查模块信息
            main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 4.找网
            main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 5.配置差分包网址,识别码,时延,及升级方式
            main_queue_data = route_queue_put('AT', 'config_fotacfg', http_or_https, server_address, config_username, config_password, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 6.升级包下载前flash分区擦写量查询
            route_queue_put('AT', 'qftest_value_record', mode, runtimes)

            # 7.进行DFOTA升级
            log_queue.put(
                ['df', runtimes, 'fota_a_b_start_timestamp' if mode == 'forward' else 'fota_b_a_start_timestamp',
                 time.time()])
            main_queue_data = route_queue_put('AT', 'AT+QFOTAUP=100', 10, 1, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 8.检测"fota",6 上报
            main_queue_data = route_queue_put('AT', 'fota_online_download_urc_check', online_error_list, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 9.升级包下载完成后flash分区擦写量查询
            route_queue_put('AT', 'qftest_value_record', mode, runtimes)

            # 10.关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 11.检查驱动消失，驱动消失失败说明DFOTA异常，暂停退出脚本
            route_queue_put('Process', 'check_usb_driver_dis', True, runtimes)

            break  # 全部正常时退出该循环

        while True:
            """
            OTA升级差分包升级流程：
            1. 检测USB驱动加载
            2. 打开AT口
            3. 读取AT口DFOTA升级信息
            4. 关闭AT口
            5. 检测驱动消失
            """
            # 1.检测USB驱动加载
            main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 2.打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 3.读取AT口DFOTA升级信息
            main_queue_data = route_queue_put('AT', 'check_otafota_status', [version, after_upgrade_version], mode, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 4.关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 5.检查驱动消失，驱动消失失败说明DFOTA异常，暂停退出脚本
            route_queue_put('Process', 'check_usb_driver_dis', True, runtimes)

            break  # 退出升级成功后的循环

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
            # 1.检测USB驱动加载
            main_queue_data = route_queue_put('Process', 'check_usb_driver', True, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 2.打开AT口
            main_queue_data = route_queue_put('AT', 'open', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 3. 检查URC
            main_queue_data = route_queue_put('AT', 'check_urc', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 3. 检查URC
            main_queue_data = route_queue_put('AT', 'check_success_urc', mode, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 开机检测ATFWD
            main_queue_data = route_queue_put('AT', 'check_atfwdok', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_OTA_exception_init()
                continue

            # 4. 检查版本号
            main_queue_data = route_queue_put('AT', 'dfota_version_check', b_a_version, mode, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 5. 检查模块信息
            main_queue_data = route_queue_put('AT', 'check_module_info', imei, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 6. 找网
            main_queue_data = route_queue_put('AT', 'check_network', False, runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 查询统计还原次数
            main_queue_data = route_queue_put('AT', 'check_restore', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            # 7. 关闭AT口
            main_queue_data = route_queue_put('AT', 'close', runtimes)
            if main_queue_data is False:
                dfota_manager.dfota_otaupgrade_exception_init()
                continue

            break  # 退出升级成功后的循环

    # LOG相关
    log_queue.put(['to_csv'])  # 所有LOG写入CSV
    if mode == 'backward':  # 只有反向升级完成时候才写入result_log
        log_queue.put(['write_result_log', runtimes])  # 每个runtimes往result_log文件写入log
