// Headless TOUCH reproduction of the feed swipe behaviour. Drives Flutter's gesture
// recognizer with realistic touch via CDP Input.synthesizeScrollGesture and reports whether
// the active <video> src changes (= paged) and whether the swapped clip plays.
// Run from /tmp/inspect (where node_modules/playwright lives):
//   cd /tmp/inspect && node /home/dev/newtimeline-dev/scripts/feed-repro.js
const { chromium } = require('playwright');

async function run(vw, vh) {
  const b = await chromium.launch({ executablePath:'/tmp/chs/chrome-headless-shell-linux64/chrome-headless-shell', args:['--no-sandbox','--disable-gpu'] });
  const ctx = await b.newContext({ viewport:{width:vw,height:vh}, hasTouch:true, isMobile:true });
  const p = await ctx.newPage();
  const errs = [];
  p.on('console', m => { if (m.type()==='error') errs.push('CONSOLE:'+m.text().slice(0,160)); });
  p.on('pageerror', e => errs.push('PAGEERR:'+String(e).slice(0,160)));
  await p.goto('http://localhost:8080/', {waitUntil:'load',timeout:60000});
  await p.waitForTimeout(12000);

  const srcOf = async () => p.evaluate(() => { const v=document.querySelector('video'); return (v&&(v.currentSrc||v.src)||'').slice(-16); });
  const playState = async () => p.evaluate(() => { const v=document.querySelector('video'); return v?{paused:v.paused,ct:Math.round(v.currentTime*100)/100,rs:v.readyState}:null; });

  const centreEl = await p.evaluate(() => {
    const x=window.innerWidth/2, y=window.innerHeight/2;
    return document.elementsFromPoint(x,y).slice(0,4).map(e=>e.tagName.toLowerCase());
  });

  const cdp = await ctx.newCDPSession(p);
  async function gesture(yDistance, speed, label) {
    const before = await srcOf();
    await cdp.send('Input.synthesizeScrollGesture', {
      x: Math.round(vw/2), y: Math.round(vh/2),
      xDistance: 0, yDistance, gestureSourceType: 'touch', speed,
    });
    await p.waitForTimeout(1700);
    const after = await srcOf();
    return { label, before, after, changed: before!==after, play: await playState() };
  }

  const results = [];
  results.push(await gesture(-200, 800,  'up-gentle'));
  results.push(await gesture(-400, 1500, 'up-medium'));
  results.push(await gesture(-600, 4000, 'up-fling'));
  results.push(await gesture(300, 1500,  'down-medium'));
  results.push(await gesture(300, 1500,  'down-medium2'));

  console.log(`=== ${vw}x${vh} ===`);
  console.log('centreEl:', JSON.stringify(centreEl));
  console.log('errs:', JSON.stringify(errs.slice(0,6)));
  for (const r of results) console.log(JSON.stringify(r));
  await ctx.close(); await b.close();
}

(async () => {
  await run(420, 860);
  await run(420, 680);
})().catch(e=>{console.error('FATAL',e);process.exit(1)});
