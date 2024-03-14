# -*- encoding=utf-8 -*-
# 5G_Dial_TCP_UDP_FTP_HTTP_PING.py的参数统计
from logging.handlers import RotatingFileHandler
from threading import Thread
from pandas import DataFrame
import time
import sys
import os
import re
import pandas as pd
import numpy as np
import logging
import platform
import json

cefs_erasetimes_list = []
ufs_erasetimes_list = []
class LogThread(Thread):
    def __init__(self, version, restart_mode, dial_mode, info, log_queue, main_queue):
        super().__init__()
        self.version = version
        self.restart_mode = restart_mode
        self.info = info
        self.log_queue = log_queue
        self.main_queue = main_queue
        self.dial_mode = dial_mode
        self.df = DataFrame(columns=['runtimes_start_timestamp'])
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]

        # 初始化log文件夹
        self.init_log_dir(self.info)

        # 初始化log文件
        self.at_log_handle = open('ATLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.dos_log_handle = open('DOSLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.debug_log_handle = open('Debug-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.ping_log_handle = open('PINGLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.modem_log_handle = open('MODEMLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.result_log_handle = open('RESULTLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.network_log_handle = open('NETWORKLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.handles = ['self.at_log_handle', 'self.dos_log_handle', 'self.debug_log_handle',
                        'self.result_log_handle', 'self.network_log_handle', 'self.ping_log_handle',
                        'self.modem_log_handle']
        if os.name != 'nt':
            self.quectel_cm_log_handle = open('QUECTEL_CM-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
            self.handles.append('self.quectel_cm_log_handle')
        self.thread_timestamp = time.time()

        # 初始化往at_log写入当前脚本的名称
        _, file_name = os.path.split(os.path.realpath(sys.argv[0]))
        self.at_log_handle.write("测试类型: {}-{}\n".format(file_name, self.info))
        self.at_log_handle.write('测试环境：{}-{}-{}\n'.format(platform.platform(), platform.machine(), sys.version))
        try:
            with open('../../../../lib/Communal/version.json') as f:
                version_info = json.loads(f.read())
        except FileNotFoundError:
            with open('../version.json') as f:
                version_info = json.loads(f.read())
        self.at_log_handle.write('脚本版本：{}-{}\n'.format(version_info['date'], version_info['commit_id']))

        # 初始化logger
        handler = RotatingFileHandler('_.log', 'a', 1024 * 1024 * 100, 10, delay=False)
        handler.setFormatter(logging.Formatter('[%(asctime)s.%(msecs)03d] %(levelname)s %(module)s->%(lineno)d->%(funcName)s->%(message)s'))
        handler.setLevel(logging.DEBUG)
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

    def run(self):
        while True:
            module, *param = self.log_queue.get()
            if (time.time() - self.thread_timestamp) > 300:
                self.log_size_checker()
                self.thread_timestamp = time.time()
            if module in self._methods_list:
                if 'end_script' == module:
                    evt = param.pop()
                    getattr(self.__class__, '{}'.format(module))(self, *param)
                    self.main_queue.put(True)
                    evt.set()
                else:
                    getattr(self.__class__, '{}'.format(module))(self, *param)

    def log_size_checker(self):
        for handle in self.handles:
            exec(f"""if {handle}.tell() > 1024 * 1024 * 100:
                        {handle}.close()
                        file_name = {handle}.name
                        file_name = (file_name + '.1') if file_name[-1] not in '0123456789' else '{{}}.{{}}'.format('.'.join(file_name.split('.')[:2]), int(file_name.split('.')[-1]) + 1)
                        {handle} = open(file_name, "a+", encoding='utf-8', buffering=1)""")

    def at_log(self, log_queue_data):
        self.at_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

    def dos_log(self, log_queue_data):
        self.dos_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

    def debug_log(self, log_queue_data):
        self.debug_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

    def ping_log(self, log_queue_data):
        self.ping_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

    def modem_log(self, log_queue_data):
        self.modem_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

    def result_log(self, log_queue_data):
        self.result_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

    def network_log(self, log_queue_data):
        self.network_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

    def quectel_cm_log(self, log_queue_data):
        self.quectel_cm_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

    def all(self, log_queue_data):
        content_print = re.sub(r'\[.*?]\s*(Run|run)times\s*:\s*\d+\s+', '', log_queue_data)
        content_at = re.sub(r'(Run|run)times\s*:\s*\d+\s+', '', log_queue_data)
        print(content_print)
        self.at_log_handle.write(content_at + '\n')
        self.dos_log_handle.write(log_queue_data + '\n')

    def df(self, runtimes, column_name, content):
        self.df.loc[runtimes, column_name] = content  # 推送数据到DataFrame
        if 'error' in column_name:  # 如果有错误上报立刻写入csv
            self.df.to_csv('_cache.csv', index=False)  # 保存到csv文件并且去除索引

    def to_csv(self):
        self.df.to_csv('_cache.csv', index=False)  # 保存到csv文件并且去除索引

    def init_log_dir(self, info):
        """
        初始化log存放的文件夹，将当前的时间作为文件夹的名称
        :param info: 当前脚本的类型
        :return: None
        """
        local_time = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
        file_path = os.path.join(os.getcwd(), '{}-{}'.format(local_time, info))
        os.mkdir(file_path)  # 创建文件夹
        os.chdir(file_path)  # 进入创建的文件夹

        # 避免KeyError, init_df_column中列表的值都为下面参数统计中用到的值
        init_df_column = ['runtimes', 'dial_connect_time', 'dial_fail_times',
                          'dial_disconnect_time', 'dial_disconnect_fail_times',
                          'tcp_fail_times', 'udp_fail_times', 'ftp_fail_times', 'http_fail_times',
                          'ping_package_loss_rate', 'ip_address', 'qtemp_list', 'dial_disconnect_success_times', 'cefs_erase_times',
                          'usrdata_erase_times']
        for column_name in init_df_column:
            self.df.loc[0, column_name] = np.nan

    def write_result_log(self, runtimes):
        pass
        """
        每个runtimes写入result_log的内容
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        if self.restart_mode == 1 or self.restart_mode == 2:
            # 用作写入result_log时宽度设置
            result_width_standard = {0: ['local_time', 25], 1: ['runtimes', 8],
                                     2: ['dial_connect_time(S)', 20], 3: ['dial_fail_times', 15],
                                     4: ['dial_disconnect_time(S)', 23], 5: ['dial_disconnect_fail_times', 26],
                                     6: ['tcp_fail_times', 14], 7: ['udp_fail_times', 14],
                                     8: ['ftp_fail_times', 14], 9: ['http_fail_times', 15],
                                     10: ['ping_package_loss_rate', 22], 11: ['ip_address', 30], 12: ['qtemp_list', 50],
                                     13: ['cefs_erase_times', 10], 14: ['usrdata_erase_times', 10]}

        else:
            # 用作写入result_log时宽度设置
            result_width_standard = {0: ['local_time', 25], 1: ['runtimes', 8],
                                     2: ['dial_connect_time(S)', 20], 3: ['dial_fail_times', 15],
                                     4: ['dial_disconnect_time(S)', 23], 5: ['dial_disconnect_fail_times', 26],
                                     6: ['tcp_fail_times', 14], 7: ['udp_fail_times', 14],
                                     8: ['ftp_fail_times', 14], 9: ['http_fail_times', 15],
                                     10: ['ping_package_loss_rate', 22], 11: ['ip_address', 30], 12: ['qtemp_list', 50],
                                     13: ['cefs_erasetimes', 10], 14: ['usrdata_erasetimes', 10]}


        # 当runtimes为1的时候，拼接所有的统计参数并写入log
        if runtimes == 1:
            header_string = ''
            for index, (para, width) in result_width_standard.items():
                header_string += format(para, '^{}'.format(width)) + '\t'  # 将变量格式化为指定宽度后加制表符(\t)
            self.result_log_handle.write(header_string + '\n')
        # # 参数统计
        runtimes_start_timestamp = self.df.loc[runtimes, 'runtimes_start_timestamp']  # 写入当前runtimes的时间戳
        local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(float(runtimes_start_timestamp))))
        dial_connect_time = '' if pd.isna(self.df.loc[runtimes, 'dial_connect_time']) else round(float(self.df.loc[runtimes, 'dial_connect_time']), 2)
        dial_fail_times = int(self.df['dial_fail_times'].sum())
        dial_disconnect_time = '' if pd.isna(self.df.loc[runtimes, 'dial_disconnect_time']) else round(float(self.df.loc[runtimes, 'dial_disconnect_time']), 2)
        dial_disconnect_fail_times = int(self.df['dial_disconnect_fail_times'].sum())
        tcp_fail_times = int(self.df['tcp_fail_times'].sum())
        udp_fail_times = int(self.df['udp_fail_times'].sum())
        ftp_fail_times = int(self.df['ftp_fail_times'].sum())
        http_fail_times = int(self.df['http_fail_times'].sum())
        ping_package_loss_rate = '{:.2f}%'.format(self.df.loc[runtimes, 'ping_package_loss_rate']) if pd.notna(self.df.loc[runtimes, 'ping_package_loss_rate']) else ''
        ip_address = '' if pd.isna(self.df.loc[runtimes, 'ip_address']) else self.df.loc[runtimes, 'ip_address']
        qtemp_list = '' if pd.isna(self.df.loc[runtimes, 'qtemp_list']) else self.df.loc[runtimes, 'qtemp_list']

        if self.restart_mode == 1 or self.restart_mode == 2:
            cefs_erase_times = '' if pd.isna(self.df.loc[runtimes, 'cefs_erase_times']) else int(self.df.loc[runtimes, 'cefs_erase_times'])
            usrdata_erase_times = '' if pd.isna(self.df.loc[runtimes, 'usrdata_erase_times']) else int(self.df.loc[runtimes, 'usrdata_erase_times'])

            result_list = [local_time, runtimes, dial_connect_time, dial_fail_times, dial_disconnect_time, dial_disconnect_fail_times,
                           tcp_fail_times, udp_fail_times, ftp_fail_times, http_fail_times,
                           ping_package_loss_rate, ip_address, qtemp_list, cefs_erase_times, usrdata_erase_times]
            result_list.reverse()  # 反转列表，便于弹出
            result_string = ''
            for index, (para, width) in result_width_standard.items():
                try:
                    result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
                except IndexError:
                    pass
            self.result_log_handle.write(result_string + '\n')

        else:
            if runtimes == 1:
                cefs_erasetimes = self.df.loc[runtimes, 'cefs_erase_times'] - self.df.loc[runtimes, 'cefs_erase_times']
                usrdata_erasetimes = self.df.loc[runtimes, 'usrdata_erase_times'] - self.df.loc[runtimes, 'usrdata_erase_times']

            else:
                cefs_erasetimes = self.df.loc[runtimes, 'cefs_erase_times'] - self.df.loc[
                    runtimes - 1, 'cefs_erase_times']
                usrdata_erasetimes = self.df.loc[runtimes, 'usrdata_erase_times'] - self.df.loc[
                    runtimes - 1, 'usrdata_erase_times']

                cefs_erasetimes_list.append(cefs_erasetimes)
                ufs_erasetimes_list.append(usrdata_erasetimes)

            # 结果统计
            result_string = ''
            result_list = [local_time, runtimes, dial_connect_time, dial_fail_times, dial_disconnect_time, dial_disconnect_fail_times,
                           tcp_fail_times, udp_fail_times, ftp_fail_times, http_fail_times,
                           ping_package_loss_rate, ip_address, qtemp_list, cefs_erasetimes, usrdata_erasetimes]

            result_list.reverse()  # 反转列表，便于弹出
            # 3. 跟据第一步创建的标准进行最后字符串的拼接
            for index, (para, width) in result_width_standard.items():
                try:
                    result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
                except IndexError:
                    pass
            self.result_log_handle.write(result_string + '\n')

    def end_script(self, script_start_time, runtimes):
        dial_connect_time_avg = ''
        dial_disconnect_time_avg = ''
        dial_disconnect_fail_times = ''
        dial_disconnect_success_rate = ''
        script_start_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(script_start_time))
        script_end_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
        ping_package_loss_rate = np.round(np.mean(self.df['ping_package_loss_rate'].dropna()), 2)
        # 拨号连接参数
        if self.dial_mode.upper() in ["NDIS", "MBIM"] and os.name == 'nt':
            dial_connect_time_avg = np.round(np.mean(self.df['dial_connect_time'].dropna()), 2)  # 拨号平均时间
        dial_fail_times = int(self.df['dial_fail_times'].sum())  # 拨号失败次数
        dial_success_rate = '{:.2f}%'.format((runtimes - dial_fail_times) * 100 / runtimes)  # 拨号成功率
        # 拨号断开连接参数
        if self.dial_mode.upper() in ["NDIS", "MBIM"] and os.name == 'nt':
            dial_disconnect_time_avg = np.round(np.mean(self.df['dial_disconnect_time'].dropna()), 2)  # 拨号断开连接平均时间
            dial_disconnect_fail_times = int(self.df['dial_disconnect_fail_times'].sum())  # 拨号断开连接连接失败次数
            dial_disconnect_success_rate = '{:.2f}%'.format(self.df['dial_disconnect_success_times'].sum() * 100 / (self.df['dial_disconnect_fail_times'].sum() + self.df['dial_disconnect_success_times'].sum()))  # tcp_upd断开连接成功率
        # TCP等参数
        tcp_fail_times = int(self.df['tcp_fail_times'].sum())
        udp_fail_times = int(self.df['udp_fail_times'].sum())
        ftp_fail_times = int(self.df['ftp_fail_times'].sum())
        http_fail_times = int(self.df['http_fail_times'].sum())
        if self.dial_mode.upper() in ["NDIS", "MBIM"] and os.name == 'nt':
            dial_string = '拨号平均时间(dial_connect_time_avg)：{}秒\n'.format(dial_connect_time_avg) + \
                          '拨号失败次数(dial_fail_times)：{}次\n'.format(dial_fail_times) + \
                          '拨号成功率(dial_success_rate)：{}\n'.format(dial_success_rate) + \
                          '断开拨号平均时间(dial_connect_time_avg)：{}秒\n'.format(dial_disconnect_time_avg) + \
                          '断开拨号失败次数(dial_fail_times)：{}次\n'.format(dial_disconnect_fail_times) + \
                          '断开拨号成功率(dial_success_rate)：{}\n'.format(dial_disconnect_success_rate)
        else:
            dial_string = '拨号失败次数(dial_fail_times)：{}次\n'.format(dial_fail_times) + \
                          '拨号成功率(dial_success_rate)：{}\n'.format(dial_success_rate)

        if self.restart_mode == 1 or self.restart_mode == 2:
            # 新增统计flash擦除次数
            cefs_erase_averagetimes = self.df['cefs_erase_times'].mean()
            cefs_erase_maxtimes = self.df['cefs_erase_times'].max()
            usrdata_erase_averagetimes = self.df['usrdata_erase_times'].mean()
            usrdata_erase_maxtimes = self.df['usrdata_erase_times'].max()

            result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                     '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
                     dial_string + \
                     'TCP异常次数(tcp_fail_times)：{}次\n'.format(tcp_fail_times) + \
                     'UDP异常次数(udp_fail_times)：{}次\n'.format(udp_fail_times) + \
                     'FTP异常次数(ftp_fail_times)：{}次\n'.format(ftp_fail_times) + \
                     'HTTP异常次数(http_fail_times)：{}次\n'.format(http_fail_times) + \
                     'ping平均丢包率(ping_package_loss_rate): {}%\n'.format(ping_package_loss_rate) + \
                     'cefs平均擦除次数(cefs_erase_averagetimes): {}次\n'.format(cefs_erase_averagetimes) + \
                     'cefs最大擦除次数(cefs_erase_maxtimes): {}次\n'.format(cefs_erase_maxtimes) + \
                     'usrdata平均擦除次数(usrdata_erase_averagetimes): {}次\n'.format(usrdata_erase_averagetimes) + \
                     'usrdata最大擦除次数(usrdata_erase_maxtimes): {}次\n'.format(usrdata_erase_maxtimes)

        else:
            # 统计flash参数平均值，最大值，最小值
            cefs_erasetotal = 0
            ufs_erasetotal = 0
            for i in cefs_erasetimes_list:
                cefs_erasetotal += i
            cefs_erase_averagetimes = round(cefs_erasetotal / len(cefs_erasetimes_list), 2)
            cefs_erasetimes_list.sort(reverse=True)
            cefs_erase_maxtimes = round(cefs_erasetimes_list[0], 2)

            for j in ufs_erasetimes_list:
                ufs_erasetotal += j
            usrdata_erase_averagetimes = round(ufs_erasetotal / len(ufs_erasetimes_list), 2)
            ufs_erasetimes_list.sort(reverse=True)
            usrdata_erase_maxtimes = round(ufs_erasetimes_list[0], 2)

            result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                     '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
                     dial_string + \
                     'TCP异常次数(tcp_fail_times)：{}次\n'.format(tcp_fail_times) + \
                     'UDP异常次数(udp_fail_times)：{}次\n'.format(udp_fail_times) + \
                     'FTP异常次数(ftp_fail_times)：{}次\n'.format(ftp_fail_times) + \
                     'HTTP异常次数(http_fail_times)：{}次\n'.format(http_fail_times) + \
                     'ping平均丢包率(ping_package_loss_rate): {}%\n'.format(ping_package_loss_rate) + \
                     'cefs平均递增擦除次数(cefs_erase_averagetimes): {}次\n'.format(cefs_erase_averagetimes) + \
                     'cefs最大递增擦除次数(cefs_erase_maxtimes): {}次\n'.format(cefs_erase_maxtimes) + \
                     'usrdata平均递增擦除次数(usrdata_erase_averagetimes): {}次\n'.format(usrdata_erase_averagetimes) + \
                     'usrdata最大递增擦除次数(usrdata_erase_maxtimes): {}次\n'.format(usrdata_erase_maxtimes)

        print(result)
        with open('统计结果.txt', 'a', encoding='utf-8', buffering=1) as f:
            f.write('-----------压力统计结果start-----------{}-----------压力统计结果end-----------\n'.format(result))
