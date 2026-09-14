// A presentational reveal only. The page never calls an app or executes a run.
const statement = document.querySelector('.statement h2');
if (statement && 'IntersectionObserver' in window && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
  const observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      statement.classList.add('statement-visible');
      observer.disconnect();
    }
  }, { threshold: 0.2 });
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
      }
      child.replaceWith(fragment);
    }
  }
  observer.observe(statement);
}

// Subtle hero entrance; reduced-motion and no-JS visitors simply see the hero.
const hero = document.querySelector('.hero');
if (hero && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
  hero.classList.add('hero-enter');
  requestAnimationFrame(() => requestAnimationFrame(() => hero.classList.add('hero-loaded')));
}
