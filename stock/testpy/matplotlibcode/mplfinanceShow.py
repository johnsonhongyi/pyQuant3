import matplotlib.pyplot as plt
import mplfinance.original_flavor as finance
# from mplfinance.original_flavor import candlestick_ohlc
import sys

# stdout=sys.stdout
sys.path.append('../../')
from JSONData import tdx_data_Day as tdd

def show_ohlc_upper(df):
    # 加载数据
    # df = pd.read_csv("data.csv")

    # 计算OHLC数据
    df =  df.rename(columns={'date': 'Date', "open":"Open","high":"High","low": "Low","close":"Close"})
    # df.Date = df.Date.apply(lambda x:x.replace('-',''))
    # pd.to_datetime()
    # df=df.dropna(subset=['upper'],how='any')
    # df=df.dropna(subset=['lower'],how='all')

    df=df[df.upper > 0]
    df=df.reset_index()
    
    df.Date = df.index
    # print(df.Date)
    ohlc = df[["Date", "Open", "High", "Low", "Close"]].values

    # 计算上轨和下轨
    # upper_band = df["Close"] + 0.5
    # lower_band = df["Close"] - 0.5
    upper_band = df["upper"]
    lower_band = df["lower"]

    # 计算当前价格的位置
    position = ['' for i in range(len(df))]
    for i in range(len(df)):
        if df["Close"][i] > upper_band[i]:
            position[i] = 'Upper Band'
        elif df["Close"][i] < lower_band[i]:
            position[i] = 'Lower Band'
        # else:
            # position[i] = 'Middle Band'

    # 绘制OHLC图
    fig, ax = plt.subplots()
    finance.candlestick_ohlc(ax, ohlc, width=0.6, colorup='g', colordown='r')

    # 添加上轨和下轨
    plt.plot(df["Date"], upper_band, 'r--', label='Upper Band')
    plt.plot(df["Date"], lower_band, 'g--', label='Lower Band')

    # 添加位置
    for i, txt in enumerate(position):
        plt.annotate(txt, (df["Date"][i], df["Close"][i]), xytext=(0,20), textcoords='offset points')

    # 添加图例
    plt.legend(loc='best')

    # 显示图形
    plt.show()

dfc = tdd.get_tdx_Exp_day_to_df('000002', dl=90).sort_index(ascending=True).reset_index()

show_ohlc_upper(dfc)