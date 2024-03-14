import certifi
from PyQt5.QtCore import QThread, pyqtSignal
import os
import signal
import subprocess
import time
import zipfile
import shutil
import pycurl
from queue import Empty
import datetime


class RunScript(QThread):
    def __init__(self, script_name, ui, que):
        super().__init__()
        self.exit_flag = False
        self.reset_flag = False
        self.script_name = script_name
        self.ui = ui
        self.que = que

    def __del__(self):
        self.wait()

    def run(self):
        time.sleep(0.1)
        path = os.path.join(os.getcwd(), 'script', self.script_name)
        s = subprocess.Popen(['python', path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.que.put(s)
        while True:
            time.sleep(0.001)
            if self.exit_flag:
                self.ui.label_script_status.setText('正在停止...')
                self.ui.label_script_status.setStyleSheet("QLabel{background:yellow}")
                s.send_signal(signal.CTRL_BREAK_EVENT)
                s.wait()
                self.ui.button_start.setDisabled(False)
                self.ui.button_end.setDisabled(True)
                self.ui.lcd_runtimes.display(0)
                self.ui.label_script_status.setText('脚本已结束')
                self.ui.label_script_status.setStyleSheet("QLabel{background:white}")
                self.ui.statusBar.showMessage('log已统计完成，脚本运行结束')
                self.que.put('s')
                break
            if self.reset_flag:
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(s.pid)])
                # kill_proc_tree(s.pid)
                self.ui.button_start.setDisabled(False)
                self.ui.button_end.setDisabled(True)
                self.ui.button_reset.setDisabled(True)
                self.ui.lcd_runtimes.display(0)
                self.ui.label_script_status.setText('脚本已重置')
                self.ui.label_script_status.setStyleSheet("QLabel{background:white}")
                self.ui.statusBar.showMessage('脚本已重置')
                self.que.put('s')
                break
            if s.poll() is not None:  # 脚本跑崩了，写入log
                self.que.put('s')
                break


class NonBlockRead(QThread):

    dos_signal = pyqtSignal(str)

    def __init__(self, que):
        super().__init__()
        self.que = que

    def run(self):
        pipe = ''
        time.sleep(1)  # 等待主线程将subprocess实例推送过来
        with open('bug_reporter.txt', 'w', encoding='GBK') as f:
            while True:
                time.sleep(0.001)
                try:
                    pipe = self.que.get_nowait()
                except Empty:
                    pass
                try:
                    return_value = pipe.stdout.readline().decode('GBK', 'ignore')
                    if return_value != '':
                        f.write('{} {}'.format(datetime.datetime.now(), return_value))
                        f.flush()
                        self.dos_signal.emit(return_value)
                except AttributeError:
                    break


class ExtractFile(QThread):

    def __init__(self, latest_version, branch, combo_box, ui):
        super().__init__()
        self.script_path_list = []
        self.all_version = []
        self.latest_version = latest_version
        self.branch = branch
        self.script_list = []
        self.combo_box = combo_box
        self.combo_box.clear()
        self.ui = ui

    def __del__(self):
        self.wait()

    def run(self):
        try:
            self.ui.statusBar.showMessage('正在切换{}分支...'.format(self.branch))
            if os.path.isdir(os.path.join(os.getcwd(), 'cache')):
                for dir_file in os.listdir(os.path.join(os.getcwd(), 'cache')):  # 解压所有的文件
                    if dir_file.endswith('.zip'):
                        try:
                            z = zipfile.ZipFile(os.path.join(os.getcwd(), 'cache', dir_file))
                            z.extractall(os.path.join(os.getcwd(), 'cache'))
                        except:
                            pass
                for script_folder in os.listdir(os.path.join(os.getcwd(), 'cache')):  # 将所有文件夹的名字放入列表
                    if os.path.isdir(os.path.join(os.getcwd(), 'cache', script_folder)):
                        path_split_list = os.path.join(os.getcwd(), 'cache', script_folder).split('-')
                        self.script_path_list.append(path_split_list)
                self.all_version = [version[2] for version in self.script_path_list]  # 取出所有提交的commit id
            else:
                os.mkdir('cache')  # 如果没有则新建文件夹
            if self.latest_version not in self.all_version:  # 如果没有最新版本，下载版本并解压
                with open(os.path.join(os.getcwd(), 'cache', 'Standard-{}.zip'.format(self.branch)), 'wb') as f:
                    curl = pycurl.Curl()
                    curl.setopt(pycurl.CAINFO, certifi.where())
                    curl.setopt(pycurl.HTTPHEADER, ["PRIVATE-TOKEN: yzAJTSRxGVriiPDiEZ5V"])
                    curl.setopt(pycurl.URL, "https://stgit.quectel.com/api/v4/projects/173/repository/archive.zip?sha={}".format(self.branch))
                    curl.setopt(pycurl.WRITEDATA, f)
                    curl.perform()
                    curl.close()
                z = zipfile.ZipFile(os.path.join(os.getcwd(), 'cache', 'Standard-{}.zip'.format(self.branch)))
                z.extractall(os.path.join(os.getcwd(), 'cache'))
            for _, _, main_scripts in os.walk(os.path.join(os.getcwd(), 'cache', 'Standard-{}-{}'.format(self.branch, self.latest_version), 'bin')):
                for script in main_scripts:
                    if script.endswith('.py'):
                        self.script_list.append(script)
            for script in self.script_list:
                self.combo_box.addItem(script)
            if os.path.isdir(os.path.join('script')):
                shutil.rmtree(os.path.join(os.getcwd(), 'script'))
            os.mkdir(os.path.join(os.getcwd(), 'script'))
            for path, _, files in os.walk(os.path.join(os.getcwd(), 'cache', 'Standard-{}-{}'.format(self.branch, self.latest_version))):
                for file in files:
                    if file.endswith('.py'):
                        shutil.copy(os.path.join(path, file), os.path.join(os.getcwd(), 'script'))
            self.ui.statusBar.showMessage('分支: {}，请选择需要运行的脚本'.format(self.branch))
            self.ui.statusBar.setStyleSheet("color:black")
        except Exception as e:
            self.ui.statusBar.showMessage('网络异常，请检查网络 {}'.format(e))
