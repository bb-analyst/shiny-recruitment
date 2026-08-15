// Delegated click handler for the similar-players comparison table headers.
// Clicking a metric column header toggles it in/out of the similarity
// calculation. Bound to document so it survives the table re-rendering.
//
// The profile page is a Shiny module, so the input id is namespaced; the server
// stamps the resolved id onto the table wrapper as data-sim-input and we read
// it back here rather than hard-coding it.
document.addEventListener("click", function (event) {
    const th = event.target.closest(".pp-st-table thead th[data-metric]");
    if (!th) return;

    const wrap = th.closest("[data-sim-input]");
    if (!wrap) return;

    Shiny.setInputValue(
        wrap.dataset.simInput,
        { metric: th.dataset.metric, t: Date.now() },
        { priority: "event" }
    );
});
