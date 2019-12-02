"""
# ===============================================================================
#  Author: WangFan <sgwf525@126.com>
#  Version: 0.1
#  Description: 批量清空腾讯企业邮箱邮件
# ===============================================================================
"""
import re
import json
import asyncio
import aiohttp
import execjs
from PIL import Image
from lxml.html import InputElement
from lxml.html import SelectElement
from pyquery import PyQuery as pq


class EmailDeleter(object):

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36',
    }

    def __init__(self, username, password):
        self.client = None
        self.username = username
        self.password = password
        self.sid = None

    @staticmethod
    def serialize_ex(inputs: pq) -> Iterator:
        """html文件转为keys 和 vals 两个列表."""
        keys = []
        vals = []
        radios = {}
        for e in inputs:

            if not hasattr(e, 'name') or not e.name:
                continue

            name = e.name
            value = e.value if e.value is not None else ''

            if isinstance(e, InputElement):
                if e.type in ('radio',):  # and e.checked:
                    if name not in radios:
                        keys.append(name)
                        vals.append('')
                        radios[name] = value if e.checked else ''
                    elif e.checked:
                        radios[name] = value

                elif e.type == 'checkbox':
                    if e.checked:
                        keys.append(name)
                        vals.append(value)
                elif e.type == 'button':
                    continue
                else:
                    keys.append(name)
                    vals.append(value)

            elif isinstance(e, SelectElement):
                if not value:
                    value = e.value_options[0] if len(e.value_options) else ''
                keys.append(name)
                vals.append(value)

            else:
                keys.append(name)
                vals.append(value)

        for idx, key in enumerate(keys):
            if key in radios:
                vals[idx] = radios[key]

        assert len(keys) == len(vals)
        return zip(keys, vals)

    async def extract_login_form(self) -> pq:
        """提取登录表单"""
        url = 'https://exmail.qq.com/cgi-bin/loginpage'
        async with self.client.get(url, verify_ssl=False, proxy='http://10.10.9.45:8888',) as r:
            resp = await r.text()
        doc = pq(resp)
        form = doc('#loginForm')
        # now = time.time()
        # ts = int(now)
        ts = form('[name="ts"]').val()
        form('[name="pp"]').val(self.password)
        form('[name="inputuin"]').val(self.username)
        form('[name="uin"]').val(self.username.split('@')[0])
        form('[name="domain"]').val(self.username.split('@')[1])
        form('[name="btlogin"]').remove()  # 删除标签,无须作为参数
        content = f'{self.password}\n{ts}\n'
        with open('encrypt.js', 'r') as f:
            js = execjs.compile(f.read())
            p = js.call('Q', content)  # 执行处理好的js文件,返回加密串
        form('[name="p"]').val(p)
        return form

    # async def get_public_key(self):
    #     """获取rsa加密公钥"""
    #     url = 'https://rescdn.qqmail.com/bizmail/zh_CN/htmledition/js_biz/home/new_index/pkg47f67b.js'
    #     async with self.client.get(url, verify_ssl=False) as r:
    #         resp = await r.text()
    #     content = re.findall(r'setPublic\("(.*?)"\);', resp)[0]
    #     keys = content.split('","')
    #     return keys

    async def verif_code_login(self, resp: str) -> str:
        """登录时需要验证码"""
        url = 'https://exmail.qq.com'
        path = re.findall(r'x3egetTop\(\)\.location\.href=\\x22(.*?)\\x22\\x3c/script', resp)[0]
        path = path.replace('\\x26', '&')
        path = path.replace('\\x22', '')
        path = path.replace('+', '')
        url = url + path
        async with self.client.get(
                url,
                headers=self.headers,
                proxy='http://10.10.9.45:8888',
                verify_ssl=False
        ):
            pass
        url = 'https://exmail.qq.com/cgi-bin/getverifyimage?aid=23000101&f=html&ck=1&%22,Math.random(),%22'
        async with self.client.get(
                url,
                headers=self.headers,
                verify_ssl=False
        ) as r:
            resp = await r.content.read()
        with open('./captcha.jpg', 'wb') as f:
            f.write(resp)
        img = Image.open(f'./captcha.jpg')
        # loop = asyncio.get_running_loop()
        # loop.run_in_executor(None, img.show)
        img.show()
        capt = input('请输入图片里的验证码：')
        url = 'https://exmail.qq.com/cgi-bin/login'
        form = await self.extract_login_form()
        data = dict(self.serialize_ex(form(':input')))
        data['data-statistic-login-type'] = 'home_login'
        data['verifycode'] = capt
        async with self.client.post(
                url,
                data=data,
                headers=self.headers,
                verify_ssl=False
        ) as r:
            resp = await r.text()
        return resp

    async def login(self):
        """登录企业邮箱"""
        url = 'https://exmail.qq.com/cgi-bin/login'
        form = await self.extract_login_form()
        data = dict(self.serialize_ex(form(':input')))
        data['data-statistic-login-type'] = 'home_login'  # 与前端点击请求完全一致
        async with self.client.post(
                url,
                data=data,
                headers=self.headers,
                verify_ssl=False
        ) as r:
            resp = await r.text()
        if '正在登录腾讯企业邮箱' not in resp:
            # 需要输入验证码
            resp = await self.verif_code_login(resp)
        return resp

    async def get_folder_info(self, resp):
        """获取首页"""
        self.sid = sid = re.findall(r'"frame_html\?sid=(.*?)"', resp)[0]
        r = re.findall(r'targetUrl\+="\&r=(.*?)";', resp)[0]
        url = f'https://exmail.qq.com/cgi-bin/frame_html?sid={sid}&r={r}'
        async with self.client.get(
                url,
                headers=self.headers,
                verify_ssl=False
        ) as r:
            resp = await r.text()
        if self.username in resp:  # 校验是否登录成功
            print('登录成功')
        else:
            print('登录失败')
            exit()
        f = re.findall(r'originUserFolders = (.*?);', resp.replace('\n', ''))[1]
        f = f.replace('id', '"id"')  # 替换成json可处理的格式
        f = f.replace('name', '"name"')
        f = f.replace('father"id"', '"fatherid"')
        f = f.replace('unread', '"unread"')
        f = f.replace('children', '"children"')
        f = f.replace('level', '"level"')
        f = f.replace('isLeaf', '"isLeaf"')
        folder_info = json.loads(f)
        for i in folder_info:
            print(f'name:{i["name"]} id:{i["id"]}')

    async def delete_email(self, folder_id):
        """删除邮件"""
        url = f'https://exmail.qq.com/cgi-bin/foldermgr?sid={self.sid}'
        data = {
            'sid': self.sid,
            'fun': 'empty',
            'folderid': folder_id,
            'cleantrash': '',
        }
        async with self.client.post(
                url,
                data=data,
                headers=self.headers,
                verify_ssl=False
        ) as r:
            resp = await r.text()
        if '文件夹操作成功' in resp:
            print('删除成功')
        else:
            print('删除失败')

    async def run(self):
        self.client = aiohttp.ClientSession()
        resp = await self.login()
        await self.get_folder_info(resp)
        folder_id = input('输入指定邮箱id:')
        num = input('每次最多清空5000封邮件,请输入循环次数:')
        for _ in range(int(num)):
            await self.delete_email(folder_id)
            await asyncio.sleep(2)
        await self.client.close()


if __name__ == '__main__':
    e = EmailDeleter('wangfan@botpy.com', '******')
    asyncio.run(e.run())

