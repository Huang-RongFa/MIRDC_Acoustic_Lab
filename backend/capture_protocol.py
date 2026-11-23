"""Validate browser capture telemetry before sharing it with room peers."""
import math


def capture_settings(message):
    rate = message.get('requested_sample_rate')
    count = message.get('requested_channel_count')
    if type(rate) is not int or rate not in (44100, 48000) or type(count) is not int or count not in (1, 2):
        raise ValueError('invalid capture request')
    result = {'requested_sample_rate': rate, 'requested_channel_count': count}
    for field, low, high in [('actual_sample_rate',8000,384000),('input_sample_rate',8000,384000),('channel_count',1,2)]:
        value = message.get(field)
        if value is not None and (type(value) is not int or not low <= value <= high):
            raise ValueError('invalid capture capability')
        result[field] = value
    status = message.get('support_status')
    if status not in ('ready','unavailable') or (status=='ready' and (result['actual_sample_rate'] is None or (count==2 and result['channel_count']!=2))):
        raise ValueError('unverified stereo capability')
    result['support_status'] = status
    return result


def preview_channels(message):
    channels = message.get('channels', [message.get('samples')])
    if not isinstance(channels,list) or not 1 <= len(channels) <= 2:
        return None
    size = None
    for channel in channels:
        if not isinstance(channel,list) or not 1 <= len(channel) <= (128 if 'channels' in message else 256):
            return None
        if size is not None and size != len(channel):
            return None
        size = len(channel)
        if not all(type(x) in (int,float) and math.isfinite(x) and -1 <= x <= 1 for x in channel):
            return None
    return channels
