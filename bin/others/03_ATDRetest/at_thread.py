# -*- encoding=utf-8 -*-
import random
from threading import Thread
import datetime
import serial
import time
import os
import re
import serial.tools.list_ports
import threading
import logging
# TODO:增加URC内容顺序的check
# TODO:增加URC格式的check


class URCError(Exception):
    pass


class ATThread(Thread):
    def __init__(self, at_port, dm_port, at_queue, main_queue, log_queue):
        super().__init__()
        self.at_port = at_port.upper() if os.name == 'nt' else at_port  # win平台转换为大写便于后续判断
        self.dm_port = dm_port.upper() if os.name == 'nt' else dm_port  # win平台转换为大写便于后续判断
        self.at_queue = at_queue
        self.main_queue = main_queue
        self.log_queue = log_queue
        self.restore_times = 0
        self.at_port_opened = type(serial)  # 初始化AT口
        self.at_port_opened_flag = False  # AT口打开时为True，串口读取URC；AT口关闭的时候为False，不再读取URC
        self._methods_list = [x for x, y in self.__class__.__dict__.items()]
        self.logger = logging.getLogger(__name__)

    def run(self):
        while True:
            time.sleep(0.001)  # 减小CPU开销
            (func, *param), evt = ['0', '0'] if self.at_queue.empty() else self.at_queue.get()  # 如果at_queue有内容读，无内容[0,0]
            runtimes = param[-1] if len(param) != 0 else 0
            self.logger.info('{}->{}->{}'.format(func, param, evt)) if func != '0' else ''
            try:
                if func == 'open':  # 每次检测到端口后打开端口，进行各种AT操作前打开需要确保端口是打开状态
                    # 调用方式：'AT', 'open', runtimes
                    open_port_status = self.open()  # 打开端口
                    if open_port_status:
                        self.main_queue.put(True)
                        evt.set()
                    else:
                        self.log_queue.put(['all', '[{}] runtimes:{} 连续10次打开端口失败'.format(datetime.datetime.now(), runtimes)])
                        self.log_queue.put(['df', runtimes, 'error', '[{}] runtimes:{} 连续10次打开端口失败'.format(datetime.datetime.now(), runtimes)])
                        self.log_queue.put(['write_result_log', runtimes])
                        self.main_queue.put(False)
                        evt.set()
                elif func == 'close':  # 重启模块/不再进行AT口操作/新的Runtimes必须关闭口，并在下个Runtimes打开
                    # 调用方式：'AT', 'close', runtimes
                    self.close()  # 关闭端口
                    self.main_queue.put(True)
                    evt.set()
                elif func in self._methods_list:
                    at_status = getattr(self.__class__, '{}'.format(func))(self, *param)
                    if at_status is not False:
                        self.main_queue.put(True)
                    else:
                        self.at_port_opened.close()
                        self.at_port_opened_flag = False
                        self.main_queue.put(False)
                    evt.set()
                elif func.upper().startswith('AT'):  # 主脚本调用单独发AT，分为只返回OK和返回OK继续返回值类型(AT+QPOWD)
                    at_status = self.at(func, param)
                    if at_status:
                        self.main_queue.put(True)
                    else:
                        self.at_port_opened.close()
                        self.at_port_opened_flag = False
                        self.main_queue.put(False)
                    evt.set()
                elif self.at_port_opened_flag:  # 没有检测到任何方法，并且端口是打开的状态，不停的读取URC，此方法要放最后
                    return_value = self.readline(self.at_port_opened)
                    if return_value != '':
                        self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                        self.urc_checker(return_value, '')
            except serial.serialutil.SerialException:
                port_list = ''
                self.at_port_opened.close()
                self.at_port_opened_flag = False
                for _ in range(3):
                    port_list = self.get_port_list()
                    self.log_queue.put(['at_log', '[{}] 端口异常, 当前COM口情况: {}'.format(datetime.datetime.now(), port_list)])
                self.log_queue.put(['all', '[{}] runtimes:{} 端口异常，当前端口情况：{}'.format(datetime.datetime.now(), runtimes, port_list)])
                self.log_queue.put(['df', runtimes, 'error', '[{}] runtimes:{} 端口异常，当前端口情况：{}'.format(datetime.datetime.now(), runtimes, port_list)])
                self.log_queue.put(['write_result_log', runtimes])
                if type(evt) == threading.Event:
                    self.main_queue.put(False)
                    evt.set()
            except URCError:
                self.at_port_opened.close()
                self.at_port_opened_flag = False
                self.log_queue.put(['write_result_log', runtimes])
                if type(evt) == threading.Event:
                    self.main_queue.put(False)
                    evt.set()

    def open(self):
        """
        打开AT口，如果打开失败，重新打开，打开后at_port_opened_flag设置为True，开始读URC
        :return: None
        """
        for _ in range(10):
            self.logger.info(self.at_port_opened)
            try:  # 打开之前判断是否有close属性，有则close，没有pass
                getattr(self.at_port_opened, 'close')
                self.at_port_opened.close()
            except AttributeError:
                pass
            try:  # 端口打开失败->等待3S->再次打开端口->失败报端口异常
                self.at_port_opened = serial.Serial(self.at_port, baudrate=115200, timeout=0)
                self.at_port_opened_flag = True
                return True
            except serial.serialutil.SerialException:
                time.sleep(2)
        self.log_queue.put(['all', '[{}] 连续10次打开AT口失败'.format(datetime.datetime.now())])
        os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")

    def close(self):
        """
        关闭AT口，并将at_port_opened设置为False，停止读取urc
        :return: None
        """
        self.logger.info(self.at_port_opened)
        self.at_port_opened_flag = False
        self.at_port_opened.close()

    def at(self, func, param):
        """
        需要传入参数参考 [at_command, timeout, repeat_times, result, result_timeout, mode, runtime]
        例如：
            发送AT+QPOWD=0:
                ('AT', 'AT+QPOWD=1', 0.3, 1, 'POWERED DOWN', 60, 1, self.runtimes)
                意思是代表发送AT+QPOWD=1命令，等待OK超时为0.3S，仅发送一次，60S内等待POWERED DOWN上报，使用send_at_two_steps_check，当前runtimes
            发送AT+CFUN?:
                ('AT', 'AT+CFUN?', 6, 1, self.runtimes)
                意思是发送AT+CFUN?，等待超时时间6秒，默认发送1次，当前runtimes次数
        参数参考：
            at_command:AT指令,例如AT+CFUN?;
            timeout:文档中AT指令的超时时间,例如0.3;
            repeat_times:如果不是OK或者指定值时发送AT的次数,一般为1,如果到达指定次数没有返回OK，返回False;
            result:send_at_two_steps_check方法需要用到,检测AT+QPOWD=0这种会二次返回AT的指令;
            result_timeout:返回OK后继续检测，直到URC上报的时间;
            mode:空("")或0代表使用send_at函数,1代表使用send_at_two_steps_check函数。
            runtimes:当前的runtimes,例如100
        :param func: 参数解析的func，以AT开头
        :param param: 参数解析的后的param
        :return:True：指定次数内返回OK；False：指定次数内没有返回OK。
        """
        mode = ''
        result = ''
        result_timeout = ''
        at_command = func  # AT指令即为func
        if len(param) == 6:
            timeout, repeat_times, result, result_timeout, mode, runtimes = param
        else:
            timeout, repeat_times, runtimes = param
        for times in range(1, repeat_times + 1):  # +1是为了从1开始，range(1,4)返回123
            if mode == 0 or mode == '':
                at_return_value = self.send_at(at_command, self.at_port_opened, runtimes, timeout)
            else:
                at_return_value = self.send_at_two_steps_check(at_command, self.at_port_opened, runtimes, timeout, result, result_timeout)
            if 'OK' in at_return_value:
                return True
            elif times == repeat_times:
                self.log_queue.put(['df', runtimes, 'error', '[{}] runtimes:{} {}返回值错误'.format(datetime.datetime.now(), runtimes, at_command)])
                return False

    def readline(self, port):
        """
        重写readline方法，首先用in_waiting方法获取IO buffer中是否有值：
        如果有值，读取直到\n；
        如果有值，超过1S，直接返回；
        如果没有值，返回 ''
        :param port: 已经打开的端口
        :return: buf:端口读取到的值；没有值返回 ''
        """
        buf = ''
        try:
            if port.in_waiting > 0:
                start_time = time.time()
                while True:
                    buf += port.read(1).decode('utf-8', 'replace')
                    if buf.endswith('\n'):
                        self.logger.info(repr(buf))
                        return buf
                    elif time.time()-start_time > 1:
                        self.logger.info('异常 {}'.format(repr(buf)))
                        return buf
            else:
                return buf
        except OSError as error:
            self.logger.info('Fatal ERROR: {}'.format(error))
            return buf

    def dial_mode_check(self, dial_mode, runtimes):
        """
        查询AT+QCFG="USBNET"当前的模式。
        :param dial_mode: 拨号方式 NDIS/MBIM
        :param runtimes: 运行次数
        :return: False, 对比不一致； True, 对比一致
        """
        dial_mode = dial_mode.upper()  # 转换为大写，防止主脚本写错
        return_value = self.send_at('AT+QCFG="USBNET"', self.at_port_opened, runtimes)
        usbnet_mode = ''.join(re.findall(r'\"usbnet\",(\d+)', return_value, re.IGNORECASE))
        if dial_mode == 'NDIS' and usbnet_mode != '0':
            self.log_queue.put(['all', '[{}] runtimes:{} NDIS拨号方式，AT+QCFG="USBNET"返回值应该是0，当前为{}，请检查'.format(datetime.datetime.now(), runtimes, usbnet_mode)])
            return False
        elif dial_mode == 'MBIM' and usbnet_mode != '2':
            self.log_queue.put(['all', '[{}] runtimes:{} MBIM拨号方式，AT+QCFG="USBNET"返回值应该是2，当前为{}，请检查'.format(datetime.datetime.now(), runtimes, usbnet_mode)])
            return False
        elif dial_mode == 'ECM' and usbnet_mode != '1':
            self.log_queue.put(['all', '[{}] runtimes:{} ECM拨号方式，AT+QCFG="USBNET"返回值应该是1，当前为{}，请检查'.format(datetime.datetime.now(), runtimes, usbnet_mode)])
            return False
        elif dial_mode == 'WWAN' and usbnet_mode != '0':
            self.log_queue.put(['all', '[{}] runtimes:{} WWAN拨号方式，AT+QCFG="USBNET"返回值应该是0，当前为{}，请检查'.format(datetime.datetime.now(), runtimes, usbnet_mode)])
            return False
        return True

    def check_power_down_urc(self, info, timeout, runtimes):
        """
        用于关机POWERED DOWN URC检测。
        检测指定的URC，例如按压POWERKEY关机时候，模块会上报POWERED DOWN。
        :param info: 需要检测的内容，例如POWERED DOWN
        :param timeout: 检测的超时时间
        :param runtimes: 当前脚本的运行次数
        :return: True：有指定的URC；False：未检测到。
        """
        at_start_timestamp = time.time()
        port_check_interval = time.time()
        while True:
            time.sleep(0.001)  # 减小CPU开销
            # AT端口值获取
            if (time.time()-at_start_timestamp) > timeout:  # 判断是否超时
                self.log_queue.put(['all', '[{}] runtimes:{} {}S内未收到{}上报，模块未掉口，关机失败'.format(datetime.datetime.now(), runtimes, timeout, info)])
                return False
            elif time.time()-port_check_interval > 1:  # 每隔1S检查一次驱动情况
                port_list = self.get_port_list()
                if self.at_port not in port_list and self.dm_port not in port_list:
                    self.log_queue.put(['all', '[{}] runtimes:{} {}S内未收到{}上报，模块已掉口'.format(datetime.datetime.now(), runtimes, round(time.time()-at_start_timestamp), info)])
                    return True
                port_check_interval = time.time()
            else:
                return_value = self.readline(self.at_port_opened)
                if return_value != '':
                    self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                    self.urc_checker(return_value, runtimes)
                    if info in return_value:
                        return True

    def prepare_at(self, version, imei, cpin_flag, runtimes):
        """
        脚本运行前模块需要执行的AT指令。
        :param version: 当前模块的版本
        :param imei: 当前模块的IMEI号
        :param cpin_flag: cpin
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        # TODO:重新checkAT指令的超时时间
        self.send_at('ATE1', self.at_port_opened, runtimes, 2)
        # 版本号
        return_value = self.send_at('ATI+CSUB', self.at_port_opened, runtimes, 0.6)
        revision = ''.join(re.findall(r'Revision: (.*)', return_value))
        sub_edition = ''.join(re.findall('SubEdition: (.*)', return_value))
        version_r = revision+sub_edition
        version_r = re.sub(r'\r|\n', '', version_r)
        if version not in version_r:
            self.log_queue.put(['all', "ATI查询的版本号和当前设置版本号不一致,请确认下当前设置的版本号是否正确"])
            os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")
        # IMEI
        return_value = self.send_at('AT+EGMR=0,7', self.at_port_opened, runtimes, 0.3)
        if imei not in return_value:
            self.log_queue.put(['all', "AT+EGMR=0,7查询的IMEI号和当前设置的IMEI号不一致,请确认下当前设置的IMEI号是否正确"])
            os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")
        # CPIN  如果要锁PIN找网时间设置为True，如果要开机到找网的时间设置为False
        return_value = self.send_at('AT+CPIN?', self.at_port_opened, runtimes, 5)
        if cpin_flag:  # 如果计算锁PIN找网时间
            if 'CPIN: READY' in return_value:
                self.send_at('AT+CLCK="SC",1,"1234"', self.at_port_opened, runtimes, 5)
        else:  # 如果计算开机找网时间
            if 'SIM PIN' in return_value:
                self.send_at('AT+CLCK="SC",0,"1234"', self.at_port_opened, runtimes, 5)
        # 5G特殊指令
        self.send_at('AT+QNWPREFCFG="gw_band"', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG="lte_band"', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG="nsa_nr5g_band"', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG="nr5g_band"', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG="ue_usage_setting"', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG="roam_pref",255', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG="roam_pref"', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG="srv_domain",2', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG="srv_domain"', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG= "mode_pref",AUTO', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QNWPREFCFG= "mode_pref"', self.at_port_opened, runtimes, 0.3)
        # 其他
        self.send_at('AT+CREG=2;+CGREG=2;+CEREG=2;&W', self.at_port_opened, runtimes, 0.9)
        self.send_at('AT+QUIMSLOT=?', self.at_port_opened, runtimes, 0.3)
        self.send_at('AT+QPRTPARA=?', self.at_port_opened, runtimes, 10)
        self.send_at('AT+QPRTPARA=1', self.at_port_opened, runtimes, 10)
        self.send_at('AT&W', self.at_port_opened, runtimes, 0.3)

    def qprtpara_restore_times(self, runtimes):
        """
        统计开关机压测过程中发生还原次数
        :param runtimes:
        :return:
        """
        return_qprtpara = self.send_at('AT+QPRTPARA=4', self.at_port_opened, runtimes, 10)
        restore_times_re = ''.join(re.findall(r'\+QPRTPARA:\s\d*,(\d*)', return_qprtpara))
        if restore_times_re and (int(restore_times_re) - self.restore_times) != 0:
            self.restore_times = int(restore_times_re)
            self.log_queue.put(['all', "[{}] runtimes:{} AT+QPRTPARA=4查询发现还原动作！".format(datetime.datetime.now(), runtimes-1)])
            self.log_queue.put(['df', runtimes, 'restore_times', 1])
        else:
            self.log_queue.put(['df', runtimes, 'restore_times', 0])

    def check_urc(self, runtimes):
        """
        用于开机检测端口是否有任何内容上报，如果读取到任何内容，则停止。
        :param runtimes: 当前脚本的运行次数
        :return: True：有URC；False：未检测到
        """
        port_check_interval = time.time()
        check_urc_start_timestamp = time.time()
        while True:
            time.sleep(0.001)  # 减小CPU开销
            check_urc_total_time = time.time()-check_urc_start_timestamp
            if check_urc_total_time > 60:  # 暂定60S没有URC上报则异常
                return_value = self.send_at('AT', self.at_port_opened, runtimes)
                self.urc_checker(return_value, runtimes)
                if 'OK' in return_value:
                    self.log_queue.put(['all', "[{}] runtimes:{} 检测到驱动后60S内无开机URC上报".format(datetime.datetime.now(), runtimes)])
                    self.log_queue.put(['df', runtimes, 'rn_timestamp', time.time()]) if runtimes != 0 else 1
                    return True
                else:
                    self.log_queue.put(['all', "[{}] runtimes:{} 检测到驱动后60S内无开机URC上报且发送AT无返回值".format(datetime.datetime.now(), runtimes)])
                    self.log_queue.put(['df', runtimes, 'error', '[{}] runtimes:{} 无URC上报'.format(datetime.datetime.now(), runtimes)])
                    return False
            elif time.time()-port_check_interval > 3:  # 每隔3S检查一次驱动情况
                port_check_interval = time.time()
                port_check_status = self.check_port(runtimes)
                if port_check_status is False:
                    check_urc_start_timestamp = time.time()
            else:  # 检查URC
                at_port_data = self.readline(self.at_port_opened)
                if at_port_data != '':
                    self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(at_port_data).replace("'", ''))])
                    self.log_queue.put(['df', runtimes, 'rn_timestamp', time.time()]) if runtimes != 0 else 1
                    self.urc_checker(at_port_data, runtimes)
                    return True

    def check_module_info(self, imei, runtimes):
        """
        查询和对比模块IMEI、CFUN、CPIN号
        :param imei: 模块的IMEI号
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        # TODO:此处timeout需要修改
        # IMEI
        imei_value = self.send_at('AT+EGMR=0,7', self.at_port_opened, runtimes, timeout=3)
        imei_re = ''.join(re.findall(r'EGMR: "(\d{15})"', imei_value))
        if imei_re != imei and 'OK' in imei_value:
            self.log_queue.put(['all', '[{}] runtimes:{} 模块IMEI号发生改变'.format(datetime.datetime.now(), runtimes)])
            os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")  # 模块IMEI号发生改变,暂停脚本
        # CFUN
        cfun_value = self.send_at('AT+CFUN?', self.at_port_opened, runtimes, timeout=3)
        return_value_re = ''.join(re.findall(r'CFUN:\s(\d+)', cfun_value))
        if '1' not in return_value_re and 'OK' in cfun_value:
            self.log_queue.put(['df', runtimes, 'cfun_fail_times', 1])
            self.log_queue.put(['all', "[{}] runtimes:{} CFUN值错误，当前CFUN={}".format(datetime.datetime.now(), runtimes, return_value_re)])
            return False
        # CPIN
        cpin_value = self.send_at('AT+CPIN?', self.at_port_opened, runtimes, timeout=3)
        cpin_value_re = ''.join(re.findall(r"\+(.*ERROR.*)", cpin_value))
        if cpin_value_re != '':
            self.log_queue.put(['all', "[{}] runtimes:{} CPIN值异常 {}".format(datetime.datetime.now(), runtimes, cpin_value_re)])
            return False
        return True

    def check_network(self, cpin_flag, runtimes):
        """
        使用AT+COPS?检查当前网络，如果Act有值，则认为注上网。
        :param cpin_flag: False：找网时间从开机到找网；True：找网时间从解PIN到注网。
        :param runtimes: 当前的脚本的运行次数
        :return: None
        """
        creg_value = ''
        cgreg_value = ''
        cereg_value = ''
        net_timeout = 360
        # 找网成功标志
        cops_flag = False
        # others
        network_result = {}  # 每次找网的log，用于写入network_log
        network_result_head = True  # 通过runtimes=1和此参数为True的时候给第一行写上log

        if cpin_flag:
            self.send_at('AT+CPIN=1234', self.at_port_opened, runtimes, 0.3)
        # 如果需要计算锁PIN找网时间则需要解PIN
        check_network_start_timestamp = time.time()  # 所有找网操作之前的时间戳，用于计算找网时间
        self.log_queue.put(['network_log', '{}runtimes:{}{}'.format('=' * 30, runtimes, '=' * 90)]) if runtimes != 1 else ''  # 每次写入network log

        while True:
            # 获取AT+CSQ的值
            csq_result = self.send_at('AT+CSQ', self.at_port_opened, runtimes)
            csq_value = "".join(re.findall(r'\+CSQ: (\d+),\d+', csq_result))

            # 进行AT+COPS?找网
            cops_result = self.send_at('AT+COPS?', self.at_port_opened, runtimes)
            cops_value = "".join(re.findall(r'\+COPS: .*,.*,.*,(\d+)', cops_result))
            if cops_value != '':
                self.log_queue.put(['df', runtimes, 'cops_value', cops_value])  # net_fail_times
                self.log_queue.put(['df', runtimes, 'net_register_timestamp', time.time()])  # net_register_timestamp
                cops_flag = True

            # 找网当前时间判断，超时写超时，不超时等0.1S后再找
            check_network_time = round(time.time() - check_network_start_timestamp, 2)
            if check_network_time >= net_timeout:
                self.log_queue.put(['all', '[{}] runtimes:{} 找网超时'.format(datetime.datetime.now(), runtimes)])
            else:
                time.sleep(0.1)  # 每次找网的时间间隔，时间太短log会很多

            # NETWORK LOG写入：每次while循环将各个结果写入network_log
            if cops_flag or check_network_time >= net_timeout:  # 如果找网失败或者cops找到网了，需要查一下creg，cereg，cgreg
                cereg_result = self.send_at('AT+CEREG?', self.at_port_opened, runtimes)
                cereg_value = ''.join(re.findall(r'\+CEREG:\s\S+', cereg_result))
                creg_result = self.send_at('AT+CREG?', self.at_port_opened, runtimes)
                creg_value = ''.join(re.findall(r'\+CREG:\s\S+', creg_result))
                cgreg_result = self.send_at('AT+CGREG?', self.at_port_opened, runtimes)
                cgreg_value = ''.join(re.findall(r'\+CGREG:\s\S+', cgreg_result))
            network_result[format("LocalTime", "^28")] = format('[{}]'.format(datetime.datetime.now()), "^28")
            network_result[format("runtimes", "^8")] = format(runtimes, "^8")
            network_result[format("csq_value", "^9")] = format(csq_value, "^9")
            network_result[format("cops_value", "^10")] = format(cops_value, "^10")
            network_result[format("check_network_time", "^18")] = format(check_network_time, "^18")
            network_result[format("creg_value", "^35")] = format(creg_value, "^35")
            network_result[format("cgreg_value", "^35")] = format(cgreg_value, "^35")
            network_result[format("cereg_value", "^35")] = format(cereg_value, "^35")
            if network_result_head and runtimes == 1:  # 只有第一次会写入network_log表头
                network_result_head = False
                self.log_queue.put(['network_log', '\t'.join(network_result.keys())])
                self.log_queue.put(['network_log', '{}runtimes:{}{}'.format('=' * 30, runtimes, '=' * 90)])
            self.log_queue.put(['network_log', '\t'.join(network_result.values())])  # 每次写入network log

            # 只有成功或者失败的时候才会退出
            if cops_flag or check_network_time >= net_timeout:  # 如果找到网或者找网总时间大于360S
                self.log_queue.put(['df', runtimes, 'check_network_time', check_network_time]) if cops_flag else ''  # check_network_time
                self.log_queue.put(['df', runtimes, 'net_fail_times', 0 if cops_flag else 1])  # net_fail_times
                self.send_at('AT+COPS?', self.at_port_opened, runtimes, timeout=3)
                self.send_at('AT+QENG="servingcell"', self.at_port_opened, runtimes, timeout=3)
                self.send_at('AT+QENDC', self.at_port_opened, runtimes, timeout=0.3)
                break

    def send_at(self, at_command, at_port_open, runtimes, timeout=0.3):
        """
        发送AT指令。（用于返回OK的AT指令）
        :param at_command: AT指令内容
        :param at_port_open: 打开的AT口
        :param runtimes: 当前脚本的运行次数
        :param timeout: AT指令的超时时间，参考AT文档
        :return: AT指令返回值
        """
        # TODO:缺少AT不通重发AT机制
        for _ in range(1, 11):  # 连续10次发送AT返回空，并且每次检测到口还在，则判定为AT不通
            at_start_timestamp = time.time()
            at_port_open.write('{}\r\n'.format(at_command).encode('utf-8'))
            self.log_queue.put(['at_log', '[{} Send] {}'.format(datetime.datetime.now(), '{}\\r\\n'.format(at_command))])
            self.logger.info('Send: {}'.format(at_command))
            return_value_cache = ''
            while True:
                # AT端口值获取
                time.sleep(0.001)  # 减小CPU开销
                return_value = self.readline(at_port_open)
                if return_value != '':
                    self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                    self.urc_checker(return_value, runtimes)
                    return_value_cache += '[{}] {}'.format(datetime.datetime.now(), return_value)
                    if 'OK' in return_value and at_command in return_value_cache:  # 避免发AT无返回值后，再次发AT获取到返回值的情况
                        self.at_format_check(at_command, return_value_cache)
                        return return_value_cache
                    if re.findall(r'ERROR\s+', return_value) and at_command in return_value_cache:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}指令返回ERROR'.format(datetime.datetime.now(), runtimes, at_command)]) if 'COPS' not in at_command else ''  # *屏蔽锁pin AT+COPS错误
                        return return_value_cache
                # 超时等判断
                current_total_time = time.time() - at_start_timestamp
                if current_total_time > timeout:
                    if return_value_cache and at_command in return_value_cache:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}命令执行超时'.format(datetime.datetime.now(), runtimes, at_command)])
                        return return_value_cache
                    elif return_value_cache and at_command not in return_value_cache and 'OK' in return_value_cache:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}命令执行返回格式错误，未返回AT指令本身'.format(datetime.datetime.now(), runtimes, at_command)])
                        return return_value_cache
                    else:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}命令执行{}S内无任何回显'.format(datetime.datetime.now(), runtimes, at_command, timeout)])
                        self.check_port(runtimes)
                        time.sleep(0.5)
                        break
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 连续10次执行{}命令无任何回显，AT不通'.format(datetime.datetime.now(), runtimes, at_command, timeout)])
            os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")

    def send_at_two_steps_check(self, at_command, at_port_open, runtimes, timeout, result, result_timeout):
        """
        发送AT指令。（用于返回OK后还会继续返回信息的AT指令，例如AT+QPOWD=0，在返回OK后，会再次有POWERED DOWN上报）
        :param at_command: AT指令
        :param at_port_open: 打开的AT口
        :param runtimes: 脚本的运行次数
        :param timeout: AT指令的超时时间，参考AT文档
        :param result: AT指令返回OK后，再次返回的内容
        :param result_timeout: 返回AT后的urc的上报的超时时间
        :return: AT指令返回值
        """
        for _ in range(1, 11):  # 连续10次发送AT返回空，并且每次检测到口还在，则判定为AT不通
            at_start_timestamp = time.time()
            at_port_open.write('{}\r\n'.format(at_command).encode('utf-8'))
            self.log_queue.put(['at_log', '[{} Send] {}'.format(datetime.datetime.now(), '{}\\r\\n'.format(at_command))])
            self.logger.info('Send: {}'.format(at_command))
            return_value_cache = ''
            at_returned_ok_flag = False
            at_returned_ok_timestamp = time.time()
            urc_check_interval = time.time()
            while True:
                # AT端口值获取
                time.sleep(0.001)  # 减小CPU开销
                return_value = self.readline(at_port_open)
                if return_value != '':
                    return_value_cache += '[{} Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))
                    self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                    self.urc_checker(return_value, runtimes)
                    if 'OK' in return_value and at_command in return_value_cache:
                        at_returned_ok_timestamp = time.time()
                        urc_check_interval = time.time()
                        at_returned_ok_flag = True
                    if re.findall(r'ERROR\s+', return_value) and at_command in return_value_cache:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}指令返回ERROR'.format(datetime.datetime.now(), runtimes, at_command)])
                        return return_value_cache
                if at_returned_ok_flag:  # 如果返回OK了
                    if result in return_value_cache:
                        return return_value_cache
                    elif time.time()-at_returned_ok_timestamp > result_timeout:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}S内未收到{}上报，模块未掉口，关机失败'.format(datetime.datetime.now(), runtimes, result_timeout, result)])
                        os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")
                    elif time.time()-urc_check_interval > 1:  # 每隔1S检查一次驱动情况
                        urc_check_interval = time.time()
                        port_list = self.get_port_list()
                        if self.at_port not in port_list and self.dm_port not in port_list:
                            self.log_queue.put(['all', '[{}] runtimes:{} {}S内未收到{}上报，模块已掉口'.format(datetime.datetime.now(), runtimes, round(time.time() - at_start_timestamp), result)])
                            return return_value_cache
                elif (time.time()-at_start_timestamp) > timeout:  # 如果超时
                    if return_value_cache and at_command in return_value_cache:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}命令执行超时'.format(datetime.datetime.now(), runtimes, at_command)])
                        return return_value_cache
                    elif return_value_cache and at_command not in return_value_cache and 'OK' in return_value_cache:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}命令执行返回格式错误，未返回AT指令本身'.format(datetime.datetime.now(), runtimes, at_command)])
                        return return_value_cache
                    else:
                        self.log_queue.put(['all', '[{}] runtimes:{} {}命令执行{}S内无任何回显'.format(datetime.datetime.now(), runtimes, at_command, timeout)])
                        self.check_port(runtimes)
                        time.sleep(0.5)
                        break
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 连续10次执行{}命令无任何回显，AT不通'.format(datetime.datetime.now(), runtimes, at_command, timeout)])
            os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")

    @staticmethod
    def at_format_check(at_command, return_value):
        """
        用于AT指令格式的检查。
        :param at_command: AT指令
        :param return_value: AT指令的返回值
        :return: None
        """
        # 可能存在部分指令不符合以下格式，通过at_command区分
        # TODO:check
        return_value = ''.join(re.findall(r"\[.*?]\s'AT[\s\S]*", return_value))  # 此处替换为了防止发送AT前有URC上报
        at_check_cache = return_value.split('\r\n')
        if 'OK' in return_value:
            for item in at_check_cache:
                num_r, num_n = len(re.findall(r'\r', item)), len(re.findall(r'\n', item))
                if at_command.upper() in item and (num_r != 1 or num_n != 0):  # AT command在返回值，并且\r为1，\n为0
                    print('[{}] {}指令格式错误'.format(datetime.datetime.now(), at_command))
                elif at_command.upper() not in item and (num_r != 0 or num_n != 0):  # AT command不在返回值，并且\r为0，\n为0
                    print('[{}] {}指令格式错误'.format(datetime.datetime.now(), at_command))

    def urc_checker(self, content, runtimes):
        """
        URC持续上报和AT指令发送过程中异常URC检测
        :param content: AT和URC返回内容
        :return: None
        """
        cpin_not_ready = re.findall(r'CPIN: NOT READY', content)
        cpin_not_inserted = re.findall(r'CPIN: NOT INSERTED', content)
        if cpin_not_ready:
            self.log_queue.put(['df', runtimes, 'cpin_not_ready', 1])  # net_fail_times
            self.log_queue.put(['all', '[{}] runtimes:{} CPIN: NOT READY'.format(datetime.datetime.now(), runtimes)])
            self.log_queue.put(['df', runtimes, 'error', '[{}] runtimes:{} CPIN: NOT READY'.format(datetime.datetime.now(), runtimes)])
            raise URCError
        elif cpin_not_inserted:
            self.log_queue.put(['df', runtimes, 'cpin_not_inserted', 1])  # net_fail_times
            self.log_queue.put(['all', '[{}] runtimes:{} CPIN: NOT INSERTED'.format(datetime.datetime.now(), runtimes)])
            self.log_queue.put(['df', runtimes, 'error', '[{}] runtimes:{} CPIN: NOT INSERTED'.format(datetime.datetime.now(), runtimes)])
            raise URCError

    def check_file_size(self, file_size, runtimes):
        """
        检查所有UFS分区文件大小。
        :param file_size: 文件大小，用于与AT指令查询值对比
        :param runtimes: 当前脚本的运行的次数
        :return:
        """
        time.sleep(10)  # 刚推送完可能查不到，所以等待10s
        return_value = self.send_at('AT+QFLST', self.at_port_opened, runtimes, 3)
        return_value = ''.join(re.findall(r'UFS:.*?,(\d+)', return_value))
        if str(file_size) in return_value:
            self.log_queue.put(['at_log', '[{}] 版本包大小检查一致'.format(datetime.datetime.now())])
            return True
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 版本包大小检查不一致'.format(datetime.datetime.now(), runtimes)])
            return False

    def dfota_version_check(self, version, mode, runtimes):
        """
        查询和对比模块版本号
        :param version: 当前模块的版本号
        :param runtimes: 当前脚本的运行次数
        :return: None
        """
        return_value = self.send_at('ATI+CSUB', self.at_port_opened, runtimes, 20)
        revision = ''.join(re.findall(r'Revision: (.*)', return_value))
        sub_edition = ''.join(re.findall('SubEdition: (.*)', return_value))
        version_r = revision+sub_edition
        version_r = re.sub(r'\r|\n', '', version_r)
        if version != version_r:
            self.log_queue.put(['df', runtimes, 'fota_a_b_version_fail_times' if mode == 'forward' else 'fota_b_a_version_fail_times', 1])
            self.log_queue.put(['all', '[{}] runtimes:{} 模块版本号检查失败'.format(datetime.datetime.now(), runtimes)])

    def check_dfota_status(self, package_error_list, upgrade_error_list, mode, vbat, runtimes):
        """
        用于DFOTA上报的URC检测
        :param package_error_list: 文档定义的升级过程中出现升级包错误
        :param upgrade_error_list: 文档定义的升级过程中的非升级包错误
        :param runtimes: 当前脚本的运行次数
        :param vbat: 是否进行升级过程中断电
        :return: True：有指定的URC；False：未检测到。
        """
        dfota_start_timestamp = time.time()
        driver_check_interval = time.time()
        dfota_timeout = 1000
        vbat_point = random.randint(15, 85)
        vbat_point_list = [',' + str(i) for i in range(vbat_point - 15, vbat_point + 15)]
        self.log_queue.put(['at_log', '[{}] 即将在升级到{}%附近时断电'.format(datetime.datetime.now(), vbat_point)]) if vbat else ''
        while True:
            # AT端口值获取
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.at_port_opened)
            if return_value != '':
                self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                self.urc_checker(return_value, runtimes)
                upgrade_error = [i for i in upgrade_error_list if i in return_value]  # 循环获取log中有无upgrade_error_list中的问题
                package_error = [i for i in package_error_list if i in return_value]  # 循环获取log中有无package_error_list中的问题
                if package_error:
                    self.log_queue.put(['df', runtimes, 'fota_a_b_fail_times' if mode == 'forward' else 'fota_b_a_fail_times', 1])
                    self.log_queue.put(['all', '[{}] runtimes:{} 升级过程升级包错误，错误代码{}'.format(datetime.datetime.now(), runtimes, package_error)])
                    return False
                elif upgrade_error:
                    self.log_queue.put(['df', runtimes, 'fota_a_b_fail_times' if mode == 'forward' else 'fota_b_a_fail_times', 1])
                    self.log_queue.put(['all', '[{}] runtimes:{} 升级过程中异常，错误代码{}'.format(datetime.datetime.now(), runtimes, upgrade_error)])
                    return False
                elif '"FOTA","END",0' in return_value:
                    self.log_queue.put(['df', runtimes, 'fota_a_b_end_timestamp' if mode == 'forward' else 'fota_b_a_end_timestamp', time.time()])
                    self.log_queue.put(['at_log', '[{}] DFOTA升级成功'.format(datetime.datetime.now())])  # 写入log
                    return True
                elif vbat:
                    current_status = ''.join(re.findall(r'(,\d+)\s*$', return_value))
                    if current_status in vbat_point_list:
                        self.log_queue.put(['df', runtimes, 'fota_a_b_start_timestamp' if mode == 'forward' else 'fota_b_a_start_timestamp', time.time()])
                        self.log_queue.put(['at_log', '[{}] 在升级到{}%时断电'.format(datetime.datetime.now(), current_status[1:])])  # 写入log
                        return True
            elif (time.time()-dfota_start_timestamp) > dfota_timeout:
                return_value = self.send_at('AT', self.at_port_opened, runtimes)
                if 'AT' in return_value and 'OK' in return_value:
                    self.log_queue.put(['all', '[{}] runtimes:{} 升级指令发送成功但重启后未升级且可以发AT'.format(datetime.datetime.now(), runtimes)])
                    os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")
                self.log_queue.put(['df', runtimes, 'fota_a_b_fail_times' if mode == 'forward' else 'fota_b_a_fail_times', 1])
                self.log_queue.put(['all', '[{}] runtimes:{} {}S内DFOTA未升级成功'.format(datetime.datetime.now(), runtimes, dfota_timeout)])
                return False
            elif time.time()-driver_check_interval > 1:
                driver_check_interval = time.time()
                self.check_port(runtimes)

    def fota_online_urc_check(self, online_error_list, runtimes):
        """
        DFOTA在线升级指令升级返回OK后，再次返回例如"HTTPEND",0
        此函数就是为了检测版本包下载完成的标志
        :param online_error_list: 下载包过程中可能出现的错误 目前： [601， 701]
        :param runtimes: 脚本运行次数
        :return: True:下载成功；False：下载失败
        """
        download_start_timestamp = time.time()
        download_timeout = 300
        while True:
            time.sleep(0.001)  # 减小CPU开销
            return_value = self.readline(self.at_port_opened)
            if return_value != '':
                self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(return_value).replace("'", ''))])
                self.urc_checker(return_value, runtimes)
                download_error_list = [i for i in online_error_list if i in return_value]
                if download_error_list:
                    self.log_queue.put(['all', '[{}] runtimes:{} 下载升级包错误，错误代码{}'.format(datetime.datetime.now(), runtimes, download_error_list)])
                    return False
                elif 'END",0' in return_value:
                    self.log_queue.put(['at_log', '[{}] 升级包下载成功'.format(datetime.datetime.now())])  # 写入log
                    return True
            elif time.time()-download_start_timestamp > download_timeout:
                self.log_queue.put(['all', '[{}] runtimes:{} {}S内未检查到DFOTA升级包下载完成的URC'.format(datetime.datetime.now(), runtimes, download_timeout)])
                return False

    def data_interface(self, mode, debug, runtimes):
        """
        data_interface指令相关操作
        :param mode: 0：设置0,0；1：设置1,1；2，检查0，0；3，检查1，1
        :param debug: 设置脚本遇到异常是停止还是继续运行False：继续运行；True：停止脚本
        :param runtimes: 当前runtimes
        :return:
        """
        time.sleep(5)  # 上报URC后等待5S才会发AT
        if mode == 0 or mode == 1:
            command_string = '0,0' if mode == 0 else '1,1'
            self.send_at('at+qcfg="data_interface",{}'.format(command_string), self.at_port_opened, runtimes)
            for i in range(10):
                time.sleep(1)
                data_interface = self.send_at('at+qcfg="data_interface"', self.at_port_opened, runtimes)
                if ',{}'.format(command_string) in data_interface:
                    return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} atfwd异常，at+qcfg="data_interface"设置为{}后，查询仅返回OK'.format(datetime.datetime.now(), runtimes, command_string)])
                self.log_queue.put(['df', runtimes, 'data_interface_value_error_times', 1])
                if debug:
                    os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")
        elif mode == 2 or mode == 3:
            command_string = '0,0' if mode == 2 else '1,1'
            for i in range(10):
                time.sleep(1)
                data_interface = self.send_at('at+qcfg="data_interface"', self.at_port_opened, runtimes)
                if ',{}'.format(command_string) in data_interface:
                    return True
            else:
                self.log_queue.put(['all', '[{}] runtimes:{} atfwd异常，at+qcfg="data_interface"查询预期{}失败，仅返回OK'.format(datetime.datetime.now(), runtimes, command_string)])
                self.log_queue.put(['df', runtimes, 'data_interface_value_error_times', 1])
                if debug:
                    os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")

    def check_port(self, runtimes):
        """
        发送AT不通等情况需要检测当前的端口情况，可能出现DUMP和模块异常关机两种情况。
        1. 模块DUMP，现象：仅有DM口，AT口不存在
        电脑设置DUMP重启->模块DUMP->检测模块重启->检测到AT口出现->检测URC->检测到URC后等待10S(最好等待)->脚本继续进行
        电脑没有设置DUMP重启->模块DUMP->检测模块重启->卡死在等待重启界面->现场保留状态
        2. 模块异常关机，现象：发送指令或者检测过程中DM口和AT口都消失了
        模块重启->检测AT口出现->检测URC->检测到URC后等待10S(最好等待)
        :param runtimes:当前脚本的运行次数。
        :return:None
        """
        port_list = self.get_port_list()
        if (self.at_port not in port_list and self.dm_port in port_list) or (self.at_port not in port_list and self.dm_port not in port_list):
            time.sleep(1)  # 如果出现异常情况，等待1S重新获取端口情况，避免没有同时消失造成的异常关机和DUMP的误判
            port_list = self.get_port_list()
            if self.at_port not in port_list and self.dm_port in port_list:
                self.log_queue.put(['all', '[{}] runtimes:{} 模块DUMP'.format(datetime.datetime.now(), runtimes)])
                self.check_at_dm_port(runtimes)
                self.check_urc(runtimes)
                time.sleep(3)
                return False
            elif self.at_port not in port_list and self.dm_port not in port_list:
                self.log_queue.put(['all', '[{}] runtimes:{} 模块异常关机'.format(datetime.datetime.now(), runtimes)])
                self.check_at_dm_port(runtimes)
                self.check_urc(runtimes)
                time.sleep(3)
                return False

    def check_at_dm_port(self, runtimes):
        """
        检测当前电脑的端口列表，仅当AT口和DM口都出现才会break，否则一直检测。
        :return: None
        """
        self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), '开始检测USB驱动是否重新加载')])
        start_timestamp = time.time()
        start_timestamp_check = time.time()
        while True:
            time.sleep(0.5)  # 每隔0.5S检查一次
            # 检测at口和dm口是否在端口列表
            port_list = self.get_port_list()
            if self.at_port in port_list and self.dm_port in port_list:
                time.sleep(1)  # 端口出现后等待1s打开口
                break
            # 每隔300S检测是否正常开机，没有则上报未正常开机
            if time.time()-start_timestamp_check > 300:
                start_timestamp_check = time.time()
                self.log_queue.put(['all', '[{}] runtimes:{} 模块300S内未正常开机'.format(datetime.datetime.now(), runtimes)])
            # TODO：此处可以增加自动打开QPST抓DUMP。
            # DUMP 300S强制重启
            if time.time()-start_timestamp > 300 and self.dm_port in port_list and self.at_port not in port_list:
                start_timestamp = time.time()
                self.log_queue.put(['at_log', '[{}] 300S内模块未从DUMP模式恢复，强制重启'.format(datetime.datetime.now())])
                with serial.Serial(self.dm_port, 115200, timeout=0.8) as dm_port:
                    dm_port.write(bytes.fromhex('0700000008000000'))

    def get_port_list(self):
        """
        获取当前电脑设备管理器中所有的COM口的列表
        :return: COM口列表，例如['COM3', 'COM4']
        """
        try:
            self.logger.info('get_port_list')
            port_name_list = []
            ports = serial.tools.list_ports.comports()
            for port, _, _ in sorted(ports):
                port_name_list.append(port)
            self.logger.info(port_name_list)
            return port_name_list
        except TypeError:  # Linux偶现
            return self.get_port_list()

    def check_cpin(self):

        while True:
            time.sleep(0.001)
            port_data = self.at_port_opened.readline().decode("utf-8", 'ignore')
            if port_data != "":
                self.log_queue.put(['at_log', '[{} Recv] {}'.format(datetime.datetime.now(), repr(port_data).replace("'", ''))])
                if 'CPIN: READY' in port_data:
                    return True
        
    def switch_slot(self, imei, runtimes):
        """
        查看当前卡槽位置并切换卡槽
        """
        start_time = time.time()
        slot_value = self.send_at('AT+QUIMSLOT?', self.at_port_opened, runtimes, timeout=3)
        return_value_re = ''.join(re.findall(r'QUIMSLOT:\s(\d+)', slot_value))
        if '1' == return_value_re and 'OK' in slot_value:
            try:
                self.send_at('AT+QUIMSLOT=2', self.at_port_opened, runtimes, timeout=3)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{}卡槽1切换卡槽2失败！'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'switch_error_times', 1])
                self.main_queue.put(False)
            switch_time = time.time()-start_time
            self.log_queue.put(['df', runtimes, 'switch_time', switch_time])
            status = self.check_cpin()
            if status:
                self.check_module_info(imei, runtimes)
        else:
            try:
                self.send_at('AT+QUIMSLOT=1', self.at_port_opened, runtimes, timeout=3)
            except Exception as e:
                self.log_queue.put(['all', '[{}] runtimes:{}卡槽2切换卡槽1失败！'.format(datetime.datetime.now(), runtimes)])
                self.log_queue.put(['df', runtimes, 'switch_error_times', 1])
                self.main_queue.put(False)
            switch_time = time.time() - start_time
            self.log_queue.put(['df', runtimes, 'switch_time', switch_time])
            status = self.check_cpin()
            if status:
                self.check_module_info(imei, runtimes)

    def cfun_change(self, runtimes):
        value = random.choice(['0', '1', '4'])
        self.send_at('AT+CFUN?', self.at_port_opened, runtimes, timeout=15)
        for i in range(1, 6):
            self.send_at('AT+CFUN={}'.format(value), self.at_port_opened, runtimes, timeout=15)
            cfun_value = self.send_at('AT+CFUN?', self.at_port_opened, runtimes, timeout=15)
            cfun_value_re = re.findall(r'CFUN:\s(\d+)', cfun_value)
            if value in cfun_value_re:
                break
            else:
                self.log_queue.put(['all', '[{}] runtimes:{}第{}次切换CFUN为{}失败！'.format(datetime.datetime.now(), runtimes, i, value)])
                self.log_queue.put(['df', runtimes, 'cfun_fail_times', i])
        else:
            self.log_queue.put(['all', '[{}] 切换CFUN为{}连续五次失败！'.format(datetime.datetime.now(), value)])
            os.system("echo 保留现场，问题定位完成后请直接关闭脚本 & pause >nul")
        if value == '1':
            time.sleep(3)   # 切换成功后等待3S再找网
            self.check_network(False, runtimes)
        elif value == '0':
            return True
        elif value == '4':
            time.sleep(0.1)
            self.send_at('AT+QCCID', self.at_port_opened, runtimes, timeout=0.3)
            self.send_at('AT+CPMS?', self.at_port_opened, runtimes, timeout=0.3)

    def check_atd(self, runtimes):
        self.send_at('AT+QCFG="ims"', self.at_port_opened, runtimes, timeout=1)
        self.send_at('AT+CGPADDR', self.at_port_opened, runtimes, timeout=1)
        self.send_at('AT+CGDCONT?', self.at_port_opened, runtimes, timeout=1)
        return_val = self.send_at('ATD10010;', self.at_port_opened, runtimes, timeout=1)
        if 'ERROR' in return_val:
            return False
        time.sleep(3)
        for i in range(5):
            return_value = self.send_at('AT+CLCC;', self.at_port_opened, runtimes, timeout=1)
            return_value_re = re.findall(r'(?<=CLCC: 3,0,).*?(?=,0)', return_value)
            if '0' in return_value_re:
                self.send_at('ATH;', self.at_port_opened, runtimes, timeout=1)
                time.sleep(0.5)
                return True
            else:
                self.log_queue.put(['at_log', '[{}] 未识别到stat为0'.format(datetime.datetime.now())])

    def debug_check(self, debug_port, debug_port_pwd, runtimes):
        with serial.Serial(debug_port, 115200, timeout=0.5) as debug_port:
            debug_port.write('\r\n'.encode('utf-8'))
            debug_port.read()
            debug_port.write('\r\n'.encode('utf-8'))
            starttime = time.time()
            flag = False
            eflag = False
            fflag = False
            while True:
                return_value_login = debug_port.readline().decode("UTF-8", 'ignore')
                if return_value_login != '':
                    self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value_login))])
                    if "login:" in return_value_login:  # 登录debug口
                        debug_port.write('root\r\n'.encode('utf-8'))
                    if 'word:' in return_value_login:
                        debug_port.write('{}\r\n'.format(debug_port_pwd).encode('utf-8'))
                        time.sleep(3)
                        debug_port.write('\r\n'.encode('utf-8'))
                        time.sleep(2)
                        flag = True
                    if flag:
                        debug_port.write('cat /run/ql_voice_server.log\r\n'.encode('utf-8'))
                        time.sleep(2)
                        flag = False
                    if 'msg_id=0X2E' in return_value_login:
                        eflag = True
                    if 'msg_id=0X1F' in return_value_login:
                        fflag = True
                if time.time() - starttime > 15:
                    break
            if eflag and fflag:
                self.log_queue.put(['at_log', '[{}] 识别到msg_id=0X2E及msg_id=0X1F'.format(datetime.datetime.now())])
                return True
            else:
                self.log_queue.put(['all', '[{}] 未识别到msg_id=0X2E及msg_id=0X1F'.format(datetime.datetime.now())])
                input("保留现场，问题定位完成后请直接关闭脚本")
                # debug_port.write('dmesg\r\n'.encode('utf-8'))
                # start_time = time.time()
                # while True:
                #     return_value_login = debug_port.readline().decode("UTF-8", 'ignore')
                #     if return_value_login != '':
                #         self.log_queue.put(['debug_log', '[{}] {}'.format(datetime.datetime.now(), repr(return_value_login))])
                #     if time.time() - start_time > 20:
                #         self.atd(runtimes)

    # def atd(self, runtimes):
    #     self.send_at('ATD10086;', self.at_port_opened, runtimes, timeout=1)
    #     time.sleep(0.8)
    #     self.send_at('AT+QTEST="DUMP",1', self.at_port_opened, runtimes, timeout=8)
    #     input("保留现场，问题定位完成后请直接关闭脚本")
