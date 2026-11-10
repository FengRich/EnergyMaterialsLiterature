async (page) => {
  const assert = (condition, detail) => { if (!condition) throw new Error(detail); };
  const base = await page.evaluate(() => new URL(".", location.href).href);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));

  await page.goto(base + "index.html");
  assert(await page.locator("h1").textContent() === "AI & Computational Energy Materials Literature Hub", "Wrong home");
  assert(await page.getByRole("heading", {name: "Representative papers"}).isVisible(), "Missing weekly picks");

  await page.getByRole("link", {name: "Library", exact: true}).click();
  const visible = page.locator("[data-paper]:visible");
  const start = await visible.count();
  assert(start >= 10, "Expected real papers in library");
  const first = visible.first();
  const doi = await first.locator(".doi a").textContent();
  const journal = await first.getAttribute("data-journal");
  const domain = (await first.getAttribute("data-domains")).split("|")[0];
  await page.getByRole("searchbox").fill(doi);
  assert(await visible.count() === 1, "DOI keyword search did not isolate its paper");
  await visible.locator("summary").click();
  assert(await visible.locator("details").evaluate(element => element.open), "Paper details did not expand");
  await page.getByRole("searchbox").fill("");
  await page.getByLabel("Journal").selectOption(journal);
  await page.getByLabel("Research area").selectOption(domain);
  const filtered = await visible.evaluateAll(elements => elements.map(element => element.dataset));
  assert(filtered.length >= 1 && filtered.every(row => row.journal === journal && row.domains.split("|").includes(domain)), "Combined filters are wrong");
  await page.getByLabel("Journal").selectOption("");
  await page.getByLabel("Research area").selectOption("");
  await page.getByLabel("Sort").selectOption("asc");
  const dates = await visible.evaluateAll(elements => elements.map(element => element.dataset.date).filter(Boolean));
  assert(dates.every((date, index) => index === 0 || dates[index - 1] <= date), "Oldest-first sorting is wrong");

  await page.setViewportSize({width: 390, height: 844});
  for (const path of ["index", "library", "archive", "pending", "about"]) {
    const response = await page.goto(base + path + ".html");
    assert(response.ok(), "Failed to load " + path);
    const size = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
    assert(size[0] <= size[1], path + " overflows at mobile width");
    assert(await page.locator('nav a[aria-current="page"]').count() === 1, "Missing current page navigation");
  }
  assert(await page.getByRole("heading", {name: "Journal whitelist"}).isVisible(), "Missing journal whitelist");
  assert(errors.length === 0, errors.join("\n"));
  return {libraryPapers: start, mobileWidth: 390, pages: 5, errors};
}
