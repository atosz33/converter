from __future__ import unicode_literals
import json
import sys
import hashlib
import datetime
import os
import logging
import youtube_dl
import unidecode
import uuid
import websockets
import asyncio
from utils import glog
from utils.utils import get_timestamp
from utils.logger import app_logger

APP_PATH = os.environ.get('APP_PWD')
DURATION_LIMIT = 600
target_client = None
st = get_timestamp(time_format='%Y-%m-%d_%H-%M')


async def notify(payload):
    async with websockets.connect(os.environ.get('SOCKET_URI')) as websocket:
        await websocket.send(str(payload).encode())


def progress_hook(d):
    progress_client_id = 'progress-'+str(uuid.uuid4())
    try:
        tb = int(d['total_bytes'])
    except KeyError:
        tb = int(d['total_bytes_estimate'])
    payload = {
        'name': progress_client_id,
        'target': target_client,
        'type': 'progress'
    }
    if d['status'] == 'downloading':
        percent = ('{0:.' + str(1) + 'f}').format(100 *
                                                  (int(d['downloaded_bytes']) / float(tb)))
        payload['percent'] = percent
    elif d['status'] == 'finished':
        payload['message'] = 'Finishing ...'
    asyncio.run(notify(payload))


def download(urls, audio_format='mp3', audio_quality='128', action_from='web', target=None):
    global target_client
    target_client = target
    # generate random dir name
    dir_name = uuid.uuid4().hex
    dir_path = os.path.join(APP_PATH+'/web/files/', dir_name)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    ydl_opts = {
        'forceurl': True,
        'writethumbnail': True,
        'writeinfojson': True,
        'noplaylist': True,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': audio_quality,
        }],
        # 'logger': BasicLogger(urls=urls),
        'outtmpl': dir_path + '/%(title)s.%(ext)s',
    }
    if target:
        ydl_opts['progress_hooks'] = [progress_hook]

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(urls[0], download=False)
        if 'is_live' in info:
            if info['is_live']:
                return json.dumps({
                    'status': False,
                    'code': 'live_video',
                    'error': 'Your requested video is live streaming, and can not be downloaded.'
                })
        if int(info['duration']) > DURATION_LIMIT:
            return json.dumps({
                'status': False,
                'code': 'exceed_time',
                'error': 'Only videos less than {} minutes could be processed for now.'.format(int(DURATION_LIMIT/60))
            })

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download(urls)
        dir_list = os.listdir(dir_path)
        thumb = None
        filename = None
        title = False
        video_id = None
        for f_name in dir_list:
            # remove accents from file name for accented language and etc ...
            if not title:
                base = os.path.basename(f_name)
                title = os.path.splitext(base)[0]
            new_file = unidecode.unidecode(f_name)
            # then rename it
            os.rename(dir_path + '/' + f_name, dir_path + '/' + new_file)
            if new_file.endswith('.' + audio_format):
                filename = new_file
                file_size = os.path.getsize(dir_path + '/' + new_file)
            if new_file.endswith('.jpg'):
                thumb = new_file
            if new_file.endswith('.json'):
                with open(dir_path + '/' + new_file) as f:
                    data = json.load(f)
                video_id = data['id']
        json_result = json.dumps({
            'status': True,
            'data': {
                'id': video_id,
                'title': title,
                'path': dir_name,
                'filename': filename,
                'thumb': thumb,
                'extenstion': '.' + audio_format
            }
        })
        return json_result
    except (youtube_dl.utils.DownloadError, youtube_dl.utils.ExtractorError):
        return json.dumps({
            'status': False,
            'code': 'not_found',
            'error': 'This video is unavailable.'
        })


if __name__ == '__main__':
    print(download(['https://www.youtube.com/watch?v=QG9M6IcU000']))
