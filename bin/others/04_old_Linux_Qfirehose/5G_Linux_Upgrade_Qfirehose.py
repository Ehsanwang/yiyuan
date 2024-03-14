import os, re, datetime, time, sys

sys.path.append(r'..\..\..\lib\Upgrade')
import upgrade_view
import upgrade_method

filename = ""
QFIRHOSE_upgrade_filename = ""
logpath = os.path.dirname(os.path.abspath(__file__))

content_divider = "#################################################"
content_start_time = "Start Time: "
content_end_time = "End Time: "
content_test_type = "Test Type is: "
content_upgrade_mode = "Upgrade Mode is: "
content_upgrade_case = "Upgrade Case is: "
content_upgrade_version_title = "Upgrade Version Below: "
content_upgrade_version_a = "Version A is: "
content_upgrade_version_b = "Version B is: "
content_upgrade_origin_imei = "Origin Imei: "
content_upgrade_get_cfun = "cfun is: "
content_upgrade_get_network = "Network result: "
content_test_platforms = "Tester Platform is: "
content_windows = "Windows"
content_linux = "Linux"
content_test_platforms_unknow = "Unknow"
content_print_to_check = "Please to check below args whether right: "

content_args_title = "Reference Args Below: "
content_modem_port_title = "Modem Port is: "
content_uart_port = "Uart Port is: "
content_dm_port = "DM Port is: "
content_baudrate = "Baudrate is: "
content_stopbits = "Stopbits is: "
content_parity = "Parity is: "
content_bytesize = "Bytesize is: "
content_control_test_type = "Control Test Type is: "
content_whether_test = "Wether Test: "
content_Exit = "Exit!"
content_Start = "Start!"


content_upgrade_success = "Upgrade module successfully"
content_upgrade_unsuccess = "Upgrade module unsuccessfully"
content_modem_communicate_print = "Modem port communicate success"
content_modem_port_check_version_ok = "Modem port check version ok"
content_modem_port_check_version_fail = "Modem port check version fail"
content_modem_port_check_version_fail_veresionis = "Modem port check version fail,version is "
content_modem_port_error_waiting = "Modem port error,waiting ....."
content_waiting_modem_port = "waiting modem port ......."
content_check_imei_ok = "imei check ok"
content_check_imei_fail = "imei check fail"
content_check_imei_fail_imeiis = "imei check fail,imei is "
content_get_cfun = "cfun is: "
content_get_network = "network is: "



content_modem_port = "/dev/ttyUSB2"
content_at_command_check = "AT\r"
content_at_command_version_check = "AT+QGMR?\r"
content_find_modemport_shell = "ls /dev/ttyUSB2"
content_find_dm_shell = "ls /dev/ttyUSB2"

content_set_test_time = "Set Test Time is: "
content_set_test_times = "Set Test Times is: "
content_test_times_done = "Number of arrival tests: "
content_test_time_done = "Test time reached: "

content_test_times_tile = "Test Times is: "
content_test_diff_time_tile = "Diff Time is: "
content_test_upgrade_versiona = "Upgrade Version A now,Version is: "
content_test_upgrade_versionb = "Upgrade Version B now,Version is: "
content_test_upgrade_success = "Upgrade Success"
content_test_upgrade_fail_drive_fail = "Upgrade Fail,Not Find Driver"
content_test_upgrade_fail_modem_communicate_fail = "Upgrade Fail,Modem Port Communicate Fail"

content_upgrade_origin_version_at = "Origin AT version is: "




conten_feature_not_ready = "feature not ready ,please select others"

#vars
test_type = ""
upgrade_mode = ""
upgrade_case = ""
upgrade_control_type = ""
upgrade_test_time = ""
upgrade_test_times = ""
start_time = ""
end_time = ""
version_a = ""
version_b = ""
whether_start_test = ""

origin_imei = ""
net_result = ""
cfun_result = ""
args = []
modem_port = ""
uart_port = ""
dm_port = ""
baudrate = ""
stopbits = ""
parity = ""
bytesize = ""




def init_class():
    global upgrade_method
    global upgrade_view
    upgrade_method = upgrade_method.Method()
    upgrade_view = upgrade_view.View()


def init_source():
    global version_a
    global version_b
    global origin_version_at
    global origin_imei
    global cfun_result
    global net_result
    global platforms
    global modem_port
    global uart_port
    global dm_port
    global baudrate
    global stopbits
    global parity
    global bytesize
    global whether_start_test
    global filename
    global QFIRHOSE_upgrade_filename
    filename = upgrade_method.use_time_to_filename()
    QFIRHOSE_upgrade_filename = upgrade_method.use_time_to_QFIRHOSE_upgrade_filename()
    upgrade_method.write_to_file(logpath, filename, content_divider)
    upgrade_method.write_to_file(logpath, filename, content_test_type + str(test_type))
    upgrade_method.write_to_file(logpath, filename, content_divider)
    upgrade_method.write_to_file(logpath, filename, content_upgrade_mode + str(upgrade_mode))
    upgrade_method.write_to_file(logpath, filename, content_divider)
    upgrade_method.write_to_file(logpath, filename, content_upgrade_case + str(upgrade_case))
    upgrade_method.write_to_file(logpath, filename, content_divider)
    # version is here
    path = os.getcwd()
    # print(path)
    version_a = upgrade_method.get_versionA(path)
    #version_b = upgrade_method.get_versionB(path, version_a)
    version_b = version_a
    upgrade_method.write_to_file(logpath, filename, content_upgrade_version_title)
    upgrade_method.write_to_file(logpath, filename, content_upgrade_version_a + version_a)
    upgrade_method.write_to_file(logpath, filename, content_upgrade_version_b + version_b)
    upgrade_method.write_to_file(logpath, filename, content_divider)
    # get platforms
    platforms = upgrade_method.get_platform()
    # print(platforms)
    if "Windows" in platforms:
        upgrade_method.write_to_file(logpath, filename, content_test_platforms + content_windows)
        upgrade_method.write_to_file(logpath, filename, content_divider)
    elif "Ubuntu" in platforms:
        upgrade_method.write_to_file(logpath, filename, content_test_platforms + content_linux)
        upgrade_method.write_to_file(logpath, filename, content_divider)
    else:
        upgrade_method.write_to_file(logpath, filename, content_test_platforms + content_test_platforms_unknow)
        upgrade_method.write_to_file(logpath, filename, content_divider)
    # get default args
    args = upgrade_method.get_default_args()
    # print(args)
    if "Windows" in platforms:
        modem_port_input = upgrade_method.get_windows_modemport_input()
        if "com" in modem_port_input:
            modem_port = modem_port_input
        elif "COM" in modem_port_input:
            modem_port = modem_port_input
        else:
            modem_port = "com"+modem_port_input
        uart_port = upgrade_method.get_9091_port()
    elif "Ubuntu" in platforms:
        modem_port = args[0]
        uart_port = args[1]
    else:
        upgrade_method.write_to_file(logpath, filename, content_test_platforms + content_test_platforms_unknow)
    dm_port = args[2]
    baudrate = args[3]
    stopbits = args[4]
    parity = args[5]
    bytesize = args[6]
    # print(content_args_title)
    # print(content_modem_port + modem_port)
    # print(content_uart_port + uart_port)
    # print(content_dm_port + dm_port)
    # print(content_baudrate + str(baudrate))
    # print(content_stopbits + str(stopbits))
    # print(content_parity + parity)
    # print(content_bytesize + str(bytesize))
    upgrade_method.write_to_file(logpath, filename, content_args_title)
    upgrade_method.write_to_file(logpath, filename, content_modem_port_title +modem_port)
    upgrade_method.write_to_file(logpath, filename, content_uart_port + uart_port)
    upgrade_method.write_to_file(logpath, filename, content_dm_port + dm_port)
    upgrade_method.write_to_file(logpath, filename, content_baudrate + str(baudrate))
    upgrade_method.write_to_file(logpath, filename, content_stopbits + str(stopbits))
    upgrade_method.write_to_file(logpath, filename, content_parity + parity)
    upgrade_method.write_to_file(logpath, filename, content_bytesize + str(bytesize))
    upgrade_method.write_to_file(logpath, filename, content_divider)

    # get version_at
    origin_version_at = upgrade_method.get_version(modem_port)
    upgrade_method.write_to_file(logpath, filename, content_upgrade_origin_version_at + origin_version_at)
    upgrade_method.write_to_file(logpath, filename, content_divider)
    # get imei
    origin_imei = upgrade_method.get_imei(modem_port)
    upgrade_method.write_to_file(logpath, filename, content_upgrade_origin_imei + origin_imei)
    upgrade_method.write_to_file(logpath, filename, content_divider)
    # get cfun
    cfun_result = upgrade_method.get_cfun(modem_port)
    upgrade_method.write_to_file(logpath, filename, content_upgrade_get_cfun + cfun_result)
    upgrade_method.write_to_file(logpath, filename, content_divider)
    # get network
    net_result = upgrade_method.get_network(modem_port)
    upgrade_method.write_to_file(logpath, filename, content_upgrade_get_network + str(net_result))
    upgrade_method.write_to_file(logpath, filename, content_divider)

    #upgrade test type : time or times or keep running
    upgrade_method.write_to_file(logpath, filename, content_control_test_type + str(upgrade_control_type))
    if upgrade_control_type == "1":
        upgrade_method.write_to_file(logpath, filename, content_set_test_time + upgrade_test_time)
        upgrade_method.write_to_file(logpath, filename, content_divider)
    elif upgrade_control_type == "2":
        upgrade_method.write_to_file(logpath, filename, content_set_test_times + upgrade_test_times)
        upgrade_method.write_to_file(logpath, filename, content_divider)
    # start time
    start_time = upgrade_method.get_date_time_now()
    upgrade_method.write_to_file(logpath, filename, content_start_time + start_time)
    upgrade_method.write_to_file(logpath, filename, content_divider)
    #args check
    print_to_check()
    #get args check result
    whether_start_test = upgrade_view.get_args_check_result()
    if whether_start_test == "y":
        print(content_Start)
    elif whether_start_test == "n":
        print(content_Exit)
    else:
        print(content_Exit)




def print_to_check():
    print(content_divider)
    print(content_print_to_check)
    print(content_divider)
    print(content_test_type+str(test_type))
    print(content_divider)
    print(content_upgrade_mode + str(upgrade_mode))
    print(content_divider)
    print(content_upgrade_case + str(upgrade_case))
    print(content_divider)
    print(content_upgrade_version_title+version_a+" "+version_b)
    print(content_divider)
    print(content_upgrade_origin_version_at + origin_version_at)
    print(content_divider)
    print(content_upgrade_origin_imei + origin_imei)
    print(content_divider)
    print(content_upgrade_get_cfun + cfun_result)
    print(content_divider)
    print(content_upgrade_get_network + str(net_result))
    print(content_divider)
    print(content_test_platforms+platforms)
    print(content_divider)
    print(content_args_title)
    print(content_modem_port_title + modem_port)
    print(content_uart_port + uart_port)
    print(content_dm_port + dm_port)
    print(content_baudrate + str(baudrate))
    print(content_stopbits + str(stopbits))
    print(content_parity + parity)
    print(content_bytesize + str(bytesize))
    print(content_divider)
    print(content_control_test_type + str(upgrade_control_type))
    if upgrade_control_type == "1":
        print(content_set_test_time + upgrade_test_time)
    elif upgrade_control_type == "2":
        print(content_set_test_times + upgrade_test_times)
    print(content_divider)




def upgrade(version):
    result_versiona_check = ""
    result_versiona = upgrade_method.upgrade_version(version)
    result_versiona_check = upgrade_method.check_upgrade_result(result_versiona)
    if result_versiona_check == 0:
        upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_upgrade_success)
        print(content_upgrade_success)
    elif result_versiona_check == 1:
        upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_upgrade_unsuccess)
        print(content_upgrade_unsuccess)
    upgrade_method.write_to_file(logpath, QFIRHOSE_upgrade_filename, content_divider)
    upgrade_method.write_to_file(logpath, QFIRHOSE_upgrade_filename, content_test_times_tile + str(test_times_origin))
    upgrade_method.write_to_file(logpath, QFIRHOSE_upgrade_filename, result_versiona)
    for i in range(119):
        time.sleep(1)
        result_find_modem_port = upgrade_method.send_shell(content_find_modemport_shell)
        if result_find_modem_port == 0:
            break
        else:
            print(content_waiting_modem_port)
            if i == 119:
                upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_test_upgrade_fail_drive_fail)
    for i in range(119):
        time.sleep(1)
        result_check_at = upgrade_method.check_at(modem_port, content_at_command_check)
        if result_check_at == 0:
            print(content_modem_communicate_print)
            upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_test_upgrade_success)
            break
        elif result_check_at == 1:
            print(content_modem_port_error_waiting)
            if i == 119:
                upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_test_upgrade_fail_modem_communicate_fail)
    for i in range(30):
        time.sleep(1)
        result_check_version_at = upgrade_method.check_version(modem_port, origin_version_at)
        if 0 == result_check_version_at:
            print(content_modem_port_check_version_ok)
            upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_modem_port_check_version_ok)
            break
        else:
            if i == 29:
                print(content_modem_port_check_version_fail)
                upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now()) + "\t" + content_modem_port_check_version_fail)
                upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now()) + "\t" + content_modem_port_check_version_fail_veresionis + result_check_version_at)
    for i in range(30):
        time.sleep(1)
        result_imei_check = upgrade_method.check_imei(modem_port, origin_imei)
        if 0 == result_imei_check:
            print(content_check_imei_ok)
            upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_check_imei_ok)
            break
        else:
            if i == 29:
                print(content_check_imei_fail)
                upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now()) + "\t" + content_modem_port_check_version_fail)
                upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now()) + "\t" + content_check_imei_fail_imeiis + result_imei_check)

    for i in range(30):
        time.sleep(1)
        result_cfun = upgrade_method.get_cfun(modem_port)
        if "CFUN" in result_cfun:
            print(content_get_cfun + result_cfun)
            upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_get_cfun + result_cfun)
            break
        else:
            if i == 29:
                print(content_get_cfun + result_cfun)
                upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now()) + "\t" + content_get_cfun + result_cfun)
            pass
    for i in range(30):
        time.sleep(1)
        result_network = upgrade_method.get_network(modem_port)
        if "CREG" in result_network[1]:
            print(content_get_network + str(result_network))
            upgrade_method.write_to_file(logpath, filename, str(datetime.datetime.now())+"\t"+content_get_network + str(result_network))
            break
        else:
            if i == 29:
                print(content_get_network + str(result_network))
                upgrade_method.write_to_file(logpath, filename,
                                             str(datetime.datetime.now()) + "\t" + content_get_network + str(
                                                 result_network))
            pass





def upgrade_process():
    version = "a"
    global test_times_origin
    test_times_origin = 0
    if upgrade_control_type == "2":
        while True:
            time.sleep(1)
            test_times_origin += 1
            if test_times_origin > int(upgrade_test_times):
                print(content_test_times_done+str(test_times_origin-1))
                upgrade_method.write_to_file(logpath, filename, content_test_times_done + str(test_times_origin-1))
                end_time = upgrade_method.get_date_time_now()
                upgrade_method.write_to_file(logpath, filename, content_divider)
                upgrade_method.write_to_file(logpath, filename, content_end_time + end_time)
                upgrade_method.write_to_file(logpath, filename, content_divider)
                return 
            else:
                upgrade_method.write_to_file(logpath, filename, content_test_times_tile + str(test_times_origin))
                print(content_test_times_tile+str(test_times_origin))
                if version == "a":
                    version = "b"
                    print(content_test_upgrade_versiona + version_a)
                    upgrade_method.write_to_file(logpath, filename, content_test_upgrade_versiona + version_a)
                    upgrade(version_a)
                    time.sleep(3)
                elif version == "b":
                    version = "a"
                    print(content_test_upgrade_versionb + version_b)
                    upgrade_method.write_to_file(logpath, filename, content_test_upgrade_versionb + version_b)
                    upgrade(version_b)
                    time.sleep(3)
    elif upgrade_control_type == "1":
        time_start = upgrade_method.get_time_ticks()
        while True:
            time.sleep(1)
            test_times_origin += 1
            time_now = upgrade_method.get_time_ticks()
            diff_time = time_now - time_start
            if diff_time > int(upgrade_test_time):
                print(content_test_times_done + str(test_times_origin - 1))
                upgrade_method.write_to_file(logpath, filename, content_test_times_done + str(test_times_origin - 1))
                print(content_test_time_done + str(diff_time))
                upgrade_method.write_to_file(logpath, filename, content_test_time_done + str(diff_time))
                end_time = upgrade_method.get_date_time_now()
                upgrade_method.write_to_file(logpath, filename, content_divider)
                upgrade_method.write_to_file(logpath, filename, content_end_time + end_time)
                upgrade_method.write_to_file(logpath, filename, content_divider)
                return 
            else:
                upgrade_method.write_to_file(logpath, filename, content_test_times_tile + str(test_times_origin))
                print(content_test_times_tile + str(test_times_origin))
                upgrade_method.write_to_file(logpath, filename, content_test_diff_time_tile + str(diff_time))
                print(content_test_diff_time_tile + str(diff_time))
                if version == "a":
                    version = "b"
                    print(content_test_upgrade_versiona + version_a)
                    upgrade_method.write_to_file(logpath, filename, content_test_upgrade_versiona + version_a)
                    upgrade(version_a)
                    time.sleep(3)
                elif version == "b":
                    version = "a"
                    print(content_test_upgrade_versionb + version_b)
                    upgrade_method.write_to_file(logpath, filename, content_test_upgrade_versionb + version_b)
                    upgrade(version_b)
                    time.sleep(3)
    elif upgrade_control_type == "3":
        while True:
            time.sleep(1)
            test_times_origin += 1
            upgrade_method.write_to_file(logpath, filename, content_test_times_tile + str(test_times_origin))
            print(content_test_times_tile + str(test_times_origin))
            if version == "a":
                 version = "b"
                 print(content_test_upgrade_versiona + version_a)
                 upgrade_method.write_to_file(logpath, filename, content_test_upgrade_versiona + version_a)
                 upgrade(version_a)
                 time.sleep(3)
            elif version == "b":
                 version = "a"
                 print(content_test_upgrade_versionb + version_b)
                 upgrade_method.write_to_file(logpath, filename, content_test_upgrade_versionb + version_b)
                 upgrade(version_b)
                 time.sleep(3)
        



def main():
    while True:
        upgrade_view.printmenu()
        global test_type
        test_type = upgrade_view.get_testtype_input()
        if test_type == "1":
            upgrade_view.print_upgrade_mode()
            global upgrade_mode
            upgrade_mode = upgrade_view.get_upgrademode_input()
            if upgrade_mode == "1":
                upgrade_view.print_upgrade_case()
                global upgrade_case
                upgrade_case = upgrade_view.get_upgrade_case_input()
                if upgrade_case == "1":
                    upgrade_view.print_test_control_type()
                    global upgrade_control_type
                    upgrade_control_type = upgrade_view.get_test_control_type()
                    if upgrade_control_type == "-1":
                        break
                    elif upgrade_control_type == "1": #time
                        upgrade_view.print_test_time_set()
                        global upgrade_test_time
                        upgrade_test_time = upgrade_view.get_test_time()
                        init_source()
                        if whether_start_test == "y":
                            upgrade_process()
                        elif whether_start_test == "n":
                            break
                        else:
                            break
                        break
                    elif upgrade_control_type == "2": #times
                        upgrade_view.print_test_times_set()
                        global upgrade_test_times
                        upgrade_test_times = upgrade_view.get_test_times()
                        init_source()
                        if whether_start_test == "y":
                            upgrade_process()
                        elif whether_start_test == "n":
                            break
                        else:
                            break
                        break
                    elif upgrade_control_type == "3": #keep running
                        init_source()
                        if whether_start_test == "y":
                            upgrade_process()
                        elif whether_start_test == "n":
                            break
                        else:
                            break
                        break
                    else:
                        print(conten_feature_not_ready)
                elif upgrade_case == "-1":
                    break
                else:
                    print(conten_feature_not_ready)
            elif upgrade_mode == "-1":
                break
            else:
                print(conten_feature_not_ready)
        elif test_type == "-1":
            break
        else:
            print(conten_feature_not_ready)





if __name__ == '__main__':
    init_class()
    main()

