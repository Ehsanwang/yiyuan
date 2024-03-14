import sys
import struct
import pkg_resources
import os
import subprocess

# 脚本依赖的PIP包名称，一行一个，如果新增则添加
REQUIRE = """
    pandas
    pyserial
    requests
    requests-toolbelt
    aioftp
"""


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
    env_pip_list = [p.project_name for p in pkg_resources.working_set]  # 获取当前Python环境的pip包
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


if __name__ == '__main__':
    pause()
    environment_check()
