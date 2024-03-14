from threading import Lock
from collections.abc import Iterable
from xml.etree import ElementTree
from io import BytesIO
from math import ceil
from concurrent.futures import ThreadPoolExecutor, as_completed
from asyncio.subprocess import PIPE, STDOUT
import asyncio
import requests
import time
import logging
import datetime
import math
import os
import platform
import re
import socket
import timeit

FILE_NAME = "speedtest_server_config.xml"  # speedtest server list xml file


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
    url = '{protocol}{sep}x={x}.{tail}'.format(protocol=protocol_url, sep=sep, x=int(time.time() * 1000), tail=0)

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


def distance(origin: tuple = (float, float), destination: tuple = (float, float)) -> float:
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
    """
    Infinite data generator.
    :param lst: Iterable elements.
    :return: Item from list.
    """
    while True:
        for i in lst:
            yield i


class ConstBase:

    # download
    download_flag = True
    download_length = 0
    download_error_package = 0

    # upload
    upload_flag = True
    upload_length = 0


class GetConfigError(Exception):
    """Fail to get config"""


class GetServerError(Exception):
    """Fail to get server"""


class UploadCancel(Exception):
    """Cancel while post data"""


class UploadContentIterator(Iterable):
    def __init__(self, size, const):
        self.chars = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        self.io_data = BytesIO(self.chars * ceil(size / len(self.chars)))
        self.chunk_size = 1024
        self.total_size = 0
        self.size = size + 1
        self.const = const

    def __iter__(self):
        return self

    def __next__(self):
        if self.size - self.total_size < self.chunk_size:
            self.chunk_size = self.size - self.total_size + 1
        data = self.io_data.read(self.chunk_size)
        data_len = len(data)
        self.total_size += data_len
        if self.const.upload_flag is False:
            del self.io_data
            raise UploadCancel
        if self.total_size >= self.size:
            del self.io_data
            raise StopIteration
        with Lock():
            self.const.upload_length += data_len
        return data


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

        # 初始化变量类
        self.const = ConstBase()

        # 初始化logger
        self.log_queue = log_queue
        self.logger = logging.getLogger(__name__)

        # 结果统计
        self.result = dict()
        # "server": '',  # server信息
        # "latency": '',  # 服务器的延迟信息 (ms)
        # "download": '',  # 下载速度
        # "download_total": '',  # 下载流量数量
        # "upload": '',  # 上传速度
        # "upload_total": "",  # 上传数据量

    def subprocess_nonblock_readline(self, *args, timeout=60):
        async def run_command():
            cache = ''
            process = await asyncio.create_subprocess_exec(*args, stdout=PIPE, stderr=STDOUT)
            while True:
                try:
                    line = await asyncio.wait_for(process.stdout.readline(), timeout)
                    line = line.decode("utf-8", 'replace')
                    cache += line
                    self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), re.sub(r"[\r\n']", '', line))])
                    if line == '':
                        try:
                            process.kill()
                        except ProcessLookupError:  # Linux
                            pass
                        break
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:  # Linux
                        pass
                    break
            await process.wait()  # wait for the child process to exit
            return cache

        if os.name == 'nt':
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        future = asyncio.ensure_future(run_command())
        loop.run_until_complete(future)
        loop.close()
        return future.result()

    def get_config(self):
        self.logger.info("Speedtest: get config.")
        self.log_queue.put(['at_log', '[{}] 获取配置信息'.format(datetime.datetime.now())])
        headers = {'user-agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                 "(KHTML, like Gecko) Chrome/86.0.4240.75 Safari/537.36", 'Accept-Encoding': 'gzip'}

        repeat_times = 10
        for i in range(repeat_times):
            try:
                # get config content from http://www.speedtest.net/speedtest-config.php
                self.logger.info("Speedtest: get config from http://www.speedtest.net/speedtest-config.php.")
                params = build_request_para(url='://www.speedtest.net/speedtest-config.php', headers=headers)
                config_xml = requests.get(**params, timeout=3).content

                # get ip latitude and longitude with amap api
                self.logger.info("Speedtest: get lat lon from amap api.")
                ip = ElementTree.fromstring(config_xml).find('client').attrib["ip"]
                r = requests.get("https://restapi.amap.com/v3/ip?output=json&key=f15b3b1288acd61a7ace3dbf3819cdeb&ip={}".format(ip), headers=headers, timeout=3)

                # Amap api will return json string contain current ip`s rectangle(latitude and longitude).
                # if rectangle list is not empty, get center point of rectangle; else:
                # 1. get current ip`s fuzzy position;
                # 2. get fuzzy position`s latitude and longitude with amap api.
                if not r.json()['rectangle']:
                    r = requests.get("https://ip.tool.chinaz.com/", headers=headers, timeout=3)
                    ip_address = ''.join(re.findall(r'WhoIpWrap jspu[\s|\S]*?</div', r.text))
                    address = ''.join(re.findall("<span.*?>(.*?)</span>", ip_address)[-1])
                    r = requests.get("https://restapi.amap.com/v3/geocode/geo?key=f15b3b1288acd61a7ace3dbf3819cdeb&output=json&address={}".format(address), headers=headers, timeout=3)
                    api_lat_lon = sorted((float(i) for i in r.json()['geocodes'][0]['location'].split(',')), reverse=False)
                else:
                    rectangle = re.split(r'[,|;]', r.json()['rectangle'])
                    api_lat_lon = ((float(rectangle[1]) + float(rectangle[3])) / 2, (float(rectangle[0]) + float(rectangle[2])) / 2)
                self.logger.info('api_lat_lon: {}'.format(api_lat_lon))
                break
            except Exception as e:
                self.logger.info(e)
                continue
        else:
            self.log_queue.put(['at_log', '[{}] {}'.format(datetime.datetime.now(), os.popen('ping www.baidu.com' if os.name == 'nt' else 'ping www.baidu.com -c 4').read())])
            self.log_queue.put(['all', '[{}] runtimes:{} 连续{}次获取Speedtest配置文件失败，请检查ATlog ping状态是否正常，如果正常无需关注，'.format(datetime.datetime.now(), self.runtimes, repeat_times)])
            return False

        self.logger.info("Speedtest: Parse speedtest xml content.")
        try:
            root = ElementTree.fromstring(config_xml)
        except ElementTree.ParseError:
            self.log_queue.put(['all', '[{}] runtimes:{} 解析Speedtest Config XML内容失败.'.format(datetime.datetime.now(), self.runtimes)])
            self.logger.info(config_xml)
            return False

        server_config = root.find('server-config').attrib
        client = root.find('client').attrib
        isp = client['isp']
        self.result.update({"isp": isp})
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
        self.log_queue.put(['at_log', '[{}] 获取服务器列表'.format(datetime.datetime.now())])
        urls = [
            '://www.speedtest.net/speedtest-servers-static.php',
            'http://c.speedtest.net/speedtest-servers-static.php',
            '://www.speedtest.net/speedtest-servers.php',
            'http://c.speedtest.net/speedtest-servers.php',
        ]

        headers = dict()
        headers['Accept-Encoding'] = 'gzip'
        response = b''
        if os.path.exists(FILE_NAME):
            with open(FILE_NAME, 'r') as f:
                response = f.read()
        else:
            for url in urls:
                try:
                    url = build_request_para(url)
                    try:
                        r = requests.get(**url, timeout=3)
                        if b'404 - Not Found' not in r.content:
                            response += r.content
                    except requests.exceptions.RequestException:
                        continue
                except (requests.exceptions.RequestException, socket.error) as e:
                    self.logger.info(e)
            response = re.sub(r'\s?</servers>\s?</settings>\s?<\?xml.*?>\s?<settings>\s?<servers>\s?', '', response.decode('utf-8', 'replace'))
            if response:
                with open(FILE_NAME, 'w') as f:
                    f.write(response)

        try:
            root = ElementTree.fromstring(response)

            servers = ElementTree.Element.iter(root, 'server')

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
        except ElementTree.ParseError as e:
            self.logger.info(e)
        except Exception as e:
            self.logger.info(e)

        return True

    def url_latency(self, headers, server_url):
        self.logger.info("Speedtest: get url latency.")
        try:
            server, url = server_url.split('~')
            t = requests.get(url, headers=headers, timeout=1).elapsed.total_seconds()
        except (requests.exceptions.RequestException, socket.error):
            return ['0000', 3600]
        return [server, t]

    def get_best_server(self, limit=5):
        self.logger.info("Speedtest: get best server.")
        if not self.servers:
            self.get_servers()
        if self.servers == {}:
            self.log_queue.put(['all', '[{}] runtimes:{} 获取服务器列表失败.'.format(datetime.datetime.now(), self.runtimes)])
            return False

        self.log_queue.put(['at_log', '[{}] 获取最佳测速服务器'.format(datetime.datetime.now())])
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
        with ThreadPoolExecutor(max_workers=5) as executor:
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
                self.logger.info(self._best)
                self.result.update({"server": '{sponsor}-{id}-{host}-{distance}km'.format(sponsor=self._best['sponsor'], id=self._best['id'], host=self._best['host'], distance=self._best['d'])})
                return True

    def url_get(self, url):
        download = 0
        try:
            r = requests.get(**build_request_para(url), stream=True, timeout=3)
            for line in r.iter_content(chunk_size=512):
                if self.const.download_flag is False:
                    r.close()
                    return
                elif line:
                    line_len = len(line)
                    download += line_len
                    with Lock():
                        self.const.download_length += line_len
            r.close()
            self.const.download_error_package += (int(r.headers['Content-Length']) - download)
            if self.const.download_error_package != 0:
                self.log_queue.put(['all', '[{}] runtimes:{} 下载过程中出现丢包：返回{}，漏接收{}'.format(datetime.datetime.now(), self.runtimes, r.headers['Content-Length'], self.const.download_error_package)])
        except requests.exceptions.Timeout as e:
            self.logger.info('url get {}'.format(e))
        except requests.exceptions.ConnectionError as e:
            self.logger.info('url get {}'.format(e))
        except requests.exceptions.RequestException as e:
            self.log_queue.put(['all', '[{}] runtimes:{} GET "{}" 异常:{}.'.format(datetime.datetime.now(), self.runtimes, build_request_para(url)["url"], e)])

    def download(self):
        self.logger.info("Speedtest: download.")
        self.log_queue.put(['at_log', '[{}] 进行下载速度测试'.format(datetime.datetime.now())])
        urls = []
        download_jpg_size = self.config['sizes']['download']
        for size in download_jpg_size:
            urls.append('%s/random%sx%s.jpg' % (os.path.dirname(self._best['url']), size, size))
        urls = sorted(urls)
        max_threads = self.config['threads']['download']

        self.const.download_flag = True
        self.const.download_length = 0
        self.const.download_error_package = 0
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
                    for future in future_to_url:
                        future.cancel()
                    self.const.download_flag = False
                    break
            download_speed = round(((self.const.download_length / 1000 / 1000 / (timeit.default_timer() - start_time)) * 8.0), 2)
            self.result.update({"download": download_speed})
            self.result.update({"download_total": round(self.const.download_length / 1000 / 1000, 2)})

    def url_post(self, url, size, data):
        try:
            # 创建请求头部
            headers = {'Content-length': '{}'.format(size)}
            # 创建请求参数
            param = build_request_para(url=url, headers=headers, data=data)
            r = requests.post(**param, timeout=3)
            r.close()
        except requests.exceptions.Timeout as e:
            self.logger.info('url post {}'.format(e))
        except requests.exceptions.ConnectionError as e:
            self.logger.info('url post {}'.format(e))
        except UploadCancel:
            pass
        except (socket.error, requests.exceptions.RequestException) as e:
            self.log_queue.put(['all', '[{}] runtimes:{} POST "{}" 异常:{}.'.format(datetime.datetime.now(), self.runtimes, url, e)])

    def upload(self):
        self.logger.info("Speedtest: upload.")
        self.log_queue.put(['at_log', '[{}] 进行上传速度测试'.format(datetime.datetime.now())])

        sizes = self.config['sizes']['upload']
        max_threads = self.config['threads']['upload']
        post_url = self._best['url']
        sizes_gen = gen(sizes)

        # 初始化参数
        self.const.upload_flag = True
        self.const.upload_length = 0

        start_time = timeit.default_timer()

        # 进行POST操作
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_url = {executor.submit(self.url_post, post_url, size, UploadContentIterator(size, self.const)) for size in sizes}
            while True:
                time.sleep(0.1)
                already_done = set(f for f in future_to_url if f.done())
                for done in already_done:
                    future_to_url.remove(done)
                if len(future_to_url) < max_threads * 10:
                    for i in range(max_threads * 10 - len(future_to_url)):
                        next_size = next(sizes_gen)
                        future_to_url.add(executor.submit(self.url_post, post_url, next_size, UploadContentIterator(next_size, self.const)))
                if timeit.default_timer() - start_time > 10:
                    for future in future_to_url:
                        future.cancel()
                    self.const.upload_flag = False
                    for _ in as_completed(future_to_url):
                        ...
                    break
        upload_speed = round(((self.const.upload_length / 1000 / 1000 / (timeit.default_timer() - start_time)) * 8.0), 2)
        self.result.update({"upload": upload_speed})
        self.result.update({"upload_total": round(self.const.upload_length / 1000 / 1000, 2)})

    def speedtest_rebuilt(self):
        try:
            # get config and servers
            get_config_result = self.get_config()
            if not get_config_result:
                return False
            get_best_server_result = self.get_best_server()
            if not get_best_server_result:
                return False
            # test download and upload
            if get_config_result and get_best_server_result:
                self.download()
                self.upload()
            return self.result
        except Exception as e:
            self.log_queue.put(['all', '[{}] runtimes:{} speedtest测速异常: {}'.format(datetime.datetime.now(), self.runtimes, e)])
            return False

    def speedtest(self, app_path):
        """Official version"""
        try:
            # get config and servers
            get_config_result = self.get_config()
            if not get_config_result:
                return False
            get_best_server_result = self.get_best_server()
            if not get_best_server_result:
                return False
            # test download and upload
            speedtest = self.subprocess_nonblock_readline(app_path, '--accept-license', '-s', self._best['id'])
            return speedtest
        except Exception as e:
            self.log_queue.put(['all', '[{}] runtimes:{} speedtest测速异常: {}'.format(datetime.datetime.now(), self.runtimes, e)])
            return False


if __name__ == '__main__':
    from queue import Queue
    log_que = Queue()
    runtime = 0
    speedtest_result = Speedtest(log_que, runtime).speedtest('speedtest')
    print(speedtest_result)

    # while True:
    #     runtime += 1
    #     speedtest_result = Speedtest(log_que, runtime).speedtest_rebuilt()
    #     print(speedtest_result)
    #     # dataframe 统计
    #     print(['df', runtime, 'download_speed', float(speedtest_result['download'])])
    #     print(['df', runtime, 'download_data', float(speedtest_result['download_total'])])
    #     print(['df', runtime, 'upload_speed', float(speedtest_result['upload'])])
    #     print(['df', runtime, 'upload_data', float(speedtest_result['upload_total'])])
    #     print(['df', runtime, 'server_info', speedtest_result['server']])
    #     print(['df', runtime, 'ping_delay', float(speedtest_result['latency'])])
    #     # AT log打印
    #     print(['at_log', '[{}] 下载速度: {} Mbps'.format(datetime.datetime.now(), float(speedtest_result['download']))])
    #     print(['at_log', '[{}] 上传速度: {} Mbps'.format(datetime.datetime.now(), float(speedtest_result['upload']))])
    #     print(['at_log', '[{}] 服务器: {} '.format(datetime.datetime.now(), speedtest_result['server'])])
    #     print(['at_log', '[{}] ISP: {} '.format(datetime.datetime.now(), speedtest_result['isp'])])
    #     print(['at_log', '[{}] 测速服务器延迟: {} ms'.format(datetime.datetime.now(), speedtest_result['latency'])])
    #     print(['at_log', '[{}] 下载测试消耗数据量: {} MB'.format(datetime.datetime.now(), float(speedtest_result['download_total']))])
    #     print(['at_log', '[{}] 上传测试消耗数据量: {} MB'.format(datetime.datetime.now(), float(speedtest_result['upload_total']))])
