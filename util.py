import requests
import json
import os
import re
import shutil
import qrcode
import pytz
from datetime import datetime as dt, timedelta, timezone as dt_timezone
from PIL import Image
from pyzbar.pyzbar import decode
from pytz import timezone
from concurrent.futures import ThreadPoolExecutor

current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

timeout = config['util']['timeout']
threads = config['util']['threads']
tz = timezone(config['util']['timezone'])

def download_qrcode(url, name):
    try:
        res=requests.get(url, timeout=timeout)
    except Exception as e:
        print(f"下载登录二维码时发生错误: {e}")
        return
    with open(f"{name}qrcode.jpg","wb") as f:
        f.write(res.content)
    print(f"登录二维码已保存为{name}qrcode.jpg")
    barcode_url = ''
    barcodes = decode(Image.open(f"{name}qrcode.jpg"))
    for barcode in barcodes:
        barcode_url = barcode.data.decode("utf-8")
    qr = qrcode.QRCode()
    qr.add_data(barcode_url)
    qr.print_ascii(invert=True)

def cookie_date(expires_matches):
    expires_datetimes = []
    for date_str in expires_matches:
        # 正确解析日期
        parsed_date = dt.strptime(date_str, '%a, %d-%b-%Y %H:%M:%S GMT')
        # 转换时区并计算时间戳
        utc_time = parsed_date.replace(tzinfo=timezone.utc)
        timestamp = int(utc_time.timestamp() * 1000)
        expires_datetimes.append(timestamp)
    return expires_datetimes

def clear_folder(folder_path):
    try:
        if os.path.isfile(folder_path) or os.path.islink(folder_path):
            os.unlink(folder_path)
        elif os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
    except Exception as e:
        print(f'删除 {folder_path} 时发生错误。原因: {e}')
    os.makedirs(folder_path)

def download_image(item, folder):
    if not item.get('cover'):
        return
    try:
        response = requests.get(item['cover'], timeout=timeout)
    except Exception as e:
        print(f"下载图片 {item['index']} 时发生错误: {e}")
        return
    if response.status_code == 200:
        file_path = os.path.join(folder, f"{item['index']}.jpg")
        with open(file_path, 'wb') as f:
            f.write(response.content)

def download_images_to_folder(slides, folder):
    with ThreadPoolExecutor(max_workers=threads) as executor:
        for item in slides:
            executor.submit(download_image, item, folder)

def images_to_pdf(folder, output_path):
    if not os.path.exists(folder):
        print(f'文件夹 {folder} 不存在')
        return
    image_files = [f for f in os.listdir(folder) if f.endswith(('.png', '.jpg', '.jpeg'))]
    if not image_files:
        print(f'文件夹 {folder} 中没有任何图片文件')
        return
    image_files.sort(key=lambda x: int(x.split('.')[0]))
    images = [Image.open(os.path.join(folder, f)).convert('RGB') for f in image_files]
    if images:
        images[0].save(output_path, save_all=True, append_images=images[1:])
        print(f'PDF文件已生成: {output_path}')
    else:
        print("没有找到任何图片文件")
    images[0].save(output_path, save_all=True, append_images=images[1:])

def convert_date(timestamp_ms):
    dt_obj = dt.fromtimestamp(timestamp_ms/1000, tz=dt_timezone.utc).astimezone(tz)
    return dt_obj  # 返回datetime对象而非字符串
    self.cookie_time = convert_date(int(date))

def check_time(target_dt, minutes):
    target_time_minus = target_dt - timedelta(minutes=minutes)
    current_time = dt.now(tz)
    remaining = (target_time_minus - current_time).total_seconds()
    return remaining

def check_time2(time_dict):
    today = str(datetime.now(tz).weekday() + 1)
    if today not in time_dict:
        return True
    time = time_dict[today]
    given_time = datetime.strptime(time, "%H:%M").time()
    current_time = datetime.now(tz).time()
    return current_time >= given_time

def format_json_to_text(json_data, list_data):
    index_data = []
    text_result = "问题列表:\n"
    for index, problem_info in json_data.items():
        if index in list_data:
            index_data.append(problem_info['index'])
        text_result += "-"*20 + "\n"
        body = problem_info.get('body', '未知问题')
        answers = problem_info.get('answers', [])
        text_result += f"PPT: 第{problem_info['index']}页\n问题: {body}\n"
        if 'options' in problem_info:
            for option in problem_info['options']:
                text_result += f"- {option['key']}: {option['value']}\n"
        if answers not in [[],None,'null']:
            answer_text = ', '.join(answers)
            text_result += f"答案: {answer_text}\n"
        else:
            text_result += "答案: 暂无\n"
    text_result += "已解锁问题:\n"
    if not index_data:
        text_result += "无\n"
    else:
        for item in index_data:
            text_result += f"- PPT第{item}页\n"
    return text_result

def check_answers_in_options(answers, options):
    option_keys = [option['key'] for option in options]
    if answers in [[],None,'null'] or any(answer not in option_keys for answer in answers):
        return False
    return True

def check_answers_in_blanks(answers, blanks):
    if answers in [[],None,'null'] or len(answers) != blanks or any(not answer for answer in answers):
        return False
    return True

async def recv_json(websocket):
    server_response = await websocket.recv()
    # print(f"Received from server: {server_response}")
    info=json.loads(server_response)
    return info
