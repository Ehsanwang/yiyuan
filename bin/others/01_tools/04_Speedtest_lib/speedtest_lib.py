import logging
import datetime
import math
import os
import platform
import re
import socket
import timeit
import xml.etree.ElementTree as ET
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from threading import Lock


class GetConfigError(Exception):
    """Fail to get config"""


class GetServerError(Exception):
    """Fail to get server"""


def build_request_para(url: str, headers: dict = None, secure: bool = False, data: str = None) -> dict:
    """
    Build speedtest recognized url.
    :param url: url
    :param headers: user-agent
    :param secure: False: HTTP; True: HTTPS
    :param data: post data
    :return: requests para dict.
    """
    # rebuild url
    if url.startswith(":"):
        protocol = 'https' if secure else 'http'
        protocol_url = "{}{}".format(protocol, url)
    else:
        protocol_url = url
    if '?' in url:
        sep = '&'
    else:
        sep = '?'
    url = '{protocol}{sep}x={x}.{tail}'.format(protocol=protocol_url, sep=sep, x=int(time.time()*1000), tail=0)

    # rebuild headers
    headers = headers or {}
    headers.update({
        'Cache-Control': 'no-cache',
    })

    # fill into dict and return distance(kilometer)
    params = dict()
    params.update({'url': url})
    params.update({'headers': headers})
    params.update({'data': data})
    return params


def distance(origin: tuple = (float, float), destination:  tuple = (float, float)) -> float:
    """
    >>> distance((31.8642, 117.2865),(24.1500, 120.6667))
    919.5606576575959

    Calc distance via latitude and longitude.
    :param origin: tuple or list like (31.8642, 117.2865)
    :param destination: same as origin
    :return: kilometer(float)
    """
    lat1, lon1 = origin
    lat2, lon2 = destination
    radius = 6371  # km

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) * math.sin(d_lat / 2) +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) * math.sin(d_lon / 2) *
         math.sin(d_lon / 2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    d = radius * c
    return d


def gen(lst):
    while True:
        for i in lst:
            yield i


class Speedtest:
    def __init__(self, log_queue, runtimes):
        # init some param
        self.lat_lon = ()
        self.config = {}
        self.servers = {}
        self._best = {}
        self.closest = []
        self.debug = True
        self.runtimes = runtimes

        # 结果统计
        self.result = dict()
        # "server": '',  # server信息
        # "latency": '',  # 服务器的延迟信息 (ms)
        # "download": '',  # 下载速度
        # "download_total": '',  # 下载流量数量
        # "upload": '',  # 上传速度
        # "upload_total": "",  # 上传数据量

        # 初始化logger
        self.log_queue = log_queue
        self.logger = logging.getLogger(__name__)

        # init download and upload para
        self.download_flag = True
        self.download_length = 0
        self.download_error_package = 0
        self.upload_length = 0

        # get config and servers
        self.get_config()
        self.get_best_server()

    def get_config(self):
        self.logger.info("Speedtest: get config.")
        headers = dict()
        headers['Accept-Encoding'] = 'gzip'
        headers['user-agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHT" \
                                "ML, like Gecko) Chrome/86.0.4240.75 Safari/537.36"
        paras = build_request_para(url='://www.speedtest.net/speedtest-config.php', headers=headers)

        times = 10
        for i in range(times):
            try:
                self.logger.info("Speedtest: get config from http://www.speedtest.net/speedtest-config.php.")
                config_xml = requests.get(**paras, timeout=3).content

                self.logger.info("Speedtest: get ip address from https://ip.tool.chinaz.com/.")
                r = requests.get("https://ip.tool.chinaz.com/", headers=headers, timeout=3)
                ip_address = ''.join(re.findall(r'WhoIpWrap jspu[\s|\S]*?</div', r.text))
                address = ''.join(re.findall("<span.*?>(.*?)</span>", ip_address)[-1])
                self.logger.info("Speedtest: ip and address:{}.".format(ip_address))

                self.logger.info("Speedtest: get config from baidu api.")
                r = requests.get("http://api.map.baidu.com/geocoder?output=json&address={}".format(address),
                                 headers=headers, timeout=3)
                api_lat_lon = (r.json()['result']['location']['lat'], r.json()['result']['location']['lng'])
                break
            except (socket.error, requests.exceptions.RequestException, json.decoder.JSONDecodeError):
                continue
        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 连续{}次获取Speedtest配置文件失败'.format(datetime.datetime.now(), self.runtimes, times)])
            return False

        self.logger.info("Speedtest: Parse speedtest xml content.")
        try:
            root = ET.fromstring(config_xml)
        except ET.ParseError:
            self.log_queue.put(['all', '[{}] runtimes:{} 解析Speedtest Config XML内容失败.'.format(datetime.datetime.now(), self.runtimes)])
            return False

        server_config = root.find('server-config').attrib
        client = root.find('client').attrib

        ignore_servers = [int(server) for server in server_config['ignoreids'].split(',')]

        sizes = {
            'upload': [32768, 65536, 131072, 262144, 524288, 1048576, 7340032],
            'download': [350, 500, 750, 1000, 1500, 2000, 2500, 3000, 3500, 4000]
        }

        threads = {
            'upload': int(server_config['threadcount']) * 2,
            'download': int(server_config['threadcount']) * 2
        }

        self.config.update({
            'client': client,
            'ignore_servers': ignore_servers,
            'sizes': sizes,
            'threads': threads,
        })

        self.logger.info("Speedtest: Calc latitude and longitude.")
        try:
            self.lat_lon = (float(client['lat']), float(client['lon']))
            if distance(self.lat_lon, api_lat_lon) > 100:
                self.lat_lon = api_lat_lon
        except ValueError:
            self.log_queue.put(['all', '[{}] runtimes:{} Undefined location: lat:{} lon:{}'.format(datetime.datetime.now(), self.runtimes, client.get('lat'), client.get('lon'))])
            return False

        self.logger.info("Config: {}".format(self.config))
        return self.config

    def get_servers(self):
        self.logger.info("Speedtest: get servers.")
        urls = [
            '://www.speedtest.net/speedtest-servers-static.php',
            'http://c.speedtest.net/speedtest-servers-static.php',
            '://www.speedtest.net/speedtest-servers.php',
            'http://c.speedtest.net/speedtest-servers.php',
        ]

        headers = dict()
        headers['Accept-Encoding'] = 'gzip'
        for url in urls:
            url = build_request_para(url)
            try:
                r = requests.get(**url)
            except requests.exceptions.RequestException:
                continue
            response = r.content

            try:
                root = ET.fromstring(response)
            except ET.ParseError:
                continue

            servers = ET.Element.iter(root, 'server')

            for server in servers:
                server_attrib = server.attrib
                if int(server_attrib.get('id')) in self.config['ignore_servers']:
                    continue
                d = round(distance(self.lat_lon, (float(server_attrib.get('lat')), float(server_attrib.get('lon')))), 2)

                ############################
                # 调试代码
                if self.debug:
                    if server_attrib.get('id') == "13704":  # 13407被公司内网屏蔽
                        continue
                ############################

                server_attrib['d'] = d
                self.servers[d] = server_attrib

            break

        else:
            self.log_queue.put(['all', '[{}] runtimes:{} 获取服务器列表失败.'.format(datetime.datetime.now(), self.runtimes)])
            return False

    def url_latency(self, headers, server_url):
        self.logger.info("Speedtest: get url latency.")
        try:
            server, url = server_url.split('~')
            t = requests.get(url, headers=headers).elapsed.total_seconds()
        except (requests.exceptions.RequestException, socket.error):
            return ['0000', 3600]
        return [server, t]

    def get_best_server(self, limit=5):
        self.logger.info("Speedtest: get best server.")
        if not self.servers:
            self.get_servers()
        # get closest limit servers
        servers = [i[1] for i in sorted(zip(self.servers.keys(), self.servers.values()))][:limit]
        # build latency url
        urls = []
        for server in servers:
            base_url = os.path.dirname(server['url'])
            timestamp = int(timeit.time.time() * 1000)
            latency_url = '{}/latency.txt?x={}'.format(base_url, timestamp)
            latency_urls = ['{}~{}{}'.format(server['id'], latency_url, num) for num in range(0, 5)]
            urls.extend(latency_urls)

        # User-Agent
        ua_tuple = (
            'Mozilla/5.0',
            '(%s; U; %s; en-us)' % (platform.platform(),
                                    platform.architecture()[0]),
            'Python/%s' % platform.python_version(),
            '(KHTML, like Gecko)'
        )
        headers = {'User-Agent': ' '.join(ua_tuple)}

        # ping urls and get lowest latency server and update to self._best
        latency_results = dict()
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_url = {executor.submit(self.url_latency, headers, url): url for url in urls}
            for future in as_completed(future_to_url):
                server_id, last_time = future.result()
                if server_id not in latency_results.keys():
                    latency_results[server_id] = list()
                latency_results[server_id].append(last_time)
        for k, v in latency_results.items():
            latency_results[k] = sum(v) / len(v)
        self.result.update({'latency': round(float(list(latency_results.values())[0] * 1000), 1)})
        # get like this {'11707': 0.3905054, '17204': 0.4650308000000001}
        min_latency_id = min(sorted(zip(latency_results.values(), latency_results.keys())))[1]
        for server in servers:
            if min_latency_id in server.values():
                self._best.update(server)
                self.result.update({"server": '{sponsor}-{id}-{host}-{distance}km'.format(sponsor=self._best['sponsor'], id=self._best['id'], host=self._best['host'], distance=self._best['d'])})
                return True

    @staticmethod
    def progress_bar(start, end, transmitted, start_time):
        percent = int(start / end * 100)
        speed = str(round(((transmitted / 1000 / 1000 / (timeit.default_timer() - start_time)) * 8.0), 2))
        print("\r{:^3}% [{}{}] {:>4}.{:<2} Mbps".format(percent, percent * '#', (100 - percent) * '-', speed.split('.')[0], speed.split('.')[1]), end='')

    def url_get(self, url):
        download = 0
        try:
            r = requests.get(**build_request_para(url), stream=True)
            for line in r.iter_content(chunk_size=512):
                if self.download_flag is False:
                    r.close()
                    return
                elif line:
                    line_len = len(line)
                    download += line_len
                    with Lock():
                        self.download_length += line_len
            self.download_error_package += (int(r.headers['Content-Length']) - download)
            if self.download_error_package != 0:
                print("download_error_package", self.download_error_package)
        except requests.exceptions.RequestException as e:
            self.log_queue.put(['all', '[{}] runtimes:{} GET "{}" 异常:{}.'.format(datetime.datetime.now(), self.runtimes, build_request_para(url)["url"], e)])

    def download(self):
        self.logger.info("Speedtest: download.")
        urls = []
        download_jpg_size = self.config['sizes']['download']
        for size in download_jpg_size:
            urls.append('%s/random%sx%s.jpg' % (os.path.dirname(self._best['url']), size, size))
        urls = sorted(urls)
        max_threads = self.config['threads']['download']

        self.download_flag = True
        self.download_length = 0
        self.download_error_package = 0
        start_time = timeit.default_timer()
        url_gen = gen(urls)
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_url = {executor.submit(self.url_get, url) for url in urls}
            while True:
                time.sleep(0.1)
                already_done = set(f for f in future_to_url if f.done())
                for done in already_done:
                    future_to_url.remove(done)
                if len(future_to_url) < max_threads * 10:
                    for i in range(max_threads * 10 - len(future_to_url)):
                        future_to_url.add(executor.submit(self.url_get, next(url_gen)))
                if timeit.default_timer() - start_time > 10:
                    self.download_flag = False
                    for future in future_to_url:
                        future.cancel()
                    break
            download_speed = round(((self.download_length / 1000 / 1000 / (timeit.default_timer() - start_time)) * 8.0), 2)
            self.result.update({"download": download_speed})
            self.result.update({"download_total": round(self.download_length / 1000 / 1000, 2)})

    def url_post(self, url, size, data):
        upload = 0
        try:
            # 创建请求头部
            headers = {'Content-length': '{}'.format(size)}
            # 创建请求参数
            param = build_request_para(url=url, headers=headers, data=data)
            r = requests.post(**param)
            if r.status_code == 200:
                upload = size
            else:
                upload = 0
        except (socket.error, requests.exceptions.RequestException) as e:
            self.log_queue.put(['all', '[{}] runtimes:{} POST "{}" 异常:{}.'.format(datetime.datetime.now(), self.runtimes, url, e)])
            upload = 0
        finally:
            with Lock():
                self.upload_length += upload

    def upload(self):
        self.logger.info("Speedtest: upload.")
        sizes = self.config['sizes']['upload']
        max_threads = self.config['threads']['upload']
        post_url = self._best['url']
        data = {}
        chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!@#$%^&*()_+-=<>?:";012345678901234567'
        for size in set(sizes):
            send_data = ((chars * (size // len(chars))) + chars[0: (size % len(chars))]).encode()
            data.update({'{}'.format(size): send_data})
        sizes_gen = gen(sizes)

        # 初始化参数
        self.upload_length = 0
        start_time = timeit.default_timer()

        # 进行POST操作
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_url = {executor.submit(self.url_post, post_url, size, data['{}'.format(size)]) for size in sizes}
            while True:
                time.sleep(0.1)
                already_done = set(f for f in future_to_url if f.done())
                for done in already_done:
                    future_to_url.remove(done)
                if len(future_to_url) < max_threads * 10:
                    for i in range(max_threads * 10 - len(future_to_url)):
                        next_size = next(sizes_gen)
                        future_to_url.add(executor.submit(self.url_post, post_url, next_size, data[str(next_size)]))
                if timeit.default_timer() - start_time > 10:
                    for future in future_to_url:
                        future.cancel()
                    break
            for _ in as_completed(future_to_url):
                ...
        upload_speed = round(((self.upload_length / 1000 / 1000 / (timeit.default_timer() - start_time)) * 8.0), 2)
        self.result.update({"upload": upload_speed})
        self.result.update({"upload_speed": round(self.upload_length / 1000 / 1000, 2)})

    def speedtest(self):
        self.download()
        self.upload()
        return self.result


if __name__ == '__main__':
    from queue import Queue
    log_que = Queue()
    runtimes = 1

    s = Speedtest(log_que, runtimes).speedtest()
    print(s)