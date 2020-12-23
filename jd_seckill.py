#!/usr/bin/python3
# -*- coding: utf-8 -*- 

import requests
import time
import json
import os
import copy
import threading
from bs4 import BeautifulSoup
from datetime import datetime

#cookie，可以在我的订单页面，搜索list的网络请求，获取cookie值
thor = 'CE937B0BD5B8F3E90A6BB85695BCBDB701E282EC17F097DE0458C96762B5A4AFFEE1ED9D63457359F775EA07D315445D8426C6D1F2E593FDE170E09C8838ABCBE44D8902AEA1CFF470506B47FB116FAA5435DB281862350DE6DBA258B11BE15444004A85C2790B0FD0BA999781BCF5CD353D1DD07653A699CC0DC1213E4950BF'
#日志模板，有颜色和状态
LOG_TEMPLE_BLUE='\033[1;34m{}\033[0m '
LOG_TEMPLE_RED='\033[1;31m{}\033[0m '
LOG_TEMPLE_SUCCESS='\033[1;32mSUCCESS\033[0m '
LOG_TEMPLE_FAILED='\033[1;31mFAILED\033[0m '

def timestamp_to_str(timestamp):
    return datetime.strftime(datetime.fromtimestamp(timestamp),'%Y-%m-%d %H:%M:%S.%f')

def timeduration_to_str(timeduration):
    return "%10.0f s"%timeduration

class JD:
    base_headers = {
        'referer': '',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36',
    }

    #初始化配置
    def __init__(self):
        self.index = 'https://www.jd.com/'

        self.clock_url = 'https://a.jd.com//ajax/queryServerData.html'
        #用户信息获取地址
        self.user_url = 'https://passport.jd.com/user/petName/getUserInfoForMiniJd.action?&callback=jsonpUserinfo&_=' + \
            str(int(time.time() * 1000)) 
        #加购物车
        self.buy_url = 'https://cart.jd.com/gate.action?pid={}&pcount=1&ptype=1'   
        #修改购物车商品数量为1
        self.change_num = 'https://cart.jd.com/changeNum.action?pid={}&pcount=1&ptype=1'
        #下单
        self.pay_url = 'https://cart.jd.com/gotoOrder.action'  
        #订单提交
        self.pay_success = 'https://trade.jd.com/shopping/order/submitOrder.action'  
        #商品id
        self.goods_id = ''  
        #会话
        self.session = requests.session()

        #cookie
        self.thor = thor
        #重试次数限制
        self.retry_limit = 100
        #重试间隔
        self.gap = 0.1
        #重试计数
        self.retry_count = 0
        #本地时间与京东时间差
        self.time_diff = 0.0

  
    #登录，然后抢预约成功的商品
    def start(self, items): 

        self.init_time()
        self.pull_user_info()        

        #遍历预约成功的商品，挨个抢购

        threads = []
        for key in items:

            item = copy.copy(self)

            order_time = items[key]["order_time"]
            item_url = items[key]["item_url"]

            timetuple = time.strptime(order_time, "%Y-%m-%d %H:%M")
            order_time_st = time.mktime(timetuple)

            item.goods_url = item_url
            item.key = key
            item.order_time_st = order_time_st
            item.order_time = order_time

            thread = threading.Thread(target=self.run, args=(item,))
            thread.start()
            threads.append(thread)

        for thread in threads:            
            thread.join()
      
    def init_time(self):
        ret = requests.get(self.clock_url).text
        js = json.loads(ret)
        servertime = js.get('serverTime')/1000
        localtime = time.time()
        self.time_diff = servertime - localtime
        print("server time: ", timestamp_to_str(servertime))
        print(" local time: ", timestamp_to_str(localtime))
        print("calibration: ", self.time_diff, " s")

    def pull_user_info(self):

        headers = copy.copy(JD.base_headers)
        headers['referer'] = 'https://cart.jd.com/cart.action'
        c = requests.cookies.RequestsCookieJar()
        c.set('thor', self.thor)  
        self.session.cookies.update(c)
        response = self.session.get(
            url=self.user_url, headers=headers).text.strip('jsonpUserinfo()\n')
        self.user_info = json.loads(response)
        if not self.user_info.get('nickName'):
            raise Exception("账号验证错误请检查cookie: thor")

        print("user nick name: ", self.user_info["nickName"])

    def run(self, item):
        while True:
            localtime = time.time() + self.time_diff
            if item.order_time_st - localtime > 10:
                time.sleep(5)
                print("\r %s left"%(timeduration_to_str(item.order_time_st - localtime)) )
            elif item.order_time_st - localtime > item.gap:
                time.sleep(item.gap)
                print("\r %s left"%(timeduration_to_str(item.order_time_st - localtime)) )
            elif item.order_time_st - localtime > 0:
                # we need to wait a very short time
                # let's spin
                print("\r %s left"%(timeduration_to_str(item.order_time_st - localtime)) )
                pass
            else:
                break

        for i in range(item.retry_limit):
            try:
                ok = self.order(item)
                if ok:
                    print("'%s' ordered sucessfully. Exit"%item.key)
                    break

                item.retry_count = item.retry_count + 1
                time.sleep(item.gap)
            except BaseException as ex:
                print("except %s"%ex)
                time.sleep(item.gap)
                pass
        

    def order(self, item):
        
        #获取商品id，从url的/开始位置截取到.位置
        item.goods_id = item.goods_url[
            item.goods_url.rindex('/') + 1:item.goods_url.rindex('.')]

        headers = copy.copy(JD.base_headers)
        headers['referer'] = item.goods_url
        # url格式化，把商品id填入buy_url
        buy_url = item.buy_url.format(item.goods_id)
        #get请求，添加购物车
        item.session.get(url=buy_url, headers=headers)  
        #修正购物车商品数量（第二次重试后修正购物车数量）
        if item.retry_count > 0 :
            print('第',item.retry_count,'次重试，抢购商品为：',item.goods_id,'修正购物车商品数量。')
            change_num_url = item.change_num.format(item.goods_id)
            item.session.get(url=change_num_url, headers=headers)
        #get请求
        item.session.get(url=item.pay_url, headers=headers) 
        #post请求，提交订单
        response = item.session.post(
            url=item.pay_success, headers=headers)
        order_id = json.loads(response.text).get('orderId')
        if order_id:
            print('抢购成功订单号:', order_id)
            return True

    
if __name__ == "__main__":

    items = {
        "3060": {
            "order_time" : "2020-12-21 22:06",
            "item_url" : "https://item.jd.com/8711257.html"
        }
    }

    jd = JD()
    jd.start(items)
    