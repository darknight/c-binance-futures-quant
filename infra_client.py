import calendar
from contextlib import contextmanager
import socket
import json
import requests
import time
import boto3
from datetime import datetime as dt, timezone
from websocket import create_connection
from settings import settings
from sqlmodel import create_engine


class InfraClient(object):
    def __init__(self, **params):
        self.msgSymbol = ""

        if "larkMsgSymbol" in params:
            self.msgSymbol = params["larkMsgSymbol"]

        self._telegram_bot_token = settings.telegram_bot_token
        self._telegram_chat_id = settings.telegram_chat_id

        self._engine = create_engine(settings.database_url, echo=False)

        self.wsConnectionA = {}

        if "connectWsA" in params and params["connectWsA"]:
            self.wsConnectionA = create_connection(settings.ws_address_a)

        self.wsConnectionB = {}

        if "connectWsB" in params and params["connectWsB"]:
            self.wsConnectionB = create_connection(settings.ws_address_b)

        self._last_notify_ts = 0

        self.privateIP = self.get_private_ip()

        self.updateMachineStatusTs = 0

        if settings.r2_account_id:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_access_key_secret,
            )
            self.r2_bucket = settings.r2_bucket_name
        else:
            self.s3_client = None
            self.r2_bucket = None

        self.serverName = settings.server_name

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
        if isinstance(initValue, dt):
            return int(initValue.timestamp())
        elif isinstance(initValue, str):
            parsed = time.strptime(initValue, "%Y-%m-%d %H:%M:%S")
            return calendar.timegm(parsed)
        else:
            if initValue > 99999999999:
                initValue = int(initValue / 1000)
            return dt.fromtimestamp(initValue, tz=timezone.utc)

    def turn_ts_to_day_time(self, initValue):
        if isinstance(initValue, dt):
            return int(initValue.timestamp())
        elif isinstance(initValue, str):
            parsed = time.strptime(initValue, "%Y-%m-%d %H:%M:%S")
            return calendar.timegm(parsed)
        else:
            if initValue > 99999999999:
                initValue = int(initValue / 1000)
            utc_dt = dt.fromtimestamp(initValue, tz=timezone.utc)
            return utc_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    def turn_ts_to_min(self, initValue):
        if initValue > 99999999999:
            initValue = int(initValue / 1000)
        utc_time = time.gmtime(initValue)
        return time.strftime("%M", utc_time)

    def generate_ts_with_min(self, min):
        now = int(time.time())
        utc_time = time.gmtime(now)
        dt_str = time.strftime("%Y-%m-%d %H:" + str(min) + ":00", utc_time)
        parsed = time.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return calendar.timegm(parsed)

    @contextmanager
    def get_session(self):
        from sqlmodel import Session
        session = Session(self._engine)
        try:
            yield session
        finally:
            session.close()

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
            body = json.dumps(obj, ensure_ascii=False)
            self.s3_client.put_object(
                Bucket=self.r2_bucket, Key=name, Body=body,
                ContentType='application/json'
            )
        except Exception as e:
            print(e)

    def oss_get_obj(self, name):
        try:
            resp = self.s3_client.get_object(Bucket=self.r2_bucket, Key=name)
            return json.loads(resp['Body'].read().decode('utf-8'))
        except Exception as e:
            print(e)

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
