#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telethon import TelegramClient
import asyncio
import yaml
import time
import plain_db
import webgram
import post_2_album
from bs4 import BeautifulSoup
import cached_url
import os
import export_to_telegraph
from telegram_util import isCN, matchKey
import requests
import base64
from requests_toolbelt import MultipartEncoder

with open('credential') as f:
    credential = yaml.load(f, Loader=yaml.FullLoader)

existing = plain_db.load('existing')

Day = 24 * 60 * 60

def getPosts(channel):
    start = time.time()
    result = []
    posts = webgram.getPosts(channel)[1:]
    result += posts
    while posts and posts[0].time > (time.time() - 
            credential['channels'][channel]['back_days'] * Day):
        pivot = posts[0].post_id
        posts = webgram.getPosts(channel, posts[0].post_id, 
            direction='before', force_cache=True)[1:]
        result += posts
    for post in result:
        if post.time > time.time() - Day:
            continue
        try:
            yield post_2_album.get('https://t.me/' + post.getKey()), post
        except Exception as e:
            print('post_2_album failed', post.getKey(), str(e))

def getLinkReplace(url, album):
    if 'telegra.ph' in url and 'douban.com/note/' in album.cap_html:
        return ''
    if 'telegra.ph' in url:
        soup = BeautifulSoup(cached_url.get(url, force_cache=True), 'html.parser')
        title = export_to_telegraph.getTitle(url)
        try:
            return '\n\n【%s】 %s' % (title, soup.find('address').find('a')['href'])
        except:
            return ''
    return '\n\n' + url

def getText(album, post):
    soup = BeautifulSoup(album.cap_html, 'html.parser')
    for item in soup.find_all('a'):
        if item.get('href'):
            item.replace_with(getLinkReplace(item.get('href'), album))
    for item in soup.find_all('br'):
        item.replace_with('\n')
    text = soup.text.strip()
    if post.file:
        text += '\n\n' + album.url
    return text

with open('cookie') as f:
    cookie = f.read().strip()
with open('auth_token') as f:
    auth_token = f.read().strip()
with open('request_body_template') as f:
    request_body_template = f.read().strip()
headers = {}
headers['method'] = headers.get('method', 'POST')
headers['accept'] = headers.get('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/apng,*/*;q=0.8,application/signed-exchange;v=b3')
headers['user-agent'] = headers.get('user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36')
headers['cookie'] = cookie
headers['referer'] = 'https://www.douban.com/'
headers['origin'] = 'https://www.douban.com'
headers['host'] = 'www.douban.com'

def postMedia(fn):
    headers_copy = headers.copy()
    headers_copy['sec-ch-ua'] = '"Google Chrome";v="87", " Not;A Brand";v="99", "Chromium";v="87"'
    headers_copy['sec-ch-ua-mobile'] = '?0' 
    headers_copy['Sec-Fetch-Dest'] = 'empty'
    headers_copy['Sec-Fetch-Mode'] = 'cors'
    headers_copy['Sec-Fetch-Site'] = 'same-origin'
    # headers_copy['Content-Type'] = "multipart/form-data; boundary=----WebKitFormBoundaryqvxBU8yBTb28YrZ8"
    # print(request_body_template % fn[4:])
    fields = {
        'image': (fn[4:], open(fn, 'rb').read(), "image/" + fn.split('.')[-1]),
        'ck': "qaJS",
        'upload_auth_token': auth_token,
    }
    boundary = '----WebKitFormBoundaryqvxBU8yBTb28YrZ8'
    m = MultipartEncoder(fields=fields, boundary=boundary)

    headers_copy['Content-Type'] = m.content_type

    result = requests.post('https://www.douban.com/j/upload', 
        headers=headers_copy, 
        data=m)
    return result.json()['url']

async def getMediaSingle(post):
    fn = await post.download_media('tmp/')
    if not fn:
        return
    return postMedia(fn)

async def getMedia(posts):
    result = []
    for post in posts:
        media = await getMediaSingle(post)
        if media:
            result.append(media)
    return result

def matchLanguage(channel, status_text):
    if not credential['channels'][channel].get('chinese_only'):
        return True
    return isCN(status_text)

client_cache = {}
async def getTelethonClient():
    if 'client' in client_cache:
        return client_cache['client']
    client = TelegramClient('session_file', credential['telegram_api_id'], credential['telegram_api_hash'])
    await client.start(password=credential['telegram_user_password'])
    client_cache['client'] = client   
    return client_cache['client']

async def getChannelImp(client, channel):
    if channel not in credential['id_map']:
        entity = await client.get_entity(channel)
        credential['id_map'][channel] = entity.id
        with open('credential', 'w') as f:
            f.write(yaml.dump(credential, sort_keys=True, indent=2, allow_unicode=True))
        return entity
    return await client.get_entity(credential['id_map'][channel])
        
channels_cache = {}
async def getChannel(client, channel):
    if channel in channels_cache:
        return channels_cache[channel]
    channels_cache[channel] = await getChannelImp(client, channel)
    return channels_cache[channel]

def getGroupedPosts(posts):
    grouped_id = None
    result = []
    for post in posts[::-1]:
        if not grouped_id and not post.grouped_id:
            return [post]
        if not grouped_id:
            grouped_id = post.grouped_id
        if post.grouped_id == grouped_id:
            result.append(post)
    return result

async def getMediaIds(channel, post, album):
    if not album.imgs:
        return []
    client = await getTelethonClient()
    entity = await getChannel(client, channel)
    posts = await client.get_messages(entity, min_id=post.post_id - 1, max_id = post.post_id + 9)
    media_ids = await getMedia(getGroupedPosts(posts))
    return list(media_ids)

async def post_douban(channel, post, album, status_text):
    media_ids = await getMediaIds(channel, post, album)
    if not media_ids and (album.video or album.imgs):
        print('all media upload failed: ', album.url)
        return
    result = requests.post('https://www.douban.com/', headers=headers, data={
        'uploaded': '|'.join(media_ids), 'ck': 'qaJS', 'comment': status_text}) 
    result = result.status_code
    return result
    
async def run():
    for channel in credential['channels']:
        for album, post in getPosts(channel):
            if existing.get(album.url):
                continue
            if album.video and (not album.imgs):
                continue
            status_text = getText(album, post) or album.url
            if not matchLanguage(channel, status_text):
                continue
            if matchKey(status_text, ['维吾尔', '藏人', '西藏', 
                '我们今天需要的普世价值', '共同的经历和常识',
                '新疆', '香港']):
                # 上次在豆瓣上发相关内容差点被永久封号。。。。
                continue
            existing.update(album.url, -1) # place holder
            result = await post_douban(channel, post, album, status_text)
            existing.update(album.url, result)
            if 'client' in client_cache:
                await client_cache['client'].disconnect()
            return # only send one item every 10 minute
        
if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    r = loop.run_until_complete(run())
    loop.close()