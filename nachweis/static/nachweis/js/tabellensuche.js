// Wiederverwendbare Client-Tabellensuche – filtert tbody-Zeilen nach Textinhalt.
// Selbst-initialisierend und ohne Inline-JS (CSP-konform, laedt via script-src 'self').
// Markup:
//   <input type="search" data-tsuche="#meine-tabelle" data-count="#treffer">
//   <table id="meine-tabelle"> … <tr>-Zeilen … <tr data-tsuche-skip> = nie filtern </table>
// Mehrere durch Leerzeichen getrennte Begriffe werden UND-verknuepft (alle muessen vorkommen).
(function () {
  function norm(s) { return (s || "").toLowerCase(); }

  function anwenden(input) {
    var tab = document.querySelector(input.getAttribute("data-tsuche"));
    if (!tab || !tab.tBodies.length) return;
    var q = norm(input.value).trim();
    var begriffe = q ? q.split(/\s+/) : [];
    var zeilen = tab.tBodies[0].rows;
    var sichtbar = 0, gesamt = 0;
    for (var i = 0; i < zeilen.length; i++) {
      var zeile = zeilen[i];
      if (zeile.hasAttribute("data-tsuche-skip")) continue;   // z. B. die "leer"-Zeile
      gesamt++;
      var txt = norm(zeile.textContent);
      var treffer = begriffe.every(function (b) { return txt.indexOf(b) !== -1; });
      zeile.hidden = !treffer;
      if (treffer) sichtbar++;
    }
    var cntSel = input.getAttribute("data-count");
    if (cntSel) {
      var el = document.querySelector(cntSel);
      if (el) el.textContent = q ? (sichtbar + " / " + gesamt) : "";
    }
  }

  function init() {
    var felder = document.querySelectorAll("input[data-tsuche]");
    for (var i = 0; i < felder.length; i++) {
      (function (input) {
        input.addEventListener("input", function () { anwenden(input); });
        if (input.value) anwenden(input);   // vorbefuellter Wert (z. B. Zurueck-Navigation)
      })(felder[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();
