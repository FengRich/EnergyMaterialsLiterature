"use strict";

const list = document.querySelector("#paper-list");
if (list) {
  const query = document.querySelector("#query");
  const journal = document.querySelector("#journal");
  const domain = document.querySelector("#domain");
  const order = document.querySelector("#order");
  const count = document.querySelector("#result-count");
  const papers = [...list.querySelectorAll("[data-paper]")].map(element => ({
    element,
    words: element.textContent.toLocaleLowerCase(),
  }));

  function filterPapers() {
    const terms = query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    let visible = 0;
    for (const {element, words} of papers) {
      const matches = terms.every(term => words.includes(term))
        && (!journal.value || element.dataset.journal === journal.value)
        && (!domain.value || element.dataset.domains.split("|").includes(domain.value));
      element.hidden = !matches;
      visible += Number(matches);
    }
    count.textContent = `${visible} of ${papers.length} papers`;
  }

  function sortPapers() {
    const direction = order.value === "asc" ? 1 : -1;
    papers.sort((a, b) => {
      const first = a.element.dataset.date;
      const second = b.element.dataset.date;
      if (!first || !second) return Number(!first) - Number(!second);
      return direction * first.localeCompare(second);
    });
    const fragment = document.createDocumentFragment();
    for (const {element} of papers) fragment.append(element);
    list.append(fragment);
  }

  query.addEventListener("input", filterPapers);
  order.addEventListener("change", sortPapers);
  for (const control of [journal, domain]) control.addEventListener("change", filterPapers);
  filterPapers();
}
