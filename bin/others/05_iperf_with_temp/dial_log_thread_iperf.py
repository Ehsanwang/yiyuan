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
            print(os.getcwd())
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

        self.runtimes = ''
        self.local_time = ''
        self.speed_abnormal_times = ''

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
        init_df_column = ['runtimes', 'tcp_upload_speed', 'tcp_upload_size', 'tcp_upload_server_speed',
                          'tcp_upload_server_size', 'tcp_download_speed', 'tcp_download_size',
                          'tcp_download_server_speed', 'tcp_download_server_size', 'tcp_download_server_retransmitted',
                          'udp_upload_speed', 'udp_upload_size', 'udp_upload_packet', 'udp_server_upload_speed',
                          'udp_server_upload_size', 'udp_server_upload_jitter', 'udp_server_upload_packet',
                          'udp_server_upload_packet_lost', 'udp_server_upload_packet_lost_percent',
                          'udp_download_speed', 'udp_download_size', 'udp_download_jitter', 'udp_download_packet',
                          'udp_download_packet_lost', 'udp_download_packet_lost_percent', 'udp_server_download_speed',
                          'udp_server_download_size', 'udp_server_download_jitter', 'udp_server_download_packet',
                          'udp_server_download_packet_lost', 'udp_server_download_packet_lost_percent', 'speed_abnormal_times', 'qtemp_list']
        for column_name in init_df_column:
            self.df.loc[0, column_name] = np.nan

    def write_result_log(self, udp, reverse, port, runtimes):
        """
        每个runtimes写入result_log的内容
        :param runtimes: 当前脚本的运行次数
        :param udp:
        :param reverse:
        :param port:
        :return: None
        """
        # 用作写入result_log时宽度设置
        result_width_standard_tcp_upload = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['tcp_upload_speed', 16],
                                            3: ['tcp_upload_size', 15],
                                            4: ['tcp_upload_server_speed', 23],
                                            5: ['tcp_upload_server_size', 22],
                                            6: ['speed_abnormal_times', 20], 7: ['qtemp_list', 50]}
        result_width_standard_tcp_download = {0: ['local_time', 25], 1: ['runtimes', 8],
                                              2: ['tcp_download_speed', 18],
                                              3: ['tcp_download_size', 17],
                                              4: ['tcp_download_server_speed', 25],
                                              5: ['tcp_download_server_size', 24],
                                              6: ['tcp_download_server_retransmitted', 33],
                                              7: ['speed_abnormal_times', 20], 8: ['qtemp_list', 50]}
        result_width_standard_tcp = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['tcp_upload_speed', 16],
                                     3: ['tcp_upload_size', 15], 4: ['tcp_upload_server_speed', 23],
                                     5: ['tcp_upload_server_size', 22], 6: ['tcp_download_speed', 18],
                                     7: ['tcp_download_size', 17], 8: ['tcp_download_server_speed', 25],
                                     9: ['tcp_download_server_size', 24], 10: ['tcp_download_server_retransmitted', 33],
                                     11: ['speed_abnormal_times', 20], 12: ['qtemp_list', 50]}
        result_width_standard_udp_upload = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['udp_upload_speed', 16],
                                            3: ['udp_upload_size', 15], 4: ['udp_upload_packet', 17],
                                            5: ['udp_server_upload_speed', 23], 6: ['udp_server_upload_size', 22],
                                            7: ['udp_server_upload_jitter', 24], 8: ['udp_server_upload_packet', 24],
                                            9: ['udp_server_upload_packet_lost', 29],
                                            10: ['udp_server_upload_packet_lost_percent', 37],
                                            11: ['speed_abnormal_times', 20], 12: ['qtemp_list', 50]}
        result_width_standard_udp_download = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['udp_download_speed', 18],
                                              3: ['udp_download_size', 17], 4: ['udp_download_jitter', 19],
                                              5: ['udp_download_packet', 19], 6: ['udp_download_packet_lost', 24],
                                              7: ['udp_download_packet_lost_percent', 32], 8: ['udp_server_download_speed', 25],
                                              9: ['udp_server_download_size', 24], 10: ['udp_server_download_jitter', 26],
                                              11: ['udp_server_download_packet', 26], 12: ['udp_server_download_packet_lost', 31],
                                              13: ['udp_server_download_packet_lost_percent', 39],
                                              14: ['speed_abnormal_times', 20], 15: ['qtemp_list', 50]}
        result_width_standard_udp = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['udp_upload_speed', 16],
                                     3: ['udp_upload_size', 15], 4: ['udp_upload_packet', 17],
                                     5: ['udp_server_upload_speed', 23], 6: ['udp_server_upload_size', 22],
                                     7: ['udp_server_upload_jitter', 24], 8: ['udp_server_upload_packet', 24],
                                     9: ['udp_server_upload_packet_lost', 29],
                                     10: ['udp_server_upload_packet_lost_percent', 37],
                                     11: ['speed_abnormal_times', 20], 12: ['udp_download_speed', 18],
                                     13: ['udp_download_size', 17], 14: ['udp_download_jitter', 19],
                                     15: ['udp_download_packet', 19], 16: ['udp_download_packet_lost', 24],
                                     17: ['udp_download_packet_lost_percent', 32], 18: ['udp_server_download_speed', 25],
                                     19: ['udp_server_download_size', 24], 20: ['udp_server_download_jitter', 26],
                                     21: ['udp_server_download_packet', 26], 22: ['udp_server_download_packet_lost', 31],
                                     23: ['udp_server_download_packet_lost_percent', 39], 24: ['qtemp_list', 50]}
        ports = port.split(',')
        if len(ports) == 1 and udp and reverse is False:
            result_width_standard = result_width_standard_udp_upload
        elif len(ports) == 1 and udp and reverse:
            result_width_standard = result_width_standard_udp_download
        elif len(ports) == 1 and udp is False and reverse is False:
            result_width_standard = result_width_standard_tcp_upload
        elif len(ports) == 1 and udp is False and reverse:
            result_width_standard = result_width_standard_tcp_download
        else:
            result_width_standard = result_width_standard_udp if udp else result_width_standard_tcp
        # 当runtimes为1的时候，拼接所有的统计参数并写入log
        if runtimes == 1:
            header_string = ''
            for index, (para, width) in result_width_standard.items():
                header_string += format(para, '^{}'.format(width)) + '\t'  # 将变量格式化为指定宽度后加制表符(\t)
            self.result_log_handle.write(header_string + '\n')

        # 参数统计
        runtimes_start_timestamp = self.df.loc[runtimes, 'runtimes_start_timestamp']  # 写入当前runtimes的时间戳
        self.runtimes = runtimes
        self.local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(float(runtimes_start_timestamp))))
        for a, (x, y) in result_width_standard.items():
            if x != 'local_time' and x != 'runtimes':
                value = '' if pd.isna(self.df.loc[runtimes, x]) else self.df.loc[runtimes, x]
                setattr(self, x, value)
        self.speed_abnormal_times = int(self.df.loc[runtimes, 'speed_abnormal_times'])
        result_list = [getattr(self, x) for a, (x, y) in result_width_standard.items()]
        result_list.reverse()  # 反转列表，便于弹出
        result_string = ''
        for index, (para, width) in result_width_standard.items():
            try:
                result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
            except IndexError:
                pass
        self.result_log_handle.write(result_string + '\n')

    def end_script(self, udp, reverse, port, bandwidth, script_start_time, runtimes):
        script_start_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(script_start_time))
        script_end_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
        # tcp上传
        tcp_upload_size = np.round(np.mean(self.df['tcp_upload_size'].dropna()), 2)  # 平均上传大小
        tcp_upload_size_all = np.round(np.sum(self.df['tcp_upload_size'].dropna()), 2)  # 总上传大小
        tcp_upload_speed = np.round(np.mean(self.df['tcp_upload_speed'].dropna()), 2)  # 平均上传速度
        tcp_upload_speed_min = np.round(np.min(self.df['tcp_upload_speed'].dropna()), 2)  # 最小上传速度
        tcp_upload_speed_max = np.round(np.max(self.df['tcp_upload_speed'].dropna()), 2)  # 最大上传速度
        tcp_upload_server_size_all = np.round(np.sum(self.df['tcp_upload_server_size'].dropna()), 2)  # 服务端接收总数据
        tcp_upload_server_speed = np.round(np.mean(self.df['tcp_upload_server_speed'].dropna()), 2)  # 服务端接收平均速率
        # tcp下载
        tcp_download_size = np.round(np.mean(self.df['tcp_download_size'].dropna()), 2)
        tcp_download_size_all = np.round(np.sum(self.df['tcp_download_size'].dropna()), 2)
        tcp_download_speed = np.round(np.mean(self.df['tcp_download_speed'].dropna()), 2)
        tcp_download_speed_min = np.round(np.min(self.df['tcp_download_speed'].dropna()), 2)
        tcp_download_speed_max = np.round(np.max(self.df['tcp_download_speed'].dropna()), 2)
        tcp_download_server_size_all = np.round(np.sum(self.df['tcp_download_server_size'].dropna()), 2)  # 服务端接收总数据
        tcp_download_server_speed = np.round(np.mean(self.df['tcp_download_server_speed'].dropna()), 2)  # 服务端接收平均速率
        tcp_download_server_retransmitted = int(np.sum(self.df['tcp_download_server_retransmitted'].dropna()))  # 服务端接收平均速率
        # udp上传
        udp_upload_size = np.round(np.mean(self.df['udp_upload_size'].dropna()), 2)
        udp_upload_size_all = np.round(np.sum(self.df['udp_upload_size'].dropna()), 2)
        udp_upload_speed = np.round(np.mean(self.df['udp_upload_speed'].dropna()), 2)
        udp_upload_speed_min = np.round(np.min(self.df['udp_upload_speed'].dropna()), 2)
        udp_upload_speed_max = np.round(np.max(self.df['udp_upload_speed'].dropna()), 2)
        udp_upload_packet = int(np.sum(self.df['udp_upload_packet'].dropna()))
        udp_server_upload_speed = np.round(np.mean(self.df['udp_server_upload_speed'].dropna()), 2)
        udp_server_upload_size_all = np.round(np.sum(self.df['udp_server_upload_size'].dropna()), 2)  # 服务端接收总数据
        udp_server_upload_jitter = np.round(np.mean(self.df['udp_server_upload_jitter'].dropna()), 2)
        udp_server_upload_packet_lost = int(np.sum(self.df['udp_server_upload_packet_lost'].dropna()))
        udp_server_upload_packet = int(np.sum(self.df['udp_server_upload_packet'].dropna()))
        udp_server_upload_packet_lost_percent = np.round((np.sum(self.df['udp_server_upload_packet_lost'].dropna()) / np.sum(self.df['udp_server_upload_packet'].dropna())) * 100, 2)
        # udp下载
        udp_download_size = np.round(np.mean(self.df['udp_download_size'].dropna()), 2)
        udp_download_size_all = np.round(np.sum(self.df['udp_download_size'].dropna()), 2)
        udp_download_speed = np.round(np.mean(self.df['udp_download_speed'].dropna()), 2)
        udp_download_speed_min = np.round(np.min(self.df['udp_download_speed'].dropna()), 2)
        udp_download_speed_max = np.round(np.max(self.df['udp_download_speed'].dropna()), 2)
        udp_download_packet = int(np.sum(self.df['udp_download_packet'].dropna()))
        udp_download_jitter = np.round(np.mean(self.df['udp_download_jitter'].dropna()), 2)
        udp_download_packet_lost = int(np.sum(self.df['udp_download_packet_lost'].dropna()))
        udp_download_packet_lost_percent = np.round((np.sum(self.df['udp_download_packet_lost'].dropna()) / np.sum(self.df['udp_download_packet'].dropna())) * 100, 2)
        udp_server_download_speed = np.round(np.mean(self.df['udp_server_download_speed'].dropna()), 2)
        udp_server_download_size_all = np.round(np.sum(self.df['udp_server_download_size'].dropna()), 2)  # 服务端接收总数据
        udp_server_download_jitter = np.round(np.mean(self.df['udp_server_download_jitter'].dropna()), 2)
        udp_server_download_packet_lost = int(np.sum(self.df['udp_server_download_packet_lost'].dropna()))
        udp_server_download_packet = int(np.sum(self.df['udp_server_download_packet'].dropna()))
        udp_server_download_packet_lost_percent = np.round((np.sum(self.df['udp_server_download_packet_lost'].dropna()) / np.sum(self.df['udp_server_download_packet'].dropna())) * 100, 2)
        speed_abnormal_times = int(np.sum(self.df['speed_abnormal_times']))
        result_head = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                      '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes)
        result_tcp_upload = 'TCP上传最小速率(tcp_upload_speed_min)：{} Mbits/sec\n'.format(tcp_upload_speed_min) + \
                            'TCP上传最大速率(tcp_upload_speed_max)：{} Mbits/sec\n'.format(tcp_upload_speed_max) + \
                            'TCP上传平均速率(tcp_upload_speed)：{} Mbits/sec\n'.format(tcp_upload_speed) + \
                            'TCP上传平均发送(tcp_upload_size)：{} MBytes\n'.format(tcp_upload_size) + \
                            'TCP上传共发送(tcp_upload_size_all): {} MBytes\n'.format(tcp_upload_size_all) + \
                            '服务端接收平均速率(tcp_upload_server_speed)：{} Mbits/sec\n'.format(tcp_upload_server_speed) + \
                            '服务端接收数据量(tcp_upload_server_size_all)：{} MBytes\n'.format(tcp_upload_server_size_all)
        result_tcp_download = 'TCP下载最小速率(tcp_download_speed_min)：{} Mbits/sec\n'.format(tcp_download_speed_min) + \
                              'TCP下载最大速率(tcp_download_speed_max)：{} Mbits/sec\n'.format(tcp_download_speed_max) + \
                              'TCP下载平均速率(tcp_download_speed)：{} Mbits/sec\n'.format(tcp_download_speed) + \
                              'TCP下载接收(tcp_download_size)：{} MBytes\n'.format(tcp_download_size) + \
                              'TCP下载共接收(tcp_download_size_all): {} MBytes\n'.format(tcp_download_size_all) + \
                              '服务端发送平均速率(tcp_download_server_speed)：{} Mbits/sec\n'.format(tcp_download_server_speed) + \
                              '服务端发送数据量(tcp_download_server_size_all)：{} MBytes\n'.format(tcp_download_server_size_all) + \
                              '服务端重发次数(tcp_download_server_retransmitted)：{} 次\n'.format(tcp_download_server_retransmitted)
        result_udp_upload = 'UDP上传最小速率(udp_upload_speed_min)：{} Mbits/sec\n'.format(udp_upload_speed_min) + \
                            'UDP上传最大速率(udp_upload_speed_max)：{} Mbits/sec\n'.format(udp_upload_speed_max) + \
                            'UDP上传平均速率(udp_upload_speed)：{} Mbits/sec\n'.format(udp_upload_speed) + \
                            'UDP上传平均发送(udp_upload_size)：{} MBytes\n'.format(udp_upload_size) + \
                            'UDP上传共发送(udp_upload_size_all): {} MBytes\n'.format(udp_upload_size_all) + \
                            'UDP上传数据包(udp_upload_packet)：{} 个\n'.format(udp_upload_packet) + \
                            '服务端接收平均速率(udp_server_upload_speed)：{} Mbits/sec\n'.format(udp_server_upload_speed) + \
                            '服务端接收数据量(udp_server_upload_size_all)：{} MBytes\n'.format(udp_server_upload_size_all) + \
                            '服务端平均抖动(udp_server_upload_jitter)：{} ms\n'.format(udp_server_upload_jitter) + \
                            '服务端丢包数(udp_server_upload_packet_lost)：{} 个\n'.format(udp_server_upload_packet_lost) + \
                            '服务端总包数(udp_server_upload_packet)：{} 个\n'.format(udp_server_upload_packet) + \
                            '服务端平均丢包率(udp_server_upload_packet_lost_percent)：{} %\n'.format(udp_server_upload_packet_lost_percent)
        result_udp_download = 'UDP下载最小速率(udp_download_speed_min)：{} Mbits/sec\n'.format(udp_download_speed_min) + \
                              'UDP下载最大速率(udp_download_speed_max)：{} Mbits/sec\n'.format(udp_download_speed_max) + \
                              'UDP下载平均速率(udp_download_speed)：{} Mbits/sec\n'.format(udp_download_speed) + \
                              'UDP下载平均发送(udp_download_size)：{} MBytes\n'.format(udp_download_size) + \
                              'UDP下载共发送(udp_download_size_all): {} MBytes\n'.format(udp_download_size_all) + \
                              'UDP下载平均抖动(udp_download_jitter)：{} ms\n'.format(udp_download_jitter) + \
                              'UDP下载数据包(udp_download_packet)：{} 个\n'.format(udp_download_packet) + \
                              'UDP下载丢失数据包(udp_download_packet_lost)：{} 个\n'.format(udp_download_packet_lost) + \
                              'UDP下载丢包率(udp_download_packet_lost_percent)：{} %\n'.format(udp_download_packet_lost_percent) + \
                              '服务端发送平均速率(udp_server_download_speed)：{} Mbits/sec\n'.format(udp_server_download_speed) + \
                              '服务端发送数据量(udp_server_download_size_all)：{} MBytes\n'.format(udp_server_download_size_all) + \
                              '服务端平均抖动(udp_server_download_jitter)：{} ms\n'.format(udp_server_download_jitter) + \
                              '服务端丢包数(udp_server_download_packet_lost)：{} 个\n'.format(udp_server_download_packet_lost) + \
                              '服务端总包数(udp_server_download_packet)：{} 个\n'.format(udp_server_download_packet) + \
                              '服务端平均丢包率(udp_server_download_packet_lost_percent)：{} %\n'.format(udp_server_download_packet_lost_percent)
        result_udp_abnormal = '{}速率异常次数(speed_abnormal_times)：{} 次\n'.format("UDP" if udp else "TCP", speed_abnormal_times)
        ports = port.split(',')
        if len(ports) == 1 and udp and reverse is False:
            result = result_head + result_udp_upload + result_udp_abnormal
        elif len(ports) == 1 and udp and reverse:
            result = result_head + result_udp_download + result_udp_abnormal
        elif len(ports) == 1 and udp is False and reverse is False:
            result = result_head + result_tcp_upload + result_udp_abnormal
        elif len(ports) == 1 and udp is False and reverse:
            result = result_head + result_tcp_download + result_udp_abnormal
        else:
            if udp:
                result = result_head + result_udp_upload + result_udp_download + result_udp_abnormal
            else:
                result = result_head + result_tcp_upload + result_tcp_download + result_udp_abnormal
        print(result)
        with open('统计结果.txt', 'a', encoding='utf-8', buffering=1) as f:
            f.write('-----------压力统计结果start-----------{}-----------压力统计结果end-----------\n'.format(result))
