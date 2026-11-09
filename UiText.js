.pragma library

// The host tooltip owns its Text item, so escape markup at this boundary.
function tooltip(value) {
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
