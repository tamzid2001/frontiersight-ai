import {test,expect} from '@playwright/test';
const ready=async page=>{await expect(page.locator('#pi-status')).toContainText('Simulation computed',{timeout:30000});await expect(page.locator('#view-physical')).not.toHaveAttribute('aria-busy','true');};
test('one editor, real transform controls, camera zoom, history and shared time',async({page})=>{
 const errors=[];page.on('pageerror',error=>errors.push(error.message));await page.goto('/create');await ready(page);
 await expect(page.locator('#tabs [data-view="create"]')).toHaveCount(1);await expect(page.locator('#tabs [data-view="studio"],#tabs [data-view="physical"],#tabs [data-view="counterfactual"]')).toHaveCount(0);
 const before=await page.locator('#pi-source').inputValue();const picture=await page.locator('#pi-viewport canvas').screenshot();
 await page.locator('[data-ul="zoom-in"]').click();expect(await page.locator('#pi-viewport canvas').screenshot()).not.toEqual(picture);expect(await page.locator('#pi-source').inputValue()).toBe(before);
 for(const name of ['zoom-out','fit','reset-camera','grid','axes','snap','move','rotate','scale','select'])await page.locator(`[data-ul="${name}"]`).click();
 await page.getByRole('combobox',{name:'Component',exact:true}).selectOption('person');const count=await page.locator('#pi-object option').count();await page.locator('[data-ul="duplicate"]').click();await ready(page);await expect(page.locator('#pi-object option')).toHaveCount(count+1);
 await page.locator('[data-ul="undo"]').click();await ready(page);await expect(page.locator('#pi-object option')).toHaveCount(count);await page.locator('[data-ul="redo"]').click();await ready(page);await expect(page.locator('#pi-object option')).toHaveCount(count+1);
 await page.getByRole('combobox',{name:'Component',exact:true}).selectOption('person_copy1');await page.locator('[data-ul="delete"]').click();await ready(page);await expect(page.locator('#pi-object option')).toHaveCount(count);
 await page.locator('#ul-time').fill('8');await expect(page.locator('#pi-clock')).toHaveText('8.00 s');await page.locator('[data-ul="frame-next"]').click();await expect(page.locator('#ul-clock')).toHaveText('8.10 s');
 for(const name of ['timeline-in','timeline-out','timeline-fit','play','pause'])await page.locator(`[data-ul="${name}"]`).click();
 await page.getByRole('tab',{name:'2D top view',exact:true}).click();await expect(page.locator('#pi-camera')).toHaveValue('top');await page.getByRole('tab',{name:'3D world',exact:true}).click();
 await page.getByRole('tab',{name:'Video & observations',exact:true}).click();await expect(page.locator('#pi-object option')).toHaveCount(count);await expect(page.locator('#edge-file')).toBeVisible();
 await page.getByRole('button',{name:'Devices & Worker Endpoints',exact:true}).click();await expect(page.locator('#edge-url')).toBeVisible();await expect(page.locator('#view-create')).not.toBeVisible();
 expect(errors).toEqual([]);
});
test('legacy physical route enters unified editor; mobile fits without horizontal page overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/physical-intelligence');await ready(page);await expect(page.locator('#view-create')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
 const download=page.waitForEvent('download');await page.locator('[data-ul="export"]').click();expect((await download).suggestedFilename()).toBe('frontiersight-editor.json');
});
