from flask import Flask, request, jsonify
import requests
import logging
from urllib.parse import unquote
import re
from datetime import datetime
import time
import threading
from collections import OrderedDict
import os

# 作者：乾堃氏族:鲲鹏_Roc
# 版本：1.0.1
# 说明：本Python程序用于将AlecaFrame的消息通过企业微信Webhook转发到指定的企业微信群组中。
# 注意：请确保你已经在企业微信中创建了一个Webhook，并将其地址替换到代码中的WECHAT_WEBHOOK_URL变量中。
# 另外，确保你已经安装了Flask和requests库，可以使用pip install flask requests命令进行安装。
# 该脚本使用Flask框架搭建了一个简单的Web服务器，监听9090口，并处理POST请求。
# 当收到请求时，它会解析请求体中的消息内容，并进行一些处理和过滤，然后将处理后的消息通过企业微信Webhook发送到指定的微信群组中。
# 该脚本还实现了消息去重功能，避免重复发送相同的消息。消息缓存会在2分钟内有效，超过时间后会被清除。
# 如果你有任何问题或建议，请随时联系我。谢谢！
# 如果这个程序帮助到了你，可以在Warframe给我留个好评，哈哈：https://warframe.market/zh-hans/profile/Qian.Kun
# Github地址：https://github.com/AdminRoc/AlecaFrameWebhookForwarder
# 使用文档地址：https://qcnye09jdqm2.feishu.cn/docx/Cyi7dgT5Woi3IGxFIfyc6h4ynlc?from=from_copylink
# 交易模式焚诀：https://api.xiaoheihe.cn/v3/bbs/app/api/web/share?h_camp=link&h_src=YXBwX3NoYXJl&link_id=16e971c39cec （文档地址在视频下方的文本里）

app = Flask(__name__)

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

WECHAT_WEBHOOK_URL = os.getenv("WECHAT_WEBHOOK_URL", "************这里填写你自己机器人的WebHook地址**************注意：AlecaFrame设置里的Webhook地址填写：http://127.0.0.1:9090/wechat_forward")
EXCLUDE_KEYWORDS = {"Warframe.x64.exe", "Warframe"}
MESSAGE_CACHE = OrderedDict()  
CACHE_LOCK = threading.Lock()  
CACHE_EXPIRY = 120  

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@app.route('/wechat_forward', methods=['POST'])
def forward_to_wechat():
    if "************" in WECHAT_WEBHOOK_URL:
        logging.error("请注意：你还没有配置企业微信Webhook地址！请用记事本打开代码，修改第28行！此外，请不要忘记在AlecaFrame设置里的Webhook地址填写：http://127.0.0.1:9090/wechat_forward")
        return jsonify({"status": "error", "message": "未配置Webhook地址"}), 500
    
    try:
        raw_body = request.get_data().decode('utf-8', errors='ignore')
        logging.info("原始请求体：%s", raw_body)

        raw_data = request.get_json(silent=True)
        if raw_data is None:
            raw_data = request.form.to_dict()

        message_content = ""
        if "content" in raw_data:
            message_content = unquote(raw_data["content"]).strip()
        elif raw_body:
            message_content = unquote(raw_body.split('=')[-1] if '=' in raw_body else raw_body).strip()

        message_content = re.sub(r'\*{2,}', '', message_content)  
        player_name = re.search(r'<PLAYER_NAME>(.*?)</PLAYER_NAME>', message_content)
        cleaned_content = message_content
        if player_name:
            player = player_name.group(1).strip()
            cleaned_content = message_content.replace(f'<PLAYER_NAME>{player}</PLAYER_NAME>', f'**{player}**')

        if any(keyword in cleaned_content for keyword in EXCLUDE_KEYWORDS):
            logging.warning("检测到排除关键词，已过滤消息：%s", cleaned_content)
            return jsonify({"status": "filtered", "message": "包含敏感关键词"}), 200

        with CACHE_LOCK:
            current_time = time.time()
            expired = [msg for msg, ts in MESSAGE_CACHE.items() if current_time - ts > CACHE_EXPIRY]
            for msg in expired:
                del MESSAGE_CACHE[msg]
            
            if cleaned_content in MESSAGE_CACHE:
                logging.warning("他妈的，这条消息在2分钟内被发送过了，我就不给你转发到企业微信了：%s", cleaned_content)
                return jsonify({"status": "filtered", "message": "重复消息"}), 200
            
            MESSAGE_CACHE[cleaned_content] = current_time
            if len(MESSAGE_CACHE) > 1000:
                MESSAGE_CACHE.popitem(last=False)

        receive_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_format = f"##### <font color=\"info\">{receive_time}</font>"

        main_title = "# Warframe出现新信息！请尽快使用电脑查收！"  
        sub_title = "## 接收到的内容"  
        content_section = f"{cleaned_content}" if cleaned_content else "(无具体消息内容)"
        
        md_content = f"""
{main_title}

{sub_title}
{content_section}

{time_format}
""".strip()

        wechat_payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": md_content
            }
        }

        response = requests.post(
            WECHAT_WEBHOOK_URL,
            json=wechat_payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        response.raise_for_status()
        logging.info("企业微信响应：%s", response.json())
        return jsonify({"status": "success"}), 200

    except requests.exceptions.HTTPError as e:
        logging.error("企业微信接口错误：%s", str(e), exc_info=True)
        return jsonify({"status": "error", "message": "消息发送失败"}), 500
    except requests.exceptions.RequestException as e:
        logging.error("网络请求异常：%s", str(e))
        return jsonify({"status": "error", "message": "消息发送超时或失败"}), 500
    except Exception as e:
        logging.error("数据处理失败：%s", str(e), exc_info=True)
        return jsonify({"status": "error", "message": "数据解析失败"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=9090, debug=False)