"""Media accepted from an authenticated WeCom single-chat callback."""
import asyncio
import base64
from email.message import Message
import hashlib
from pathlib import Path
from urllib.parse import urlparse, unquote

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import httpx

MAX_BYTES = 8 * 1024 * 1024
CHUNK = 512 * 1024


def trusted_url(url):
    parts = urlparse(url)
    host = (parts.hostname or '').lower()
    allowed = ('work.weixin.qq.com', 'weixin.qq.com', 'qpic.cn')
    return (parts.scheme == 'https' and not parts.username and not parts.password
            and parts.port in (None, 443)
            and any(host == suffix or host.endswith('.' + suffix) for suffix in allowed))


def decrypt(data, encoded):
    try:
        key = base64.b64decode(encoded + '=' * (-len(encoded) % 4), validate=True)
        if len(key) != 32 or not data or len(data) % 16:
            raise ValueError()
        cipher = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
        plain = cipher.update(data) + cipher.finalize()
        padding = plain[-1]
        if not 1 <= padding <= 32 or plain[-padding:] != bytes([padding]) * padding:
            raise ValueError()
        return plain[:-padding]
    except (TypeError, ValueError, IndexError):
        raise ValueError('附件解密失败，请重新发送原文件。') from None


async def download_attachment(kind, metadata, client=None):
    url = metadata.get('url', '')
    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=12, follow_redirects=False)
    try:
        async with asyncio.timeout(25):
            for _ in range(4):
                if not trusted_url(url):
                    raise ValueError('附件地址不在支持的企业微信媒体域名内。')
                async with client.stream('GET', url, follow_redirects=False) as response:
                    if response.is_redirect and response.next_request:
                        url = str(response.next_request.url)
                        continue
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes(65536):
                        if len(data) + len(chunk) > MAX_BYTES + 32:
                            raise ValueError('附件超过 8 MiB。')
                        data.extend(chunk)
                    header = Message()
                    header['content-disposition'] = response.headers.get('content-disposition', '')
                    filename = metadata.get('filename') or header.get_filename() or Path(unquote(urlparse(url).path)).name
                    key = metadata.get('aeskey')
                    payload = decrypt(bytes(data), key) if key else bytes(data)
                    if kind == 'image' and not Path(filename or '').suffix:
                        if payload.startswith(b'\x89PNG'): filename = '图片.png'
                        elif payload.startswith(b'\xff\xd8\xff'): filename = '图片.jpg'
                        elif payload[8:12] == b'WEBP': filename = '图片.webp'
                    return unquote(filename or ''), payload
            raise ValueError('附件重定向次数过多。')
    except (httpx.HTTPError, TimeoutError):
        raise ValueError('附件下载失败或地址已过期，请重发文件。') from None
    finally:
        if owned:
            await client.aclose()


async def upload_file(request, name, data):
    if not data:
        raise ValueError('空文件无法发送。')
    count = (len(data) + CHUNK - 1) // CHUNK
    init = await request('aibot_upload_media_init', {
        'type': 'file', 'filename': name, 'total_size': len(data),
        'total_chunks': count, 'md5': hashlib.md5(data, usedforsecurity=False).hexdigest(),
    })
    upload_id = init.get('body', {}).get('upload_id')
    if not upload_id:
        raise ValueError('企业微信未返回素材上传编号。')
    for index in range(count):
        block = data[index * CHUNK:(index + 1) * CHUNK]
        await request('aibot_upload_media_chunk', {'upload_id': upload_id, 'chunk_index': index,
                                                  'base64_data': base64.b64encode(block).decode('ascii')})
    result = await request('aibot_upload_media_finish', {'upload_id': upload_id})
    media_id = result.get('body', {}).get('media_id')
    if not media_id:
        raise ValueError('企业微信未返回文件素材编号。')
    return media_id

