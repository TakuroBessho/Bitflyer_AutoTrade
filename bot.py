import _importpath
import numpy as np
import time
import datetime
import pybitflyer
import talib
import smtplib
from email.mime.text import MIMEText
import sqlite3
from requests_oauthlib import OAuth1Session
from api import sharedata
from models import manipulate_db
from api import coingecko


# ビットフライヤーのAPI鍵
API_KEY = "API公開鍵"
API_SECRET = "API秘密鍵"
api = pybitflyer.API(api_key=API_KEY, api_secret=API_SECRET)

# ツイッターのAPI鍵
CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET = sharedata.get_tweet_apikey()

twitter = OAuth1Session(
    CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
url = "https://api.twitter.com/1.1/statuses/update.json"


# データベースのパスを指定
dbpath = sharedata.get_db_path()

# データベースに接続する
c = sqlite3.connect(dbpath)
cur = c.cursor()
db = manipulate_db.DB()


def order_buy(amount):
    order = api.sendchildorder(product_code="FX_BTC_JPY",
                               child_order_type="MARKET",
                               side="BUY",
                               size=amount,
                               )
    return order


def order_sell(amount):
    order = api.sendchildorder(product_code="FX_BTC_JPY",
                               child_order_type="MARKET",
                               side="SELL",
                               size=amount,
                               )
    return order


def order_close(side, amount):
    """[ポジションをクローズする関数]

    Arguments:
        side {[str]} -- [sell or buy]
        amount {[float]} -- [取引量]
    """

    if side == 'buy':
        order = order_buy(amount)
    elif side == 'sell':
        order = order_sell(amount)


def send_mail(msg):
    SMTP_SERVER = "smtp.mail.yahoo.co.jp"
    SMTP_PORT = 587
    SMTP_USERNAME = ""  # 送信元アドレス
    SMTP_PASSWORD = ""  # パスワード
    EMAIL_FROM = ""  # 送信元アドレス
    EMAIL_TO = ""  # 送信先アドレス
    EMAIL_SUBJECT = "ビットフライヤーの自動取引プログラムの運用報告について"
    co_msg = msg
    msg = MIMEText(co_msg)
    msg['Subject'] = EMAIL_SUBJECT
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    mail = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    mail.login(SMTP_USERNAME, SMTP_PASSWORD)
    mail.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
    mail.quit()


def create_tweet(ticker, side):
    if side == 'buy':
        tweet = d + '　' + ticker + 'を' + str(get_ticker()) + 'でロングしました'
    elif side == 'sell':
        tweet = d + '　' + ticker + 'を' + str(get_ticker()) + 'でショートしました'
    else:
        tweet = d + '　' + ticker + 'は' + str(get_ticker()) + 'でノーポジです'
    return tweet


def tweet_position(side):
    tweet = create_tweet(ticker, side)
    params = {"status": tweet}
    res = twitter.post(url, params=params)
    if res.status_code == 200:
        print("Success.")
        print(tweet)
    else:
        print("Failed. : %d" % res.status_code)
    return


def order_process(flag, side):
    """[取引処理の一連の流れを記述した関数]

    Arguments:
        flag {[bool]} -- [入ってきたものと反対のflagを返す]
        side {[buy or sell]} -- [入ってきたものと反対のモノを返す]

    Returns:
        [tuple] -- [取引終了後にsideとflagをそれぞれ逆にして戻り値に渡す]
    """
    balances = api.getcollateral()['collateral']
    amount = round(balances / get_ticker(), 2) 

    if side == 'buy':
        order_buy(amount=amount)
        balances = api.getcollateral()['collateral']
        base_msg = create_base_msg(get_ticker(), balances, rate)
        botmsg = create_bot_msg(base_msg, d, amount, side, singnal)
        db.bot_insert_db((d, bot_num, exchange, balances, side))
        send_mail(botmsg)
        tweet_position(side)
        side = 'sell'
    elif side == 'sell':
        order_sell(amount=amount)
        balances = api.getcollateral()['collateral']
        base_msg = create_base_msg(get_ticker(), balances, rate)
        botmsg = create_bot_msg(base_msg, d, amount, side, singnal)
        db.bot_insert_db((d, bot_num, exchange, balances, side))
        send_mail(botmsg)
        tweet_position(side)
        side = 'buy'
    else:
        balances = api.getcollateral()['collateral']
        base_msg = create_base_msg(get_ticker(), balances, rate)
        botmsg = create_bot_msg(base_msg, d, amount, 'no', singnal)
        db.bot_insert_db((d, bot_num, exchange, balances, 'no'))
        send_mail(botmsg)
        tweet_position(side)

    if flag:
        flag = False
    else:
        flag = True
    return flag, side, amount


def algorithmic_trade(flag):
    """[トレードのロジック部分を記述した関数]

    Arguments:
        flag {[bool]} -- [trueかfalse]

    Returns:
        [tuple] -- [注文サイドとフラグを引く継ぐ]
    """

    if momentam[-1] > 0 and macd[2][-1] > 0:
        flag, side, amount = order_process(flag, 'buy')
        print(d, 'buyBTC')
    elif momentam[-1] > 0 and 0 > macd[-1] > 0:
        flag, side, amount = order_process(flag, 'sell')

        print(d, 'sellBTC', side)
    else:
        order_process(flag, 'no')
        side = 'no'
        amount = round(balances / get_ticker(), 2)
        print(d, 'no trade')
    return flag, side, amount


def get_ticker():
    json = api.ticker(product_code=product_code)
    return json["ltp"]


def create_base_msg(latestprice, bal, rate):
    """[メールの本文を作成する関数1]

    Arguments:
        latestprice {[int]} -- [最新価格]
        bal {[int]} -- [口座残高]
        rate {[float]} -- [証拠金維持率]

    Returns:
        [str] -- [メール本文]
    """

    # 残高情報が上書きされないのでここで再取得する(そもそも残高をグローバル環境が持ってくる必要がない)
    bal = api.getcollateral()['collateral']
    msg = 'さくらVPSのmomentam.pyの運用状況について'\
        'メール報告を行います。 \n \n現在のビットフライヤーLightningにおける \n'\
        'ビットコイン最新価格は' + str(latestprice) + \
        '円、\n\nFX口座の証拠金残高は' + str(bal) + '円、' \
        '証拠金維持率は' + str(rate) + '%になっています。 \n \n'
    return msg


def create_bot_msg(base_msg, date, amount, order, signal):
    """[メールに送る本文を作成する関数2]]

    Arguments:
        date {[str]} -- [日付]
        amount {[int]]} -- [売買量]
        order {str} -- [注文方式 売りor買いorNO]
        signal {[tuple]} -- [使用しているトレードシグナル]
    """

    if order == 'no':
        botmsg = base_msg + '\n' + date +\
                 'はno_tradeでした。 \n ' + 'momsignal:' + str(signal[0])\
                 + ' ' + 'macdsignal:' + str(signal[1])
    elif order == 'close':
        botmsg = base_msg + '\n' + d + 'にポジションをCloseしました。 \n ' + 'momsignal:' + \
                 str(momsignal) + '  \n' + 'macdsignal:' + str(macdsignal)
    else:
        botmsg = base_msg + date + 'に' + str(amount) + 'BTCを' + order + 'しました。 \n ' + \
                'momsignal:' + str(signal[0]) + '  \n' + 'macdsignal:' + str(signal[1])
    return botmsg


# ｰｰｰｰｰｰーｰｰｰｰｰｰーーbot本体の処理ｰｰｰｰｰｰーｰｰｰｰｰｰーーｰｰｰｰｰｰ#

# 初期設定
flag = True
product_code = "FX_BTC_JPY"
ticker = 'Bitcoin'
exchange = 'bitflyer'
bot_num = 1


# whileでエラーが起こるまで取引し続ける
try:
    while True:
        # 価格取得&シグナル算出 botを走らせる前準備
        bitcoin_price = coingecko.get_fullprice('bitcoin', terms='max')
        bitcoin_price = coingecko.get_price(bitcoin_price)['price']
        numpyprice = np.array(bitcoin_price)
        macd = talib.MACD(numpyprice, 15, 17, 3)
        momentam = talib.MOM(numpyprice, timeperiod=6)
        momsignal = round(momentam[int(len(momentam)-1)] / bitcoin_price[int(len(bitcoin_price) - 1)] * 100, 2)
        macdsignal = round(macd[2][int(len(macd[2])-1)] / bitcoin_price[int(len(bitcoin_price) - 1)] * 100, 2)

        # 今日の価格情報と自分の口座残高を把握する
        balances = api.getcollateral()['collateral']
        rate = round(api.getcollateral()['keep_rate'] * 100, 2)
        d = datetime.datetime.today().strftime("%Y-%m-%d %H:%M:%S")
        singnal = (momsignal, macdsignal)

        if flag:
            flag, side, amount = algorithmic_trade(flag)
            print(flag, side, amount)
        else:
            order_close(side, amount)
            balances = api.getcollateral()['collateral']
            base_msg = create_base_msg(get_ticker(), balances, rate)
            botmsg = create_bot_msg(base_msg, d, amount, 'close', singnal)
            send_mail(botmsg)
            print(d, 'close_BTC')
            flag = True
            flag, side, amount = algorithmic_trade(flag)
            print(flag, side, amount)
        time.sleep(86400)

except Exception as e:
    botmsg = base_msg + d + \
        'にビットフライヤーのプログラムにエラーが発生しました \n ' + \
        'モメンタムシグナルは' + str(momsignal) + 'です。 \n ' + \
        'macdシグナルは' + str(macdsignal) + str(e.args)
    send_mail(botmsg)
    print('bitflyer01', e.args)
