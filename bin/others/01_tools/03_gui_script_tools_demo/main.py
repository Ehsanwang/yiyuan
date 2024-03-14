from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QMainWindow, QApplication, QGridLayout, QLabel, QLineEdit, QMessageBox
from main_window import Ui_MainWindow
import sys
import requests
import pandas as pd
from pandas import DataFrame
import json
import os
import re
from queue import Queue
from functions import ExtractFile, NonBlockRead, RunScript


class MainWindow(QMainWindow, Ui_MainWindow):

    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        # 初始化branch和脚本名称
        self.fill_branches()
        self.fill_script()
        self.ui.combo_box_branch_name.activated.connect(self.fill_script)
        self.ui.combo_box_script_name.activated.connect(self.fill_param)
        # 初始化参数列表和布局
        self.fill_param_layout = QGridLayout()
        self.param_list_final = []
        # 初始化LCD、按钮状态和信号槽
        self.ui.lcd_runtimes.setStyleSheet("color:red")
        self.ui.button_end.setDisabled(True)
        self.ui.button_reset.setDisabled(True)
        self.ui.button_start.clicked.connect(self.modify_para)
        self.ui.button_start.clicked.connect(self.run_script)
        self.ui.button_end.clicked.connect(self.stop_script)
        self.ui.button_reset.clicked.connect(self.reset_script)
        self.ui.button_open_log_dir.clicked.connect(self.open_log_dir)
        self.ui.button_open_script_raw.clicked.connect(self.open_raw_file)
        # 初始化runtimes的timer和dos_log的timer
        self.timer_runtimes = QTimer()
        self.timer_runtimes.timeout.connect(self.get_current_runtimes)
        self.timer_dos_log = QTimer()
        self.timer_dos_log.timeout.connect(self.fill_dos_log)
        # text_editor改为不可编辑模式
        self.ui.text_edit_dos_log.setFocusPolicy(False)
        self.ui.text_edit_cmd_window.setFocusPolicy(False)
        # 初始化线程和队列
        self.thread = ''
        self.que = Queue()

    @staticmethod
    def open_log_dir():
        os.popen('explorer.exe {}'.format(os.getcwd()))

    def open_raw_file(self):
        print()
        os.popen('notepad.exe {}'.format(os.path.join(os.getcwd(), 'script', self.ui.combo_box_script_name.currentText())))

    def run_script(self):
        if self.ui.combo_box_script_name.currentText() != '':
            # 设置界面和按钮信息
            self.ui.statusBar.showMessage('分支: {}，脚本: {}   正在运行'.format(self.ui.combo_box_branch_name.currentText(), self.ui.combo_box_script_name.currentText()))
            self.ui.label_script_status.setText('正在运行')
            self.ui.label_script_status.setStyleSheet("QLabel{background:green}")
            self.ui.button_start.setDisabled(True)
            self.ui.button_end.setDisabled(False)
            self.ui.button_reset.setDisabled(False)
            self.ui.text_edit_dos_log.clear()
            self.ui.text_edit_cmd_window.clear()
            # 启动线程
            self.thread = RunScript(self.ui.combo_box_script_name.currentText(), self.ui, self.que)
            self.thread.start()
            # 启动获取runtimes的定时器
            self.timer_runtimes.start(2000)
            self.timer_dos_log.start(2000)
            # 启动阻塞读取的线程
            non_block_read_thread = NonBlockRead(self.que)
            non_block_read_thread.dos_signal.connect(self.fill_cmd_window)
            non_block_read_thread.start()
            non_block_read_thread.exec()

    def stop_script(self):
        self.ui.statusBar.showMessage('正在停止脚本并统计log，请稍后...')
        self.ui.button_reset.setDisabled(True)
        self.thread.exit_flag = True
        self.timer_runtimes.stop()
        self.timer_dos_log.stop()

    def reset_script(self):
        reply = QMessageBox.warning(self, 'Message', '你想重置脚本吗(log信息不会统计)', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.thread.reset_flag = True
            self.timer_runtimes.stop()
            self.timer_dos_log.stop()

    def get_current_runtimes(self):
        current_log_dir = [directory for directory in os.listdir() if os.path.isdir(directory) and directory.startswith('20')].pop()
        if os.path.isfile(os.path.join(os.getcwd(), current_log_dir, '_cache.csv')):
            data = pd.read_csv(os.path.join(os.getcwd(), current_log_dir, '_cache.csv'))
            df = DataFrame(data)
            self.ui.lcd_runtimes.display(int(df['runtimes'].iloc[-1]+1))
        else:
            self.ui.lcd_runtimes.display(1)

    def modify_para(self):
        if self.ui.combo_box_script_name.currentText() != "":
            new_para = ''
            para_dict = {}
            rows = self.fill_param_layout.rowCount()
            for row in range(rows):
                try:
                    para_dict[self.fill_param_layout.itemAtPosition(row, 0).widget().text()] = self.fill_param_layout.itemAtPosition(row, 1).widget().text()
                except:
                    pass
            with open('param.json', 'w', encoding='utf-8') as f:
                json.dump(para_dict, f, indent=2, sort_keys=True, ensure_ascii=False)
            with open(os.path.join(os.getcwd(), 'script', self.ui.combo_box_script_name.currentText()), 'rt', encoding='utf-8') as f:
                file_content = ''.join(re.findall(r'# 需要配置的参数\s*([\s\S]*?)# ==[=]*', f.read()))
                # print(repr(file_co ntent))
                file_content = file_content.split('\n')
                for para, value in para_dict.items():
                    for line in file_content:
                        if line.startswith(para):
                            line = re.sub(r"""(.*?=\s*[r]*["|'])(.*)(["|']\s*#.*)""", r'\g<1>{}\g<3>'.format(value), line)
                            new_para += repr(line).strip("'").strip('"') + '\n'
            # print(new_para)
            with open(os.path.join(os.getcwd(), 'script', self.ui.combo_box_script_name.currentText()), 'rb+') as f:
                param_start_pointer = 0
                while True:
                    line = f.readline().decode('utf-8', 'ignore')
                    if '# 需要配置的参数' in line:
                        param_start_pointer = f.tell()
                    if param_start_pointer != 0 and f.tell() > param_start_pointer:
                        if '# ===' in line:
                            f.seek(pointer, 0)
                            last_content = f.read().decode('utf-8', 'ignore')
                            break
                    pointer = f.tell()
                f.seek(param_start_pointer, 0)
                f.truncate()
                f.write(new_para.encode('utf-8'))
                f.write(last_content.replace('SIGINT', 'SIGBREAK').replace(', end=""', '').encode('utf-8'))

    def fill_dos_log(self):
        current_log_dir = [directory for directory in os.listdir() if os.path.isdir(directory) and directory.startswith('20')].pop()
        current_dos_log = [dos_log for dos_log in os.listdir(os.path.join(os.getcwd(), current_log_dir)) if dos_log.startswith("DOS")].pop()
        with open(os.path.join(os.getcwd(), current_log_dir, current_dos_log), 'r', encoding='GBK') as f:
            data = f.read()
            if data == '':
                self.ui.text_edit_dos_log.setText('暂无异常上报')
            else:
                self.ui.text_edit_dos_log.setText(data)
            cursor = self.ui.text_edit_dos_log.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.ui.text_edit_dos_log.setTextCursor(cursor)

    def fill_cmd_window(self, return_value):
        return_value = return_value.replace('\\r', '').replace('\\n', '')
        self.ui.text_edit_cmd_window.append(return_value)

    def fill_param(self):
        self.ui.statusBar.showMessage('分支: {}，脚本: {}'.format(self.ui.combo_box_branch_name.currentText(), self.ui.combo_box_script_name.currentText()))
        self.param_list_final.clear()
        param_list_cache = []
        param_dict = {}
        for i in range(self.fill_param_layout.count()):  # 删除所有的控件元素
            self.fill_param_layout.itemAt(i).widget().deleteLater()
        if os.path.isfile(os.path.join(os.getcwd(), 'param.json')):
            with open('param.json', 'r') as f:
                param_dict = json.load(f)
        # 处理参数成['uart_port', 'COM10', '定义串口号,用于控制DTR引脚电平或检测URC信息', 1]的形式
        with open(os.path.join(os.getcwd(), 'script', self.ui.combo_box_script_name.currentText()), 'r', encoding='utf-8') as f:
            params = ''.join(re.findall(r'# 需要配置的参数\s*([\s\S]*?)# ====', f.read())).split('\n')
            for param in params:
                if param != '':
                    param_list_cache.append(re.split(r'[=|#]', param.replace(' ', '')))
            for param in param_list_cache:
                if "'" in param[1] or '"' in param[1]:
                    arg = param[1].replace("r'", '').replace('r"', '').replace('"', '').replace("'", '')
                    if param[0] in param_dict:
                        self.param_list_final.append([param[0], param_dict[param[0]], param[2]])
                    else:
                        self.param_list_final.append([param[0], arg, param[2]])
                else:
                    if param[0] in param_dict:
                        self.param_list_final.append([param[0], param_dict[param[0]], param[2]])
                    else:
                        self.param_list_final.append([param[0], param[1], param[2]])
        for (num, [arg, value, description]) in enumerate(self.param_list_final):
            button = QLabel(arg)
            button.setFixedWidth(70)
            button.setToolTip(arg)
            label = QLineEdit(value)
            label.setToolTip(description)
            self.fill_param_layout.addWidget(button, num, 0)
            self.fill_param_layout.addWidget(label, num, 1)
        self.ui.group_box_para_set.setLayout(self.fill_param_layout)

    def fill_script(self):
        extract_file = ExtractFile(self.get_latest_version(), self.ui.combo_box_branch_name.currentText(), self.ui.combo_box_script_name, self.ui)
        extract_file.start()

    def fill_branches(self):
        try:
            # 获取所有的tag
            all_branches_and_tags = []
            urls = ['https://stgit.quectel.com/api/v4/projects/173/repository/branches',
                    'https://stgit.quectel.com/api/v4/projects/173/repository/tags']
            for url in urls:
                r = requests.get(url + '?private_token=yzAJTSRxGVriiPDiEZ5V', timeout=1)
                for key in r.json():
                    all_branches_and_tags.append(key['name'])
            for item in all_branches_and_tags:
                self.ui.combo_box_branch_name.addItem(item)
            self.ui.statusBar.showMessage('请在脚本名称下拉框中选择脚本')
        except Exception as e:
            self.ui.statusBar.showMessage('网络异常，请检查网络 {}'.format(e))
            self.ui.statusBar.setStyleSheet("color:red")

    def get_latest_version(self):
        branch_or_tag = self.ui.combo_box_branch_name.currentText()
        url = 'https://stgit.quectel.com/api/v4/projects/173/repository/commits/{}?private_token=yzAJTSRxGVriiPDiEZ5V'.format(branch_or_tag)
        try:
            r = requests.get(url, timeout=1)
            latest_version = r.json()['id']
            return latest_version
        except Exception as e:
            self.ui.statusBar.showMessage('网络异常，请检查网络 {}'.format(e))
            self.ui.statusBar.setStyleSheet("color:red")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
