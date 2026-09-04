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
});
