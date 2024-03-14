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
    def __init__(self, mode, version, info, connect_mode, log_queue, main_queue):
        super().__init__()
        self.version = version
        self.info = info
        self.connect_mode = connect_mode
        self.log_queue = log_queue
        self.main_queue = main_queue
        self.df = DataFrame(columns=['runtimes_start_timestamp'])
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.mode = mode

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
        # 如果是flash_record字段，并且内容正常，并且对应runtimes中qftest_record不是空，再次写入需要判断
        if 'qftest_record' in column_name and content != '{}' and not pd.isna(self.df.loc[runtimes, 'qftest_record']):
            prev_dict = eval(self.df.loc[runtimes, 'qftest_record'])  # 获取dict
            cur_dict = eval(content)  # 获取dict
            for (k0, v0), (k1, v1) in zip(prev_dict.items(), cur_dict.items()):
                if k1 == k0 and int(v1) > int(v0):  # 最新的dict中key等于之前的key，value大于之前的value，更新content
                    content = content
                    break
                else:  # 获取的value小于现在的value，不更新，可能是清零了
                    content = self.df.loc[runtimes, 'qftest_record']
                    break

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
        init_df_column = ['runtimes', 'speed_abnormal_times', 'client_send', 'client_send_bandwidth', 'server_receive',
                          'server_receive_bandwidth', 'server_send', 'server_send_bandwidth', 'client_receive',
                          'client_receive_bandwidth', 'client_send', 'client_send_bandwidth', 'client_send_jitter',
                          'client_send_loss', 'client_send_total', 'client_send_loss_percent', 'server_receive',
                          'server_receive_bandwidth', 'server_receive_jitter', 'server_receive_loss',
                          'server_receive_total', 'server_receive_loss_percent', 'server_send', 'server_send_bandwidth',
                          'server_send_jitter', 'server_send_loss', 'server_send_total', 'server_send_loss_percent',
                          'client_receive', 'client_receive_bandwidth', 'client_receive_jitter', 'client_receive_loss',
                          'client_receive_total', 'client_receive_loss_percent', 'qftest_record']
        for column_name in init_df_column:
            self.df.loc[0, column_name] = np.nan

    def write_result_log(self, runtimes):
        """
        每个runtimes写入result_log的内容
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        # 用作写入result_log时宽度设置
        result_width_standard_tcp_upload = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['client_send', 19],
                                            3: ['client_send_bandwidth', 30],
                                            4: ['server_receive', 22],
                                            5: ['server_receive_bandwidth', 33],
                                            6: ['speed_abnormal_times', 20]}

        result_width_standard_tcp_download = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['server_send', 19],
                                              3: ['server_send_bandwidth', 30],
                                              4: ['client_receive', 22],
                                              5: ['client_receive_bandwidth', 33],
                                              6: ['speed_abnormal_times', 20]}

        result_width_standard_tcp_bidir = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['client_send', 19],
                                           3: ['client_send_bandwidth', 30],
                                           4: ['server_receive', 22],
                                           5: ['server_receive_bandwidth', 33],
                                           6: ['server_send', 19],
                                           7: ['server_send_bandwidth', 30],
                                           8: ['client_receive', 22],
                                           9: ['client_receive_bandwidth', 33],
                                           10: ['speed_abnormal_times', 20]}

        result_width_standard_udp_upload = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['client_send', 19],
                                            3: ['client_send_bandwidth', 30], 4: ['client_send_jitter', 22],
                                            5: ['client_send_loss', 16], 6: ['client_send_total', 17],
                                            7: ['client_send_loss_percent', 27],
                                            8: ['server_receive', 22],
                                            9: ['server_receive_bandwidth', 33],
                                            10: ['server_receive_jitter', 25],
                                            11: ['server_receive_loss', 19], 12: ['server_receive_total', 20],
                                            13: ['server_receive_loss_percent', 30],
                                            14: ['speed_abnormal_times', 20]}

        result_width_standard_udp_download = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['server_send', 19],
                                              3: ['server_send_bandwidth', 30], 4: ['server_send_jitter', 22],
                                              5: ['server_send_loss', 16], 6: ['server_send_total', 17],
                                              7: ['server_send_loss_percent', 27],
                                              8: ['client_receive', 22],
                                              9: ['client_receive_bandwidth', 33],
                                              10: ['client_receive_jitter', 25],
                                              11: ['client_receive_loss', 19], 12: ['client_receive_total', 20],
                                              13: ['client_receive_loss_percent', 30],
                                              14: ['speed_abnormal_times', 20]}

        result_width_standard_udp_bidir = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['client_send', 19],
                                           3: ['client_send_bandwidth', 30], 4: ['client_send_jitter', 22],
                                           5: ['client_send_loss', 16], 6: ['client_send_total', 17],
                                           7: ['client_send_loss_percent', 27],
                                           8: ['server_receive', 22],
                                           9: ['server_receive_bandwidth', 33],
                                           10: ['server_receive_jitter', 25],
                                           11: ['server_receive_loss', 19], 12: ['server_receive_total', 20],
                                           13: ['server_receive_loss_percent', 30],
                                           14: ['server_send', 19],
                                           15: ['server_send_bandwidth', 30], 16: ['server_send_jitter', 22],
                                           17: ['server_send_loss', 16], 18: ['server_send_total', 17],
                                           19: ['server_send_loss_percent', 27],
                                           20: ['client_receive', 22],
                                           21: ['client_receive_bandwidth', 33],
                                           22: ['client_receive_jitter', 25],
                                           23: ['client_receive_loss', 19], 24: ['client_receive_total', 20],
                                           25: ['client_receive_loss_percent', 30],
                                           26: ['speed_abnormal_times', 20]}

        result_mapping = {
            1: result_width_standard_tcp_upload,
            2: result_width_standard_tcp_download,
            3: result_width_standard_tcp_bidir,
            4: result_width_standard_udp_upload,
            5: result_width_standard_udp_download,
            6: result_width_standard_udp_bidir,
        }

        result_width_standard = result_mapping[self.mode]

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
        self.speed_abnormal_times = 0 if pd.isna(self.df.loc[runtimes, 'speed_abnormal_times']) else int(float(self.df.loc[runtimes, 'speed_abnormal_times']))
        result_list = [getattr(self, x) for a, (x, y) in result_width_standard.items()]
        result_list.reverse()  # 反转列表，便于弹出
        result_string = ''
        for index, (para, width) in result_width_standard.items():
            try:
                result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
            except IndexError:
                pass
        self.result_log_handle.write(result_string + '\n')

    def end_script(self, script_start_time, runtimes):
        script_start_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(script_start_time))
        script_end_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))

        result_head = '{}\n[{}]-[{}]\n'.format(self.info, script_start_time_format, script_end_time_format) + \
                      '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes)

        speed_abnormal_times = int(np.sum(self.df['speed_abnormal_times']))
        result_abnormal = '速率异常次数(speed_abnormal_times)：{} 次\n'.format(speed_abnormal_times)
        if self.mode in [1, 2, 3]:
            # tcp上传
            client_send = np.round(np.mean(self.df['client_send'].dropna()), 2)  # 发送平均数据量
            client_send_total = np.round(np.sum(self.df['client_send'].dropna()), 2)  # 总上传数据量
            client_send_bandwidth = np.round(np.mean(self.df['client_send_bandwidth'].dropna()), 2)  # 发送平均带宽
            client_send_bandwidth_min = np.round(np.min(self.df['client_send_bandwidth'].dropna()), 2)  # 最小发送速度
            client_send_bandwidth_max = np.round(np.max(self.df['client_send_bandwidth'].dropna()), 2)  # 最大发送速度
            server_receive_total = np.round(np.sum(self.df['server_receive'].dropna()), 2)  # 接收平均数据量
            server_receive_bandwidth = np.round(np.mean(self.df['server_receive_bandwidth'].dropna()), 2)  # 接收平均带宽

            # tcp下载
            server_send_total = np.round(np.sum(self.df['server_send'].dropna()), 2)
            server_send_bandwidth = np.round(np.mean(self.df['server_send_bandwidth'].dropna()), 2)
            client_receive = np.round(np.mean(self.df['client_receive'].dropna()), 2)
            client_receive_total = np.round(np.sum(self.df['client_receive'].dropna()), 2)
            client_receive_bandwidth = np.round(np.mean(self.df['client_receive_bandwidth'].dropna()), 2)
            client_receive_bandwidth_min = np.round(np.min(self.df['client_receive_bandwidth'].dropna()), 2)  # 最小发送速度
            client_receive_bandwidth_max = np.round(np.max(self.df['client_receive_bandwidth'].dropna()), 2)  # 最大发送速度

            result_tcp_upload = 'TCP发送最小速率(client_send_bandwidth_min)：{} Mbits/sec\n'.format(client_send_bandwidth_min) + \
                                'TCP发送最大速率(client_send_bandwidth_max)：{} Mbits/sec\n'.format(client_send_bandwidth_max) + \
                                'TCP发送平均速率(client_send_bandwidth)：{} Mbits/sec\n'.format(client_send_bandwidth) + \
                                'TCP发送平均发送(client_send)：{} MBytes\n'.format(client_send) + \
                                'TCP发送共发送(client_send_total): {} MBytes\n'.format(client_send_total) + \
                                '服务端接收平均速率(server_receive_bandwidth)：{} Mbits/sec\n'.format(server_receive_bandwidth) + \
                                '服务端接收总数据量(server_receive_total)：{} MBytes\n'.format(server_receive_total)

            result_tcp_download = 'TCP接收最小速率(client_receive_bandwidth_min)：{} Mbits/sec\n'.format(client_receive_bandwidth_min) + \
                                  'TCP接收最大速率(client_receive_bandwidth_max)：{} Mbits/sec\n'.format(client_receive_bandwidth_max) + \
                                  'TCP接收平均速率(client_receive_bandwidth)：{} Mbits/sec\n'.format(client_receive_bandwidth) + \
                                  'TCP平均接收(client_receive)：{} MBytes\n'.format(client_receive) + \
                                  'TCP共接收(client_receive_total): {} MBytes\n'.format(client_receive_total) + \
                                  '服务端发送平均速率(server_send_bandwidth)：{} Mbits/sec\n'.format(server_send_bandwidth) + \
                                  '服务端发送数总据量(server_send)：{} MBytes\n'.format(server_send_total)

            if self.mode == 1:
                result = result_head + result_tcp_upload + result_abnormal
            elif self.mode == 2:
                result = result_head + result_tcp_download + result_abnormal
            else:
                text1 = "-------------------------------\n模块作为发送端，Server作为接收端时：\n"
                text2 = '-------------------------------\n模块作为接收端，Server作为发送端时：\n'
                result = result_head + text1 + result_tcp_upload + text2 + result_tcp_download + result_abnormal
        else:
            # udp上传
            client_send = np.round(np.mean(self.df['client_send'].dropna()), 2)
            client_send_all = np.round(np.sum(self.df['client_send'].dropna()), 2)
            client_send_bandwidth = np.round(np.mean(self.df['client_send_bandwidth'].dropna()), 2)
            client_send_bandwidth_min = np.round(np.min(self.df['client_send_bandwidth'].dropna()), 2)  # 最小发送速度
            client_send_bandwidth_max = np.round(np.max(self.df['client_send_bandwidth'].dropna()), 2)  # 最大发送速度
            client_send_jitter = np.round(np.mean(self.df['client_send_jitter'].dropna()), 2)
            client_send_loss = np.round(np.sum(self.df['client_send_loss'].dropna()), 0)
            client_send_total = np.round(np.sum(self.df['client_send_total'].dropna()), 0)
            client_send_loss_percent = np.round(np.mean(self.df['client_send_loss_percent'].dropna()), 2)
            server_receive = np.round(np.sum(self.df['server_receive'].dropna()), 2)
            server_receive_bandwidth = np.round(np.mean(self.df['server_receive_bandwidth'].dropna()), 2)
            server_receive_jitter = np.round(np.mean(self.df['server_receive_jitter'].dropna()), 2)
            server_receive_loss = np.round(np.sum(self.df['server_receive_loss'].dropna()), 0)
            server_receive_total = np.round(np.sum(self.df['server_receive_total'].dropna()), 0)
            server_receive_loss_percent = np.round(np.mean(self.df['server_receive_loss_percent'].dropna()), 2)

            # udp下载
            server_send = np.round(np.sum(self.df['server_send'].dropna()), 2)
            server_send_bandwidth = np.round(np.mean(self.df['server_send_bandwidth'].dropna()), 2)
            server_send_jitter = np.round(np.mean(self.df['server_send_jitter'].dropna()), 2)
            server_send_loss = np.round(np.sum(self.df['server_send_loss'].dropna()), 0)
            server_send_total = np.round(np.sum(self.df['server_send_total'].dropna()), 0)
            server_send_loss_percent = np.round(np.mean(self.df['server_send_loss_percent'].dropna()), 2)
            client_receive = np.round(np.mean(self.df['client_receive'].dropna()), 2)
            client_receive_all = np.round(np.sum(self.df['client_receive'].dropna()), 2)
            client_receive_bandwidth = np.round(np.mean(self.df['client_receive_bandwidth'].dropna()), 2)
            client_receive_bandwidth_min = np.round(np.min(self.df['client_receive_bandwidth'].dropna()), 2)  # 最小发送速度
            client_receive_bandwidth_max = np.round(np.max(self.df['client_receive_bandwidth'].dropna()), 2)  # 最大发送速度
            client_receive_jitter = np.round(np.mean(self.df['client_receive_jitter'].dropna()), 2)
            client_receive_loss = np.round(np.sum(self.df['client_receive_loss'].dropna()), 0)
            client_receive_total = np.round(np.sum(self.df['client_receive_total'].dropna()), 0)
            client_receive_loss_percent = np.round(np.mean(self.df['client_receive_loss_percent'].dropna()), 2)

            result_udp_upload = 'UDP发送最小速率(client_send_bandwidth_min)：{} Mbits/sec\n'.format(client_send_bandwidth_min) + \
                                'UDP发送最大速率(client_send_bandwidth_max)：{} Mbits/sec\n'.format(client_send_bandwidth_max) + \
                                'UDP发送平均速率(client_send_bandwidth)：{} Mbits/sec\n'.format(client_send_bandwidth) + \
                                'UDP平均发送(client_send)：{} MBytes\n'.format(client_send) + \
                                'UDP共发送(client_send_total): {} MBytes\n'.format(client_send_all) + \
                                'UDP发送平均jitter(client_send_jitter): {} ms\n'.format(client_send_jitter) + \
                                'UDP发送共丢包(client_send_loss): {} 个\n'.format(client_send_loss) + \
                                'UDP发送总包数(client_send_total): {} 个\n'.format(client_send_total) + \
                                'UDP发送丢包率(client_send_loss_percent): {} %\n'.format(client_send_loss_percent) + \
                                '服务端接收平均速率(server_receive_bandwidth)：{} Mbits/sec\n'.format(server_receive_bandwidth) + \
                                '服务端总接收数据量(server_receive)：{} MBytes\n'.format(server_receive) + \
                                '服务端平均jitter(server_receive_jitter)：{} ms\n'.format(server_receive_jitter) + \
                                '服务端共丢包(server_receive_loss)：{} 个\n'.format(server_receive_loss) + \
                                '服务端总包数(server_receive_total)：{} 个\n'.format(server_receive_total) + \
                                '服务端平均丢包率(server_receive_loss_percent)：{} %\n'.format(server_receive_loss_percent)

            result_udp_download = 'UDP接收最小速率(client_receive_bandwidth_min)：{} Mbits/sec\n'.format(client_receive_bandwidth_min) + \
                                  'UDP接收最大速率(client_receive_bandwidth_max)：{} Mbits/sec\n'.format(client_receive_bandwidth_max) + \
                                  'UDP接收平均速率(client_receive_bandwidth)：{} Mbits/sec\n'.format(client_receive_bandwidth) + \
                                  'UDP平均接收(client_receive)：{} MBytes\n'.format(client_receive) + \
                                  'UDP共接收(client_receive_total): {} MBytes\n'.format(client_receive_all) + \
                                  'UDP接收平均jitter(client_receive_jitter): {} ms\n'.format(client_receive_jitter) + \
                                  'UDP接收共丢包(client_receive_loss): {} 个\n'.format(client_receive_loss) + \
                                  'UDP接收总包数(client_receive_total): {} 个\n'.format(client_receive_total) + \
                                  'UDP接收丢包率(client_receive_loss_percent): {} %\n'.format(client_receive_loss_percent) + \
                                  '服务端发送平均速率(server_receive_bandwidth)：{} Mbits/sec\n'.format(server_send_bandwidth) + \
                                  '服务端总发送数据量(server_receive)：{} MBytes\n'.format(server_send) + \
                                  '服务端发送平均jitter(server_receive_jitter)：{} ms\n'.format(server_send_jitter) + \
                                  '服务端共丢包(server_receive_loss)：{} 个\n'.format(server_send_loss) + \
                                  '服务端总包数(server_receive_total)：{} 个\n'.format(server_send_total) + \
                                  '服务端平均丢包率(server_receive_loss_percent)：{} %\n'.format(server_send_loss_percent)

            if self.mode == 4:
                result = result_head + result_udp_upload + result_abnormal
            elif self.mode == 5:
                result = result_head + result_udp_download + result_abnormal
            else:
                text1 = "-------------------------------\n模块作为发送端，Server作为接收端时：\n"
                text2 = '-------------------------------\n模块作为接收端，Server作为发送端时：\n'
                result = result_head + text1 + result_udp_upload + text2 + result_udp_download + result_abnormal

        print(result)
        with open('统计结果.txt', 'a', encoding='utf-8', buffering=1) as f:
            f.write('-----------压力统计结果start-----------{}-----------压力统计结果end-----------\n'.format(result))
