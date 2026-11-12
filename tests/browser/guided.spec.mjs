import {test,expect} from '@playwright/test';
import {readFile,mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import AxeBuilder from '@axe-core/playwright';

const ready=async page=>{
 await expect(page.locator('#pi-status')).toContainText('Simulation computed',{timeout:30000});
 await expect(page.locator('#view-physical')).not.toHaveAttribute('aria-busy','true');
};
const openTools=async page=>{
 if(!await page.locator('[data-ul="export"]').isVisible())await page.locator('.ul-tool-dock summary').click();
};

for(const viewport of [{width:1440,height:1000},{width:768,height:1024},{width:375,height:812}]){
 test(`sample to recomputed proof and recoverable history at ${viewport.width}px`,async({page},testInfo)=>{
  await page.setViewportSize(viewport);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/create');await ready(page);
  const accessibility=await new AxeBuilder({page}).include('#view-create').withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
  expect(accessibility.violations.map(value=>({id:value.id,nodes:value.nodes.map(node=>node.target)}))).toEqual([]);
  await page.getByRole('button',{name:'Try warehouse sample',exact:true}).click();
  await expect(page.locator('#guide-phase-title')).toHaveText('Inspect and compare');
  await expect(page.locator('#guide-source')).toHaveText('Synthetic fixture');
  await expect(page.locator('#guide-coordinates')).toContainText('no measured depth');
  const before=JSON.parse(await page.locator('#pi-source').inputValue());
  const visual=await page.evaluate(async()=>{
   const {illustrativeBody,disposeObject}=await import('/world-visuals.mjs');
   const THREE=await import('three');
   const body=illustrativeBody({id:'person',label:'Person',geometry:{kind:'box',half_extents_m:[.25,.25,.85]}});
   const size=new THREE.Box3().setFromObject(body).getSize(new THREE.Vector3());
   const result={width:size.x,height:size.y,depth:size.z,visualOnly:body.userData.visualOnly};disposeObject(body);return result;
  });
  expect(visual.width).toBeCloseTo(.5);expect(visual.height).toBeCloseTo(1.7);expect(visual.depth).toBeCloseTo(.5);expect(visual.visualOnly).toBe(true);
  await page.getByRole('button',{name:'Lift two seconds earlier & compare',exact:true}).click();
  await expect(page.locator('#guide-phase-title')).toHaveText('Review proof');
  await expect(page.locator('#guide-proof-state')).toContainText('Baseline and alternative recomputed');
  const after=JSON.parse(await page.locator('#pi-source').inputValue());
  expect(before.objects.find(o=>o.id==='forks').joint.start_s).toBe(4);
  expect(after.objects.find(o=>o.id==='forks').joint.start_s).toBe(2);
  const [evidence]=await Promise.all([page.waitForEvent('download'),page.getByRole('button',{name:'Download evidence JSON',exact:true}).click()]);
  const packet=JSON.parse(await readFile(await evidence.path(),'utf8'));
  expect(packet.packet.kind).toBe('counterfactual_comparison');
  expect(packet.packet.result.changed_object_ids).toEqual(['forks']);
  expect(packet.packet.result.baseline_digest).not.toBe(packet.packet.result.alternative_digest);
  expect(packet.packet.simulation_only).toBe(true);expect(packet.signature).toBeNull();
  expect(packet.packet_sha256).toMatch(/^[a-f0-9]{64}$/);
  await expect(page.locator('#guide-proof-digest')).toHaveText(packet.packet_sha256);
  const directory=process.env.FRONTIER_EVIDENCE_DIR||testInfo.outputDir;await mkdir(directory,{recursive:true});
  await page.screenshot({path:join(directory,`guided-proof-${viewport.width}.png`),fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await openTools(page);
  const [draft]=await Promise.all([page.waitForEvent('download'),page.locator('[data-ul="export"]').click()]);
  const draftPath=await draft.path();
  await page.reload();await ready(page);await page.locator('#guide-file').setInputFiles(draftPath);
  await expect(page.locator('#guide-phase-title')).toHaveText('Inspect and compare');
  expect(JSON.parse(await page.locator('#pi-source').inputValue()).objects.find(o=>o.id==='forks').joint.start_s).toBe(2);
  await openTools(page);await page.locator('[data-ul="undo"]').click();await ready(page);
  expect(JSON.parse(await page.locator('#pi-source').inputValue()).objects.find(o=>o.id==='forks').joint.start_s).toBe(4);
  await page.locator('[data-ul="redo"]').click();await ready(page);
  expect(JSON.parse(await page.locator('#pi-source').inputValue()).objects.find(o=>o.id==='forks').joint.start_s).toBe(2);
  expect(errors).toEqual([]);
 });
}

test('invalid imports and blocked authorization do not invent a successful result',async({page})=>{
 await page.goto('/create');await ready(page);const original=await page.locator('#pi-source').inputValue();
 await page.locator('#guide-file').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{"schema_version":"old"}')});
 await expect(page.locator('#guide-status')).toContainText('Choose a canonical v2 scene');
 expect(await page.locator('#pi-source').inputValue()).toBe(original);
 const denied=await page.request.post('/api/v1/scenes/create',{data:{name:'Blocked',scene:JSON.parse(original)}});
 expect(denied.status()).toBe(401);
 const tab=page.getByRole('tab',{name:'3D world',exact:true});await tab.focus();await page.keyboard.press('ArrowRight');
 await expect(page.getByRole('tab',{name:'Video & observations',exact:true})).toBeFocused();
 await expect(page.getByRole('tab',{name:'Video & observations',exact:true})).toHaveAttribute('aria-selected','true');
});
