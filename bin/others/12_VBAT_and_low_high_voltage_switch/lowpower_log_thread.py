# -*- encoding=utf-8 -*-
from logging.handlers import RotatingFileHandler
from threading import Thread
from pandas import DataFrame
import sys
import os
import re
import numpy as np
import logging
import platform
import time
import json


class LowLogThread(Thread):
    def __init__(self, version, info, vbat, log_queue, main_queue):
        super().__init__()
        self.version = version
        self.info = info
        self.vbat = vbat
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
        self.handles = ['self.at_log_handle', 'self.dos_log_handle', 'self.debug_log_handle',
                        'self.result_log_handle', 'self.network_log_handle']
        self.thread_timestamp = time.time()

        # 初始化logger
        handler = RotatingFileHandler('_.log', 'a', 1024 * 1024 * 100, 10, delay=False)
        handler.setFormatter(logging.Formatter('[%(asctime)s.%(msecs)03d] %(levelname)s %(module)s->%(lineno)d->%(funcName)s->%(message)s'))
        handler.setLevel(logging.ERROR)
        logger = logging.getLogger()
        logger.setLevel(logging.ERROR)
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
                          'rn_timestamp', 'net_fail_times', 'sleep_upset_times', 'sleep_curr_avg',
                          'sleep_real_rate', 'wake_curr_avg', 'wake_upset_times', 'wake_real_rate']
        for column_name in init_df_column:
            self.df.loc[0, column_name] = np.nan

    def write_result_log(self, runtimes):
        """
        每个runtimes写入result_log的内容
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        # 用作写入result_log时宽度设置
        check_usb_time = ''
        power_on_time = ''
        power_on_fail_times = ''
        net_fail_times = ''
        if self.vbat:  # 重启模块
            result_width_standard = {0: ['local_time', 25], 1: ['runtimes', 8], 2: ['check_usb_time', 14],
                                     3: ['power_on_time', 13], 4: ['power_on_fail_times', 19], 5: ['net_fail_times', 16],
                                     6: ['sleep_upset_times', 17], 7: ['sleep_curr_value', 16],
                                     8: ['sleep_real_rate', 15], 9: ['wake_upset_times', 16],
                                     10: ['wake_curr_value', 15], 11: ['wake_real_rate', 14]}
        else:
            result_width_standard = {0: ['local_time', 25], 1: ['runtimes', 8],
                                     2: ['sleep_upset_times', 17], 3: ['sleep_curr_value', 16],
                                     4: ['sleep_real_rate', 15], 5: ['wake_upset_times', 16],
                                     6: ['wake_curr_value', 15], 7: ['wake_real_rate', 14]}
        # 当runtimes为1的时候，拼接所有的统计参数并写入log
        if runtimes == 1:
            header_string = ''
            for index, (para, width) in result_width_standard.items():
                header_string += format(para, '^{}'.format(width)) + '\t'  # 将变量格式化为指定宽度后加制表符(\t)
            self.result_log_handle.write(header_string + '\n')
        # timestamp，usb出现时间为driver_appear_timestamp-power_on_timestamp，开机时间为rn_timestamp-power_on_timestamp
        runtimes_start_timestamp = self.df.loc[runtimes, 'runtimes_start_timestamp']
        # 参数统计
        local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(float(runtimes_start_timestamp))))
        if self.vbat:
            # 开关机参数统计
            power_on_timestamp = '' if self.df.loc[runtimes, 'power_on_timestamp'] == '' else self.df.loc[runtimes, 'power_on_timestamp']
            rn_timestamp = '' if self.df.loc[runtimes, 'rn_timestamp'] == '' else self.df.loc[runtimes, 'rn_timestamp']  # 接收到\r\n的时间戳，没有\r\n出现开机失败并且时间戳记为空('')
            driver_appear_timestamp = '' if self.df.loc[runtimes, 'driver_appear_timestamp'] == '' else self.df.loc[runtimes, 'driver_appear_timestamp']  # 驱动出现的时间戳，如果没有出现则为('')
            check_usb_time = 999 if power_on_timestamp is False or driver_appear_timestamp is False else round((float(driver_appear_timestamp) - float(power_on_timestamp)), 2)
            power_on_time = 999 if power_on_timestamp is False or rn_timestamp is False or rn_timestamp is False else round((float(rn_timestamp) - float(power_on_timestamp)), 2)
            power_on_fail_times = list(self.df['rn_timestamp']).count('')  # 无\r\n上报('rn_timestamp'为空)则开机失败，计算rn_timestamp列开机失败(为空的次数)，下面同理
            net_fail_times = int(self.df['net_fail_times'].sum())
        # 慢时钟参数统计
        sleep_upset_times = int(self.df['sleep_upset_times'].sum())
        sleep_curr_value = round(float(self.df.loc[runtimes, 'sleep_curr_avg']), 2)
        sleep_real_rate = round(float(self.df.loc[runtimes, 'sleep_real_rate']), 2)
        wake_upset_times = int(self.df['wake_upset_times'].sum())
        wake_curr_value = round(float(self.df.loc[runtimes, 'wake_curr_avg']), 2)
        wake_real_rate = round(float(self.df.loc[runtimes, 'wake_real_rate']), 2)
        # 结果统计
        result_string = ''
        # 将结果放入列表中
        if self.vbat:
            result_list = [local_time, runtimes, check_usb_time, power_on_time, power_on_fail_times, net_fail_times, sleep_upset_times,
                           sleep_curr_value, sleep_real_rate, wake_upset_times, wake_curr_value, wake_real_rate]
        else:
            result_list = [local_time, runtimes, sleep_upset_times, sleep_curr_value, sleep_real_rate, wake_upset_times,
                           wake_curr_value, wake_real_rate]
        result_list.reverse()  # 反转列表，便于弹出
        # 3. 跟据第一步创建的标准进行最后字符串的拼接
        for index, (para, width) in result_width_standard.items():
            try:
                result_string += format(result_list.pop(), '^{}'.format(width)) + '\t'  # 不要忘记\t
            except IndexError:
                pass
        self.result_log_handle.write(result_string + '\n')

    def end_script(self, script_start_time, runtimes):
        """
        结束脚本并统计结果
        :param script_start_time: 脚本开始时间
        :param runtimes: 当前脚本运行次数
        :return: None
        """
        check_usb_time_avg = ''
        power_on_time_avg = ''
        power_on_fail_times = ''
        script_start_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(script_start_time))
        script_end_time_format = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
        if self.vbat:
            usb_time_frame = self.df.loc[(self.df.power_on_timestamp.notnull()) & (self.df.driver_appear_timestamp.notnull()), ['driver_appear_timestamp', 'power_on_timestamp']]  # 获取有driver_appear_timestamp和power_on_timestamp的runtimes
            check_usb_time_avg = round((usb_time_frame['driver_appear_timestamp'] - usb_time_frame['power_on_timestamp']).sum() / len(usb_time_frame['driver_appear_timestamp'] - usb_time_frame['power_on_timestamp']), 2)  # 计算平均时间
            power_on_time_frame = self.df.loc[(self.df.power_on_timestamp.notnull()) & (self.df.rn_timestamp.notnull()), ['rn_timestamp', 'power_on_timestamp']]  # 获取有rn_timestamp和power_on_timestamp的runtimes
            power_on_time_avg = round((power_on_time_frame['rn_timestamp'] - power_on_time_frame['power_on_timestamp']).sum() / len(power_on_time_frame['rn_timestamp'] - power_on_time_frame['power_on_timestamp']), 2)  # 计算平均时间
            power_on_fail_times = list(self.df['rn_timestamp']).count('')
        net_fail_times = int(self.df['net_fail_times'].sum())
        sleep_upset_times = int(self.df['sleep_upset_times'].sum())
        sleep_curr_value = round(self.df['sleep_curr_avg'].sum() / len(self.df['sleep_curr_avg']), 2)
        sleep_real_rate = round(self.df['sleep_real_rate'].sum() / runtimes, 2) * 100
        wake_upset_times = int(self.df['wake_upset_times'].sum())
        wake_curr_value = round(self.df['wake_curr_avg'].sum() / len(self.df['wake_curr_avg']), 2)
        wake_real_rate = round(self.df['wake_real_rate'].sum() / runtimes, 2) * 100
        if self.vbat:
            result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                     '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
                     'USB驱动加载时间(check_usb_time): {}秒\n'.format(check_usb_time_avg) + \
                     '模块开机时间(power_on_time): {}秒\n'.format(power_on_time_avg) + \
                     '模块开机失败次数(power_on_fail_times): {}次\n'.format(power_on_fail_times) + \
                     '模块找网失败次数(net_fail_times): {}次\n'.format(net_fail_times) + \
                     '睡眠耗流平均值(sleep_curr_value): {} mA\n'.format(sleep_curr_value) + \
                     '睡眠耗流偏高次数(sleep_upset_times): {}次\n'.format(sleep_upset_times) + \
                     '睡眠耗流偏高频率(sleep_real_rate): {} %\n'.format(sleep_real_rate) + \
                     '唤醒耗流平均值(wake_curr_value): {} mA\n'.format(wake_curr_value) + \
                     '唤醒耗流偏高次数(wake_upset_times): {}次\n'.format(wake_upset_times) + \
                     '唤醒耗流偏高频率(wake_real_rate): {} %\n'.format(wake_real_rate)
        else:
            result = '\n[{}]-[{}]\n'.format(script_start_time_format, script_end_time_format) + \
                     '共运行{}H/{}次\n'.format(round((time.time() - script_start_time) / 3600, 2), runtimes) + \
                     '模块找网失败次数(net_fail_times): {}次\n'.format(net_fail_times) + \
                     '睡眠耗流平均值(sleep_curr_value): {} mA\n'.format(sleep_curr_value) + \
                     '睡眠耗流偏高次数(sleep_upset_times): {}次\n'.format(sleep_upset_times) + \
                     '睡眠耗流偏高频率(sleep_real_rate): {} %\n'.format(sleep_real_rate) + \
                     '唤醒耗流平均值(wake_curr_value): {} mA\n'.format(wake_curr_value) + \
                     '唤醒耗流偏高次数(wake_upset_times): {}次\n'.format(wake_upset_times) + \
                     '唤醒耗流偏高频率(wake_real_rate): {} %\n'.format(wake_real_rate)
        print(result)
        with open('统计结果.txt', 'a', encoding='utf-8', buffering=1) as f:
            f.write('-----------压力统计结果start-----------{}-----------压力统计结果end-----------\n'.format(result))
