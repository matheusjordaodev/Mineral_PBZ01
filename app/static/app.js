let map;
let baseLayerOSM;
let baseLayerSatellite;
let currentBase = "osm";
const layerObjects = {}; // { layerId: L.GeoJSON }
let fullBounds = null;

// Coordenadas aproximadas para a área de interesse (ajuste como quiser)
const AOI_CENTER = [-23.5, -44.9];
const AOI_BOUNDS = [
  [-23.6, -45.0],
  [-23.4, -44.8],
];

function initMap() {
  map = L.map("map", {
    center: AOI_CENTER,
    zoom: 13,
    minZoom: 11,
    maxZoom: 18,
    maxBounds: AOI_BOUNDS, // mantém a área de interesse "travada"
    maxBoundsViscosity: 0.8,
  });

  baseLayerOSM = L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      attribution: "&copy; OpenStreetMap contributors",
    }
  ).addTo(map);

  baseLayerSatellite = L.tileLayer(
    "https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    {
      subdomains: ["mt0", "mt1", "mt2", "mt3"],
      attribution: "&copy; Google",
    }
  );

  // Botões laterais
  setupGisButtons();
  setupQuickButtons();

  // Buscar lista de camadas e carregar as visíveis por padrão
  fetch("/api/layers")
    .then((r) => r.json())
    .then((data) => {
      data.layers.forEach((layer) => {
        if (layer.default_visible) {
          loadLayer(layer.id);
        }
      });
    });

  // Checkboxes de camada
  document.querySelectorAll(".layer-toggle").forEach((checkbox) => {
    checkbox.addEventListener("change", (e) => {
      const layerId = e.target.dataset.layerId;
      const checked = e.target.checked;
      if (checked) {
        loadLayer(layerId);
      } else {
        removeLayer(layerId);
      }
    });
  });
}

function loadLayer(layerId) {
  fetch(`/api/features/${layerId}`)
    .then((r) => {
      if (!r.ok) throw new Error("Erro ao buscar GeoJSON");
      return r.json();
    })
    .then((geojson) => {
      // Remove camada existente se já estiver carregada
      if (layerObjects[layerId]) {
        map.removeLayer(layerObjects[layerId]);
      }

      const layer = L.geoJSON(geojson, {
        onEachFeature: (feature, lyr) => {
          lyr.on("click", () => {
            onFeatureClick(layerId, feature);
          });
        },
        pointToLayer: (feature, latlng) => {
          let color = "#22c55e";
          if (layerId === "videotransecto") color = "#2563eb";
          if (layerId === "fotoquadrado") color = "#f97316";
          return L.circleMarker(latlng, {
            radius: 6,
            weight: 1,
            color: "#111827",
            fillColor: color,
            fillOpacity: 0.9,
          });
        },
      }).addTo(map);

      layerObjects[layerId] = layer;

      // Atualiza o fullBounds
      if (fullBounds === null) {
        fullBounds = layer.getBounds();
      } else {
        fullBounds = fullBounds.extend(layer.getBounds());
      }
    })
    .catch((err) => {
      console.error(`Erro ao carregar camada ${layerId}:`, err);
    });
}

function removeLayer(layerId) {
  const layer = layerObjects[layerId];
  if (layer) {
    map.removeLayer(layer);
    delete layerObjects[layerId];
  }
}


// --- MODAL LOGIC START ---

function setupModal() {
  const modal = document.getElementById("details-modal");
  const closeBtn = document.getElementById("modal-close-btn");

  // Close on button click
  closeBtn.addEventListener("click", () => {
    closeModal();
  });

  // Close on click outside
  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      closeModal();
    }
  });

  // Close on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.classList.contains("hidden")) {
      closeModal();
    }
  });
}

function openModal(feature) {
  const modal = document.getElementById("details-modal");
  const props = feature.properties || {};

  // 1. Title
  const titleEl = document.getElementById("modal-title");
  titleEl.textContent = `Ponto: ${props.id || props.codigo || "Sem ID"}`;

  // 2. Latest Updates (Mocked for now)
  const updatesEl = document.getElementById("modal-updates");
  // Simulating random dates/updates
  const now = new Date();
  const dateStr = now.toLocaleDateString("pt-BR");
  updatesEl.innerHTML = `
    <p><strong>${dateStr}:</strong> Vistoria realizada com sucesso.</p>
    <p><strong>${dateStr}:</strong> Dados sincronizados com o servidor.</p>
  `;

  // 3. Info / Attributes
  const attrsDiv = document.getElementById("modal-attributes");
  const rows = Object.entries(props).map(
    ([key, value]) =>
      `<div><strong>${key}:</strong> <span>${value ?? "-"}</span></div>`
  );
  attrsDiv.innerHTML =
    rows.join("") || "<em>Nenhum atributo disponível.</em>";

  // 4. Media (Mocked as requested)
  // Image: Random nature image from unsplash source or placeholder
  const imgEl = document.getElementById("modal-image");
  imgEl.src = "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?q=80&w=600&auto=format&fit=crop";

  // Video: Sample Big Buck Bunny or similar standard sample
  const videoFrame = document.getElementById("modal-video");
  // Using a sample video from Archive.org or similar that allows embedding
  // Or just a placeholder iframe. Let's use a sample mp4 directly in video tag if possible, 
  // but the HTML has an iframe. Let's switch to video tag logic or keep iframe. 
  // The user asked for "link same thing with video", so let's stick to a sample video URL.
  // We'll replace the iframe with a video tag for better control or just set src if iframe.

  // Let's actually update the HTML to rely on the container, 
  // but since we are in JS, we can manipulate the container content.
  const videoContainer = document.getElementById("modal-video-container");
  videoContainer.innerHTML = `
    <video controls width="100%" height="200">
      <source src="https://www.w3schools.com/html/mov_bbb.mp4" type="video/mp4">
      Seu navegador não suporta a tag de vídeo.
    </video>
  `;

  // 5. Links / Documents (Mocked)
  const linksEl = document.getElementById("modal-links");
  linksEl.innerHTML = `
    <li><a href="#" target="_blank">Relatório de Impacto Ambiental.pdf</a></li>
    <li><a href="#" target="_blank">Certificado de Vistoria.pdf</a></li>
    <li><a href="#" target="_blank">Planilha de Dados Brutos.xlsx</a></li>
  `;

  // Show Modal
  modal.classList.remove("hidden");
}

function closeModal() {
  const modal = document.getElementById("details-modal");
  modal.classList.add("hidden");

  // Stop video if playing
  const videoContainer = document.getElementById("modal-video-container");
  videoContainer.innerHTML = ""; // Clear content to stop playback
}

// Override the click handler
function onFeatureClick(layerId, feature) {
  openModal(feature);
}

// --- MODAL LOGIC END ---

/* Botões laterais GIS */
function setupGisButtons() {
  document.querySelectorAll(".gis-btn").forEach((btn) => {
    const action = btn.dataset.action;
    btn.addEventListener("click", () => {
      if (action === "zoom-in") map.zoomIn();
      if (action === "zoom-out") map.zoomOut();
      if (action === "zoom-full") {
        if (fullBounds) {
          map.fitBounds(fullBounds);
        } else {
          map.setView(AOI_CENTER, 13);
        }
      }
      if (action === "toggle-base") {
        toggleBaseLayer();
      }
      if (action === "locate") {
        map.setView(AOI_CENTER, 14);
      }
    });
  });
}

/* Botões de atalho na barra de filtros */
function setupQuickButtons() {
  const btnIlha = document.getElementById("btn-zoom-ilha");
  const btnFull = document.getElementById("btn-zoom-full");

  btnIlha.addEventListener("click", () => {
    map.setView(AOI_CENTER, 15);
  });

  btnFull.addEventListener("click", () => {
    if (fullBounds) {
      map.fitBounds(fullBounds);
    } else {
      map.setView(AOI_CENTER, 13);
    }
  });
}

/* Alternar mapa base */
function toggleBaseLayer() {
  if (currentBase === "osm") {
    map.removeLayer(baseLayerOSM);
    baseLayerSatellite.addTo(map);
    currentBase = "sat";
  } else {
    map.removeLayer(baseLayerSatellite);
    baseLayerOSM.addTo(map);
    currentBase = "osm";
  }
}

/* Inicializar quando o DOM estiver pronto */
document.addEventListener("DOMContentLoaded", () => {
  initMap();
  setupModal();
});
