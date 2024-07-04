tdxZT='D:\\MacTools\\WinTools\\new_tdx2\\T0002\\hq_cache'

def read_stock_data_from_tdx():
    stock_data = []
    # for market_code in ['szm','shm','bjm']:
    for market_code in ['szm']:
        
        file_path = f'{tdxZT}\\{market_code}.tnf'
        print(f"正在读取:'{file_path}文件")
        with open(file_path,'rb') as file:
            buffer = file.read()
        
        buffer_slice = buffer[50:]
        data_length = len(buffer_slice) // 314
        decode_bytes_to_string = lambda x: str(x,encoding='gbk').strip('\x00')
        
        market_codes = {'szm':('00','30'),'shm':('60','68'),'bjm':('43','83','87')}
        
        data_slice =[buffer_slice[i * 314:(i+1) * 314] for i in range(data_length)]
        stock_data += [[decode_bytes_to_string(x[:6]),decode_bytes_to_string(x[23:41]),
                        decode_bytes_to_string(x[285:293])]
                       for x in data_slice
                       if decode_bytes_to_string(x[:6]).startswith(market_codes[market_code])]
        # for x in data_slice:
        #     if decode_bytes_to_string(x[:6]).startswith(market_codes[market_code]):
        #         print(x)
        #         import ipdb;ipdb.set_trace()
                


    return stock_data
                       

if __name__ == '__main__':

    stock_data = read_stock_data_from_tdx()
    print(stock_data[:5])
    import ipdb;ipdb.set_trace()
