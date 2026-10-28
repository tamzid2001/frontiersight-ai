import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { imageScene, projectedObject } from './image-scene-core.mjs';

const loadImage=src=>new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(Error('Image could not be decoded'));image.src=src;});
let current=null,generation=0;
function release(root){root.traverse(node=>{if(node.isInstancedMesh)node.dispose();node.geometry?.dispose();for(const material of (Array.isArray(node.material)?node.material:[node.material])){material?.map?.dispose();material?.dispose();}});}

export async function buildImageScene(source, captures, container, canvas) {
 const requested=++generation;
 const sceneData=imageScene(captures,source.width,source.height);
 if(!sceneData.objects.length)throw Error('No valid detections. Segment this image first.');
 const cutouts=[];
 for(const object of sceneData.objects){
  const [x,y,w,h]=object.bounds;const cutout=document.createElement('canvas');cutout.width=Math.max(1,Math.ceil(w));cutout.height=Math.max(1,Math.ceil(h));
  const context=cutout.getContext('2d');context.drawImage(source,x,y,w,h,0,0,cutout.width,cutout.height);
  if(object.mask){try{const mask=await loadImage(object.mask);context.globalCompositeOperation='destination-in';context.imageSmoothingEnabled=false;context.drawImage(mask,0,0,cutout.width,cutout.height);context.globalCompositeOperation='source-over';}catch{object.mask=null;object.geometry='bounding_box_region';}}
  cutouts.push({object,canvas:cutout});
 }
 if(requested!==generation)return null;
 if(current)current.dispose();
 const context=canvas.getContext('2d');
 const paint2d=(background=true)=>{canvas.width=source.width;canvas.height=source.height;context.clearRect(0,0,canvas.width,canvas.height);
  if(background)context.drawImage(source,0,0);
  for(const item of cutouts)if(item.object.visible){const [x,y,w,h]=item.object.bounds;context.drawImage(item.canvas,x,y,w,h);context.strokeStyle='#17a7b8';context.lineWidth=Math.max(1,source.width/650);context.strokeRect(x,y,w,h);}
 };
 paint2d();
 const scene=new THREE.Scene();scene.background=new THREE.Color(0xe4edf1);
 let renderer;
 try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});}catch{
  container.textContent='3D needs WebGL. Your 2D cutouts remain available.';
  let background=true;current={data:sceneData,webgl:false,setBackground(value){background=value;paint2d(value);},setVisible(id,value){const object=sceneData.objects.find(item=>item.id===id);if(object)object.visible=value;paint2d(background);},dispose(){container.replaceChildren();current=null;}};return current;
 }
 renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));renderer.domElement.tabIndex=0;renderer.domElement.setAttribute('aria-label','Image-grounded 3D mask extrusions. Orbit with drag; geometry depth is an assumption.');container.replaceChildren(renderer.domElement);
 const camera=new THREE.PerspectiveCamera(44,1,0.05,100);const fullHeight=12*source.height/source.width;camera.position.set(0,fullHeight/2,Math.max(15,fullHeight*1.5));
 const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,fullHeight/2,0);controls.enableDamping=false;controls.maxDistance=45;controls.minDistance=3;controls.update();
 scene.add(new THREE.HemisphereLight(0xffffff,0x445764,2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(-4,8,10);scene.add(light);
 const floor=new THREE.Mesh(new THREE.PlaneGeometry(18,9),new THREE.MeshStandardMaterial({color:0xb5c9c0,roughness:1}));floor.rotation.x=-Math.PI/2;floor.position.z=-2;scene.add(floor);
 const texture=new THREE.CanvasTexture(source);texture.colorSpace=THREE.SRGBColorSpace;
 const backdrop=new THREE.Mesh(new THREE.PlaneGeometry(12,fullHeight),new THREE.MeshBasicMaterial({map:texture,side:THREE.DoubleSide}));backdrop.position.set(0,fullHeight/2,-0.03);scene.add(backdrop);
 const groups=new Map();
 for(const {object,canvas:cutout} of cutouts){
  const projected=projectedObject(object,source.width,source.height);const group=new THREE.Group();group.position.set(projected.x,projected.y,projected.z);
  // The mask provides the silhouette; this extrusion's thickness is explicit
  // assumed visual geometry, not a reconstruction of hidden surfaces.
  const columns=Math.min(32,cutout.width),rows=Math.min(32,cutout.height);const sample=document.createElement('canvas');sample.width=columns;sample.height=rows;const sampleContext=sample.getContext('2d');sampleContext.drawImage(cutout,0,0,columns,rows);const pixels=sampleContext.getImageData(0,0,columns,rows).data;
  const occupied=[];for(let row=0;row<rows;row++)for(let col=0;col<columns;col++){const offset=(row*columns+col)*4;if(pixels[offset+3]>128)occupied.push({row,col,offset});}
  if(occupied.length){const blocks=new THREE.InstancedMesh(new THREE.BoxGeometry(projected.width/columns,projected.height/rows,projected.depth),new THREE.MeshStandardMaterial({color:0xffffff,roughness:0.75}),occupied.length);const transform=new THREE.Object3D();
   occupied.forEach(({row,col,offset},index)=>{transform.position.set((col+.5)/columns*projected.width-projected.width/2,projected.height/2-(row+.5)/rows*projected.height,0);transform.updateMatrix();blocks.setMatrixAt(index,transform.matrix);blocks.setColorAt(index,new THREE.Color(pixels[offset]/255,pixels[offset+1]/255,pixels[offset+2]/255).convertSRGBToLinear());});blocks.instanceMatrix.needsUpdate=true;blocks.instanceColor.needsUpdate=true;group.add(blocks);}
  const photo=new THREE.CanvasTexture(cutout);photo.colorSpace=THREE.SRGBColorSpace;const face=new THREE.Mesh(new THREE.PlaneGeometry(projected.width,projected.height),new THREE.MeshBasicMaterial({map:photo,transparent:true,alphaTest:.03,side:THREE.DoubleSide}));face.position.z=projected.depth/2+.002;group.add(face);scene.add(group);groups.set(object.id,group);
 }
 const render=()=>{const width=container.clientWidth;if(!width)return;const height=Math.min(520,Math.max(260,innerHeight*.55));renderer.setSize(width,height,false);renderer.domElement.style.width='100%';renderer.domElement.style.height=height+'px';camera.aspect=width/height;camera.updateProjectionMatrix();renderer.render(scene,camera);};
 controls.addEventListener('change',render);const resize=new ResizeObserver(render);resize.observe(container);
 const observer=new IntersectionObserver(entries=>{if(entries.at(-1)?.isIntersecting)render();});observer.observe(container);
 let background=true;
 current={data:sceneData,webgl:true,setBackground(value){background=value;backdrop.visible=value;paint2d(value);render();},setVisible(id,value){const object=sceneData.objects.find(item=>item.id===id);if(!object)return;object.visible=value;groups.get(id).visible=value;paint2d(background);render();},render,
  dispose(){resize.disconnect();observer.disconnect();controls.dispose();release(scene);renderer.dispose();container.replaceChildren();current=null;}};
 paint2d();render();return current;
}

export function clearImageScene(){generation++;if(current)current.dispose();}
