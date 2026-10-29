// Mapa de sitios de interés: Leaflet + OpenStreetMap.
// Datos: /api/sitios   ·   Ruta óptima (Dijkstra): /api/sitios/<id>/ruta?modo=a_pie|carro
(() => {
  const ICONOS = {   // Emoji por categoría. Agregue las suyas aquí.
    'Parqueadero': '🅿️', 'Centro comercial': '🛍️', 'Salud': '⚕️', 'Supermercado': '🛒', 'Transporte': '🚌',
    'Educación': '🎓', 'Parque': '🌳', 'Seguridad': '🛡️', 'Restaurante': '🍽️', 'Banco': '🏦', 'Deporte': '⚽'
  };
  const icono = c => ICONOS[c] || '📍';
  const $ = id => document.getElementById(id);
  const fmtDist = m => m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(2).replace('.', ',')} km`;
  const fmtMin = min => min < 60 ? `${Math.max(1, Math.round(min))} min` : `${Math.floor(min / 60)} h ${Math.round(min % 60)} min`;

  const el = $('mapa');
  const mapa = L.map(el).setView([0, 0], +el.dataset.zoom);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(mapa);
  const capaSitios = L.layerGroup().addTo(mapa);
  const capaRuta = L.layerGroup().addTo(mapa);

  let centro = null, sitios = [], categoria = 'todas', sel = null, modo = 'a_pie', peticion = 0;
  const marcadores = new Map();

  // ---------- lista y marcadores ----------
  function visibles() {
    return sitios.filter(s => categoria === 'todas' || s.categoria === categoria)
                 .sort((a, b) => a.linea_recta_m - b.linea_recta_m);
  }

  function dibujar() {
    capaSitios.clearLayers(); marcadores.clear();
    const lista = $('lista-sitios'); lista.replaceChildren();
    const vis = visibles();
    $('lista-titulo').textContent = `Sitios (${vis.length})`;
    vis.forEach(s => {
      const m = L.marker([s.lat, s.lon], {
        title: s.nombre,
        icon: L.divIcon({ className: '', html: `<span class="pin">${icono(s.categoria)}</span>`, iconSize: [28, 28], iconAnchor: [14, 14] })
      }).on('click', () => seleccionar(s)).addTo(capaSitios);
      marcadores.set(s.id, m);

      const li = document.createElement('li');
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'item';
      const t = document.createElement('strong'); t.textContent = `${icono(s.categoria)} ${s.nombre}`;
      const d = document.createElement('small'); d.textContent = `${s.categoria} · ≈ ${fmtDist(s.linea_recta_m)} en línea recta`;
      b.append(t, d); b.addEventListener('click', () => seleccionar(s));
      li.appendChild(b); lista.appendChild(li);
    });
    if (!vis.length) lista.innerHTML = '<li class="muted">No hay sitios cargados todavía.</li>';
    marcarSeleccion();
  }

  function ajustarVista() {
    const pts = visibles().map(s => [s.lat, s.lon]);
    if (centro) pts.push([centro.lat, centro.lon]);
    if (pts.length > 1) mapa.fitBounds(L.latLngBounds(pts).pad(0.15));
    else if (pts.length === 1) mapa.setView(pts[0], 16);
  }

  function crearFiltros() {
    const cont = $('filtros'); cont.replaceChildren();
    ['todas', ...new Set(sitios.map(s => s.categoria))].forEach(c => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'chip' + (c === categoria ? ' active' : '');
      b.textContent = c === 'todas' ? 'Todas' : `${icono(c)} ${c}`;
      b.addEventListener('click', () => { categoria = c; volver(); crearFiltros(); dibujar(); ajustarVista(); });
      cont.appendChild(b);
    });
  }

  // ---------- panel de detalle ----------
  function marcarSeleccion() {
    marcadores.forEach((m, id) => m.getElement()?.firstChild?.classList.toggle('sel', !!sel && id === sel.id));
  }

  function seleccionar(s) {
    sel = s;
    marcarSeleccion();
    $('panel-lista').hidden = true; $('panel-detalle').hidden = false;
    $('d-categoria').textContent = `${icono(s.categoria)} ${s.categoria}`;
    $('d-nombre').textContent = s.nombre;
    $('d-descripcion').textContent = s.descripcion;

    const datos = $('d-datos'); datos.replaceChildren();
    const fila = (titulo, nodo) => { const dt = document.createElement('dt'); dt.textContent = titulo; const dd = document.createElement('dd'); dd.append(nodo); datos.append(dt, dd); };
    if (s.direccion) fila('Dirección', s.direccion);
    if (s.horario) fila('Horario', s.horario);
    if (s.telefono) fila('Teléfono', s.telefono);
    if (s.web && /^https?:\/\//i.test(s.web)) {
      const a = document.createElement('a'); a.href = s.web; a.textContent = s.web; a.target = '_blank'; a.rel = 'noopener noreferrer'; fila('Sitio web', a);
    }
    mapa.panTo([s.lat, s.lon]);
    pedirRuta();
  }

  function volver() {
    sel = null; peticion++; capaRuta.clearLayers();
    marcarSeleccion();
    $('panel-detalle').hidden = true; $('panel-lista').hidden = false;
  }

  function estado(cual, texto) {
    ['ruta-cargando', 'ruta-ok', 'ruta-error', 'ruta-aviso'].forEach(id => $(id).hidden = true);
    if (cual) { $(cual).hidden = false; if (texto !== undefined) $(cual).textContent = texto; }
  }

  function enlaceOSM() {
    const motor = modo === 'carro' ? 'fossgis_osrm_car' : 'fossgis_osrm_foot';
    $('d-osm').href = `https://www.openstreetmap.org/directions?engine=${motor}&route=${centro.lat}%2C${centro.lon}%3B${sel.lat}%2C${sel.lon}`;
  }

  async function pedirRuta() {
    const mio = ++peticion;
    capaRuta.clearLayers(); enlaceOSM(); estado('ruta-cargando');
    try {
      const r = await fetch(`/api/sitios/${sel.id}/ruta?modo=${modo}`);
      const d = await r.json();
      if (mio !== peticion) return;                       // llegó tarde: el usuario ya cambió de sitio o de modo
      if (!r.ok) throw new Error(d.error || 'No se pudo calcular la ruta.');
      L.polyline(d.ruta, { color: '#13402A', weight: 5, opacity: .85 }).addTo(capaRuta);
      mapa.fitBounds(L.latLngBounds(d.ruta).pad(0.2));
      $('r-dist').textContent = fmtDist(d.distancia_m);
      $('r-tiempo').textContent = `≈ ${fmtMin(d.duracion_min)} ${modo === 'a_pie' ? 'a pie' : 'en carro'} · ruta más corta (Dijkstra)`;
      $('r-recta').textContent = `En línea recta: ${fmtDist(d.linea_recta_m)}`;
      estado('ruta-ok');
      if (d.aviso) { $('ruta-aviso').hidden = false; $('ruta-aviso').textContent = d.aviso; }
    } catch (e) {
      if (mio !== peticion) return;
      estado('ruta-error', `${e.message} En línea recta: ≈ ${fmtDist(sel.linea_recta_m)}.`);
    }
  }

  document.querySelectorAll('.modos button').forEach(b => b.addEventListener('click', () => {
    modo = b.dataset.modo;
    document.querySelectorAll('.modos button').forEach(x => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
    if (sel) pedirRuta();
  }));
  $('volver').addEventListener('click', () => { volver(); ajustarVista(); });

  // ---------- carga y actualización en vivo ----------
  let version = null, ids = new Set(), temporizadorAviso = null;
  const refresco = Math.max(5, +el.dataset.refresco || 20) * 1000;

  function avisarNuevos(nuevos) {
    const caja = $('aviso-nuevo');
    caja.textContent = nuevos.length === 1 ? `➕ Nuevo sitio: ${nuevos[0].nombre}` : `➕ ${nuevos.length} sitios nuevos en el mapa`;
    caja.hidden = false;
    clearTimeout(temporizadorAviso);
    temporizadorAviso = setTimeout(() => caja.hidden = true, 8000);
  }

  async function cargar(primera) {
    const r = await fetch('/api/sitios', { cache: 'no-store' });
    const d = await r.json();
    $('actualizado').textContent = `Actualizado a las ${new Date().toLocaleTimeString('es-CO')} · el mapa se refresca solo`;
    if (d.version === version) return;                    // nada cambió: no se redibuja

    const nuevos = d.sitios.filter(s => !ids.has(s.id));
    version = d.version; centro = d.centro; sitios = d.sitios; ids = new Set(sitios.map(s => s.id));

    if (primera) {
      const logo = L.icon({ iconUrl: '/static/img/logo-icono.png', iconSize: [30, 39], iconAnchor: [15, 39] });
      L.marker([centro.lat, centro.lon], { icon: logo, title: centro.nombre, zIndexOffset: 1000 })
        .bindPopup(`<strong>${centro.nombre}</strong><br>Punto central desde donde se miden las distancias`).addTo(mapa);
    }
    if (categoria !== 'todas' && !sitios.some(s => s.categoria === categoria)) categoria = 'todas';
    crearFiltros(); dibujar();
    if (primera) ajustarVista();
    else if (nuevos.length) avisarNuevos(nuevos);

    if (sel) {                                            // el usuario tiene un sitio abierto: se conserva si sigue igual
      const actual = sitios.find(s => s.id === sel.id && s.lat === sel.lat && s.lon === sel.lon);
      if (actual) { sel = actual; marcarSeleccion(); } else { volver(); }
    }
  }

  cargar(true).catch(() => { $('lista-sitios').innerHTML = '<li class="nota-error">No se pudieron cargar los sitios.</li>'; });
  setInterval(() => { if (!document.hidden) cargar(false).catch(() => {}); }, refresco);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) cargar(false).catch(() => {}); });
})();
