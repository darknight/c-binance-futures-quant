import mysql.connector
import socket
import json
import requests
import time
import oss2
from websocket import create_connection
from settings import settings
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import connect
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdkcore.acs_exception.exceptions import ClientException
from aliyunsdkcore.acs_exception.exceptions import ServerException
from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import DescribeInstancesRequest


class InfraClient(object):
    def __init__(self, **params):
        self.msgSymbol = ""

        if "larkMsgSymbol" in params:
            self.msgSymbol = params["larkMsgSymbol"]

        self._telegram_bot_token = settings.telegram_bot_token
        self._telegram_chat_id = settings.telegram_chat_id

        self._mysql_config = {
            "host": settings.database_host,
            "port": settings.database_port,
            "user": settings.database_user,
            "password": settings.database_password,
            "database": settings.database_name,
            "charset": "utf8mb4",
        }

        self.mysqlConnect = {}
        if "connectMysql" in params and params["connectMysql"]:
            self.mysqlConnect = mysql.connector.connect(**self._mysql_config)

        self.mysqlPoolConnect = {}
        if "connectMysqlPool" in params and params["connectMysqlPool"]:
            self.mysqlPoolConnect = MySQLConnectionPool(pool_name="mypool", pool_size=30, **self._mysql_config)

        self.wsConnectionA = {}

        if "connectWsA" in params and params["connectWsA"]:
            self.wsConnectionA = create_connection(settings.ws_address_a)

        self.wsConnectionB = {}

        if "connectWsB" in params and params["connectWsB"]:
            self.wsConnectionB = create_connection(settings.ws_address_b)

        self._last_notify_ts = 0

        self.privateIP = self.get_private_ip()

        self.updateMachineStatusTs = 0

        oss_auth = oss2.Auth(settings.aliyun_api_key, settings.aliyun_api_secret)
        self.oss_bucket = oss2.Bucket(oss_auth, 'http://oss-cn-hongkong.aliyuncs.com', 'zuibite-api')

        self.serverName = self.getServerName()

    def send_notify(self, content):
        """发送通知消息（通过 Telegram）"""
        if not self._telegram_bot_token or not self._telegram_chat_id:
            return
        try:
            url = f"https://api.telegram.org/bot{self._telegram_bot_token}/sendMessage"
            data = {
                "chat_id": self._telegram_chat_id,
                "text": f"【{self.msgSymbol}】{content}【{self.privateIP}】",
            }
            requests.post(url, json=data, timeout=10)
        except Exception as e:
            print(e)
            print("sendMsg")

    def send_notify_limit_one_min(self, content):
        """发送通知消息，60秒限流"""
        now = int(time.time())
        if now - self._last_notify_ts > 60:
            self._last_notify_ts = now
            self.send_notify(content)

    def turn_ts_to_time(self, initValue):
        if isinstance(initValue, str):
            timeArray = time.strptime(initValue, "%Y-%m-%d %H:%M:%S")
            timestamp = time.mktime(timeArray)
            return timestamp
        else:
            if initValue > 99999999999:
                initValue = int(initValue / 1000)
            time_local = time.localtime(initValue)
            dt = time.strftime("%Y-%m-%d %H:%M:00", time_local)
            return dt

    def turn_ts_to_day_time(self, initValue):
        if isinstance(initValue, str):
            timeArray = time.strptime(initValue, "%Y-%m-%d %H:%M:%S")
            timestamp = time.mktime(timeArray)
            return timestamp
        else:
            if initValue > 99999999999:
                initValue = int(initValue / 1000)
            time_local = time.localtime(initValue)
            dt = time.strftime("%Y-%m-%d 00:00:00", time_local)
            return dt

    def turn_ts_to_min(self, initValue):
        if initValue > 99999999999:
            initValue = int(initValue / 1000)
        time_local = time.localtime(initValue)
        dt = time.strftime("%M", time_local)
        return dt

    def generate_ts_with_min(self, min):
        now = int(time.time())
        time_local = time.localtime(now)
        dt = time.strftime("%Y-%m-%d %H:" + str(min) + ":00", time_local)
        timeArray = time.strptime(dt, "%Y-%m-%d %H:%M:%S")
        timestamp = int(time.mktime(timeArray))
        return timestamp

    def mysql_select(self, sql, params):
        res = ()
        normal = False
        try:
            self.mysqlConnect.ping()
        except Exception as e:
            self.mysqlConnect = mysql.connector.connect(**self._mysql_config)
        while not normal:
            try:
                cursor = self.mysqlConnect.cursor()
                cursor.execute(sql, params)
                res = cursor.fetchall()
                normal = True
                cursor.close()
            except Exception as e:
                self.send_notify("mysql ex," + str(e) + "," + sql + "," + str(params))
                print("mysql error")
                print(sql)
                print(e)
                try:
                    self.mysqlConnect.ping()
                except Exception as e:
                    self.mysqlConnect = mysql.connector.connect(**self._mysql_config)
                time.sleep(3)
        return res

    def mysql_commit(self, sql, params):
        normal = False
        try:
            self.mysqlConnect.ping()
        except Exception as e:
            self.mysqlConnect = mysql.connector.connect(**self._mysql_config)
        while not normal:
            try:
                cursor = self.mysqlConnect.cursor()
                cursor.execute(sql, params)
                self.mysqlConnect.commit()
                normal = True
                cursor.close()
            except Exception as e:
                self.send_notify("mysql ex," + str(e) + "," + sql + "," + str(params))
                print("mysql error")
                print(sql)
                try:
                    self.mysqlConnect.ping()
                except Exception as e:
                    self.mysqlConnect = mysql.connector.connect(**self._mysql_config)
                time.sleep(3)

    def mysql_pool_select(self, q, params):
        res = ()
        con = self.mysqlPoolConnect.get_connection()
        c = con.cursor()
        try:
            c.execute(q, params)
            res = c.fetchall()
            normal = True
        except Exception as e:
            print(e)
            print(q)
            print("doing error")
            normal = False
        try:
            con.close()
        except Exception as e:
            print(q)
            print(e)
        return res

    def mysql_pool_commit(self, q, params):
        con = self.mysqlPoolConnect.get_connection()
        c = con.cursor()
        try:
            c.execute(q, params)
            con.commit()
            c.close()
            normal = True
        except Exception as e:
            self.send_notify_limit_one_min(str(e))
            print(q)
            print(e)
            normal = False
        try:
            con.close()
        except Exception as e:
            print(q)
            print(e)

        return normal

    def get_private_ip(self):
        privateIP = ""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            privateIP = s.getsockname()[0]
        finally:
            s.close()
        return privateIP

    def send_to_ws_a(self, msg):
        try:
            print(msg)
            self.wsConnectionA.send(msg)
        except Exception as e:
            print(e)
            try:
                self.wsConnectionA = create_connection(settings.ws_address_a)
                self.wsConnectionA.send(msg)
            except Exception as e:
                print(e)
                time.sleep(0.1)

    def get_from_ws_a(self, msg):
        result = {}
        try:
            self.wsConnectionA.send(msg)
            result = self.wsConnectionA.recv()
            return result
        except Exception as e:
            print(e)
            try:
                self.wsConnectionA = create_connection(settings.ws_address_a)
                self.wsConnectionA.send(msg)
                result = self.wsConnectionA.recv()
                return result
            except Exception as e:
                self.send_notify_limit_one_min(str(e))

        return result

    def send_to_ws_b(self, msg):
        try:
            self.wsConnectionB.send(msg)
        except Exception as e:
            try:
                self.wsConnectionB = create_connection(settings.ws_address_b)
                self.wsConnectionB.send(msg)
            except Exception as e:
                time.sleep(0.1)

    def get_from_ws_b(self, msg):
        result = {}
        try:
            self.wsConnectionB.send(msg)
            result = self.wsConnectionB.recv()
            return result
        except Exception as e:
            try:
                self.wsConnectionB = create_connection(settings.ws_address_b)
                self.wsConnectionB.send(msg)
                result = self.wsConnectionB.recv()
                print(result)
                return result
            except Exception as e:
                print(e)
                self.send_notify_limit_one_min(str(e))

        return result

    def get_aliyun_public_ip_arr_by_name(self, name):
        publicIPArr = []
        nowPage = 1
        emptyReq = False
        while not emptyReq:
            client = AcsClient(settings.aliyun_api_key, settings.aliyun_api_secret, settings.aliyun_point)
            client.add_endpoint(settings.aliyun_point, 'Ecs', "ecs." + settings.aliyun_point + ".aliyuncs.com")
            request = DescribeInstancesRequest()
            request.set_PageNumber(nowPage)
            request.set_PageSize(100)
            request.set_accept_format('json')
            instanceInfoArr = client.do_action_with_exception(request)
            instanceInfoArr = json.loads(str(instanceInfoArr, encoding='utf-8'))

            instanceInfoArr = instanceInfoArr["Instances"]["Instance"]
            if len(instanceInfoArr) == 0:
                emptyReq = True
            else:
                for i in range(len(instanceInfoArr)):
                    if instanceInfoArr[i]["InstanceName"].find(name) >= 0:
                        publicIPArr.append(instanceInfoArr[i]["PublicIpAddress"]["IpAddress"][0])

            nowPage = nowPage + 1
        return publicIPArr

    def get_aliyun_private_ip_arr_by_name(self, name):
        privateIPArr = []
        nowPage = 1
        emptyReq = False
        while not emptyReq:
            client = AcsClient(settings.aliyun_api_key, settings.aliyun_api_secret, settings.aliyun_point)
            client.add_endpoint(settings.aliyun_point, 'Ecs', "ecs." + settings.aliyun_point + ".aliyuncs.com")
            request = DescribeInstancesRequest()
            request.set_PageNumber(nowPage)
            request.set_PageSize(100)
            request.set_accept_format('json')
            instanceInfoArr = client.do_action_with_exception(request)
            instanceInfoArr = json.loads(str(instanceInfoArr, encoding='utf-8'))

            instanceInfoArr = instanceInfoArr["Instances"]["Instance"]
            if len(instanceInfoArr) == 0:
                emptyReq = True
            else:
                for i in range(len(instanceInfoArr)):
                    if instanceInfoArr[i]["InstanceName"].find(name) >= 0:
                        privateIPArr.append(instanceInfoArr[i]["VpcAttributes"]["PrivateIpAddress"]["IpAddress"][0])

            nowPage = nowPage + 1
        return privateIPArr

    def update_machine_status(self):
        now = int(time.time())
        if now - self.updateMachineStatusTs > 60:
            self.updateMachineStatusTs = now
            try:
                url = "http://" + settings.web_address + ":8888/update_machine_status"
                print(url)
                postDataObj = {'privateIP': self.privateIP, 'symbol': self.msgSymbol}
                response = requests.request("POST", url, timeout=(0.5, 0.5), data=postDataObj)
            except Exception as e:
                print(e)

    def update_trade_status(self, status, runTime):
        try:
            url = "http://" + settings.web_address + ":8888/update_trade_status"
            print(url)
            postDataObj = {'privateIP': self.privateIP, 'status': status, "runTime": runTime}
            response = requests.request("POST", url, timeout=(0.5, 0.5), data=postDataObj)
        except Exception as e:
            print(e)

    def cancel_binance_orders_by_web_server(self, symbol, key, secret):
        try:
            url = "http://" + settings.web_address + ":8888/cancel_binance_orders"
            print(url)
            postDataObj = {'privateIP': self.privateIP, 'symbol': symbol, 'key': key, 'secret': secret}
            response = requests.request("POST", url, timeout=(3, 3), data=postDataObj)
            print(response)
        except Exception as e:
            print(e)

    def cancel_binance_order_by_web_server(self, symbol, key, secret, clientOrderId):
        try:
            url = "http://" + settings.cancel_web_address + ":8888/cancel_binance_order"
            print(url)
            postDataObj = {'privateIP': self.privateIP, 'symbol': symbol, 'key': key, 'secret': secret, 'clientOrderId': clientOrderId}
            response = requests.request("POST", url, timeout=(3, 3), data=postDataObj)
            print(response)
        except Exception as e:
            print(e)

    def open_take_binance_orders_by_web_server(self, symbol, direction, key, secret, price, openTime, positionValue, volMultiple):
        try:
            url = "http://" + TRADE_WEB_ADDRESS + ":8888/take_open"

            postDataObj = {'privateIP': self.privateIP, 'volMultiple': volMultiple, 'symbol': symbol, 'direction': direction, 'key': key, 'secret': secret, 'price': price, 'openTime': openTime, 'positionValue': positionValue}
            response = requests.request("POST", url, timeout=(3, 3), data=postDataObj)
        except Exception as e:
            print(e)

    def end_open_by_web_server(self, symbol):
        try:
            url = "http://" + TRADE_WEB_ADDRESS + ":8888/end_open"

            postDataObj = {'privateIP': self.privateIP, 'symbol': symbol}
            response = requests.request("POST", url, timeout=(3, 3), data=postDataObj)
        except Exception as e:
            print(e)

    def get_percent_num(self, num, total):
        if total == 0:
            return 0
        else:
            return num / total * 100

    def oss_put_obj(self, obj, name):
        try:
            inputData = json.dumps(obj, ensure_ascii=False)
            ossResult = self.oss_bucket.put_object(name, inputData)
        except Exception as e:
            print(e)

    def oss_get_obj(self, name):
        try:
            object_stream = self.oss_bucket.get_object(name)
            readObj = object_stream.read()
            readObj = json.loads(str(readObj, 'utf-8'))
            return readObj
        except Exception as e:
            print(e)

    def getServerName(self):
        serverName = ""
        privateIP = ""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            privateIP = s.getsockname()[0]
        finally:
            s.close()
        nowPage = 1
        emptyReq = False
        while serverName == "" and not emptyReq:
            client = AcsClient(settings.aliyun_api_key, settings.aliyun_api_secret, settings.aliyun_point)
            client.add_endpoint(settings.aliyun_point, 'Ecs', "ecs." + settings.aliyun_point + ".aliyuncs.com")
            request = DescribeInstancesRequest()
            request.set_PageNumber(nowPage)
            request.set_PageSize(100)
            request.set_accept_format('json')
            instanceInfoArr = client.do_action_with_exception(request)
            instanceInfoArr = json.loads(str(instanceInfoArr, encoding='utf-8'))
            instanceInfoArr = instanceInfoArr["Instances"]["Instance"]
            if len(instanceInfoArr) == 0:
                emptyReq = True
            for i in range(len(instanceInfoArr)):
                if instanceInfoArr[i]["VpcAttributes"]["PrivateIpAddress"]["IpAddress"][0] == privateIP:
                    serverName = instanceInfoArr[i]["InstanceName"]
            nowPage = nowPage + 1
        return serverName

    def begin_trade_record(self, volMultiple, standardRate, symbol, klineArr, nowOpenRate, machineNumber, direction, myTradeType, longsConditionA, shortsConditionA, shortsConditionB, btcNowOpenRate, ethNowOpenRate, clientBeginPrice, clientEndPrice):
        try:
            url = "http://" + settings.web_address + ":8888/begin_trade_record"

            postDataObj = {
                'volMultiple': volMultiple,
                'standardRate': standardRate,
                'symbol': symbol,
                'klineArr': json.dumps(klineArr),
                'nowOpenRate': nowOpenRate,
                'machineNumber': machineNumber,
                'direction': direction,
                'myTradeType': myTradeType,
                'longsConditionA': longsConditionA,
                'shortsConditionA': shortsConditionA,
                'shortsConditionB': shortsConditionB,
                'btcNowOpenRate': btcNowOpenRate,
                'ethNowOpenRate': ethNowOpenRate,
                'clientBeginPrice': clientBeginPrice,
                'clientEndPrice': clientEndPrice,
                'privateIP': self.privateIP,
            }
            print(postDataObj)
            postDataObj = postDataObj
            print(postDataObj)
            response = requests.request("POST", url, timeout=(3, 3), data=postDataObj)
        except Exception as e:
            self.send_notify_limit_one_min(str(e))
            print(e)
