# _*_ coding: utf-8 _*_
import os, re, datetime, time
import serial
import serial.tools.list_ports
import platform
import subprocess

filename = 'yikuaiqian.txt'
logpath = os.path.dirname(os.path.abspath(__file__))

content_version1_string = "RM"
content_version2_string = "RG"
content_version3_string = "factory"
content_input_modem_port = "Please input modem port: "
content_modem_port_inputted = "Modem port is: "


class Method(object):
    def __init__(self):
        super(Method, self).__init__()

    def write_to_file(self, logpath, filename, content):
        self.logpath = logpath
        self.filename = filename
        self.content = content
        with open(filename, 'a') as file_object:
            file_object.flush()
            file_object.write(content + "\n")
            file_object.close()
        return

    def get_date_time_now(self):
        # date_now = time.strftime('%Y.%m.%d', time.localtime(time.time()))
        date_now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return date_now

    def use_time_to_filename(self):
        date_now = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        return date_now

    def use_time_to_QFIRHOSE_upgrade_filename(self):
        date_now = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        return date_now+"QFIRHOSE_upgrade"

    def get_versionA(self, path):
        self.path = path
        version_a = ""
        file_list = os.listdir(path)
        # print(file_list)
        ii = len(file_list)
        for i in range(ii):
            result = content_version1_string in file_list[i] or content_version2_string in file_list[
                i] or content_version3_string in file_list[i]
            if result:
                # print(file_list[i])
                version_a = file_list[i]
                break
        return version_a

    def get_versionB(self, path, versiona):
        self.versiona = versiona
        self.path = path
        version_b = ""
        file_list = os.listdir(path)
        ii = len(file_list)
        for i in range(ii):
            result = content_version1_string in file_list[i] or content_version2_string in file_list[i] or content_version3_string in file_list[i]
            # print(result)
            if result:
                if versiona != file_list[i]:
                    version_b = file_list[i]
                    break

        # print(version_b)
        return version_b

    def get_default_args(self):
        modem_port = "/dev/ttyUSB2"
        uart_port = "/dev/ttyUSB4"
        dm_port = "/dev/ttyUSB0"
        baudrate = 115200
        stopbits = 1
        parity = "n"
        bytesize = 8

        return modem_port, uart_port, dm_port, baudrate, stopbits, parity, bytesize

    def set_args(self, modem_port, uart_port, dm_port, baudrate, stopbits, parity, bytesize):
        self.modem_port = modem_port
        self.uart_port = uart_port
        self.dm_port = dm_port
        self.baudrate = baudrate
        self.stopbits = stopbits
        self.parity = parity
        self.bytesize = bytesize

        return modem_port, uart_port, dm_port, baudrate, stopbits, parity, bytesize

    def get_serial_port_list(self):
        port_list = list(serial.tools.list_ports.comports())
        # print(port_list)
        port_list_name = []
        if len(port_list) <= 0:
            print("The Serial port can't find!")
        else:
            for each_port in port_list:
                # print(each_port[0])
                port_list_name.append(each_port[0])
        return port_list_name

    def get_9091_port(self):
        port9091=""
        port_list = list(serial.tools.list_ports.comports())
        # print(port_list)
        port_list_name = []
        if len(port_list) <= 0:
            print("The Serial port can't find!")
        else:
            for each_port in port_list:
                if "9091" in each_port[1]:
                    port9091 = each_port[0]
                elif "9092" in each_port[1]:
                    port9091 = each_port[0]
                elif "9090" in each_port[1]:
                    port9091 = each_port[0]
        return port9091

    def check_shell(self):
        result = os.system('adb shell ls /sdcard')  # result 0 meas success ,1 means fail
        # print(result)
        if result == 0:
            return True
        else:
            return False

    def get_platform(self):
        return platform.platform()

    def get_windows_modemport_input(self):
        print(content_input_modem_port)
        modem_port = input()
        print(content_modem_port_inputted+"com"+modem_port)
        return modem_port

    def check_at(self, modem_port, atcommand):
        self.modem_port = modem_port
        self.atcommand = atcommand
        ModemPort = serial.Serial(modem_port, baudrate=115200, timeout=0.8)
        ModemPort.write(atcommand.encode())
        ModemPort.readline(800).decode("GBK")
        if "OK" in ModemPort.readline(800).decode("GBK"):
            return 0
        else:
            return 1

    def check_modem(self, modem_port, atcommand, version):
        self.modem_port = modem_port
        self.atcommand = atcommand
        self.version = version
        ModemPort = serial.Serial(modem_port, baudrate=115200, timeout=0.8)
        ModemPort.write(atcommand.encode())
        ModemPort.readline(800).decode("GBK")[0:30]
        if ModemPort.readline(800).decode("GBK")[0:30] in version:
            return 0  # modem 有且版本对比正常
        elif ModemPort.readline(800).decode("GBK")[10:30] == "":
            return 1  # modem返回值异常
        elif ModemPort.readline(800).decode("GBK")[10:30] != "":
            return ModemPort.readline(800).decode("GBK")  # modem有，但版本不对
        print(ModemPort.readline(800).decode("GBK")[0:30][0:30])

    def send_shell(self, command):
        self.command = command
        result = os.system(command)  # result 0 meas success ,1 means fail
        return result

    def upgrade_version(self, version):
        self.versiona = version
        p = subprocess.Popen(["./QFirehose -f "+version], stdout=subprocess.PIPE, shell=True)
        result = p.stdout.read().decode("gbk")
        return result

    def check_upgrade_result(self, result):
        self.result = result
        if "Upgrade module successfully" in result:
            return 0
        elif "Upgrade module unsuccessfully" in result:
            return 1

    def get_time_ticks(self):
        time_ticks = time.time()
        return time_ticks

    def get_version(self, modem_port):
        self.modem_port = modem_port
        ModemPort = serial.Serial(modem_port, baudrate=115200, timeout=0.8)
        ModemPort.write("ATI+CSUB\r".encode())
        result = ModemPort.read(size=1024).decode("GBK")
        return_value = re.sub(r'\[.*]\s', '', result)
        large_version = ''.join(re.findall(r'Revision: (.*)M', return_value))
        minor_version = "".join(re.findall(r"SubEdition: (.*?)\s+OK", return_value))
        return large_version + minor_version

    def check_version(self, modem_port, origin_version_at):
        self.modem_port = modem_port
        self.origin_version_at = origin_version_at
        ModemPort = serial.Serial(modem_port, baudrate=115200, timeout=0.8)
        ModemPort.write("ATI+CSUB\r".encode())
        result = ModemPort.read(size=1024).decode("GBK")
        return_value = re.sub(r'\[.*]\s', '', result)
        large_version = ''.join(re.findall(r'Revision: (.*)M', return_value))
        minor_version = "".join(re.findall(r"SubEdition: (.*?)\s+OK", return_value))
        return_version = large_version + minor_version
        if return_version in self.origin_version_at:
            return 0
        else:
            return return_version

    def get_cfun(self, modem_port):
        self.modem_port = modem_port
        ModemPort = serial.Serial(modem_port, baudrate=115200, timeout=0.8)
        ModemPort.write("AT+CFUN?\r".encode())
        result = ModemPort.read(size=1024).decode("GBK")
        cfun_value = ''.join(re.findall(r'\+CFUN:\s\S+', result))
        return cfun_value

    def get_imei(self, modem_port):
        self.modem_port = modem_port
        ModemPort = serial.Serial(modem_port, baudrate=115200, timeout=0.8)
        ModemPort.write('{}\r\n'.format("AT+EGMR=0,7\r").encode('utf-8'))
        result = ModemPort.read(size=1024).decode("GBK")[22:37]
        return result

    def check_imei(self, modem_port, origin_imei):
        self.modem_port = modem_port
        self.origin_imei = origin_imei
        ModemPort = serial.Serial(modem_port, baudrate=115200, timeout=0.8)
        ModemPort.write('{}\r\n'.format("AT+EGMR=0,7\r").encode('utf-8'))
        result = ModemPort.read(size=1024).decode("GBK")
        if origin_imei in result:
            return 0
        else:
            return result[22:37]

    def get_network(self, modem_port):
        self.modem_port = modem_port
        ModemPort = serial.Serial(modem_port, baudrate=115200, timeout=0.8)
        ModemPort.write('{}\r\n'.format("AT+CEREG?\r").encode('utf-8'))
        cereg_result = ModemPort.read(size=1024).decode("GBK")
        cereg_value = ''.join(re.findall(r'\+CEREG:\s\S+', cereg_result))
        ModemPort.write('{}\r\n'.format("AT+CREG?\r").encode('utf-8'))
        creg_result = ModemPort.read(size=1024).decode("GBK")
        creg_value = ''.join(re.findall(r'\+CREG:\s\S+', creg_result))
        ModemPort.write('{}\r\n'.format("AT+CGREG?\r").encode('utf-8'))
        cgreg_result = ModemPort.read(size=1024).decode("GBK")
        cgreg_value = ''.join(re.findall(r'\+CGREG:\s\S+', cgreg_result))
        net_result = [cereg_value, creg_value, cgreg_value]
        return net_result

    def get_local_time(self):
        now_time = ""
        now_time = datetime.datetime.now()
        return now_time

method = Method()
path = os.getcwd()
print(method.get_versionA(path))