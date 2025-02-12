import aiohttp
import asyncio
import time
from tqdm import tqdm
 
import random
 
questions = [
    "Why is the sky blue?", "Why do we dream?", "Why is the ocean salty?", "Why do leaves change color?",
    "Why do birds sing?", "Why do we have seasons?", "Why do stars twinkle?", "Why do we yawn?",
    "Why is the sun hot?", "Why do cats purr?", "Why do dogs bark?", "Why do fish swim?",
    "Why do we have fingerprints?", "Why do we sneeze?", "Why do we have eyebrows?", "Why do we have hair?",
    "Why do we have nails?", "Why do we have teeth?", "Why do we have bones?", "Why do we have muscles?",
    "Why do we have blood?", "Why do we have a heart?", "Why do we have lungs?", "Why do we have a brain?",
    "Why do we have skin?", "Why do we have ears?", "Why do we have eyes?", "Why do we have a nose?",
    "Why do we have a mouth?", "Why do we have a tongue?", "Why do we have a stomach?", "Why do we have intestines?",
    "Why do we have a liver?", "Why do we have kidneys?", "Why do we have a bladder?", "Why do we have a pancreas?",
    "Why do we have a spleen?", "Why do we have a gallbladder?", "Why do we have a thyroid?", "Why do we have adrenal glands?",
    "Why do we have a pituitary gland?", "Why do we have a hypothalamus?", "Why do we have a thymus?", "Why do we have lymph nodes?",
    "Why do we have a spinal cord?", "Why do we have nerves?", "Why do we have a circulatory system?", "Why do we have a respiratory system?",
    "Why do we have a digestive system?", "Why do we have an immune system?"
]
 
async def fetch(session, url):
    """
    参数:
        session (aiohttp.ClientSession): 用于请求的会话。
        url (str): 要发送请求的 URL。
    
    返回:
        tuple: 包含完成 token 数量和请求时间。
    """
    start_time = time.time()
 
    # 随机选择一个问题
    question = random.choice(questions) # <--- 这两个必须注释一个
 
    # 固定问题                                 
    # question = questions[0]             # <--- 这两个必须注释一个
 
    # 请求的内容
    json_payload = {
        "model": "deepseek-r1:8b",
        "messages": [{"role": "user", "content": question}],
        "stream": False,
        "temperature": 0.7 # 参数使用 0.7 保证每次的结果略有区别
    }
    async with session.post(url, json=json_payload) as response:
        response_json = await response.json()
        print(f"{response_json}")
        end_time = time.time()
        request_time = end_time - start_time
        completion_tokens = response_json['usage']['completion_tokens'] # 从返回的参数里获取生成的 token 的数量
        return completion_tokens, request_time
 
async def bound_fetch(sem, session, url, pbar):
    # 使用信号量 sem 来限制并发请求的数量，确保不会超过最大并发请求数
    async with sem:
        result = await fetch(session, url)
        pbar.update(1)
        return result
 
async def run(load_url, max_concurrent_requests, total_requests):
    """
    通过发送多个并发请求来运行基准测试。
    
    参数:
        load_url (str): 要发送请求的URL。
        max_concurrent_requests (int): 最大并发请求数。
        total_requests (int): 要发送的总请求数。
    
    返回:
        tuple: 包含完成 token 总数列表和响应时间列表。
    """
    # 创建 Semaphore 来限制并发请求的数量
    sem = asyncio.Semaphore(max_concurrent_requests)
    
    # 创建一个异步的HTTP会话
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        # 创建一个进度条来可视化请求的进度
        with tqdm(total=total_requests) as pbar:
            # 循环创建任务，直到达到总请求数
            for _ in range(total_requests):
                # 为每个请求创建一个任务，确保它遵守信号量的限制
                task = asyncio.ensure_future(bound_fetch(sem, session, load_url, pbar))
                tasks.append(task)  # 将任务添加到任务列表中
            
            # 等待所有任务完成并收集它们的结果
            results = await asyncio.gather(*tasks)
        
        # 计算所有结果中的完成token总数
        completion_tokens = sum(result[0] for result in results)
        
        # 从所有结果中提取响应时间
        response_times = [result[1] for result in results]
        
        # 返回完成token的总数和响应时间的列表
        return completion_tokens, response_times
 
 # https://blog.csdn.net/huapeng_guo/article/details/140033236
if __name__ == '__main__':
    import sys
 
    if len(sys.argv) != 3:
        print("Usage: python bench.py <C> <N>")
        sys.exit(1)
 
    C = int(sys.argv[1])  # 最大并发数
    N = int(sys.argv[2])  # 请求总数
 
    # vllm 和 ollama 都兼容了 openai 的 api 让测试变得更简单了
    url = 'http://192.168.50.189:11434/v1/chat/completions'
 
    start_time = time.time()
    completion_tokens, response_times = asyncio.run(run(url, C, N))
    end_time = time.time()
 
    # 计算总时间
    total_time = end_time - start_time
    # 计算每个请求的平均时间
    avg_time_per_request = sum(response_times) / len(response_times)
    # 计算每秒生成的 token 数量
    tokens_per_second = completion_tokens / total_time
 
    print(f'Performance Results:')
    print(f'  Total requests            : {N}')
    print(f'  Max concurrent requests   : {C}')
    print(f'  Total time                : {total_time:.2f} seconds')
    print(f'  Average time per request  : {avg_time_per_request:.2f} seconds')
    print(f'  Tokens per second         : {tokens_per_second:.2f}')
