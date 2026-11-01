/* TGV MAX Explorer — carte Leaflet + interactions HTMX */
(function () {
  "use strict";

  const FRANCE = [[42.2, -4.9], [51.1, 8.3]];
  const COLORS = { direct: "#1f5fd1", roundtrip: "#1f5fd1", connection: "#8a4fff", origin: "#e4572e" };

  let map = null;
  let layer = null;
  let manyStations = false;
  const linksBySlug = new Map();
  const markersBySlug = new Map();

  const $ = (sel, root = document) => root.querySelector(sel);
  const form = () => $("#search-form");

  // --- Carte ------------------------------------------------------------------

  function initMap() {
    const el = $("#map");
    if (!el || typeof L === "undefined") return;
    map = L.map(el, { zoomControl: false, preferCanvas: false, minZoom: 4 }).fitBounds(FRANCE);
    L.control.zoom({ position: "topright" }).addTo(map);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      subdomains: "abcd",
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    }).addTo(map);
    layer = L.layerGroup().addTo(map);
    map.on("zoomend", updateLabelVisibility);
    render();
  }

  /** Points d'un arc léger entre a et b (plus lisible que des segments droits superposés). */
  function arc(a, b, bend = 0.18, steps = 24) {
    const [lat1, lon1] = a, [lat2, lon2] = b;
    const mx = (lat1 + lat2) / 2, my = (lon1 + lon2) / 2;
    const dx = lat2 - lat1, dy = lon2 - lon1;
    const cx = mx - dy * bend, cy = my + dx * bend;
    const pts = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps, u = 1 - t;
      pts.push([u * u * lat1 + 2 * u * t * cx + t * t * lat2, u * u * lon1 + 2 * u * t * cy + t * t * lon2]);
    }
    return pts;
  }

  function readData() {
    const node = $("#map-data");
    if (!node) return null;
    try { return JSON.parse(node.textContent); } catch (e) { return null; }
  }

  function render() {
    if (!map) return;
    const data = readData();
    layer.clearLayers();
    linksBySlug.clear();
    markersBySlug.clear();
    if (!data) return;

    const bounds = [];
    // Beaucoup de gares : étiquettes masquées tant qu'on n'a pas zoomé (visibles au survol).
    manyStations = data.stations.length > 22;
    const showLabels = data.mode !== "overview";

    data.links.forEach((l) => {
      const color = COLORS[l.kind] || COLORS.direct;
      const line = L.polyline(arc(l.from, l.to), {
        color, weight: 2.2, opacity: 0.55, dashArray: l.kind === "connection" ? "5 6" : null,
        interactive: false,
      }).addTo(layer);
      if (!linksBySlug.has(l.slug)) linksBySlug.set(l.slug, []);
      linksBySlug.get(l.slug).push(line);
    });

    const counts = data.stations.map((s) => s.count || 1);
    const maxCount = Math.max(1, ...counts);

    data.stations.forEach((s) => {
      const isConn = !!s.connection;
      const radius = data.mode === "overview" ? 4 + 10 * Math.sqrt((s.count || 1) / maxCount) : 6;
      const m = L.circleMarker([s.lat, s.lon], {
        radius, weight: 2, color: "#fff",
        fillColor: isConn ? COLORS.connection : COLORS.direct, fillOpacity: 0.95,
      }).addTo(layer);
      bounds.push([s.lat, s.lon]);
      markersBySlug.set(s.slug, m);

      const detail = data.mode === "overview"
        ? `${s.count} trajet${s.count > 1 ? "s" : ""} MAX`
        : (s.best ? `${isConn ? "1 corresp. · " : ""}${s.best}` : "");
      if (showLabels) {
        m.bindTooltip(`${escapeHtml(s.name)}${s.best ? `<span class="dur">${escapeHtml(s.best)}</span>` : ""}`, {
          permanent: true, direction: "right", offset: [6, 0], className: `station-label${isConn ? " conn" : ""}`,
        });
      } else {
        m.bindTooltip(`<strong>${escapeHtml(s.name)}</strong>${escapeHtml(detail)}`, { className: "map-tip", direction: "top" });
      }
      m.on("click", () => onStationClick(data.mode, s.slug));
      m.on("mouseover", () => { highlight(s.slug, true); toggleForce(m, true); });
      m.on("mouseout", () => { highlight(s.slug, false); toggleForce(m, false); });
    });

    if (data.origin) {
      const o = data.origin;
      L.circleMarker([o.lat, o.lon], { radius: 9, weight: 3, color: "#fff", fillColor: COLORS.origin, fillOpacity: 1 })
        .bindTooltip(`<strong>${escapeHtml(o.name)}</strong>`, { permanent: true, direction: "left", offset: [-8, 0], className: "station-label origin-label" })
        .addTo(layer);
      bounds.push([o.lat, o.lon]);
    }

    updateLabelVisibility();
    if (bounds.length > 1) map.flyToBounds(bounds, { padding: [50, 50], maxZoom: 8, duration: 0.6 });
    else if (bounds.length === 1) map.flyTo(bounds[0], 7, { duration: 0.6 });
    else map.flyToBounds(FRANCE, { duration: 0.6 });
  }

  function updateLabelVisibility() {
    map.getContainer().classList.toggle("hide-labels", manyStations && map.getZoom() < 7);
  }

  function toggleForce(marker, on) {
    const tip = marker.getTooltip() && marker.getTooltip().getElement();
    if (tip) tip.classList.toggle("force", on);
  }

  function highlight(slug, on) {
    (linksBySlug.get(slug) || []).forEach((l) => l.setStyle({ weight: on ? 4.5 : 2.2, opacity: on ? 0.95 : 0.55 }));
    const m = markersBySlug.get(slug);
    if (m) toggleForce(m, on);
    if (m) { m.setStyle({ weight: on ? 3 : 2, color: on ? "#14213d" : "#fff" }); if (on) m.bringToFront(); }
    document.querySelectorAll(`.card[data-slug="${CSS.escape(slug)}"]`).forEach((c) => c.classList.toggle("is-hover", on));
  }

  function onStationClick(mode, slug) {
    if (mode === "overview") return pick("origin", slug);
    if (mode === "to") return pick("origin", slug);
    const card = document.querySelector(`.card[data-slug="${CSS.escape(slug)}"]`);
    if (card) {
      if (card.tagName === "DETAILS") card.open = true;
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      card.classList.add("is-hover");
      setTimeout(() => card.classList.remove("is-hover"), 1200);
    }
  }

  // --- Formulaire ---------------------------------------------------------------

  function submit() {
    const f = form();
    if (!f) return;
    if (window.htmx) window.htmx.trigger(f, "submit");
    else f.requestSubmit();
  }

  function pick(field, slug) {
    const select = form() && form().elements[field];
    if (!select) return;
    select.value = slug;
    submit();
  }

  function isoDate(d) {
    const z = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
  }

  function nextWeekday(from, weekday) {
    const d = new Date(from);
    d.setDate(d.getDate() + ((weekday - d.getDay() + 7) % 7));
    return d;
  }

  function applyWeekendPreset(kind) {
    const f = form();
    if (!f) return;
    const today = new Date();
    const set = (name, v) => { if (f.elements[name]) f.elements[name].value = v; };
    let out, back;
    if (kind === "day") {
      out = f.elements.out_date.value ? new Date(f.elements.out_date.value) : today;
      back = out; set("out_after", "06:00"); set("back_after", "16:00");
    } else if (kind === "sat-sun") {
      out = nextWeekday(today, 6); back = new Date(out); back.setDate(out.getDate() + 1);
      set("out_after", "06:00"); set("back_after", "14:00");
    } else {
      out = nextWeekday(today, 5); back = new Date(out); back.setDate(out.getDate() + (kind === "fri-mon" ? 3 : 2));
      set("out_after", "16:00"); set("back_after", kind === "fri-mon" ? "06:00" : "14:00");
    }
    set("out_date", isoDate(out));
    set("back_date", isoDate(back));
    submit();
  }

  document.addEventListener("click", (e) => {
    const t = e.target.closest("[data-pick-origin],[data-pick-destination],[data-date-step],[data-swap],[data-enable-connections],[data-weekend]");
    if (!t) return;
    const f = form();
    if (t.dataset.pickOrigin) {
      pick("origin", t.dataset.pickOrigin);
    } else if (t.dataset.pickDestination) {
      pick("destination", t.dataset.pickDestination);
    } else if (t.dataset.dateStep) {
      const input = f.elements.date;
      const d = input.value ? new Date(input.value + "T12:00:00") : new Date();
      d.setDate(d.getDate() + Number(t.dataset.dateStep));
      input.value = isoDate(d);
      submit();
    } else if ("swap" in t.dataset) {
      const o = f.elements.origin, d = f.elements.destination;
      [o.value, d.value] = [d.value, o.value];
      submit();
    } else if ("enableConnections" in t.dataset) {
      f.elements.connections.checked = true;
      submit();
    } else if (t.dataset.weekend) {
      applyWeekendPreset(t.dataset.weekend);
    }
  });

  document.addEventListener("mouseover", (e) => {
    const card = e.target.closest(".card[data-slug]");
    if (card && !card.contains(e.relatedTarget)) highlight(card.dataset.slug, true);
  });
  document.addEventListener("mouseout", (e) => {
    const card = e.target.closest(".card[data-slug]");
    if (card && !card.contains(e.relatedTarget)) highlight(card.dataset.slug, false);
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (window.htmx) {
      // Retour arrière : on recharge la page plutôt que de restaurer un DOM sans carte.
      window.htmx.config.historyCacheSize = 0;
      window.htmx.config.refreshOnHistoryMiss = true;
    }
    initMap();
  });
  document.addEventListener("htmx:afterSettle", (e) => {
    if (e.target && e.target.id === "results") render();
  });
})();
