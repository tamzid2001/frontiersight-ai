"""Bounded 2D frame/animated-preview export using the playback motion profiles.

These top-down illustrations are simulation renders, not observed camera images
or photorealistic 3D reconstructions. No ffmpeg subprocess or model call is used.
"""
from __future__ import annotations
import base64
import io
import math
from .scene_edit import validate_document, prepare_scene
from .path_automation import number
from .curves import Path

COLORS = {'pedestrian':'#38c6d9','robot':'#74dc9e','forklift':'#e9a13b',
          'vehicle':'#8297ff','cyclist':'#df91ed','shelf':'#737e92'}


def dimensions(width, height):
    if type(width) is not int or type(height) is not int or not 160 <= width <= 1024 or not 120 <= height <= 768:
        raise ValueError('render dimensions must be integer width 160..1024 and height 120..768')


def _prepared(scene):
    document = validate_document(scene)
    prepare_scene(document)  # Validate the same geometry used for viewer handoffs.
    return document, [(obj, Path(obj['waypoints'], obj.get('curve','straight'), obj.get('mode')=='loop'))
                      for obj in document['objects']]


def _frame(document, paths, timestamp, width, height):
    from PIL import Image, ImageDraw
    image = Image.new('RGB', (width,height), '#111827')
    draw = ImageDraw.Draw(image)
    scale = min((width-40)/document['stage_metres'][0],(height-50)/document['stage_metres'][1])
    left = (width-document['stage_metres'][0]*scale)/2
    bottom = height-25
    def project(x,y):return left+x*scale,bottom-y*scale
    for x in range(math.floor(document['stage_metres'][0])+1):
        draw.line([project(x,0),project(x,document['stage_metres'][1])],fill='#253043')
    for y in range(math.floor(document['stage_metres'][1])+1):
        draw.line([project(0,y),project(document['stage_metres'][0],y)],fill='#253043')
    poses=[]
    for obj,path in paths:
        outline=[project(p.x,p.y) for p in path.points]
        if len(outline)>1:draw.line(outline,fill='#586478',width=2)
        position=path.position_at_time(timestamp,obj.get('speed',0),obj.get('delay',0),obj.get('mode','stop'),obj.get('category','object'))
        x,y=project(position.x,position.y);radius=max(2,obj.get('radius',.5)*scale)
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=COLORS.get(obj.get('category'),'#d0d6df'))
        oid=obj.get('id',obj.get('object_id'));draw.text((x+radius+2,y),oid,fill='white')
        poses.append({'object_id':oid,'position_metres':[position.x,position.y],'radius_metres':obj.get('radius',.5)})
    draw.text((12,8),f'SIMULATED 2D | {timestamp:.2f}s | {document["stage_metres"][0]:g} x {document["stage_metres"][1]:g} m',fill='white')
    return image,poses


def render_frame(scene, timestamp_s=0, width=640, height=480):
    dimensions(width,height);timestamp=number(timestamp_s,'timestamp_s',0,20)
    document,paths=_prepared(scene);image,poses=_frame(document,paths,timestamp,width,height)
    stream=io.BytesIO();image.save(stream,format='PNG')
    return {'mime_type':'image/png','data_url':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode(),
            'timestamp_s':timestamp,'stage_metres':document['stage_metres'],'objects':poses,
            'source':'SIMULATED_2D_RENDER','width':width,'height':height}


def render_video_preview(scene, duration_s=4, fps=6, width=640, height=480):
    dimensions(width,height);duration=number(duration_s,'duration_s',.2,12)
    if type(fps) is not int or not 1<=fps<=15:raise ValueError('fps must be an integer 1..15')
    count=math.ceil(duration*fps)
    if count<2 or count>60 or count*width*height>20_000_000:
        raise ValueError('preview exceeds the 60-frame / 20-megapixel render budget')
    document,paths=_prepared(scene)
    frames=[_frame(document,paths,index/fps,width,height)[0] for index in range(count)]
    # GIF duration is measured in centiseconds. Report the actual quantized rate,
    # rather than falsely claiming arbitrary exact frame timing or MP4 output.
    frame_ms=max(10,round(100/fps)*10)
    stream=io.BytesIO();frames[0].save(stream,format='GIF',save_all=True,append_images=frames[1:],duration=frame_ms,loop=0,optimize=False)
    raw=stream.getvalue()
    if len(raw)>2_000_000:raise ValueError('encoded preview exceeds the 2MB response budget')
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as encoded:
        encoded_count=encoded.n_frames
        durations=[]
        for index in range(encoded_count):
            encoded.seek(index);durations.append(encoded.info.get('duration',frame_ms))
    return {'mime_type':'image/gif','data_url':'data:image/gif;base64,'+base64.b64encode(raw).decode(),
            'source':'SIMULATED_2D_ANIMATED_PREVIEW','frame_count':encoded_count,'requested_frames':count,'frame_duration_ms':frame_ms,'frame_durations_ms':durations,
            'requested_fps':fps,'encoded_fps':encoded_count*1000/sum(durations),'duration_s':sum(durations)/1000,
            'stage_metres':document['stage_metres'],'width':width,'height':height,
            'note':'Animated GIF preview, not MP4 or a camera measurement. Browser 3D rendering remains separate.'}
