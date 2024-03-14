问题验证脚本

# 基本内容

## 提前设置的命令
```text
AT+QPCMV=1,0
```

## DUMP不重启

```text
at+qcfg="aprstlevel",0
at+qcfg="modemrstlevel",0
```

## 进入DUMP

```text
at+qtest="dump",1
```

## QLog抓取log

```text
./QLog -s dump
```

## 获取对应端口号详情
```bash
udevadm info --attribute-walk --path=$(udevadm info --query=path --name=/dev/ttyUSB3) | grep ATTRS{bInterfaceNumber}
```

## 修改端口映射
```text
vim /etc/udev/rules.d/99-usb-serial.rules
```