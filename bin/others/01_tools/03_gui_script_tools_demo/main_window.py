# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'main_window.ui'
#
# Created by: PyQt5 UI code generator 5.14.2
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(924, 508)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.group_box_script_select = QtWidgets.QGroupBox(self.centralwidget)
        self.group_box_script_select.setGeometry(QtCore.QRect(30, 10, 571, 61))
        self.group_box_script_select.setObjectName("group_box_script_select")
        self.label_branch = QtWidgets.QLabel(self.group_box_script_select)
        self.label_branch.setGeometry(QtCore.QRect(20, 22, 54, 20))
        self.label_branch.setObjectName("label_branch")
        self.combo_box_branch_name = QtWidgets.QComboBox(self.group_box_script_select)
        self.combo_box_branch_name.setGeometry(QtCore.QRect(60, 20, 141, 22))
        self.combo_box_branch_name.setObjectName("combo_box_branch_name")
        self.label_script_name = QtWidgets.QLabel(self.group_box_script_select)
        self.label_script_name.setGeometry(QtCore.QRect(220, 20, 54, 21))
        self.label_script_name.setObjectName("label_script_name")
        self.combo_box_script_name = QtWidgets.QComboBox(self.group_box_script_select)
        self.combo_box_script_name.setGeometry(QtCore.QRect(280, 20, 281, 22))
        self.combo_box_script_name.setObjectName("combo_box_script_name")
        self.group_box_status = QtWidgets.QGroupBox(self.centralwidget)
        self.group_box_status.setGeometry(QtCore.QRect(630, 10, 271, 61))
        self.group_box_status.setObjectName("group_box_status")
        self.lcd_runtimes = QtWidgets.QLCDNumber(self.group_box_status)
        self.lcd_runtimes.setGeometry(QtCore.QRect(130, 20, 121, 31))
        self.lcd_runtimes.setObjectName("lcd_runtimes")
        self.label_script_status = QtWidgets.QLabel(self.group_box_status)
        self.label_script_status.setGeometry(QtCore.QRect(40, 20, 71, 31))
        self.label_script_status.setAlignment(QtCore.Qt.AlignCenter)
        self.label_script_status.setObjectName("label_script_status")
        self.group_box_para_set = QtWidgets.QGroupBox(self.centralwidget)
        self.group_box_para_set.setGeometry(QtCore.QRect(30, 100, 271, 371))
        self.group_box_para_set.setObjectName("group_box_para_set")
        self.group_box_dos_log = QtWidgets.QGroupBox(self.centralwidget)
        self.group_box_dos_log.setGeometry(QtCore.QRect(330, 100, 571, 281))
        self.group_box_dos_log.setObjectName("group_box_dos_log")
        self.text_edit_dos_log = QtWidgets.QTextEdit(self.group_box_dos_log)
        self.text_edit_dos_log.setGeometry(QtCore.QRect(10, 40, 261, 231))
        self.text_edit_dos_log.setObjectName("text_edit_dos_log")
        self.label = QtWidgets.QLabel(self.group_box_dos_log)
        self.label.setGeometry(QtCore.QRect(20, 20, 54, 12))
        self.label.setObjectName("label")
        self.label_2 = QtWidgets.QLabel(self.group_box_dos_log)
        self.label_2.setGeometry(QtCore.QRect(310, 20, 71, 16))
        self.label_2.setObjectName("label_2")
        self.text_edit_cmd_window = QtWidgets.QTextEdit(self.group_box_dos_log)
        self.text_edit_cmd_window.setGeometry(QtCore.QRect(300, 40, 261, 231))
        self.text_edit_cmd_window.setObjectName("text_edit_cmd_window")
        self.group_box_control_pannel = QtWidgets.QGroupBox(self.centralwidget)
        self.group_box_control_pannel.setGeometry(QtCore.QRect(330, 400, 571, 71))
        self.group_box_control_pannel.setObjectName("group_box_control_pannel")
        self.button_start = QtWidgets.QPushButton(self.group_box_control_pannel)
        self.button_start.setGeometry(QtCore.QRect(20, 20, 91, 31))
        self.button_start.setObjectName("button_start")
        self.button_end = QtWidgets.QPushButton(self.group_box_control_pannel)
        self.button_end.setGeometry(QtCore.QRect(130, 20, 91, 31))
        self.button_end.setObjectName("button_end")
        self.button_reset = QtWidgets.QPushButton(self.group_box_control_pannel)
        self.button_reset.setGeometry(QtCore.QRect(240, 20, 91, 31))
        self.button_reset.setObjectName("button_reset")
        self.button_open_log_dir = QtWidgets.QPushButton(self.group_box_control_pannel)
        self.button_open_log_dir.setGeometry(QtCore.QRect(350, 20, 91, 31))
        self.button_open_log_dir.setObjectName("button_open_log_dir")
        self.button_open_script_raw = QtWidgets.QPushButton(self.group_box_control_pannel)
        self.button_open_script_raw.setGeometry(QtCore.QRect(460, 20, 91, 31))
        self.button_open_script_raw.setObjectName("button_open_script_raw")
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 924, 23))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusBar = QtWidgets.QStatusBar(MainWindow)
        self.statusBar.setObjectName("statusBar")
        MainWindow.setStatusBar(self.statusBar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.group_box_script_select.setTitle(_translate("MainWindow", "选择脚本"))
        self.label_branch.setText(_translate("MainWindow", "分支:"))
        self.label_script_name.setText(_translate("MainWindow", "脚本名称:"))
        self.group_box_status.setTitle(_translate("MainWindow", "运行次数"))
        self.label_script_status.setText(_translate("MainWindow", "未开始"))
        self.group_box_para_set.setTitle(_translate("MainWindow", "参数设置"))
        self.group_box_dos_log.setTitle(_translate("MainWindow", "运行状态"))
        self.label.setText(_translate("MainWindow", "Dos log:"))
        self.label_2.setText(_translate("MainWindow", "CMD Window"))
        self.group_box_control_pannel.setTitle(_translate("MainWindow", "控制台"))
        self.button_start.setText(_translate("MainWindow", "运行脚本"))
        self.button_end.setText(_translate("MainWindow", "结束脚本"))
        self.button_reset.setText(_translate("MainWindow", "重置脚本"))
        self.button_open_log_dir.setText(_translate("MainWindow", "打开Log文件夹"))
        self.button_open_script_raw.setText(_translate("MainWindow", "打开脚本文件"))
