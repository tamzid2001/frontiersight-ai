"""Local PyAV decoding with actual PTS, bounded dimensions/time/frame counts.

PyAV/FFmpeg protocol access is restricted to local files for uploaded content.
USB and RTSP acquisition use a separate OpenCV process, never both runtimes in
one macOS process (their AVFoundation libraries can conflict).
"""
from pathlib import Path
import math
import time


def inspect_video(path,checkpoint=lambda *a:None):
    import av
    path=Path(path)
    if not path.is_file() or not 0<path.stat().st_size<=64*1024*1024: raise ValueError('video_size_limit')
    # Restrict demuxing to the selected local file; disallow external playlist,
    # network and nested-protocol references inside uploaded media.
    with av.open(str(path),options={'protocol_whitelist':'file','probesize':'5000000','analyzeduration':'5000000'}) as container:
        if not set(container.format.name.split(',')) & {'mov','mp4','matroska','webm'}: raise ValueError('unsupported_video_container')
        if len(container.streams.video)!=1: raise ValueError('exactly_one_video_stream_required')
        stream=container.streams.video[0]
        webm='webm' in container.format.name
        if webm and stream.codec_context.name not in ('vp8','vp9','av1'):raise ValueError('unsupported_webm_codec')
        upload_name='video.webm' if webm else 'video.mov' if container.metadata.get('major_brand','').strip()=='qt' else 'video.mp4'
        if stream.codec_context.name not in ('h264','hevc','vp8','vp9','av1','mpeg4'): raise ValueError('unsupported_video_codec')
        width,height=stream.codec_context.width,stream.codec_context.height
        if not 1<=width<=3840 or not 1<=height<=2160 or width*height>3840*2160: raise ValueError('video_resolution_limit')
        times=[];start=time.monotonic();first=None
        for index,frame in enumerate(container.decode(video=0)):
            if index>=3600 or time.monotonic()-start>90: raise ValueError('video_decode_budget_exceeded')
            if not 1<=frame.width<=3840 or not 1<=frame.height<=2160:raise ValueError('decoded_frame_resolution_limit')
            if frame.pts is None or frame.time_base is None: raise ValueError('video_presentation_timestamps_unavailable')
            timestamp=float(frame.pts*frame.time_base)
            if not math.isfinite(timestamp): raise ValueError('invalid_video_pts')
            if first is None: first=timestamp
            relative=timestamp-first
            if relative>120 or times and relative<=times[-1]: raise ValueError('video_pts_order_or_duration_limit')
            times.append(relative)
            if index%20==0: checkpoint(index,relative)
        if len(times)<2: raise ValueError('video_requires_multiple_frames')
        intervals=[b-a for a,b in zip(times,times[1:])]
        return {'upload_name':upload_name,'width':width,'height':height,'codec':stream.codec_context.name,'container':container.format.name,
                'duration_s':times[-1],'source_start_pts_s':first,'frame_count':len(times),'frame_timestamps_s':times,
                'average_observed_fps':(len(times)-1)/(times[-1]-times[0]),
                'variable_frame_intervals':max(intervals)-min(intervals)>1e-5,'provenance':'MEASURED_MEDIA_METADATA'}
