import json
import requests
import os
import time
import io
from PyPDF2 import PdfReader, PdfWriter

current_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(current_dir)

global WX_ACCESS_TOKEN

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

timeout = config['send']['timeout']
wx_config = config['send']['wx']

wx_touser = wx_config['touser']
wx_agentId = wx_config['agentId']
wx_secret = wx_config['secret']
wx_companyId = wx_config['companyId']

def get_wx_token():
    global WX_ACCESS_TOKEN
    WX_ACCESS_TOKEN = None
    if os.path.exists('WX_ACCESS_TOKEN.txt'):
        txt_last_edit_time = os.stat('WX_ACCESS_TOKEN.txt').st_mtime
        now_time = time.time()
        if now_time - txt_last_edit_time < 7000:  # 2小时刷新
            with open('WX_ACCESS_TOKEN.txt', 'r') as f:
                WX_ACCESS_TOKEN = f.read()
    if not WX_ACCESS_TOKEN:
        try:
            r = requests.post(
                f'https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={wx_companyId}&corpsecret={wx_secret}', timeout=timeout).json()
        except Exception as e:
            print(f"获取通行密钥时发生错误: {e}")
            return
        WX_ACCESS_TOKEN = r["access_token"]
        with open('WX_ACCESS_TOKEN.txt', 'w', encoding='utf-8') as f:
            f.write(WX_ACCESS_TOKEN)

class SendManager:
    def __init__(self,openId,wx=False,dd=False,fs=False) -> None:
        self.wx=wx
        self.dd=dd
        self.fs=fs
        self.openId=openId

    def sendMsg(self,msg):
        print(msg)
        if self.wx:
            get_wx_token()
            if WX_ACCESS_TOKEN:
                send_wx_msg(msg_part(msg, wx_config['msgLimit']))
        if self.dd:
            get_dd_token()
            if DD_ACCESS_TOKEN:
                send_dd_msg(msg_part(msg, dd_config['msgLimit']))
        if self.fs:
            get_fs_token()
            if FS_ACCESS_TOKEN:
                send_fs_msg(msg_part(msg, fs_config['msgLimit']), self.openId)
    
    def sendImage(self,path):
        if not self.openId:
            return
        if self.wx:
            get_wx_token()
            if WX_ACCESS_TOKEN:
                send_wx_image(upload_wx_file(path))
        if self.dd:
            get_dd_token()
            if DD_ACCESS_TOKEN:
                send_dd_image(upload_dd_file(path))
        if self.fs:
            get_fs_token()
            if FS_ACCESS_TOKEN:
                send_fs_image(upload_fs_image(path), self.openId)

    def sendFile(self,path):
        if not self.openId:
            return
        if self.wx:
            get_wx_token()
            if WX_ACCESS_TOKEN:
                send_wx_file(upload_wx_file(path, wx_config['dataLimit']))
        if self.dd:
            get_dd_token()
            if DD_ACCESS_TOKEN:
                send_dd_file(upload_dd_file(path, dd_config['dataLimit']))
        if self.fs:
            get_fs_token()
            if FS_ACCESS_TOKEN:
                send_fs_file(upload_fs_file(path, fs_config['dataLimit']), self.openId)

def get_pdf_size(pdf_writer):
    temp_io = io.BytesIO()
    pdf_writer.write(temp_io)
    return temp_io.getbuffer().nbytes

def split_pdf(filepath, max_size):
    if os.path.getsize(filepath) < max_size:
        return [filepath]
    pdf = PdfReader(filepath)
    pdf_writer = PdfWriter()
    filepaths = []
    output_filename = f'{filepath[:-4]}_'
    start_page = 0
    for page in range(len(pdf.pages)):
        pdf_writer.add_page(pdf.pages[page])
        if get_pdf_size(pdf_writer) >= max_size:
            if start_page != page:
                if start_page == page - 1:
                    temp_filename = f'{output_filename}{start_page + 1}.pdf'
                    temp_pdf_writer=PdfWriter()
                    temp_pdf_writer.add_page(pdf.pages[start_page])
                else:
                    temp_filename = f'{output_filename}{start_page + 1}-{page}.pdf'
                    temp_pdf_writer = PdfWriter()
                    for i in range(start_page, page):
                        temp_pdf_writer.add_page(pdf.pages[i])
                with open(temp_filename, 'wb') as out:
                    temp_pdf_writer.write(out)
                filepaths.append(temp_filename)
                pdf_writer = PdfWriter()
                pdf_writer.add_page(pdf.pages[page])
                start_page = page
                if get_pdf_size(pdf_writer) >= max_size:
                    pdf_writer = PdfWriter()
                    start_page = page + 1
            else:
                pdf_writer = PdfWriter()
                start_page = page + 1
    if start_page != len(pdf.pages):
        if start_page == len(pdf.pages) - 1:
            temp_filename = f'{output_filename}{start_page + 1}.pdf'
            temp_pdf_writer = PdfWriter()
            temp_pdf_writer.add_page(pdf.pages[start_page])
        else:
            temp_filename = f'{output_filename}{start_page + 1}-{len(pdf.pages)}.pdf'
            temp_pdf_writer = PdfWriter()
            for i in range(start_page, len(pdf.pages)):
                temp_pdf_writer.add_page(pdf.pages[i])
        with open(temp_filename, 'wb') as out:
            temp_pdf_writer.write(out)
        filepaths.append(temp_filename)
    return filepaths

def msg_part(message, max_length):
    lines = [line for line in str(message).split('\n') if line.strip() != '']
    parts = []
    part = ''
    for line in lines:
        if len(line) < max_length:
            if part:
                new_length = len(part) + 1 + len(line)
            else:
                new_length = len(line)
            if new_length <= max_length:
                if part:
                    part += '\n' + line
                else:
                    part = line
            else:
                parts.append(part)
                part = line
        else:
            if part:
                parts.append(part)
                part = ''
            for i in range(0, len(line), max_length):
                parts.append(line[i:i+max_length])
    parts.append(part)
    return parts

def upload_wx_file(filepath, max_data=20971520):
    _, ext = os.path.splitext(filepath)
    if ext.lower() == '.pdf':
        filepaths = split_pdf(filepath, max_data)
    else:
        filepaths = [filepath]
    media_ids = []
    for path in filepaths:
        files={
            'file': open(path, 'rb')
        }
        try:
            r=requests.post(f'https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={WX_ACCESS_TOKEN}&type=file', files=files, timeout=timeout)
            if r.json()['errcode'] == 60020:
                print('企业微信文件上传失败: 未配置可信IP')
                return []
        except Exception as e:
            print(f"企业微信文件上传发生错误: {e}")
            return []
        media_ids.append(r.json()['media_id'])
    return media_ids

def send_wx_msg(parts):
    for part in parts:
        data = {
            "touser": wx_touser,
            "msgtype": "text",
            "agentid": wx_agentId,
            "text": {"content": f"{part}"}
        }
        data = json.dumps(data)
        try:
            r = requests.post(
                f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={WX_ACCESS_TOKEN}', data=data, timeout=timeout)
            if r.json()['errcode'] == 60020:
                print('企业微信消息发送失败: 未配置可信IP')
                return
        except Exception as e:
            print(f"企业微信消息发送发生错误: {e}")
            return
        time.sleep(1)

def send_wx_image(media_ids):
    for id in media_ids:
        data = {
            "touser": wx_touser,
            "msgtype": "image",
            "agentid": wx_agentId,
            "image":  {'media_id':id}
        }
        data = json.dumps(data)
        try:
            r = requests.post(
                f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={WX_ACCESS_TOKEN}', data=data, timeout=timeout)
            if r.json()['errcode'] == 60020:
                print('企业微信图片发送失败: 未配置可信IP')
                return
        except Exception as e:
            print(f"企业微信图片发送发生错误: {e}")
            return
        time.sleep(1)

def send_wx_file(media_ids):
    for id in media_ids:
        data = {
            "touser": wx_touser,
            "msgtype": "file",
            "agentid": wx_agentId,
            "file":  {'media_id':id}
        }
        data = json.dumps(data)
        try:
            r = requests.post(
                f'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={WX_ACCESS_TOKEN}', data=data, timeout=timeout)
            if r.json()['errcode'] == 60020:
                print('企业微信文件发送失败: 未配置可信IP')
                return
        except Exception as e:
            print(f"企业微信文件发送发生错误: {e}")
            return
        time.sleep(1)
