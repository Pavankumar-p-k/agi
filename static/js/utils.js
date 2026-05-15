'use strict';

export const KW = {
  lion:'lion', tiger:'tiger', bear:'bear', wolf:'wolf', fox:'fox',
  eagle:'eagle', shark:'shark', whale:'whale', dolphin:'dolphin',
  elephant:'elephant', horse:'horse', dragon:'dragon', snake:'snake',
  cat:'cat', dog:'dog', owl:'owl', crow:'crow', fish:'fish',
  robot:'robot', butterfly:'butterfly', spider:'spider',
  cheetah:'cheetah', gorilla:'gorilla', panda:'panda', penguin:'penguin',
  koala:'koala', kangaroo:'kangaroo', giraffe:'giraffe', zebra:'zebra',
  hawk:'hawk', falcon:'falcon', parrot:'parrot', swan:'swan',
  octopus:'octopus', turtle:'turtle', crab:'crab', lobster:'lobster',
  bee:'bee', ant:'ant', beetle:'beetle', scorpion:'scorpion',
  dinosaur:'dinosaur', mammoth:'mammoth', unicorn:'unicorn', phoenix:'phoenix',
  car:'car', plane:'plane', rocket:'rocket', ship:'ship',
  helicopter:'helicopter', train:'train', tank:'tank', submarine:'submarine',
  drone:'drone', motorcycle:'motorcycle', truck:'truck', bus:'bus',
  bicycle:'bicycle', scooter:'scooter', yacht:'yacht', sailboat:'sailboat',
  shuttle:'shuttle', rover:'rover', jet:'jet', glider:'glider',
  tractor:'tractor', ambulance:'ambulance', taxi:'taxi', jeep:'jeep',
  london:'city', paris:'city', newyork:'city', tokyo:'city', dubai:'city',
  sydney:'city', rome:'city', berlin:'city', moscow:'city', mumbai:'city',
  shanghai:'city', singapore:'city', toronto:'city', seoul:'city', bangkok:'city',
  cairo:'city', istanbul:'city', amsterdam:'city', madrid:'city', vienna:'city',
  delhi:'city', hyderabad:'city', bangalore:'city', chennai:'city', kolkata:'city',
  india:'map', usa:'map', america:'map', china:'map', russia:'map',
  uk:'map', england:'map', france:'map', germany:'map', japan:'map',
  australia:'map', canada:'map', brazil:'map', italy:'map', spain:'map',
  africa:'map', europe:'map', asia:'map', world:'map', earth:'map',
  map:'map', globe:'globe', atlas:'map',
  castle:'castle', tower:'tower', pyramid:'pyramid', house:'house',
  bridge:'bridge', mosque:'mosque', temple:'temple', church:'church',
  skyscraper:'city', lighthouse:'lighthouse', factory:'factory', hospital:'hospital',
  stadium:'stadium', airport:'airport', museum:'museum', library:'book',
  brain:'brain', ai:'brain', heart:'heart', skull:'skull',
  fire:'fire', star:'star', moon:'moon', sun:'sun', planet:'planet',
  dna:'dna', atom:'atom', circuit:'circuit', diamond:'diamond',
  tree:'tree', mountain:'mountain', galaxy:'galaxy',
  book:'book', article:'book', document:'book', news:'book',
  code:'circuit', data:'circuit', cloud:'cloud', wifi:'circuit',
  camera:'camera', phone:'phone', laptop:'laptop', watch:'watch',
  money:'diamond', gold:'diamond', trophy:'trophy', medal:'trophy',
  music:'music', guitar:'music', piano:'music', mic:'music',
};

export const PARTICLE_COUNT = 6000;
export const ASSET_PATH = 'assets/particles/';

export const SIZE_TIERS = [0.03, 0.045, 0.06, 0.08, 0.11, 0.15];
export const SIZE_WEIGHTS = [0.18, 0.28, 0.24, 0.16, 0.09, 0.05];

export function weightedSizeTier() {
  const r = Math.random();
  let acc = 0;
  for (let i = 0; i < SIZE_WEIGHTS.length; i++) {
    acc += SIZE_WEIGHTS[i];
    if (r < acc) return SIZE_TIERS[i];
  }
  return SIZE_TIERS[2];
}

export function extractKeyword(text) {
  const lo = text.toLowerCase();
  for (const k of Object.keys(KW)) {
    if (new RegExp(`\\b${k}\\b`).test(lo)) return k;
  }
  return null;
}

export function highlightKeywords(text, kws) {
  let out = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  if (!kws || !kws.length) return out;
  kws.forEach(k => {
    const re = new RegExp(`\\b(${k})\\b`,'gi');
    out = out.replace(re, `<span class="kw-highlight">$1</span>`);
  });
  return out;
}

export function iconForType(type) {
  const m = {answer:'◈',options:'⊞',plan:'⟳',warning:'⚠',insight:'◉',question:'?',flow:'⋮'};
  return m[type] || '◈';
}
