/* One shared navigation tree: moving it preserves handlers and current state. */
(() => {
 const nav=document.getElementById("tabs"), dialog=document.getElementById("mobile-navigation"),
 trigger=document.getElementById("mobile-menu-toggle"), slot=document.getElementById("mobile-navigation-slot"), anchor=document.getElementById("desktop-navigation-anchor");
 if(!nav||!dialog||!trigger||!slot||!anchor||typeof dialog.showModal!=="function")return;
 const narrow=matchMedia("(max-width:900px)");
 function place(){if(!narrow.matches&&dialog.open)dialog.close();if(narrow.matches)slot.append(nav);else anchor.after(nav);}
 trigger.addEventListener("click",()=>{if(narrow.matches&&!dialog.open){dialog.showModal();trigger.setAttribute("aria-expanded","true");}});
 dialog.addEventListener("close",()=>{trigger.setAttribute("aria-expanded","false");dialog.returnValue="";});
 nav.addEventListener("click",event=>{if(event.target.closest("button[data-view]")&&dialog.open)dialog.close();});
 // Safari lacks closedby=any. Require pointer-down AND up outside, so a
 // text-selection drag cannot accidentally dismiss the navigation sheet.
 if(!("closedBy" in HTMLDialogElement.prototype)){
  const outside=e=>{const r=dialog.getBoundingClientRect();return e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom;};let pressedOutside=false;
  dialog.addEventListener("pointerdown",event=>{pressedOutside=outside(event);});
  dialog.addEventListener("pointerup",event=>{if(pressedOutside&&outside(event))dialog.close();pressedOutside=false;});
 }
 narrow.addEventListener("change",place);place();document.body.classList.add("nav-ready");
})();
