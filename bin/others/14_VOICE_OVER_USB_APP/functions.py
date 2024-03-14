import asyncio
import datetime
import signal
from subprocess import getoutput
import struct
import pkg_resources
import os
import subprocess
import random
import re
import time
from threading import Thread
import logging
import sys
from collections import deque

# TODO: add iperf version check
logger = logging.getLogger(__name__)

# 脚本依赖的PIP包名称，一行一个，如果新增则添加
REQUIRE = """
    pandas
    pyserial
    requests
    requests-toolbelt
    aioftp
    paramiko
"""


def iperf39_check():
    s = getoutput('iperf3 -v')
    if '3.9' not in s:
        print("""\n\n请安装iperf3.9版本\n
        Windows10：
            1. 把脚本目录下的iperf3.exe和cygwin1.dll放到任何位置，然后配置环境变量
            2. 如果之前配置过iperf3的老版本环境变量，删除之前环境变量配置的iperf3老版本
            3. 打开新的命令行，输入iperf3 -v 显示 iperf 3.9即配置成功
        Ubuntu 64 bits :
            1. sudo apt remove iperf3 libiperf0
            2. sudo apt install libsctp1
            3. wget https://iperf.fr/download/ubuntu/libiperf0_3.9-1_amd64.deb
            4. wget https://iperf.fr/download/ubuntu/iperf3_3.9-1_amd64.deb
            5. sudo dpkg -i libiperf0_3.9-1_amd64.deb iperf3_3.9-1_amd64.deb
            6. rm libiperf0_3.9-1_amd64.deb iperf3_3.9-1_amd64.deb

            如果提示libssl1.1缺失，操作如下步骤安装libssl1.1后重新运行上面1-6命令行
            1. wget http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.0g-2ubuntu4_amd64.deb
            2. sudo dpkg -i libssl1.1_1.1.0g-2ubuntu4_amd64.deb""")
        exit()


def check_python_version():
    """
    检查环境的Python版本是否正确。
    :return:
    """
    if sys.version_info.major != 3:  # 判断是否是Python3
        print("当前Python版本非Python3，请重新安装Python3 64位版本")
        print("Python包下载地址https://www.python.org/downloads/")
        print("Python安装方法参考：https://stgit.quectel.com/5G-SDX55/Standard/wikis/脚本环境安装")
        exit()
    if sys.version_info.minor <= 5:  # 判断是否小于Python3.5
        print("当前Python版本过低，请重新安装Python3.6.X以上的64位版本")
        print("Python包下载地址https://www.python.org/downloads/")
        print("Python安装方法参考：https://stgit.quectel.com/5G-SDX55/Standard/wikis/脚本环境安装")
        exit()
    if struct.calcsize("P") * 8 != 64:  # 判断当前是不是64位的Python
        print("当前Python版本非64位，请重新安装Python3 64位版本")
        print("Python包下载地址https://www.python.org/downloads/")
        print("Python安装方法参考：https://stgit.quectel.com/5G-SDX55/Standard/wikis/脚本环境安装")
        exit()


def check_pip_list():
    """
    检查是否有没有安装的PIP包，如果有，则安装。
    :return: None
    """
    env_pip_list = [p.project_name for p in pkg_resources.working_set]
    env_pip = [p for p in pkg_resources.working_set]  # 获取当前Python环境的pip包
    # 临时方案：强制更新pyserial=3.5。pyserial=3.4的serial.tools.list_ports会超时，3.5目前测试不会
    for p in env_pip:
        if p.project_name == 'pyserial':
            if p.version != '3.5':
                subprocess.call("pip --default-timeout=3600 install {} -i https://pypi.mirrors.ustc.edu.cn/simple/".format('pyserial==3.5'), shell=True)
                subprocess.call('cls' if os.name == 'nt' else 'clear', shell=True)
    pip_list = []
    for i in REQUIRE.split('\n'):
        if i != '':
            pip_list.append(i.strip())
    for package in pip_list:
        if package not in env_pip_list:
            subprocess.call("pip --default-timeout=3600 install {} -i https://pypi.mirrors.ustc.edu.cn/simple/".format(''.join(package)), shell=True)
            subprocess.call('cls' if os.name == 'nt' else 'clear', shell=True)


def environment_check():
    """
    需要检查的项目，一般在每个主脚本开头导入并调用。
    :return: None
    """
    check_python_version()
    check_pip_list()


def pause(info="保留现场，问题定位完成后请直接关闭脚本"):
    """
    暂停当前脚本
    :return: None
    """
    print(info, end='')
    while True:
        line = sys.stdin.readline()
        line = line.rstrip()  # 去掉sys.stdin.readline最后的\n
        if line.upper() == 'E':
            exit()
        elif line.upper() == 'C':
            break
        else:
            print("如有需要输入C后按ENTER继续(大部分脚本不支持): ", end='')


class IPerfError(Exception):
    """iPerf异常"""


class IPerfServer(Thread):

    ansi_color_regex = r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]'  # based on https://stackoverflow.com/a/38662876

    def __init__(self, ip, user, passwd):
        super().__init__()
        self.ip = ip
        self.user = user
        self.passwd = passwd
        self.client = None
        self.port = None
        self.iperf_success_flag = False
        self.shutdown_flag = False
        self.error_info = ''
        self.port_range = (29000, 29999)
        self.dq_stdout = deque(maxlen=10)
        self.start()
        self.wait_iperf_init()

        # if iperf server not success
        if self.error_info:
            raise IPerfError(self.error_info)
        if not self.iperf_success_flag:
            raise IPerfError("10S内未检测到Server listening on {}".format(self.port))

        logger.info("start iperf server success")

    def run(self):
        try:
            self.connect_to_server()
            self.get_port()
            self.open_iperf3_server()
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error(e)
            self.error_info = "\n\niPerf3 Exception：\nexc_type: {}\nexc_value: {}\nexc_traceback: {}\n".format(
                exc_type,
                exc_value,
                exc_traceback
            )

    def shutdown(self):
        self.client.close()

    def wait_iperf_init(self, timeout=10):
        target_time = time.perf_counter() + timeout
        while time.perf_counter() < target_time:
            if self.iperf_success_flag or self.error_info:  # if success or have error info
                break
            time.sleep(0.001)

    def connect_to_server(self):
        import paramiko
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(hostname=self.ip, username=self.user, password=self.passwd, timeout=8)

    def get_port(self):
        # get TCP and UDP port use random
        self.port = random.randint(*self.port_range)  # USE HIGH LEVEL PORT
        _, stdout, _ = self.client.exec_command('netstat -an | {} "{}"'.format('findstr' if os.name == 'nt' else 'grep', self.port))
        # port exists?
        while True:
            time.sleep(0.001)
            if stdout.channel.exit_status_ready():
                data = stdout.channel.recv(1024).decode("GBK", "ignore")
                logger.info(data)
                if not data:  # not exist
                    logger.info("current port: {}".format(self.port))
                    break
                else:  # if port already use, use random get another port
                    self.port = random.randint(*self.port_range)  # USE HIGH LEVEL PORT
                    _, stdout, _ = self.client.exec_command('netstat -an | {} "{}"'.format('findstr' if os.name == 'nt' else 'grep', self.port))

    def open_iperf3_server(self):
        # exec command open iperf server
        stdin, stdout, stderr = self.client.exec_command('{} -s -p {} -1'.format('iperf3.9', self.port), get_pty=True)

        # if iperf3 not exit or stdout or stderr has output
        while not stdout.channel.exit_status_ready() or stdout.channel.recv_ready() or stderr.channel.recv_stderr_ready():
            # decline CPU usage
            time.sleep(0.001)

            # stdout
            if stdout.channel.recv_ready():
                data = re.sub(self.ansi_color_regex, '', stdout.channel.recv(1024).decode('GBK', 'ignore'))
                logger.info('stdout: {}'.format(data))
                self.dq_stdout.append(data)
                if "listening on {}".format(self.port) in ''.join(self.dq_stdout):
                    self.iperf_success_flag = True

            # stderr
            if stderr.channel.recv_stderr_ready():
                data = re.sub(self.ansi_color_regex, '', stderr.channel.recv(1024).decode('GBK', 'ignore'))
                logger.info('stderr: {}'.format(data))


class QuectelCMThread(Thread):
    def __init__(self, log_queue):
        super().__init__()
        self.ctrl_c_flag = False
        self.terminate_flag = False
        self.log_queue = log_queue
        self.daemon = True
        self.start()
        time.sleep(20)

    def run(self):
        async def quectel_cm():
            s = await asyncio.create_subprocess_exec('quectel-CM', stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.STDOUT)
            while True:
                line = b''
                try:
                    line = await asyncio.wait_for(s.stdout.readline(), 0.1)
                except asyncio.TimeoutError:
                    pass
                finally:
                    if line:
                        self.log_queue.put(['quectel_cm_log', '[{}] {}'.format(datetime.datetime.now(), line.decode('utf-8', 'ignore'))])
                    if self.ctrl_c_flag:  # safety terminate application with ctrl c when APP have teardown action
                        ctrl_c = signal.CTRL_C_EVENT if os.name == 'nt' else signal.SIGINT
                        s.send_signal(ctrl_c)
                        self.ctrl_c_flag = False
                    if self.terminate_flag:
                        if s.returncode is None:
                            s.terminate()
                        await s.wait()
                        return True

        loop = asyncio.new_event_loop()  # in thread must creat new event loop.
        asyncio.set_event_loop(loop)
        tasks = [quectel_cm()]
        loop.run_until_complete(asyncio.wait(tasks))
        loop.close()

    def terminate(self):
        self.ctrl_c_flag = True
        time.sleep(3)
        self.terminate_flag = True
        time.sleep(3)

class VOICEAPPThread(Thread):
    def __init__(self, path, log_queue):
        super().__init__()
        self.path = path
        self.terminate_flag = False
        self.log_queue = log_queue
        self.daemon = True
        self.start()

    def run(self):
        async def quectel_cm():
            s = await asyncio.create_subprocess_shell('./loopback_test 0', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=self.path)
            while True:
                line = b''
                try:
                    line = await asyncio.wait_for(s.stdout.readline(), 0.1)
                except asyncio.TimeoutError:
                    pass
                finally:
                    if line:
                        self.log_queue.put(['loopback_log', '[{}] [VOICE OVER USB PCIE] {}'.format(datetime.datetime.now(), line.decode('utf-8', 'ignore'))])
                    if self.terminate_flag:
                        if s.returncode is None:
                            s.terminate()
                        await s.wait()
                        self.terminate_flag = False
                        break
        try:
            loop = asyncio.new_event_loop()  # in thread must creat new event loop.
            asyncio.set_event_loop(loop)
            tasks = [quectel_cm()]
            loop.run_until_complete(asyncio.wait(tasks))
            loop.close()
        except RuntimeError:
            pass

    def terminate(self):
        self.terminate_flag = True
        while True:
            self.log_queue.put(['loopback_log', '[{}] [VOICE OVER USB PCIE] {}'.format(datetime.datetime.now(), 'wait terminat')])
            time.sleep(3)
            if self.terminate_flag is False:
                self.kill_processes()
                self.log_queue.put(['loopback_log', '[{}] [VOICE OVER USB PCIE] {}'.format(datetime.datetime.now(), 'success terminated')])
                return True

    @staticmethod
    def kill_processes():
        data = os.popen('ps -ef | grep loopback_test').read()
        pid = re.findall(r'root.*?(\d+)', data)
        if pid:
            for id in pid:
                subprocess.getoutput(f'kill {id}')

if __name__ == '__main__':
    voice_path = r'/home/flynn/Downloads/voice_over_usb_pcie'
    v = VOICEAPPThread(voice_path, 1)
    time.sleep(3)
    v.terminate()
    # iperf_ip = "112.31.84.164"
    # iperf_user = "Q"
    # iperf_passwd = "st"
    # iperf_server = IPerfServer(iperf_ip, iperf_user, iperf_passwd)
    # print(1)
    # time.sleep(100)
    # iperf_server.shutdown()

    # iperf39_check()

    # from concurrent.futures import ThreadPoolExecutor
    #
    # runtime = 0
    #
    # def test(times):
    #     iperf_ip = "112.31.84.164"
    #     iperf_user = "Q"
    #     iperf_passwd = "st"
    #     print("runtime：{}".format(times))
    #     iperf_server = IPerfServer(iperf_ip, iperf_user, iperf_passwd)
    #     iperf_server.shutdown()
    #
    #
    # with ThreadPoolExecutor(max_workers=10) as t:
    #     for i in range(100000):
    #         t.submit(test, i)

    # pause()
    # environment_check()
