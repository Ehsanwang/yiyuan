# -*- encoding=utf-8 -*-
from logging.handlers import RotatingFileHandler
from threading import Thread
from pandas import DataFrame
import time
import sys
import os
import re
import numpy as np
import pandas as pd
import logging
import platform
import json


class LogThread(Thread):
    def __init__(self, version, info, log_queue, main_queue):
        super().__init__()
        self.version = version
        self.info = info
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
        self.result_log_handle = open('RESULTLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.network_log_handle = open('NETWORKLog-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.loopback_log_handle = open('loopback_Log-{}.txt'.format(self.version), "a+", encoding='utf-8', buffering=1)
        self.handles = ['self.at_log_handle', 'self.dos_log_handle', 'self.debug_log_handle',
                        'self.result_log_handle', 'self.network_log_handle', 'self.loopback_log_handle']
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
    
    def loopback_log(self, log_queue_data):
        self.loopback_log_handle.write('{}{}'.format(log_queue_data, '' if log_queue_data.endswith('\n') else '\n'))

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
        init_df_column = ['runtimes_start_timestamp', 'runtimes', 'power_on_timestamp', 'driver_appear_timestamp',
                          'rn_timestamp', 'net_fail_times', 'cops_value', 'check_network_time',
                          'net_register_timestamp', 'cpin_not_ready', 'cfun_fail_times', 'qtemp_list',
                          'power_off_start_timestamp', 'power_off_end_timestamp', 'error', 'qftest_record']
        for column_name in init_df_column:
            self.df.loc[0, column_name] = np.nan

    def end_script(self, script_start_time, runtimes):
        """
        脚本结束时log统计。
        :param script_start_time:脚本运行时候的时间戳
        :param runtimes: 当前脚本运行的次数
        :return: None
        """
        pass
        # check_usb_time_avg = ''
        # power_on_time_avg = ''
        # power_on_fail_times = ''
        # net_describe_string = 'AcT类型统计：\n'
        # script_start_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(script_start_time))
        # script_end_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
        # if self.restart_mode != 7 and self.restart_mode != 13:
        #     usb_time_frame = self.df.loc[(self.df.power_on_timestamp.notnull()) & (self.df.driver_appear_timestamp.notnull()) & (self.df.error.isnull()), ['driver_appear_timestamp', 'power_on_timestamp', 'error']]  # 获取有driver_appear_timestamp和power_on_timestamp的runtimes
        #     check_usb_time_avg = np.round(np.mean(usb_time_frame['driver_appear_timestamp'] - usb_time_frame['power_on_timestamp']), 2)
        #     power_on_time_frame = self.df.loc[(self.df.power_on_timestamp.notnull()) & (self.df.rn_timestamp.notnull()) & (self.df.error.isnull()), ['rn_timestamp', 'power_on_timestamp', 'error']]  # 获取有rn_timestamp和power_on_timestamp的runtimes
        #     power_on_time_avg = np.round(np.mean(power_on_time_frame['rn_timestamp'] - power_on_time_frame['power_on_timestamp']), 2)
        #     power_on_fail_times = list(self.df['rn_timestamp']).count('')
        # net_fail_times = int(self.df['net_fail_times'].sum())
        # if self.cpin_flag:  # 锁PIN计算锁PIN找网时间
        #     check_network_time = np.round(np.mean(self.df['check_network_time'].dropna()), 2)
        # else:  # 非锁PIN计算开机找网时间
        #     net_time_frame = self.df.loc[(self.df.power_on_timestamp.notnull()) & (self.df.net_register_timestamp.notnull()), ['power_on_timestamp', 'net_register_timestamp']]  # 获取有power_on_timestamp和net_register_timestamp
        #     check_network_time = np.round(np.mean(net_time_frame['net_register_timestamp'] - net_time_frame['power_on_timestamp']), 2)
        # cfun_fail_times = int(self.df['cfun_fail_times'].sum())
        # cpin_not_ready_times = int(self.df['cpin_not_ready'].sum())
        # power_off_time_frame = self.df.loc[(self.df.power_off_start_timestamp.notnull()) & (self.df.power_off_end_timestamp.notnull()), ['power_off_start_timestamp', 'power_off_end_timestamp']]  # 获取有rn_timestamp和power_on_timestamp的runtimes
        # power_off_time_avg = np.round(np.mean(power_off_time_frame['power_off_end_timestamp'] - power_off_time_frame['power_off_start_timestamp']), 2)
        # if self.restart_mode in [0, 2, 4, 6]:  # 需要统计开机时间关机时间
        #     result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
        #              '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
        #              'USB驱动加载时间(check_usb_time_avg): {}秒\n'.format(check_usb_time_avg) + \
        #              '模块开机时间(power_on_time_avg): {}秒\n'.format(power_on_time_avg) + \
        #              '模块关机时间(power_off_time_avg): {}秒\n'.format(power_off_time_avg) + \
        #              '模块开机失败次数(power_on_fail_times): {}次\n'.format(power_on_fail_times) + \
        #              '模块找网失败次数(net_fail_times)：{}次\n'.format(net_fail_times) + \
        #              '{}找网时间(check_network_time)：{}秒\n'.format('锁PIN' if self.cpin_flag else '开机', check_network_time) + \
        #              'CFUN值错误(cfun_fail_times): {}次\n'.format(cfun_fail_times) + \
        #              '掉卡次数(cpin_not_ready_times): {}次\n'.format(cpin_not_ready_times)
        # elif self.restart_mode in [7, 13]:  # 不需要统计开机时间和关机时间
        #     result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
        #              '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
        #              '模块找网失败次数(net_fail_times)：{}次\n'.format(net_fail_times) + \
        #              '{}找网时间(check_network_time)：{}秒\n'.format('锁PIN' if self.cpin_flag else '开机', check_network_time) + \
        #              'CFUN值错误(cfun_fail_times): {}次\n'.format(cfun_fail_times) + \
        #              '掉卡次数(cpin_not_ready_times): {}次\n'.format(cpin_not_ready_times)
        # else:  # 需要统计开机时间，不需要统计关机时间
        #     result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
        #              '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
        #              'USB驱动加载时间(check_usb_time_avg): {}秒\n'.format(check_usb_time_avg) + \
        #              '模块开机时间(power_on_time_avg): {}秒\n'.format(power_on_time_avg) + \
        #              '模块开机失败次数(power_on_fail_times): {}次\n'.format(power_on_fail_times) + \
        #              '模块找网失败次数(net_fail_times)：{}次\n'.format(net_fail_times) + \
        #              '{}找网时间(check_network_time)：{}秒\n'.format('锁PIN' if self.cpin_flag else '开机', check_network_time) + \
        #              'CFUN值错误(cfun_fail_times): {}次\n'.format(cfun_fail_times) + \
        #              '掉卡次数(cpin_not_ready_times): {}次\n'.format(cpin_not_ready_times)
        # # Act统计
        # net_dict = dict(self.df['cops_value'].value_counts(sort=False))
        # for net_type, net_times in net_dict.items():
        #     net_describe_string += '{}({}): {}次\n'.format(int(net_type), self.net_mapping[int(net_type)], net_times)
        # print(result + net_describe_string)
        # with open('统计结果.txt', 'a', encoding='utf-8', buffering=1) as f:
        #     f.write('-----------压力统计结果start-----------{}-----------压力统计结果end-----------\n'.format(result + net_describe_string))

    def write_result_log(self, runtimes):
        """
        每个runtimes写入result_log的内容
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        pass
        # # 1. 创建一个result log的标准，{index(按照序号), 列名, 列宽}
        # result_width_standard_1 = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['check_usb_time', 14],
        #                            3: ['power_on_fail_times', 19], 4: ['power_on_time(S)', 16], 5: ['cops_value', 10],
        #                            6: ['check_network_time(S)', 21], 7: ['net_fail_times', 14], 8: ['cfun_fail_times', 15],
        #                            9: ['cpin_not_ready_times', 20], 10: ['qtemp_list', 50]}
        # result_width_standard_2 = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['cops_value', 10],
        #                            3: ['check_network_time(3)', 21], 4: ['net_fail_times', 14], 5: ['cfun_fail_times', 15],
        #                            6: ['cpin_not_ready_times', 20], 7: ['qtemp_list', 50]}
        # result_width_standard_3 = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['check_usb_time', 14],
        #                            3: ['power_on_fail_times', 19], 4: ['power_on_time(S)', 16], 5: ['power_off_time(S)', 17], 6: ['cops_value', 10],
        #                            7: ['check_network_time(S)', 21], 8: ['net_fail_times', 14], 9: ['cfun_fail_times', 15],
        #                            10: ['cpin_not_ready_times', 20], 11: ['qtemp_list', 50]}
        # if self.restart_mode in [0, 2, 4, 6]:  # 需要统计开机时间关机时间
        #     result_width_standard = result_width_standard_3
        # elif self.restart_mode in [7, 13]:  # 不需要统计开机时间和关机时间
        #     result_width_standard = result_width_standard_2
        # else:  # 需要统计开机时间，不需要统计关机时间
        #     result_width_standard = result_width_standard_1

        # # 2. 如果runtimes为1，写入表头
        # if runtimes == 1:
        #     header_string = ''
        #     for index, (para, width) in result_width_standard.items():
        #         header_string += format(para, '^{}'.format(width)) + '\t'  # 将变量格式化为指定宽度后加制表符(\t)
        #     self.result_log_handle.write(header_string + '\n')

        # # 3. 统计需要统计的参数
        # power_on_fail_times = ''
        # check_usb_time = '开机失败'
        # power_on_time = '开机失败'
        # runtimes_start_timestamp = self.df.loc[runtimes, 'runtimes_start_timestamp']  # 写入当前runtimes的时间戳
        # local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(float(runtimes_start_timestamp))))
        # qtemp_list = '' if pd.isna(self.df.loc[runtimes, 'qtemp_list']) else self.df.loc[runtimes, 'qtemp_list']
        # cops_value = '' if pd.isna(self.df.loc[runtimes, 'cops_value']) else int(self.df.loc[runtimes, 'cops_value'])
        # net_fail_times = int(self.df['net_fail_times'].sum())
        # cfun_fail_times = int(self.df['cfun_fail_times'].sum())
        # cpin_not_ready_times = int(self.df['cpin_not_ready'].sum())
        # power_off_time = '' if pd.isna(self.df.loc[runtimes, 'power_off_start_timestamp']) or pd.isna(self.df.loc[runtimes, 'power_off_end_timestamp']) else np.round(self.df.loc[runtimes, 'power_off_end_timestamp'] - self.df.loc[runtimes, 'power_off_start_timestamp'], 2)
        # if self.restart_mode != 7 and self.restart_mode != 13:
        #     if pd.isna(self.df.loc[runtimes, 'error']):  # 如果没有出现异常
        #         check_usb_time = round((float(self.df.loc[runtimes, 'driver_appear_timestamp']) - float(self.df.loc[runtimes, 'power_on_timestamp'])), 2)
        #         power_on_time = round((float(self.df.loc[runtimes, 'rn_timestamp']) - float(self.df.loc[runtimes, 'power_on_timestamp'])), 2)
        #         power_on_fail_times = list(self.df['rn_timestamp']).count('')
        # if self.cpin_flag:  # 如果计算锁PIN的找网时间
        #     check_network_time = '找网失败' if not pd.isna(self.df.loc[runtimes, 'check_network_time']) else round(float(self.df.loc[runtimes, 'check_network_time']), 2)
        # else:  # 如果计算不锁PIN的从开机到找网的时间
        #     check_network_time = '找网失败' if not pd.isna(self.df.loc[runtimes, 'error']) else round(self.df.loc[runtimes, 'net_register_timestamp'] - self.df.loc[runtimes, 'power_on_timestamp'], 2)

        # # 4. 将结果放入列表中
        # if self.restart_mode in [0, 2, 4, 6]:  # 需要统计开机时间关机时间
        #     result_list = [local_time, runtimes, check_usb_time, power_on_fail_times, power_on_time, power_off_time, cops_value,
        #                    check_network_time, net_fail_times, cfun_fail_times, cpin_not_ready_times, qtemp_list]
        # elif self.restart_mode in [7, 13]:  # 不需要统计开机时间和关机时间
        #     result_list = [local_time, runtimes, cops_value, check_network_time, net_fail_times,
        #                    cfun_fail_times, cpin_not_ready_times, qtemp_list]
        # else:  # 需要统计开机时间，不需要统计关机时间
        #     result_list = [local_time, runtimes, check_usb_time, power_on_fail_times, power_on_time, cops_value,
        #                    check_network_time, net_fail_times, cfun_fail_times, cpin_not_ready_times, qtemp_list]
        # result_list.reverse()  # 反转列表，便于弹出

        # # 5. 跟据第1步创建的标准进行最后字符串的拼接
        # result_string = ''
        # for index, (para, width) in result_width_standard.items():
        #     try:
        #         result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
        #     except IndexError:
        #         pass
        # self.result_log_handle.write(result_string + '\n')
