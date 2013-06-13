# -*- coding: utf-8 -*-

import os
import os.path

from toolbox2.action import Action, ActionException
from toolbox2.action.extract.avinfo_extract import AVInfoAction
from toolbox2.worker.ffmpeg import FFmpegWorker
from toolbox2.worker.qtfaststart import QtFastStartWorker
from toolbox2.utils.dcp import DCPTrailer


class TranscodeDCPException(ActionException):
    pass


class TranscodeDCPAction(Action):
    """
    Transcode trailer DCPs to H264 15mbps HiP@4.0/MP4
    """

    name = 'transcode_dcp'
    engine = ['ffmpeg']
    category = 'transcode'
    description = 'transcode dcp trailers to H264 15mbps HiP@4.0/MP4'
    required_params = {}

    def __init__(self, log, base_dir, _id, params=None, resources=None):
        Action.__init__(self, log, base_dir, _id, params, resources)

        if not os.path.isdir(self.tmp_dir):
            os.makedirs(self.tmp_dir)

        self.video_burn = int(self.params.get('video_burn', 0))
        self.video_bitrate = int(self.params.get('video_bitrate', 15000))
        self.video_decoder = self.params.get('video_decoder', 'libopenjpeg')

        self.audio_language = self.params.get('audio_language', 'fr')

        self.container_hinting = int(self.params.get('container_hinting', 0))

        self.decoding_threads = int(self.params.get('decoding_threads', 1))
        self.encoding_threads = int(self.params.get('encoding_threads', 1))

        self.burn_options = {
            'box': int(self.params.get('video_burn_box', 0)),
            'text': self.params.get('video_burn_text', ''),
            'timecode': int(self.params.get('video_burn_timecode', 0)),
            'position': self.params.get('video_burn_position', 'center'),
            'fontname': self.params.get('video_burn_fontname', 'vera'),
            'fontsize': int(self.params.get('video_burn_fontsize', 12)),
            'padding': int(self.params.get('video_burn_padding', 10)),
        }

    def _get_avinfo(self, essence_path):
        avinfo_action = AVInfoAction(self.log, self.base_dir, self.id)
        avinfo_action.add_input_resource(1, {'path': essence_path})
        return avinfo_action.run()

    def _setup(self):
        dcp_path = self.get_input_resource(1).get('path')
        dcp_nb_video_frames = self.get_input_resource(1).get('nb_video_frames', 0)
        dcp = DCPTrailer(self.log, dcp_path)

        if not dcp.video_essences:
            raise TranscodeDCPException('No video essence found in DCP package %s' % dcp_path)

        if not dcp.audio_essences:
            raise TranscodeDCPException('No audio essence found in DCP package %s' % dcp_path)

        picture_essence = dcp.video_essences[0]['path']
        picture_avinfo = self._get_avinfo(picture_essence)
        if not picture_avinfo.video_streams:
            raise TranscodeDCPException('No video stream found in DCP essence %s' % dcp.video_essences[0]['path'])

        picture_opts = {'video_opts': []}
        picture_codec = picture_avinfo.video_streams[0]['codec_name']
        if picture_codec == 'jpeg2000' and self.video_decoder:
            picture_opts['video_opts'].append(
                ('-codec:v', self.video_decoder)
            )

        # Select audio essence by language
        audio_essence = None
        for essence in dcp.audio_essences:
            if essence['language'] == self.audio_language:
                audio_essence = essence['path']
                break

        if not audio_essence:
            audio_essence = dcp.audio_essences[0]['path']

        audio_avinfo = self._get_avinfo(audio_essence)

        ffmpeg = self._new_worker(FFmpegWorker)
        ffmpeg.add_input_file(picture_essence, picture_opts, picture_avinfo)
        ffmpeg.add_input_file(audio_essence, {}, audio_avinfo)
        ffmpeg.set_nb_frames(dcp_nb_video_frames)
        ffmpeg.set_threads(self.decoding_threads, self.encoding_threads)

        ffmpeg.video_opts = [
            ('-codec:v', 'libx264'),
            ('-pix_fmt', 'yuv420p'),
            ('-preset', 'slow'),
            ('-tune', 'film'),
            ('-profile:v', 'high'),
            ('-level', '4.0'),
            ('-b:v', '%sk' % self.video_bitrate),
            ('-x264opts', 'vbv-bufsize=%s' % self.video_bitrate),
            ('-keyint_min', 25),
            ('-aspect', '16:9'),
            ('-map', '0:0'),
        ]

        ffmpeg.audio_opts = [
            ('-acodec', 'libfaac'),
            ('-ar', 48000),
            ('-ac', 2),
            ('-b:a', 192),
            ('-map', '1:0'),
        ]

        if picture_avinfo.video_res != '1920x1080':
            source_width = picture_avinfo.video_streams[0]['width']
            source_height = picture_avinfo.video_streams[0]['height']
            height  = (1920. / source_width) * source_height
            padding = (1080. - height) / 2

            ffmpeg.video_filter_chain.insert(0,
                ('scale', 'scale=1920:%d,pad=1920:1080:00:%d' % (height, padding)),
            )

        if self.video_burn:
            ffmpeg.drawtext(self.burn_options)

        ffmpeg.format_opts += [
            ('-f', 'mp4'),
        ]

        ffmpeg.add_output_file(os.path.join(self.tmp_dir, os.path.basename(dcp_path.strip('/')) + '.mp4'))
        self.workers.append(ffmpeg)

        if not self.container_hinting:
            for index, output_file in enumerate(ffmpeg.output_files):
                self.add_output_resource(index + 1, {'path': output_file.path})
        else:
            for index, output_file in enumerate(ffmpeg.output_files):
                base, ext = os.path.splitext(output_file.path)
                hinting_output_path = '%s-hint%s' % (base, ext)
                hinting_worker = self._new_worker(QtFastStartWorker)
                hinting_worker.add_input_file(output_file.path)
                hinting_worker.add_output_file(hinting_output_path)
                self.workers.append(hinting_worker)
                self.add_output_resource(index + 1, {'path': hinting_output_path})

    def _finalize(self):
        pass
