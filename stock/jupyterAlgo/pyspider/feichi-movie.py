#-*- coding:utf-8 -*-

import json
try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib.request import urlopen, Request
import requests
requests.adapters.DEFAULT_RETRIES = 0

def get_url_data_R(url, timeout=30,headers=None):
    # headers = {'User-Agent':'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.6) Gecko/20091201 Firefox/3.5.6'}
    # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; rv:16.0) Gecko/20100101 Firefox/16.0',
    #            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #            'Connection': 'keep-alive'}
    
    # dictMerged2 = dict( dict1, **dict2 )
    # headersrc = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #        'Connection': 'keep-alive'}

    if headers is None:
        # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.2; rv:16.0) Gecko/20100101 Firefox/16.0',
        #            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        #            'Connection': 'keep-alive'}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
                   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                   'Connection': 'keep-alive'}
    # else:

    #     headers = dict({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    #                'Connection': 'keep-alive'},**headers)

               # 'Referer':'http://vip.stock.finance.sina.com.cn'
    # headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    #             'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    #             'Accept-Encoding': 'gzip, deflate',
    #             }
    # headers = {'Host': 'dcfm.eastmoney.com',
    #             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:75.0) Gecko/20100101 Firefox/75.0',
    #             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    #             'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    #             'Accept-Encoding': 'gzip, deflate',
    #             'Connection': 'keep-alive',
    #             'Cookie': 'qgqp_b_id=91b04a5f938180fcd61ff487773f9fdd; st_si=44229608519229; st_sn=17; st_psi=20200422151145626-113300300968-3614946978; st_asi=delete; emshistory=%5B%22%E8%9E%8D%E8%B5%84%E4%BD%99%E9%A2%9D617%22%2C%22%E8%9E%8D%E8%B5%84%E4%BD%99%E9%A2%9D%22%5D; cowCookie=true; intellpositionL=1380px; intellpositionT=1085px; st_pvi=50723143362736; st_sp=2020-04-22%2013%3A25%3A58; st_inirUrl=http%3A%2F%2Figuba.eastmoney.com%2F2822094037475512'
    #         }           
               
    req = Request(url, headers=headers)
    req.keep_alive = False
    try:
        fp = urlopen(req, timeout=timeout)
        data = fp.read()
        fp.close()
    # except (HTTPError, URLError) as error:
        # log.error('Data of %s not retrieved because %s\nURL: %s', name, error, url)
    except (socket.timeout, socket.error) as e:
        # print data.encoding
        data = ''

        print(('socket timed out error:%s - URL %s ' % (e, url)))
        sleeprandom(120)
    except Exception as e:
        data = ''
        print(('url Exception Error:%s - URL %s ' % (e, url)))
        # sleeprandom(60)
        sleep(120)
    # else:
        # print('Access successful.')
    return data


url='http://wozhui.zhuidianying.com/service/iBacManage.action?bizCode=12013&appID=3&type=2&search_terms=&label=&begDate=&endDate=&reBegDate=&reEndDate=&pageSize=1000&pageNo=1'

data=get_url_data_R(url, timeout=30, headers=None)
data_ = data.split('"params":')[1].split('{"data":')[1].split(',"currentPageNo"')[0]
# data_  = data__.split('],')[0]

js_data = json.loads(data_)
for item in js_data:
    title = dict(item)
    print((title['title'],title['gt_release_time'][:10]))

