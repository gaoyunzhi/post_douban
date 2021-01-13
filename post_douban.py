#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tweepy
import yaml
import time
import plain_db
import webgram
import post_2_album
from bs4 import BeautifulSoup
import cached_url
import os
import export_to_telegraph

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
	if 'douban.com/' in url:
		return '\n\n' + url
	if 'telegra.ph' in url:
		soup = BeautifulSoup(cached_url.get(url, force_cache=True), 'html.parser')
		title = export_to_telegraph.getTitle(url)
		try:
			return title + ' ' + soup.find('address').find('a')['href']
		except:
			return ''
	return url

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

def getMediaSingle(url, api, album):
	cached_url.get(url, force_cache=True, mode='b')
	path = cached_url.getFilePath(url)
	if os.stat(path).st_size >= 4883 * 1024: # twitter limit
		return
	try:
		return api.media_upload(path).media_id
	except Exception as e:
		print('media upload failed:', str(e), album.url, url, path)

def getMedia(album, api):
	# tweepy does not support video yet. 
		# Hopefully they will support it soon: https://github.com/tweepy/tweepy/pull/1414
	# if album.video:
		# result = getMediaSingle(album.video, api, album)
		# if result:
		# 	return [result]
	result = [getMediaSingle(img, api, album) for img in album.imgs]
	return [item for item in result if item][:4]
		
def run():
	for channel in credential['channels']:
		auth = tweepy.OAuthHandler(credential['twitter_consumer_key'], credential['twitter_consumer_secret'])
		auth.set_access_token(credential['channels'][channel]['access_key'], credential['channels'][channel]['access_secret'])
		api = tweepy.API(auth)
		for album, post in getPosts(channel):
			status_text = getText(album, post)
			if len(status_text) > 280: 
				continue
			if existing.get(album.url):
				continue
			existing.update(album.url, -1) # place holder
			media_ids = [item for item in getMedia(album, api) if item]
			if not media_ids and (album.video or album.imgs):
				print('all media upload failed: ', album.url)
				continue
			if not status_text:
				status_text = album.url
			try:
				result = api.update_status(status=status_text, media_ids=media_ids)
			except Exception as e:
				if 'Tweet needs to be a bit shorter.' not in str(e):
					print('send twitter status failed:', str(e), album.url)
				continue
			existing.update(album.url, result.id)
			return # only send one item every 10 minute
			
if __name__ == '__main__':
	run()