// Delegated click handler for fixture rows on the home page.
// Bound to document so it survives fixture_cards() re-rendering.
document.addEventListener("click", function (event) {
    const row = event.target.closest("tr[data-game-id]");
    if (!row) return;

    Shiny.setInputValue("fixture_clicked", row.dataset.gameId, {
        priority: "event"
    });
});
