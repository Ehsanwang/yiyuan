# -*- encoding=utf-8 -*-
from PyQt5 import QtCore
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMainWindow, QComboBox, QAction, QMessageBox
from MainWindow import Ui_MainWindow
import requests
import pycurl
import time
import sys
import certifi


class ComboBox(QComboBox):
    popupAboutToBeShown = QtCore.pyqtSignal()

    def showPopup(self):
        self.popupAboutToBeShown.emit()
        super(ComboBox, self).showPopup()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.ui.combo_box_tag.popupAboutToBeShown.connect(self.update_combo_box)
        self.status = self.statusBar()
        self.status.showMessage('准备就绪')
        self.ui.help.triggered.connect(self.show_help_info)

    def show_help_info(self):
        QMessageBox.information(self, '帮助', 'SDX55 Open Git下载工具，如有任何问题请联系 Flynn。', QMessageBox.Yes, QMessageBox.Yes)

    def update_combo_box(self):
        self.ui.combo_box_tag.clear()
        url = 'https://stgit.quectel.com/api/v4/projects/522/repository/tags?private_token=yzAJTSRxGVriiPDiEZ5V'
        r = requests.get(url)
        for item in r.json():
            self.ui.combo_box_tag.addItem(item['name'])

    def download_master(self):
        self.ui.button_master.setDisabled(True)
        self.status.showMessage('正在下载master分支')
        downloader = Downloader('master')
        downloader.sig.connect(self.download_master_success)
        downloader.start()
        downloader.exec()

    def download_master_success(self):
        self.status.showMessage("master分支下载完成")
        self.ui.button_master.setDisabled(False)

    def download_develop(self):
        self.ui.button_develop.setDisabled(True)
        self.status.showMessage('正在下载develop分支')
        downloader = Downloader('develop')
        downloader.sig.connect(self.download_develop_success)
        downloader.start()
        downloader.exec()

    def download_develop_success(self):
        self.status.showMessage("develop分支下载完成")
        self.ui.button_develop.setDisabled(False)

    def download_tag(self):
        if self.ui.combo_box_tag.currentText() == '':
            self.status.showMessage("请点击下拉菜单选择tag")
        else:
            self.ui.button_tag.setDisabled(True)
            self.status.showMessage('正在下载tag {}'.format(self.ui.combo_box_tag.currentText()))
            downloader = Downloader(self.ui.combo_box_tag.currentText())
            downloader.sig.connect(self.download_tag_success)
            downloader.start()
            downloader.exec()

    def download_tag_success(self):
        self.status.showMessage("tag: {} 下载完成".format(self.ui.combo_box_tag.currentText()))
        self.ui.button_tag.setDisabled(False)


class Downloader(QThread):
    sig = pyqtSignal()

    def __init__(self, branch):
        super().__init__()
        self.branch = branch

    def run(self):
        current_time = time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime(time.time()))
        with open('Standard_{}_{}.zip'.format(self.branch, current_time), 'wb') as f:
            curl = pycurl.Curl()
            curl.setopt(pycurl.CAINFO, certifi.where())
            curl.setopt(pycurl.HTTPHEADER, ["PRIVATE-TOKEN: yzAJTSRxGVriiPDiEZ5V"])
            curl.setopt(pycurl.URL, "https://stgit.quectel.com/api/v4/projects/522/repository/archive.zip?sha={}".format(self.branch))
            curl.setopt(pycurl.WRITEDATA, f)
            curl.perform()
            curl.close()
        self.sig.emit()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())