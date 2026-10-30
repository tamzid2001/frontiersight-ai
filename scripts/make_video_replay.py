"""Generate labelled synthetic VFR video for reproducible offline decoding tests."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path


def generate(destination):
    import av
    from PIL import Image,ImageDraw
    path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True)
    timestamps=[0,100,230,400,550,710,850,1000]
    lines=[]
    with av.open(str(path),'w',format='mp4') as output:
        stream=output.add_stream('libx264',rate=10,options={'preset':'ultrafast','tune':'zerolatency'});stream.width=160;stream.height=120;stream.pix_fmt='yuv420p';stream.codec_context.time_base=Fraction(1,1000)
        for index,pts in enumerate(timestamps):
            image=Image.new('RGB',(160,120),(25,40,55));draw=ImageDraw.Draw(image);x=20+index*5;draw.rectangle((x,40,x+16,60),fill=(56,198,217))
            frame=av.VideoFrame.from_image(image);frame.pts=pts;frame.time_base=Fraction(1,1000)
            for packet in stream.encode(frame):output.mux(packet)
            lines.append(f'<{index}f>1<|box;x1={x};y1=40;x2={x+16};y2=60;w=160;h=120;c=1|>')
        for packet in stream.encode():output.mux(packet)
    sidecar={'source':'FIXTURE','provenance':'FIXTURE','label':'Synthetic authored bounding boxes, not model observations',
             'video_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'segmentation_text':'\n'.join(lines)}
    path.with_suffix('.fixture.json').write_text(json.dumps(sidecar,indent=2)+'\n')
    return sidecar


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args();generate(args.output)
