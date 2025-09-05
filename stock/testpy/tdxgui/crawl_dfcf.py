import requests
import json

def get_stock_changes_data(page_index=0, page_size=64):
    """
    Crawls stock change data from the Eastmoney API.

    Args:
        page_index (int): The page number to retrieve (starting from 0).
        page_size (int): The number of results per page.

    Returns:
        dict: A dictionary containing the parsed stock data, or None if an error occurs.
    """
    url = "https://push2ex.eastmoney.com/getAllStockChanges"
    params = {
        "type": "8202,8193,4,32,64,8207,8209,8211,8213,8215,8204,8203,8194,8,16,128,8208,8210,8212,8214,8216",
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "pageindex": page_index,
        "pagesize": page_size,
        "dpt": "wzchanges",
        "_": "1756897471029",  # This is a timestamp; Eastmoney uses it as a cache-buster.
    }
    
    # We will let the `requests` library handle the `cb` parameter
    # by parsing the JSON response directly.
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

        # The API returns a JSONP string, so we need to clean it.
        # The requests library has a built-in JSON decoder.
        # It's better to use response.json() instead of manual string stripping.
        data = response.json()
        return data

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None


def parse_stock_data(data):
    """
    Parses the relevant information from the API response.
    
    Args:
        data (dict): The dictionary containing the API response.

    Returns:
        list: A list of dictionaries, where each dictionary represents a stock.
    """
    if not data or not data.get('data') or not data['data'].get('diff'):
        print("No valid stock data found in the response.")
        return []

    stock_list = []
    for stock in data['data']['diff']:
        stock_info = {
            '代码': stock.get('f12'),
            '名称': stock.get('f14'),
            '最新价': stock.get('f2'),
            '涨跌幅': stock.get('f3'),
            '竞价金额': stock.get('f336'),
            '竞价净额': stock.get('f337'),
        }
        stock_list.append(stock_info)
    return stock_list

if __name__ == "__main__":
    # Get the data for the first page
    stock_data = get_stock_changes_data(page_index=0, page_size=64)
    
    if stock_data:
        parsed_list = parse_stock_data(stock_data)
        if parsed_list:
            for stock in parsed_list:
                print(stock)

