// Zentrale, per Event-Delegation gebundene UI-Aktionen – ersetzt Inline-Handler
// (onclick/onsubmit/onchange), damit die CSP ohne script-src 'unsafe-inline' auskommt.
// Deklarativ via data-Attribute:
//   <form data-confirm="Wirklich löschen?">        Rückfrage vor dem Absenden
//   <button data-confirm="…" type="submit">        Rückfrage vor dem Absenden (Button im Formular)
//   <select data-autosubmit>                        Formular bei Auswahl-Änderung absenden
//   <button data-print>                             window.print()
//   <input data-select-on-click>                    Inhalt bei Klick markieren
//   <button data-copy-from="#link">                 Feldwert in die Zwischenablage; Label -> „kopiert ✓“
//   <button data-set-value="#mxp-sa" data-value="7">Verstecktes Feld auf Wert setzen
//   <button data-nav-select="#gruppe-sel" data-nav-tpl="/gruppen/{v}/druck/">  Auswahl -> Navigation
(function () {
  "use strict";

  // Rückfrage: Formular-Submit (data-confirm am <form>) …
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (f && f.dataset && f.dataset.confirm && !window.confirm(f.dataset.confirm)) {
      e.preventDefault();
    }
  });

  // … oder am auslösenden Button/Element (data-confirm am Klick-Ziel).
  document.addEventListener("click", function (e) {
    var c = e.target.closest ? e.target.closest("[data-confirm]") : null;
    if (c && !c.matches("form") && !window.confirm(c.dataset.confirm)) {
      e.preventDefault(); e.stopPropagation(); return;
    }
    var p = e.target.closest ? e.target.closest("[data-print]") : null;
    if (p) { e.preventDefault(); window.print(); return; }

    var cp = e.target.closest ? e.target.closest("[data-copy-from]") : null;
    if (cp) {
      e.preventDefault();
      var src = document.querySelector(cp.getAttribute("data-copy-from"));
      if (src && navigator.clipboard) {
        navigator.clipboard.writeText(src.value != null ? src.value : src.textContent)
          .then(function () { cp.textContent = "kopiert ✓"; });
      }
      return;
    }

    var sv = e.target.closest ? e.target.closest("[data-set-value]") : null;
    if (sv) {
      var ziel = document.querySelector(sv.getAttribute("data-set-value"));
      if (ziel) ziel.value = sv.getAttribute("data-value") || "";
      return;   // kein preventDefault: der Button darf zusätzlich sein Formular normal absenden
    }

    var nv = e.target.closest ? e.target.closest("[data-nav-select]") : null;
    if (nv) {
      e.preventDefault();
      var sel = document.querySelector(nv.getAttribute("data-nav-select"));
      var tpl = nv.getAttribute("data-nav-tpl") || "";
      if (sel && sel.value) location.href = tpl.replace("{v}", encodeURIComponent(sel.value));
      return;
    }
  });

  // Auswahl-Feld sendet sein Formular ab (Filter/Umschalter).
  document.addEventListener("change", function (e) {
    var s = e.target;
    if (s && s.matches && s.matches("[data-autosubmit]") && s.form) s.form.submit();
  });

  // Feld bei Fokus/Klick markieren (z. B. Aktivierungslink zum Kopieren).
  document.addEventListener("click", function (e) {
    var el = e.target;
    if (el && el.matches && el.matches("[data-select-on-click]") && el.select) el.select();
  });
})();
