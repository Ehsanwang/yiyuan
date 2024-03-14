import subprocess
import datetime
import os
import signal
import time 

s = subprocess.Popen(['./QLog', '-s', 'dump'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=r'/home/flynn/Downloads/Quectel_QLog_Linux&Android_V1.4.17/QLog')
while True:
    data = s.stdout.readline().decode('utf-8', 'ignore')
    if data:
        print(['at_log', '[{}] [QLOG] {}'.format(datetime.datetime.now(), data)])
    if 'Wait for connect or Press' in data:
        s.send_signal(signal.SIGINT)
        time.sleep(1)
        if s.poll() is None:
            s.terminate()
        s.wait()
        break