客户问题验证脚本：

模块开机注册NSA网络成功后，静止，然后一直执行AT+CGPADDR查询获取的IP地址，当IP地址不存在或者发生改变的时候，模块去执行AT+CFUN=4&AT+CFUN=1。

https://stgit.quectel.com/5G-SDX55/Standard/issues/139