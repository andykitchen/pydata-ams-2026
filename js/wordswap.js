// Two-column headline that flips words on a hard cut with a one-frame flicker.
// Left alternates AI / Human. Right draws from a shuffle bag. Right lags left.
// Runs only while its slide is .present.

const LEFT = ['AI', 'Human'];
const RIGHT = [
  'safety', 'philosophy', 'phenomenology', 'connection', 'compute',
  'nurture', 'creativity', 'understanding', 'future', 'care',
];

const PERIOD_MS = 1500; // one swap per period
const LAG_MS = 200; // right side follows left
const FLICKER_MS = 240;

function shuffleBag(items) {
  let bag = [];
  let last;
  return () => {
    if (bag.length === 0) {
      bag = [...items];
      for (let i = bag.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [bag[i], bag[j]] = [bag[j], bag[i]];
      }
      // don't repeat the last word across the bag boundary
      if (bag.length > 1 && bag[bag.length - 1] === last) {
        [bag[0], bag[bag.length - 1]] = [bag[bag.length - 1], bag[0]];
      }
    }
    last = bag.pop();
    return last;
  };
}

function setWord(el, word) {
  el.textContent = word;
  el.classList.add('is-flick');
  window.setTimeout(() => el.classList.remove('is-flick'), FLICKER_MS);
}

const timers = new WeakMap();

function start(slide) {
  if (timers.has(slide)) return;
  const left = slide.querySelector('[data-side="left"]');
  const right = slide.querySelector('[data-side="right"]');
  if (!left || !right) return;

  const nextRight = shuffleBag(RIGHT);
  let i = LEFT.indexOf(left.textContent.trim());

  const tick = () => {
    i = (i + 1) % LEFT.length;
    setWord(left, LEFT[i]);
    window.setTimeout(() => setWord(right, nextRight()), LAG_MS);
  };

  timers.set(slide, window.setInterval(tick, PERIOD_MS));
}

function stop(slide) {
  const t = timers.get(slide);
  if (t !== undefined) {
    window.clearInterval(t);
    timers.delete(slide);
  }
}

export function initWordSwap(deck) {
  const sync = (current, previous) => {
    if (previous && previous.matches('[data-wordswap]')) stop(previous);
    if (current && current.matches('[data-wordswap]')) start(current);
  };
  deck.on('ready', (e) => sync(e.currentSlide));
  deck.on('slidechanged', (e) => sync(e.currentSlide, e.previousSlide));
}