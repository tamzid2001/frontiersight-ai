/** Image-space geometry only. A mask supplies a silhouette, never metric depth. */
export function imageScene(captures, width, height) {
 if(!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<1||height<1||width>1600||height>1600)throw Error('Invalid image dimensions');
 if(!Array.isArray(captures)||captures.length>96)throw Error('Invalid capture collection');
 const latest=Math.max(...captures.filter(c=>Number.isFinite(c.t)).map(c=>c.t),0);
 const objects=[],seen=new Set();
 for(const capture of captures){
  if(capture.t!==latest)continue;
  const label=String(capture.concept||'object').slice(0,100);
  for(const record of capture.records||[]){
   if(objects.length>=24)break;
   const box=record.box;if(!box||![box.x1,box.y1,box.x2,box.y2,box.frame_w,box.frame_h].every(Number.isFinite))continue;
   const {x1,y1,x2,y2,frame_w:fw,frame_h:fh}=box;
   if(fw<=0||fh<=0||fw>16384||fh>16384||x1<0||y1<0||x2<x1||y2<y1||x2>fw||y2>fh)continue;
   if(!Number.isSafeInteger(record.object_id)||record.object_id<0)continue;
   const key=label+':'+record.object_id;if(seen.has(key))continue;seen.add(key);
   // SAM box maxima are inclusive; clip the extra edge to the source frame.
   const bounds=[x1/fw*width,y1/fh*height,(Math.min(fw,x2+1)-x1)/fw*width,(Math.min(fh,y2+1)-y1)/fh*height];
   if(bounds[2]<=0||bounds[3]<=0)continue;
   const decoded=record.mask?.decoded===true&&typeof record.mask.png_data_url==='string'&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(record.mask.png_data_url)&&record.mask.png_data_url.length<=2_000_000;
   objects.push({id:'image-object-'+objects.length,label,sourceObjectId:record.object_id,
    bounds,confidence:Number.isFinite(record.confidence)&&record.confidence>=0&&record.confidence<=1?record.confidence:null,
    mask:decoded?record.mask.png_data_url:null,geometry:decoded?'segmented_mask_extrusion':'bounding_box_region',
    depth:0.12,depthSource:'ASSUMPTION',source:'MODEL_DERIVED',visible:true});
  }
 }
 return {version:1,kind:'frontiersight-image-scene',coordinateSpace:'image_pixels',width,height,at:latest,
  metricReconstruction:false,physicalCalibration:null,objects,
  limitations:['Single-view depth is unknown. Extrusion thickness and layer positions are visual assumptions.','No motion, material, mass or collision-safety claim is inferred from one photograph.']};
}

export function projectedObject(object, imageWidth, imageHeight, worldWidth=12) {
 if(![imageWidth,imageHeight,worldWidth].every(value=>Number.isFinite(value)&&value>0))throw Error('Invalid projection');
 const [x,y,w,h]=object.bounds;
 if(![x,y,w,h].every(Number.isFinite)||x<0||y<0||w<=0||h<=0||x+w>imageWidth+1e-8||y+h>imageHeight+1e-8)throw Error('Invalid object bounds');
 const scale=worldWidth/imageWidth;
 return {x:(x+w/2-imageWidth/2)*scale,y:(imageHeight-y-h/2)*scale,
  width:w*scale,height:h*scale,depth:object.depth,z:0.08+(y+h)/imageHeight*0.35};
}
