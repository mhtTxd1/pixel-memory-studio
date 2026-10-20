import assert from 'node:assert/strict';
import {AvatarPlayer} from '../pixel_avatar/web/player.js';
globalThis.requestAnimationFrame=()=>1;
globalThis.cancelAnimationFrame=()=>{};
const draws=[];
const canvas={style:{},getContext:()=>({clearRect(){},drawImage(...args){draws.push(args);}})};
const manifest={cellWidth:192,cellHeight:208,
  animations:{idle:{row:0,frames:2,durations:[100,200]},waving:{row:3,frames:1,durations:[200]}},
  gaze:Array.from({length:16},(_,i)=>({row:9+Math.floor(i/8),column:i%8}))};
const p=new AvatarPlayer(canvas,{},manifest);
for(let i=0;i<16;i++){
  const angle=i*Math.PI/8;
  p.lookAt(Math.sin(angle)*100,-Math.cos(angle)*100);
  assert.equal(p.gaze,i);
}
p.lookAt(1,1);assert.equal(p.gaze,null);
p.tick(p.started+100);assert.equal(draws.at(-1)[1],192);
p.play('waving');p.tick(p.started);assert.equal(draws.at(-1)[2],3*208);
assert.throws(()=>p.play('unknown'));
p.destroy();assert.equal(p.stopped,true);
console.log('Player: 16 directions, neutral deadzone, timing, state switch and disposal passed');
