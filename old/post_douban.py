#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import plain_db
import webgram
import requests

with open('cookie') as f:
    cookie = f.read().strip()

existing = plain_db.load('existing')

Day = 24 * 60 * 60

def getPosts(channel):
    start = time.time()
    result = []
    posts = webgram.getPosts(channel)[1:]
    result += posts
    while posts and posts[0].time > (time.time() - 2 * Day):
        pivot = posts[0].post_id
        posts = webgram.getPosts(channel, posts[0].post_id, 
            direction='before', force_cache=True)[1:]
        result += posts
    for post in result:
        if post.time > time.time() - Day:
            continue
        for item in post.soup.find_all('a'):
            if item.text == 'source':
                yield item['href']
                break

def postDouban(status):
    headers = {}
    headers['method'] = headers.get('method', 'POST')
    headers['accept'] = headers.get('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/apng,*/*;q=0.8,application/signed-exchange;v=b3')
    headers['user-agent'] = headers.get('user-agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.97 Safari/537.36')
    headers['cookie'] = cookie
    headers['referer'] = 'https://www.douban.com'
    result = requests.post('https://www.douban.com/j/status/reshare', headers=headers, data={
        'sid': status, 'ck': '3DCH', 'text': ''}) 
    
def run():
    for post in getPosts('douban_read'):
        if existing.get(post):
            continue
        if 'status' not in post:
            continue
        status = int(post.strip('/').split('/')[-1])
        postDouban(status)
        existing.update(post, 1)
        return # only send one item every 10 minute
            
if __name__ == '__main__':
    run()