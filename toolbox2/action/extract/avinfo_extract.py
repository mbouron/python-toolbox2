# -*- coding: utf-8 -*-

import os
import os.path
import re

from toolbox2.action import Action, ActionException
from toolbox2.worker.ffprobe import FFprobeWorker
from toolbox2.worker.ffmpeg import FFmpegWorker


class AVInfo(object):

    RES_SD_PAL      = '720x576'
    RES_SD_PAL_VBI  = '720x608'
    RES_SD_NTSC     = '720x480'
    RES_SD_NTSC_VBI = '720x512'
    RES_HD          = '1920x1080'
    RES_HD_1280     = '1280x1080'
    RES_HD_1440     = '1440x1080'

    def __init__(self, data):
        self.data = data
        self.video_res = None
        self.video_has_vbi = False
        self.video_fps = 0
        self.video_dar = 0
        self.timecode = '00:00:00:00'
        self.video_streams = []
        self.audio_streams = []
        self.data_streams = []
        self.format = data['format']

        for stream in data['streams']:
            if stream['codec_type'] == 'video':
                self.video_streams.append(stream)
            elif stream['codec_type'] == 'audio':
                self.audio_streams.append(stream)
            else:
                self.data_streams.append(stream)

        if len(self.video_streams) > 0:
            self.video_res = '%sx%s' % (self.video_streams[0]['width'],
                                        self.video_streams[0]['height'])

        if self.video_res == self.RES_SD_PAL_VBI:
            self.video_has_vbi = True

        elif self.video_res == self.RES_SD_NTSC_VBI:
            self.video_has_vbi = True

        self._init_fps()
        self._init_dar()
        self._init_timecode()

    def _init_fps(self):
        if not self.video_streams:
            return

        match = re.match('(\d+)/(\d+)', self.video_streams[0]['r_frame_rate'])
        if match:
            (num, den) = match.groups()
            self.video_fps = round(float(num) / float(den), 2)

    def _init_dar(self):
        if not self.video_streams:
            return

        if 'display_aspect_ratio' in self.video_streams[0]:
            self.video_dar = self.video_streams[0]['display_aspect_ratio']

    def _init_timecode(self):
        self.timecode = '00:00:00:00'
        if 'timecode' in self.format['tags']:
            self.timecode = self.format['tags']['timecode']
        elif 'timecode_at_mark_in' in self.format['tags']:
            self.timecode = self.format['tags']['timecode_at_mark_in']
        elif len(self.video_streams) > 0 and 'timecode' in self.video_streams[0]:
            self.timecode = self.video_streams[0]['timecode']
        else:
            for stream in self.data_streams:
                if 'timecode' in stream['tags']:
                    self.timecode = stream['tags']['timecode']
                    break

    def video_has_VBI(self):
        return self.video_has_vbi

    def video_is_SD_PAL(self):
        return self.video_res in [self.RES_SD_PAL, self.RES_SD_PAL_VBI]

    def video_is_SD_NTSC(self):
        return self.video_res in [self.RES_SD_NTSC, self.RES_SD_NTSC_VBI]

    def video_is_HD(self):
        return self.video_res in [self.RES_HD, self.RES_HD_1280, self.RES_HD_1440]

    def video_is_SD(self):
        return not self.video_is_HD()

    def __repr__(self):
        return 'AVInfo (video_res=%s, video_has_vbi=%s, timecode=%s)' % (self.video_res, self.video_has_vbi, self.timecode)


class AVInfoActionException(ActionException):
    pass


class AVInfoAction(Action):
    """
    Extract audio/video information from media files using ffprobe/ffmpeg.
    """

    name = 'avinfo_extract'
    engine = 'ffmpeg'
    category = 'extract'
    description = 'audio/video information extract tool'
    required_params = {}

    def __init__(self, log, base_dir, _id, params, ressources):
        Action.__init__(self, log, base_dir, _id, params, ressources)
        self.input_file = None
        self.thumbnail = None
        self.probe_worker = None
        self.probe2_worker = None
        self.ffmpeg_worker = None

        if not os.path.isdir(self.tmp_dir):
            os.makedirs(self.tmp_dir)

        self.do_thumbnail = self.params.get('thumbnail', False)
        self.do_count_frames = self.params.get('count_frames', False)
        self.do_count_packets = self.params.get('count_packets', False)

    def _check(self):
        pass

    def _setup(self):

        self.input_file = self.get_input_ressource(1).get('path')
        self.thumbnail = os.path.join(self.tmp_dir, 'thumbnail.jpg')

        self.probe_worker = FFprobeWorker(self.log, {})
        self.probe_worker.add_input_file(self.input_file)
        self.workers.append(self.probe_worker)

        if self.do_thumbnail:
            self.ffmpeg_worker = FFmpegWorker(self.log, {})
            self.ffmpeg_worker.add_input_file(self.input_file)
            self.ffmpeg_worker.add_output_file(self.thumbnail)
            self.ffmpeg_worker.make_thumbnail()
            self.workers.append(self.ffmpeg_worker)
            self.add_output_ressource('thumbnail', self.thumbnail)

        if self.do_count_frames or self.do_count_packets:
            self.probe2_worker = FFprobeWorker(self.log, {})
            self.probe2_worker.add_input_file(self.input_file)
            if self.do_count_packets:
                self.probe2_worker.count_packets()
            if self.do_count_frames:
                self.probe2_worker.count_frames()
            self.workers.append(self.probe2_worker)

    def _callback(self, worker, user_callback):
        if worker in [self.probe_worker, self.probe2_worker]:
            self.update_metadata(worker.metadata)
        Action._callback(self, worker, user_callback)

    def _execute(self, callback):
        has_video_streams = False
        self.worker_count = len(self.workers)
        for self.worker_idx, worker in enumerate(self.workers):

            # If no video streams are detected, skip thumbnail
            if not has_video_streams and worker == self.ffmpeg_worker:
                continue

            self._execute_worker(worker, callback)
            if worker == self.probe_worker:
                has_video_streams = self.probe_worker.metadata['format']['nb_video_streams'] > 0
            elif worker == self.ffmpeg_worker:
                self.update_metadata({
                    'thumbnail': self.thumbnail,
                })

        self.progress = 100
        self._callback(self.workers[-1], callback)

    def _finalize(self):
        pass

    def run(self, callback=None):
        Action.run(self, callback)
        return AVInfo(self.get_metadata())
