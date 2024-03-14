# -*- encoding=utf-8 -*-
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


class LogThread(Thread):
    def __init__(self, version, info, connect_mode, log_queue, main_queue):
        super().__init__()
        self.version = version
        self.info = info
        self.connect_mode = connect_mode
        self.log_queue = log_queue
        self.main_queue = main_queue
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
        init_df_column = ['runtimes', 'dial_connect_time', 'dial_fail_times', 'post_file_time',
                          'post_file_fail_times', 'file_compare_fail_times', 'ip_error_times',
                          'get_file_time', 'get_file_fail_times',
                          'dial_disconnect_time', 'dial_disconnect_fail_times',
                          'ping_package_loss_rate', 'ip_address', 'qtemp_list', 'dial_disconnect_success_times', 'cefs_erase_times',
                          'usrdata_erase_times']
        for column_name in init_df_column:
            self.df.loc[0, column_name] = np.nan

    def write_result_log(self, runtimes):
        """
        每个runtimes写入result_log的内容
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        # 用作写入result_log时宽度设置
        result_width_standard_1 = {0: ['local_time', 25], 1: ['runtimes', 8],
                                   2: ['dial_connect_time', 17], 3: ['dial_connect_fail_times', 23],
                                   4: ['ip_error_times', 14],
                                   5: ['post_file_time', 14], 6: ['post_file_fail_times', 20],
                                   7: ['get_file_time', 13], 8: ['get_file_fail_times', 19],
                                   9: ['file_compare_fail_times', 23],
                                   10: ['dial_disconnect_time', 20], 11: ['dial_disconnect_fail_times', 26],
                                   12: ['ping_package_loss_rate', 22], 13: ['ip_address', 23], 14: ['qtemp_list', 50],
                                   15: ['cefs_erase_times', 10], 16: ['usrdata_erase_times', 10]}

        result_width_standard_0 = {0: ['local_time', 25], 1: ['runtimes', 8],
                                   2: ['post_file_time', 14], 3: ['post_file_fail_times', 20],
                                   4: ['get_file_time', 13], 5: ['get_file_fail_times', 19],
                                   6: ['file_compare_fail_times', 23], 7: ['ping_package_loss_rate', 22],
                                   8: ['ip_address', 23], 9: ['qtemp_list', 50], 10: ['cefs_erase_times', 10],
                                   11: ['usrdata_erase_times', 10]}

        result_width_standard = result_width_standard_1 if self.connect_mode == 1 else result_width_standard_0
        # 当runtimes为1的时候，拼接所有的统计参数并写入log
        if runtimes == 1:
            header_string = ''
            for index, (para, width) in result_width_standard.items():
                header_string += format(para, '^{}'.format(width)) + '\t'  # 将变量格式化为指定宽度后加制表符(\t)
            self.result_log_handle.write(header_string + '\n')

        # 参数统计
        runtimes_start_timestamp = self.df.loc[runtimes, 'runtimes_start_timestamp']  # 写入当前runtimes的时间戳
        local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(float(runtimes_start_timestamp))))
        dial_connect_time = '' if pd.isna(self.df.loc[runtimes, 'dial_connect_time']) else round(float(self.df.loc[runtimes, 'dial_connect_time']), 2)
        dial_connect_fail_times = int(self.df['dial_fail_times'].sum())
        post_file_time = '' if pd.isna(self.df.loc[runtimes, 'post_file_time']) else round(float(self.df.loc[runtimes, 'post_file_time']), 2)
        post_file_fail_times = int(self.df['post_file_fail_times'].sum())
        file_compare_fail_times = int(self.df['file_compare_fail_times'].sum())
        ip_error_times = int(self.df['ip_error_times'].sum())
        get_file_time = '' if pd.isna(self.df.loc[runtimes, 'get_file_time']) else round(float(self.df.loc[runtimes, 'get_file_time']), 2)
        get_file_fail_times = int(self.df['get_file_fail_times'].sum())
        dial_disconnect_time = '' if pd.isna(self.df.loc[runtimes, 'dial_disconnect_time']) else round(float(self.df.loc[runtimes, 'dial_disconnect_time']), 2)
        dial_disconnect_fail_times = int(self.df['dial_disconnect_fail_times'].sum())
        ping_package_loss_rate = '{:.2f}%'.format(self.df.loc[runtimes, 'ping_package_loss_rate']) if pd.notna(self.df.loc[runtimes, 'ping_package_loss_rate']) else ''
        ip_address = '' if pd.isna(self.df.loc[runtimes, 'ip_address']) else self.df.loc[runtimes, 'ip_address']
        qtemp_list = '' if pd.isna(self.df.loc[runtimes, 'qtemp_list']) else self.df.loc[runtimes, 'qtemp_list']
        cefs_erase_times = '' if pd.isna(self.df.loc[runtimes, 'cefs_erase_times']) else int(self.df.loc[runtimes, 'cefs_erase_times'])
        usrdata_erase_times = '' if pd.isna(self.df.loc[runtimes, 'usrdata_erase_times']) else int(self.df.loc[runtimes, 'usrdata_erase_times'])

        result_list_1 = [local_time, runtimes, dial_connect_time, dial_connect_fail_times,
                         ip_error_times,
                         post_file_time, post_file_fail_times,
                         get_file_time, get_file_fail_times,
                         file_compare_fail_times,
                         dial_disconnect_time, dial_disconnect_fail_times,
                         ping_package_loss_rate, ip_address, qtemp_list, cefs_erase_times, usrdata_erase_times]
        result_list_2 = [local_time, runtimes, post_file_time, post_file_fail_times, get_file_time, get_file_fail_times,
                         file_compare_fail_times, ping_package_loss_rate, ip_address, qtemp_list, cefs_erase_times, usrdata_erase_times]
        result_list = result_list_1 if self.connect_mode == 1 else result_list_2
        result_list.reverse()  # 反转列表，便于弹出
        result_string = ''
        for index, (para, width) in result_width_standard.items():
            try:
                result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
            except IndexError:
                pass
        self.result_log_handle.write(result_string + '\n')
        # 拨号时间         dial_connect_time
        # 拨号失败次数     dial_fail_times
        # 拨号成功率       dial_success_times/(dial_success_times - dial_fail_times)
        # -----------------------------------------------------------------------------
        # Post文件时间      post_file_time
        # Post文件失败次数  post_file_fail_times
        # Post文件成功率    post_file_success_times/(post_file_success_times + post_file_fail_times)
        # -----------------------------------------------------------------------------
        # Get文件时间  get_file_time
        # Get文件失败次数  get_file_fail_times
        # Get文件成功率  get_file_success_times/(get_file_success_times + get_file_fail_times)
        # -----------------------------------------------------------------------------
        # 断开拨号时间     dial_disconnect_time
        # 断开拨号失败次数 dial_disconnect_fail_times
        # 断开拨号成功率   dial_disconnect_success_times/(dial_disconnect_fail_times + dial_disconnect_success_times)
        # -----------------------------------------------------------------------------
        # 文件对比失败次数 file_compare_fail_times
        # IP检查失败次数   ip_error_times
        # 接收数据时间     download_file_end_timestamp - download_file_start_timestamp

    def end_script(self, script_start_time, connection_type, runtimes):
        script_start_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(script_start_time))
        script_end_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
        ping_package_loss_rate = np.round(np.mean(self.df['ping_package_loss_rate'].dropna()), 2)
        # 新增统计flash擦除次数
        cefs_erase_averagetimes = int(self.df['cefs_erase_times'].mean())
        cefs_erase_maxtimes = int(self.df['cefs_erase_times'].max())
        cefs_erase_mintimes = int(self.df['cefs_erase_times'].min())
        usrdata_erase_averagetimes = int(self.df['usrdata_erase_times'].mean())
        usrdata_erase_maxtimes = int(self.df['usrdata_erase_times'].max())
        usrdata_erase_mintimes = int(self.df['usrdata_erase_times'].min())

        if self.connect_mode == 1:
            # 拨号连接参数
            dial_connect_time_avg = np.round(np.mean(self.df['dial_connect_time'].dropna()), 2)  # 拨号平均时间
            dial_fail_times = int(self.df['dial_fail_times'].sum())  # 拨号失败次数
            dial_success_rate = '{:.2f}%'.format((runtimes - dial_fail_times) * 100 / runtimes)  # 拨号成功率
            # Post文件参数
            post_file_time_avg = np.round(np.mean(self.df['post_file_time'].dropna()), 2)  # 上传文件平均时间
            post_file_fail_times = int(self.df['post_file_fail_times'].sum())  # 上传文件失败次数
            post_file_success_rate = '{:.2f}%'.format(self.df['post_file_success_times'].sum() * 100 / (self.df['post_file_fail_times'].sum() + self.df['post_file_success_times'].sum()))  # tcp_upd连接成功率
            # Get文件参数
            get_file_time_avg = np.round(np.mean(self.df['get_file_time'].dropna()), 2)  # 下载文件平均时间
            get_file_fail_times = int(self.df['get_file_fail_times'].sum())  # 下载文件失败次数
            get_file_success_rate = '{:.2f}%'.format(self.df['get_file_success_times'].sum() * 100 / (self.df['get_file_fail_times'].sum() + self.df['get_file_success_times'].sum()))  # tcp_upd断开连接成功率
            # 拨号断开连接参数
            dial_disconnect_time_avg = np.round(np.mean(self.df['dial_disconnect_time'].dropna()), 2)  # 拨号断开连接平均时间
            dial_disconnect_fail_times = int(self.df['dial_disconnect_fail_times'].sum())  # 拨号断开连接连接失败次数
            dial_disconnect_success_rate = '{:.2f}%'.format(self.df['dial_disconnect_success_times'].sum() * 100 / (self.df['dial_disconnect_fail_times'].sum() + self.df['dial_disconnect_success_times'].sum()))  # tcp_upd断开连接成功率
            # 其他参数
            file_compare_fail_times = int(self.df['file_compare_fail_times'].sum())  # 文件对比失败次数
            ip_error_times = int(self.df['ip_error_times'].sum())
            result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                     '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
                     '拨号平均时间(dial_connect_time_avg)：{}秒\n'.format(dial_connect_time_avg) + \
                     '拨号失败次数(dial_fail_times)：{}次\n'.format(dial_fail_times) + \
                     '拨号成功率(dial_success_rate)：{}\n'.format(dial_success_rate) + \
                     '{}上传文件平均时间(post_file_time)：{}秒\n'.format(connection_type, post_file_time_avg) + \
                     '{}上传文件失败次数(post_file_fail_times)：{}次\n'.format(connection_type, post_file_fail_times) + \
                     '{}上传文件成功率(post_file_success_rate)：{}\n'.format(connection_type, post_file_success_rate) + \
                     '{}下载文件平均时间(get_file_time_avg)：{}秒\n'.format(connection_type, get_file_time_avg) + \
                     '{}下载文件失败次数(get_file_fail_times)：{}次\n'.format(connection_type, get_file_fail_times) + \
                     '{}下载文件成功率(get_file_success_rate)：{}\n'.format(connection_type, get_file_success_rate) + \
                     '断开拨号平均时间(dial_connect_time_avg)：{}秒\n'.format(dial_disconnect_time_avg) + \
                     '断开拨号失败次数(dial_fail_times)：{}次\n'.format(dial_disconnect_fail_times) + \
                     '断开拨号成功率(dial_success_rate)：{}\n'.format(dial_disconnect_success_rate) + \
                     '网络连接检查失败次数(ip_error_times)：{}次\n'.format(ip_error_times) + \
                     '文件对比失败次数(file_compare_fail_times)：{}次\n'.format(file_compare_fail_times) + \
                     'ping平均丢包率(ping_package_loss_rate): {}%\n'.format(ping_package_loss_rate) + \
                     'cefs平均擦除次数(cefs_erase_averagetimes): {}次\n'.format(cefs_erase_averagetimes) + \
                     'cefs最大擦除次数(cefs_erase_maxtimes): {}次\n'.format(cefs_erase_maxtimes) + \
                     'cefs最小擦除次数(cefs_erase_mintimes): {}次\n'.format(cefs_erase_mintimes) + \
                     'usrdata平均擦除次数(usrdata_erase_averagetimes): {}次\n'.format(usrdata_erase_averagetimes) + \
                     'usrdata最大擦除次数(usrdata_erase_maxtimes): {}次\n'.format(usrdata_erase_maxtimes) + \
                     'usrdata最小擦除次数(usrdata_erase_mintimes): {}次\n'.format(usrdata_erase_mintimes)
        else:
            # Post文件参数
            post_file_time_avg = np.round(np.mean(self.df['post_file_time'].dropna()), 2)  # post上传文件平均时间
            post_file_fail_times = int(self.df['post_file_fail_times'].sum())  # post上传文件失败次数
            post_file_success_rate = '{:.2f}%'.format(self.df['post_file_success_times'].sum() * 100 / (self.df['post_file_fail_times'].sum() + self.df['post_file_success_times'].sum()))  # tcp_upd连接成功率
            # Get文件参数
            get_file_time_avg = np.round(np.mean(self.df['get_file_time'].dropna()), 2)  # get下载文件平均时间
            get_file_fail_times = int(self.df['get_file_fail_times'].sum())  # get下载文件失败次数
            get_file_success_rate = '{:.2f}%'.format(self.df['get_file_success_times'].sum() * 100 / (self.df['get_file_fail_times'].sum() + self.df['get_file_success_times'].sum()))  # tcp_upd断开连接成功率
            # 其他参数
            file_compare_fail_times = int(self.df['file_compare_fail_times'].sum())  # 文件对比失败次数
            result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                     '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
                     '上传文件平均时间(post_file_time)：{}秒\n'.format(post_file_time_avg) + \
                     '上传文件失败次数(post_file_fail_times)：{}次\n'.format(post_file_fail_times) + \
                     '上传文件成功率(post_file_success_rate)：{}\n'.format(post_file_success_rate) + \
                     '下载文件平均时间(get_file_time_avg)：{}秒\n'.format(get_file_time_avg) + \
                     '下载文件失败次数(get_file_fail_times)：{}次\n'.format(get_file_fail_times) + \
                     '下载文件成功率(get_file_success_rate)：{}\n'.format(get_file_success_rate) + \
                     '文件对比失败次数(file_compare_fail_times)：{}次\n'.format(file_compare_fail_times) + \
                     'ping平均丢包率(ping_package_loss_rate): {}%\n'.format(ping_package_loss_rate) + \
                     'cefs平均擦除次数(cefs_erase_averagetimes): {}次\n'.format(cefs_erase_averagetimes) + \
                     'cefs最大擦除次数(cefs_erase_maxtimes): {}次\n'.format(cefs_erase_maxtimes) + \
                     'cefs最小擦除次数(cefs_erase_mintimes): {}次\n'.format(cefs_erase_mintimes) + \
                     'usrdata平均擦除次数(usrdata_erase_averagetimes): {}次\n'.format(usrdata_erase_averagetimes) + \
                     'usrdata最大擦除次数(usrdata_erase_maxtimes): {}次\n'.format(usrdata_erase_maxtimes) + \
                     'usrdata最小擦除次数(usrdata_erase_mintimes): {}次\n'.format(usrdata_erase_mintimes)

        print(result)
        with open('统计结果.txt', 'a', encoding='utf-8', buffering=1) as f:
            f.write('-----------压力统计结果start-----------{}-----------压力统计结果end-----------\n'.format(result))
