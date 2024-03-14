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


class LogThread(Thread):
    def __init__(self, version, info, log_queue, restart_mode, cpin_flag, main_queue):
        super().__init__()
        self.version = version
        self.info = info
        self.log_queue = log_queue
        self.restart_mode = restart_mode
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
        self.at_log_handle.write("python_file_name: {}\n开关机类型: {}\n".format(file_name, self.info))
        self.at_log_handle.write('测试环境：{}-{}\n{}\n'.format(platform.platform(), platform.machine(), sys.version))

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
                          'rn_timestamp', 'net_register_timestamp', 'cpin_not_ready', 'cfun_fail_times',
                          'mbn_null_times']
        for column_name in init_df_column:
            self.df.loc[0, column_name] = np.nan

    def end_script(self, script_start_time, runtimes):
        """
        脚本结束时log统计。
        :param script_start_time:脚本运行时候的时间戳
        :param runtimes: 当前脚本运行的次数
        :return: None
        """
        check_usb_time_avg = ''
        power_on_time_avg = ''
        power_on_fail_times = ''
        net_describe_string = 'Act类型统计：\n'
        script_start_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(script_start_time))
        script_end_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
        if self.restart_mode != 7 and self.restart_mode != 13:
            usb_time_frame = self.df.loc[(self.df.power_on_timestamp.notnull()) & (self.df.driver_appear_timestamp.notnull()), ['driver_appear_timestamp', 'power_on_timestamp']]  # 获取有driver_appear_timestamp和power_on_timestamp的runtimes
            check_usb_time_avg = np.round(np.mean(usb_time_frame['driver_appear_timestamp']-usb_time_frame['power_on_timestamp']), 2)
            power_on_time_frame = self.df.loc[(self.df.power_on_timestamp.notnull()) & (self.df.rn_timestamp.notnull()), ['rn_timestamp', 'power_on_timestamp']]  # 获取有rn_timestamp和power_on_timestamp的runtimes
            power_on_time_avg = np.round(np.mean(power_on_time_frame['rn_timestamp']-power_on_time_frame['power_on_timestamp']), 2)
            power_on_fail_times = list(self.df['rn_timestamp']).count('')
        cfun_fail_times = int(self.df['cfun_fail_times'].sum())
        cpin_not_ready_times = int(self.df['cpin_not_ready'].sum())
        mbn_null_times = int(self.df['mbn_null_times'].sum())
        if self.restart_mode != 7 and self.restart_mode != 13:
            result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                     '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
                     'USB驱动加载时间(check_usb_time_avg): {}秒\n'.format(check_usb_time_avg) + \
                     '模块开机时间(power_on_time_avg): {}秒\n'.format(power_on_time_avg) + \
                     '模块开机失败次数(power_on_fail_times): {}次\n'.format(power_on_fail_times) + \
                     'CFUN值错误(cfun_fail_times): {}次\n'.format(cfun_fail_times) + \
                     '掉卡次数(cpin_not_ready_times): {}次\n'.format(cpin_not_ready_times) + \
                     'mbn查询空值次数(mbn_null_times): {}次\n'.format(mbn_null_times)

        else:
            result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                     '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
                     'CFUN值错误(cfun_fail_times): {}次\n'.format(cfun_fail_times) + \
                     '掉卡次数(cpin_not_ready_times): {}次\n'.format(cpin_not_ready_times) + \
                     'mbn查询空值次数(mbn_null_times): {}次\n'.format(mbn_null_times)
        print(result)
        with open('统计结果.txt', 'a', encoding='utf-8', buffering=1) as f:
            f.write('-----------压力统计结果start-----------{}-----------压力统计结果end-----------\n'.format(result+net_describe_string))

    def write_result_log(self, runtimes):
        """
        每个runtimes写入result_log的内容
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        # 1. 创建一个result log的标准，{index(按照序号), 列名, 列宽}
        check_usb_time = ''
        power_on_fail_times = ''
        power_on_time = ''
        result_width_standard_1 = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['check_usb_time', 14],
                                   3: ['power_on_fail_times', 19], 4: ['power_on_time(S)', 16],  5: ['cfun_fail_times', 15],
                                   6: ['cpin_not_ready_times', 20], 7: ['mbn_null_times', 14]}
        result_width_standard_2 = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['cfun_fail_times', 15],
                                   3: ['cpin_not_ready_times', 20], 4: ['mbn_null_times', 14]}
        result_width_standard = result_width_standard_1 if self.restart_mode != 7 and self.restart_mode != 13 else result_width_standard_2
        if runtimes == 1:  # 当runtimes为1的时候，拼接所有的统计参数并写入log
            header_string = ''
            for index, (para, width) in result_width_standard.items():
                header_string += format(para, '^{}'.format(width)) + '\t'  # 将变量格式化为指定宽度后加制表符(\t)
            self.result_log_handle.write(header_string + '\n')
        # 2. 统计需要统计的参数
        runtimes_start_timestamp = self.df.loc[runtimes, 'runtimes_start_timestamp']  # 写入当前runtimes的时间戳
        local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(float(runtimes_start_timestamp))))
        if self.restart_mode != 7 and self.restart_mode != 13:
            power_on_timestamp = '' if pd.isna(self.df.loc[runtimes, 'power_on_timestamp']) else self.df.loc[runtimes, 'power_on_timestamp']  # 获取拉高DTR时候的时间戳，如果没有开机则为空('')
            driver_appear_timestamp = '' if pd.isna(self.df.loc[runtimes, 'driver_appear_timestamp']) else self.df.loc[runtimes, 'driver_appear_timestamp']  # 驱动出现的时间戳，如果没有出现则为('')
            rn_timestamp = '' if pd.isna(self.df.loc[runtimes, 'rn_timestamp']) else self.df.loc[runtimes, 'rn_timestamp']  # 接收到\r\n的时间戳，没有\r\n出现开机失败并且时间戳记为空('')
            check_usb_time = 999 if power_on_timestamp == '' or driver_appear_timestamp == '' else round((float(driver_appear_timestamp) - float(power_on_timestamp)), 2)
            power_on_time = 999 if power_on_timestamp == '' or driver_appear_timestamp == '' or rn_timestamp == '' else round((float(rn_timestamp) - float(power_on_timestamp)), 2)
            power_on_fail_times = list(self.df['rn_timestamp']).count('')  # 无\r\n上报('rn_timestamp'为空)则开机失败，计算rn_timestamp列开机失败(为空的次数)
        cfun_fail_times = int(self.df['cfun_fail_times'].sum())
        cpin_not_ready_times = int(self.df['cpin_not_ready'].sum())
        mbn_null_times = int(self.df['mbn_null_times'].sum())
        result_string = ''
        # 将结果放入列表中
        if self.restart_mode != 7 and self.restart_mode != 13:
            result_list = [local_time, runtimes, check_usb_time, power_on_fail_times, power_on_time,
                           cfun_fail_times, cpin_not_ready_times, mbn_null_times]
        else:
            result_list = [local_time, runtimes,
                           cfun_fail_times, cpin_not_ready_times, mbn_null_times]
        result_list.reverse()  # 反转列表，便于弹出
        # 3. 跟据第一步创建的标准进行最后字符串的拼接
        for index, (para, width) in result_width_standard.items():
            try:
                result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
            except IndexError:
                pass
        self.result_log_handle.write(result_string + '\n')
