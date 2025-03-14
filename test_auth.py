import requests
import json
import logging
import sys

# 设置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 确保输出显示在控制台
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

logger.info("脚本开始执行")

# API endpoint
url = "http://localhost:8000/api/auth/google"

# 请求数据
data = {"idToken": "test-token"}

# 发送请求
logger.info(f"发送请求到 {url}")
logger.info(f"请求数据: {json.dumps(data)}")

try:
    # 启用调试日志
    requests_log = logging.getLogger("urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True
    
    # 发送请求
    logger.info("开始发送POST请求")
    response = requests.post(url, json=data)
    logger.info("请求已发送，获取响应")
    
    logger.info(f"状态码: {response.status_code}")
    logger.info(f"响应头: {response.headers}")
    
    try:
        logger.info(f"响应内容: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    except:
        logger.info(f"响应文本: {response.text}")
except Exception as e:
    logger.error(f"请求出错: {str(e)}", exc_info=True)

logger.info("脚本执行完毕") 
