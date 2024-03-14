import os, re,datetime,time
import serial
import serial.tools.list_ports
import subprocess

logpath = os.path.dirname(os.path.abspath(__file__))

filename = 'yikuaiqian.txt'

# menu page items
menu_1 = "1. Upgrade Test"
menu_2 = "2. NDIS Test"
menu_3 = "3. GobiNet Test"
menu_4 = "4. Other Test"
menu_5 = "-1. Exit"
menu_6 = "Please ENTER your CHOICE:"
# upgrade mode items
upgrade_mode_1 = "1. FASTBOOT"
upgrade_mode_2 = "2. SAHARA"
upgrade_mode_3 = "3. FASTBOOT_WITH_AT_FIRST"
upgrade_mode_4 = "4. FIREHOSE"
upgrade_mode_5 = "-1. Exit"
upgrade_mode_6 = "Please ENTER your CHOICE:"
# upgrade case items
upgrade_case_1 = "1. Upgrade normal"
upgrade_case_2 = "2. Upgrade poweroff after random duration"
upgrade_case_3 = "3. Upgrade poweroff after fixed duration"
upgrade_case_4 = "-1. Exit"
upgrade_case_5 = "Please ENTER your CHOICE:"
#upgrade test control items
upgrade_test_control_type_1 = "1. Use Time"
upgrade_test_control_type_2 = "2. Use Times"
upgrade_test_control_type_3 = "3. Keep Running"
upgrade_test_control_type_4 = "-1. Exit"
#upgrade test time set
content_test_time_set = "Please input test time your want (second): "
content_test_times_set = "Please input test times your want (ex:200): "
#args check
content_get_args_check_result = "Do you want to start test? please input y/n : "


# main test select page
menu = ["#---->", menu_1, menu_2, menu_3, menu_4, menu_5, menu_6]
# upgrade mode select page
upgrade_mode = ["#---->", upgrade_mode_1, upgrade_mode_2, upgrade_mode_3, upgrade_mode_4, upgrade_mode_5, upgrade_mode_6]
# upgrade case select page
upgrade_case = ["#---->", upgrade_case_1, upgrade_case_2, upgrade_case_3, upgrade_case_4, upgrade_case_5]
#upgrade test control type
upgrade_test_control_type = ["#---->", upgrade_test_control_type_1, upgrade_test_control_type_2, upgrade_test_control_type_3, upgrade_test_control_type_4]




ii = len(menu)
iii = len(upgrade_mode)
iiii = len(upgrade_case)
iiiii = len(upgrade_test_control_type)

class View(object):
    def __init__(self):
        super(View, self).__init__()

    def printmenu(self):
        for i in range(ii):
            print(menu[i])

    def get_testtype_input(self):
        test_type = input()
        if test_type == "1":
            print("You Select Upgrade Test !")
        elif test_type == "2":
            print("You Select NDIS Test !")
        elif test_type == "3":
            print("You Select GobiNet Test !")
        elif test_type == "4":
            print("You Select Other Test !")
        elif test_type == "-1":
            print("Exit !")
        elif test_type == "":
            print("You Select nothing !")
        return test_type

    def print_upgrade_mode(self):
        for i in range(iii):
            print(upgrade_mode[i])

    def get_upgrademode_input(self):
        upgrade_mode_type = input()
        if upgrade_mode_type == "1":
            print("You Select FASTBOOT !")
        elif upgrade_mode_type == "2":
            print("You Select SAHARA !")
        elif upgrade_mode_type == "3":
            print("You Select FASTBOOT_WITH_AT_FIRST !")
        elif upgrade_mode_type == "4":
            print("You Select FIREHOSE !")
        elif upgrade_mode_type == "-1":
            print("Exit !")
        elif upgrade_mode_type == "":
            print("You Select nothing !")
        return upgrade_mode_type

    def get_upgrade_timeout(self, upgrade_type):
        self.upgrade_type = upgrade_type
        upgrade_timeout = 600000
        if upgrade_type == "1":
            upgrade_timeout = 100000
        elif upgrade_type == "2":
            upgrade_timeout = 600000
        elif upgrade_type == "3":
            upgrade_timeout = 100000
        elif upgrade_type == "4":
            upgrade_timeout = 100000
        return upgrade_timeout

    def print_upgrade_case(self):
        for i in range(iiii):
            print(upgrade_case[i])

    def get_upgrade_case_input(self):
        upgrade_case = input()
        if upgrade_case == "1":
            print("You Select Upgrade normal !")
        elif upgrade_case == "2":
            print("You Select Upgrade poweroff after random duration !")
        elif upgrade_case == "3":
            print("You Select Upgrade poweroff after fixed duration !")
        elif upgrade_case == "4":
            print("You Select back to main menu !")
        elif upgrade_case == "-1":
            print("Exit !")
        elif upgrade_case == "":
            print("You Select nothing !")
        return upgrade_case

    def print_test_control_type(self):
        for i in range(iiiii):
            print(upgrade_test_control_type[i])

    def print_test_time_set(self):
        print(content_test_time_set)

    def print_test_times_set(self):
        print(content_test_times_set)

    def get_test_control_type(self):
        test_control_type = input()
        if test_control_type == "1":
            print("You Select Use Time to Control Test process !")
        elif test_control_type == "2":
            print("You Select Use Times to Control Test process !")
        return test_control_type
    
    def get_test_time(self):
        test_time = input()
        return test_time
    
    def get_test_times(self):
        test_times = input()
        return test_times
    
    def get_args_check_result(self):
        print(content_get_args_check_result)
        get_args_check_result = input()
        return get_args_check_result
        

  





