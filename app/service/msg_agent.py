# -*- coding: utf-8 -*-
import os, gc
import pandas, numpy
import json, re, pdb
import runcmds
import multiprocessing
from datalib.CommandAgent import CommandAgent
from datasettings.settings import setting_config

def checkparams (cmdobj, cache = None):
    ctype = cmdobj['ctype']
    if cache is None or (not isinstance(cache, dict)):
        raise Exception('Runtime Error: %s without cache' % ctype)
    if 'src' not in cmdobj['ckeys']:
        raise Exception('Command Error: %s without src' % ctype)
    src = cmdobj['ckeys']['src']
    if src not in cache:
        raise Exception('Runtime Error: %s not in cache' % src)

def format_msg(message, extra = {}):
    channel_num = -1
    channel_type = 'text'
    channel_code = 200
    if 'channel' in extra:
        channel_num = extra['channel']
    if 'type' in extra:
        channel_type = extra['type']
    if 'code' in extra:
        channel_code = extra['code']
    if isinstance(message, dict) or isinstance(message, list):
        message = json.dumps(message)
    # 此处因为原始pd.DataFrame.to_json方法做改造
    elif channel_type != 'data':
        message = '"%s"' % message

    result = '{"code": %d, "data": %s, "type": "%s", "channel": %d}' % (channel_code, message, channel_type, channel_num)
    try:
        result = result.decode('unicode_escape')
    except:
        pass
    return {
        'text': result
    }

# def send_msg(channel, message, extra = {}):
#     message_sent = format_msg(message, extra)
#     channel.reply_channel.send(message_sent)

def send_msg(channel, message, extra = {}):
    message_sent = format_msg(message, extra)
    if 'queue' in channel:
        queue = channel['queue']
        channel_id = channel['id'] 
        channel_msg = message_sent
        queue.put((channel_id, channel_msg)) # 将消息扔到消息线程队列中
    else:
        channel = channel['channel']
        channel.reply_channel.send(message_sent)

def proxy_msg(msg_channel, cache = {}):
    content = msg_channel['text']
    channel = -1
    msg_type = 'text'
    message = ''
    try:
        json_data = json.loads(content)
        if 'channel' in json_data:
            channel = json_data['channel']
        if 'type' in json_data:
            msg_type = json_data['type']
        if 'message' in json_data:
            message = json_data['message']
            if not isinstance(message, unicode):
                try:
                    message = message.decode('utf-8', 'ignore')
                except:
                    message = message
        extra = {
            'channel': channel,
            'type': msg_type,
        }
        data_util = CommandAgent(setting_config)

        if msg_type == 'shell':
            if message.find('cleancache') >= 0:
                keys = list(cache.keys())
                for key in keys:
                    del cache[key]
                if 'savepath' in setting_config:
                    savepath = setting_config['savepath']
                    for filename in os.listdir(savepath):
                        if not isinstance(filename, unicode):
                            filename = filename.decode('utf-8', 'ignore')
                        filename = savepath + filename
                        if os.path.exists(filename):
                            os.remove(filename)
                        send_msg(msg_channel, '%s removed' % filename, extra = extra)
                gc.collect() # 手动回收内存
            else:
                runcmds.runcmds(message, msg_channel, cache, extra)

        elif msg_type == 'data':
            msg_obj = data_util.parsecmd(message)
            if msg_obj['ctype'] == 'pulldata':
                cmdkeys = msg_obj['ckeys']
                checkparams(msg_obj, cache)
                src = cmdkeys['src']
                node = cache[src].copy(deep = True)
                temp_cache = {
                    src: node
                }
                total = len(node)
                message = re.sub(r'^pulldata', 'filter', message)
                data = data_util.runcmd(message, temp_cache).fillna('')
                for column in data:
                    if unicode(data[column].dtype).find('datetime') >= 0:
                        data[column] = data[column].astype(unicode)
                data = data.to_json().replace('\\\"','\\\\\\\"')
                data = '{"total":%d,"data":%s}' % (total, data)
            send_msg(msg_channel, data, extra = extra)

        elif msg_type == 'command':
            msg_obj = data_util.parsecmd(message)
            if msg_obj['ctype'] == 'saveexcel' or msg_obj['ctype'] == 'savecsv':
                cmdkeys = msg_obj['ckeys']
                checkparams(msg_obj, cache)
                src = cmdkeys['src']
                node = cache[src].copy(deep = True)
                temp_cache = {
                    src: node
                }
                data_util.runcmd(message, temp_cache)
                # proc = multiprocessing.Process(target = data_util.runcmd, args = (message, temp_cache))
                # proc.daemon = False
                # proc.start()
                # proc.join()
                send_msg(
                    msg_channel,
                    { 'target': cmdkeys['tar'] },
                    extra = {
                        'channel': channel,
                        'type': 'filend',
                    }
                )
                # proc.terminate()
                return

        # send cache nodes
        cache_keys = list(cache.keys())
        cache_keys = map(lambda x: {'name': x, 'columns': list(cache[x].columns)}, cache_keys)
        send_msg(
            msg_channel,
            cache_keys,
            extra = {
                'channel': channel,
                'type': 'cache',
            }
        )
    except Exception as what:
        errmsg = 'global error: %r' % what
        send_msg(
            msg_channel,
            errmsg.replace('\"', '\\\\\"'),
            extra = {
                'type': 'error',
                'channel': extra['channel']
            }
        )
