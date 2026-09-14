// A presentational reveal only. The page never calls an app or executes a run.

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

// Hero entrance: rise, unblur, fade. Reduced-motion and no-JS visitors simply see the hero.
const hero = document.querySelector('.hero');
if (hero && !reducedMotion) {
  hero.classList.add('hero-enter');
  requestAnimationFrame(() => requestAnimationFrame(() => hero.classList.add('hero-loaded')));
}

// Scroll reveals: gentle fade up as sections enter the viewport.
if (!reducedMotion && 'IntersectionObserver' in window) {
  const revealObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
        revealObserver.unobserve(entry.target);
      }
    }
  }, { threshold: 0.15 });
  document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));
} else {
  document.querySelectorAll('.reveal').forEach(el => el.classList.add('revealed'));
}

// Statement tagline: words activate one at a time as the section scrolls into view.
const statement = document.querySelector('.statement h2');
if (statement && !reducedMotion && 'IntersectionObserver' in window) {
  const words = [];
  let order = 0;
  for (const parent of [statement, ...statement.querySelectorAll('span')]) {
    for (const child of [...parent.childNodes]) {
      if (child.nodeType !== Node.TEXT_NODE) continue;
      const fragment = document.createDocumentFragment();
      for (const word of child.textContent.split(/(\s+)/)) {
        if (!word.trim()) { fragment.append(word); continue; }
        const span = document.createElement('b');
        span.className = 'statement-word';
        span.textContent = word;
        span.style.transitionDelay = `${order++ * 70}ms`;
        fragment.append(span);
        words.push(span);
      }
      child.replaceWith(fragment);
    }
  }
  const statementObserver = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      statement.classList.add('statement-visible');
      statementObserver.disconnect();
    }
  }, { threshold: 0.3 });
  statementObserver.observe(statement);
}
