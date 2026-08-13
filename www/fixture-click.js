// Delegated click handler for fixture rows on the home page.
// Bound to document so it survives fixture_cards() re-rendering.
//
// The home page lives in a Shiny module, so the input id is namespaced. The
// server stamps the resolved id onto the fixture container as
// data-fixture-input and we read it back here rather than hard-coding it.
document.addEventListener("click", function (event) {
    const row = event.target.closest("tr[data-game-id]");
    if (!row) return;

    const container = row.closest("[data-fixture-input]");
    if (!container) return;

    Shiny.setInputValue(container.dataset.fixtureInput, row.dataset.gameId, {
        priority: "event"
    });
});
