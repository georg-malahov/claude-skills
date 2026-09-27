const WORDS="apple banana cherry grape lemon mango melon orange peach pear plum kiwi lime fig date".split(" ");
const ITEMS=Array.from({length:4000},(_,i)=>WORDS[i%WORDS.length]+" "+i);
function score(q){let s=0;for(let i=0;i<4e7;i++)s+=Math.sqrt(i%q.length+1);return s}
onmessage=(e)=>{const t=performance.now();const v=e.data.v;score(v||"x");score(v||"x");postMessage({seq:e.data.seq,hits:ITEMS.filter(s=>s.includes(v)),ms:performance.now()-t})};
