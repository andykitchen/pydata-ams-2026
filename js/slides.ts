import Reveal from './reveal.js';

import Highlight from '../plugin/highlight/index.ts';
import Notes from '../plugin/notes/index.ts';

document.addEventListener('DOMContentLoaded', async () => {
	const revealElement = document.querySelector('.reveal');

	if (!(revealElement instanceof HTMLElement)) {
		throw new Error('Unable to find presentation root (<div class="reveal">).');
	}

	const deck = new Reveal(revealElement);

	await deck.initialize({
		width: 960,
		height: 700,
		margin: 0.01,

		hash: true,

		plugins: [Highlight, Notes],
	});

	// The Maxwell's daemon simulation is compute-heavy, so only keep it
	// loaded while its slide is visible: park the URL back in data-src
	// and blank the src whenever we navigate away.
	const maxwellIframe = revealElement.querySelector<HTMLIFrameElement>('iframe[data-maxwell-sim]');

	if (maxwellIframe) {
		const suspendSim = () => {
			const src = maxwellIframe.getAttribute('src');
			if (src && src !== 'about:blank') {
				maxwellIframe.setAttribute('data-src', src);
			}
			if (maxwellIframe.hasAttribute('src')) {
				maxwellIframe.setAttribute('src', 'about:blank');
				maxwellIframe.removeAttribute('src');
			}
		};

		const resumeSim = () => {
			const dataSrc = maxwellIframe.getAttribute('data-src');
			if (dataSrc && maxwellIframe.getAttribute('src') !== dataSrc) {
				maxwellIframe.setAttribute('src', dataSrc);
			}
		};

		deck.on('slidechanged', (event: any) => {
			if (event.currentSlide?.contains(maxwellIframe)) {
				resumeSim();
			} else {
				suspendSim();
			}
		});

		// Handle a deck that opens on a slide other than the sim's.
		if (!deck.getCurrentSlide()?.contains(maxwellIframe)) {
			suspendSim();
		}
	}
});
