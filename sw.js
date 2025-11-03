self.addEventListener('install',(e)=>{e.waitUntil(caches.open('rcpwa-v4').then((c)=>c.addAll(['./','./index.html','./manifest.json','./sw.js','./icons/icon-192.png','./icons/icon-512.png','./version.json']).catch(()=>{})))});
self.addEventListener('fetch',(e)=>{if(new URL(e.request.url).origin===location.origin){e.respondWith(caches.match(e.request).then((r)=>r||fetch(e.request)));}});
