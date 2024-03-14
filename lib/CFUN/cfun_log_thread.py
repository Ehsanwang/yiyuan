# -*- encoding=utf-8 -*-
from logging.handlers import RotatingFileHandler
from threading import Thread

import pandas as pd
from pandas import DataFrame
import time
import sys
import os
import re
import numpy as np
import logging
import platform
import json


cefs_erasetimes_list = []
ufs_erasetimes_list = []
class LogThread(Thread):
    def __init__(self, version, info, log_queue, cpin_flag, main_queue):
        super().__init__()
        self.version = version
        self.info = info
        self.log_queue = log_queue
        self.cpin_flag = cpin_flag
        self.main_queue = main_queue
        self.df = DataFrame(columns=['runtimes_start_timestamp'])
        self.net_mapping = {  # AT+COPS?中Act对应关系
            2: 'UTRAN',
            4: 'UTRAN W/HSDPA',
            5: 'UTRAN W/HSUPA',
            6: 'UTRAN W/HSDPA and HSUPA',
            7: 'E-UTRAN',
            10: 'E-UTRAN connected to a 5GCN',
            11: 'NR connected to 5GCN',
            12: 'NG-RAN',
            13: 'E-UTRAN-NR dual connectivity'
        }
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]

        # 初始化log文件夹
        self.init_log_dir(self.info)

        # 初始化log文件
        self.at_log_handle = open('ATLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.dos_log_handle = open('DOSLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.debug_log_handle = open('Debug-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.result_log_handle = open('RESULTLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.network_log_handle = open('NETWORKLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.handles = ['self.at_log_handle', 'self.dos_log_handle', 'self.debug_log_handle',
                        'self.result_log_handle', 'self.network_log_handle']
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
        init_df_column = ['runtimes_start_timestamp', 'runtimes', 'cfun_fail_times', 'qftest_record', 'cefs_erase_times', 'usrdata_erase_times']
        for column_name in init_df_column:
            self.df.loc[0, column_name] = np.nan

    def write_result_log(self, runtimes):
        """
        每个runtimes写入result_log的内容
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        # 用作写入result_log时宽度设置
        result_width_standard_1 = {0: ['local_time', 25], 1: ['runtimes', 10], 2: ['cfun_fail_times', 20], 3: ['cefs_erasetimes', 10], 4: ['usrdata_erasetimes', 10]}

        # 当runtimes为1的时候，拼接所有的统计参数并写入log
        if runtimes == 1:
            header_string = ''
            for index, (para, width) in result_width_standard_1.items():
                header_string += format(para, '^{}'.format(width)) + '\t'  # 将变量格式化为指定宽度后加制表符(\t)
            self.result_log_handle.write(header_string + '\n')

        if runtimes == 1:
            cefs_erasetimes = self.df.loc[runtimes, 'cefs_erase_times'] - self.df.loc[runtimes, 'cefs_erase_times']
            usrdata_erasetimes = self.df.loc[runtimes, 'usrdata_erase_times'] - self.df.loc[runtimes, 'usrdata_erase_times']

        else:
            cefs_erasetimes = self.df.loc[runtimes, 'cefs_erase_times'] - self.df.loc[runtimes - 1, 'cefs_erase_times']
            usrdata_erasetimes = self.df.loc[runtimes, 'usrdata_erase_times'] - self.df.loc[runtimes - 1, 'usrdata_erase_times']

            cefs_erasetimes_list.append(cefs_erasetimes)
            ufs_erasetimes_list.append(usrdata_erasetimes)

        # 参数统计
        runtimes_start_timestamp = self.df.loc[runtimes, 'runtimes_start_timestamp']  # 写入当前runtimes的时间戳
        local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(float(runtimes_start_timestamp))))
        cfun_fail_times = int(self.df['cfun_fail_times'].sum())

        result_list = [local_time, runtimes, cfun_fail_times, cefs_erasetimes, usrdata_erasetimes]

        result_list.reverse()  # 反转列表，便于弹出
        result_string = ''
        for index, (para, width) in result_width_standard_1.items():
            try:
                result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
            except IndexError:
                pass
        self.result_log_handle.write(result_string + '\n')

    def end_script(self, script_start_time, runtimes):
        result = ''
        script_start_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(script_start_time))
        script_end_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))

        cfun_fail_times = int(self.df['cfun_fail_times'].sum())  # CFUN切换失败次数

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
                 'CFUN切换失败次数(cfun_fail_times)：{}次\n'.format(cfun_fail_times) + \
                 'cefs平均递增擦除次数(cefs_erase_averagetimes): {}次\n'.format(cefs_erase_averagetimes) + \
                 'cefs最大递增擦除次数(cefs_erase_maxtimes): {}次\n'.format(cefs_erase_maxtimes) + \
                 'usrdata平均递增擦除次数(usrdata_erase_averagetimes): {}次\n'.format(usrdata_erase_averagetimes) + \
                 'usrdata最大递增擦除次数(usrdata_erase_maxtimes): {}次\n'.format(usrdata_erase_maxtimes)

        print(result)
        with open('统计结果.txt', 'a', encoding='utf-8', buffering=1) as f:
            f.write('-----------压力统计结果start-----------{}-----------压力统计结果end-----------\n'.format(result))
