
        const appLoadingOverlay = document.getElementById('appLoadingOverlay');

        function setAppLoading(loading) {
            if (!appLoadingOverlay) return;
            appLoadingOverlay.style.display = loading ? 'flex' : 'none';
        }

        const loaderStyle = document.createElement('style');
        loaderStyle.textContent = '@keyframes spinLoader { to { transform: rotate(360deg); } }';
        document.head.appendChild(loaderStyle);

        // Auth State
        var authToken = localStorage.getItem('authToken');
        var currentUser = localStorage.getItem('currentUser');
        var currentUserPerfil = localStorage.getItem('currentUserPerfil');

        function decodeJwtPayload(token) {
            if (!token || typeof token !== 'string') return null;
            const parts = token.split('.');
            if (parts.length < 2) return null;
            try {
                const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
                const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
                return JSON.parse(atob(padded));
            } catch (e) {
                return null;
            }
        }

        function hydrateAuthStateFromToken() {
            const payload = decodeJwtPayload(authToken);
            if (!payload) return;

            if (payload.sub) {
                currentUser = String(payload.sub);
                localStorage.setItem('currentUser', currentUser);
            }

            if (payload.perfil) {
                currentUserPerfil = String(payload.perfil).toLowerCase();
                localStorage.setItem('currentUserPerfil', currentUserPerfil);
            }
        }

        function getCurrentPerfil() {
            return String(currentUserPerfil || 'usuario').toLowerCase();
        }

        function canAccessGerenciamentoDados() {
            const perfil = getCurrentPerfil();
            return perfil === 'admin' || perfil === 'pesquisador';
        }

        function canAccessCadastroPorIlhas() {
            return getCurrentPerfil() === 'admin';
        }

        function applyProfileVisibility() {
            const btnDados = document.getElementById('btnGerenciarDados');
            if (btnDados) btnDados.style.display = canAccessGerenciamentoDados() ? 'block' : 'none';

            const btnUsuarios = document.getElementById('btnGerenciarUsuarios');
            if (btnUsuarios) btnUsuarios.style.display = getCurrentPerfil() === 'admin' ? 'block' : 'none';

            const tabEstacoes = document.getElementById('tabEstacoes');
            if (tabEstacoes) tabEstacoes.style.display = canAccessCadastroPorIlhas() ? '' : 'none';
        }

        if (authToken) hydrateAuthStateFromToken();
        if (!authToken || !currentUser) {
            currentUser = null;
            currentUserPerfil = null;
        }

        var mapStarted = false;
        var map;
        var layerIlhas;
        var layerEspacos;
        var baseLayerSatellite;
        var baseLayerGeoServerWms;
        var ilhaMarkers = [];
        var geoserverSourceActive = false;
        var geoserverWmsActive = false;
        var ilhasVisiveis = true;
        var measureMode = false;
        var measurePoints = [];
        var measureLine = null;
        var measureBox;
        var identifyMode = false;
        var modalOverlay = document.getElementById('mockModal');
        var modalTitleEl = document.getElementById('modalTitle');
        var modalBodyEl = document.getElementById('modalBody');
        var mockContent = {
            'projeto': { title: 'Sobre o Projeto', html: '<p>O PMASCC visa monitorar a incidência do Coral-sol nas ilhas do litoral de SP.</p><p>Metodologia baseada em transectos de vídeo e foto-quadrados.</p>' },
            'documentos': { title: 'Documentos', html: '<div id="docsList"><div style="color:#c5d8e3;">Carregando...</div></div>' },
            'imagens': { title: 'Galeria de Imagens', html: '<div id="galeriaLoading" style="color:#c5d8e3;">Carregando imagens...</div><div id="galeriaContainer" style="display:none; max-height:400px; overflow-y:auto; padding-right:5px;"></div>' },
            'campanha': { title: 'Filtro por Campanha', html: '<div class="mock-filters"><label>Campanha</label><select id="filterCampanhaSelect"><option value="">Carregando...</option></select></div><div style="margin-top:10px;"><button onclick="applyCampanhaFilter()" style="padding:6px 12px; background:#0f8bb3; color:#fff; border:none; border-radius:4px; cursor:pointer;">Filtrar</button></div>' },
            'ilha': { title: 'Filtro por Ilha', html: '<div class="mock-filters"><label>Ilha</label><select id="filterIlhaSelect"><option value="">Carregando...</option></select></div><div style="margin-top:10px;"><button onclick="applyIlhaFilter()" style="padding:6px 12px; background:#0f8bb3; color:#fff; border:none; border-radius:4px; cursor:pointer;">Filtrar</button></div>' },
            'metodo': { title: 'Filtro por Método', html: '<div class="mock-filters"><label>Método</label><select><option>Vídeo Transecto</option><option>Foto Quadrado</option><option>Busca Ativa</option></select></div><div style="margin-top:10px;"><button style="padding:6px 12px; background:#0f8bb3; color:#fff; border:none; border-radius:4px;">Filtrar</button></div>' }
        };

        // Gallery State
        var currentMediaList = [];
        var currentMediaIndex = 0;
        var methodPickerResolver = null;
        var campanhaMethodHints = {};
        var campaignStationsCache = {};
        var isCreatingCampanha = false;

        var ilhas = []; // Will be fetched from API
        var selectedQCampanhaId = null;
        var selectedQEstacaoId = null;
        var selectedQEstacaoInfo = null;
        var selectedBatchCampanhaId = null;
        var isSubmittingBatchUpload = false;
        var currentDataTab = 'inicio';
        var currentDataFlowAction = 'inicio';
        var pendingDataTabAfterIlha = null;
        var dataFlowNotice = '';
        var lastCreatedCampaignContext = null;

        function getCampaignPublicId(campanha) {
            if (!campanha) return '';
            return String(campanha.uuid || campanha.id || '').trim();
        }

        function getCampaignDisplayLabel(campanha) {
            if (!campanha) return '-';
            const nome = String(campanha.nome || '').trim();
            if (campanha.data && nome) return `${nome} (${campanha.data})`;
            if (nome) return nome;
            const publicId = getCampaignPublicId(campanha);
            return publicId || 'Campanha selecionada';
        }

        function getStatusColor(corStatus) {
            if (corStatus === 'green') return '#1fbf5b';
            if (corStatus === 'yellow') return '#f0c330';
            return '#e04b4b';
        }

        const ILHA_DISPLAY_ORDER = [
            'Ilha das Couves',
            'Ilha Anchieta',
            'Ilha Vitória',
            'Ilha de Búzios',
            'Ilha Montão de Trigo',
            'Ilha da Queimada Grande',
            'Laje da Conceição',
            'Laje de Santos',
            'Ilha do Mar Virado',
            'Ilha da Moela',
            'Praia de Castelhanos',
            'Ilha do Guaraú',
            'Ilha das Cabras'
        ];

        function normalizeTextForSort(text) {
            return String(text || '')
                .normalize('NFD')
                .replace(/[\u0300-\u036f]/g, '')
                .toLowerCase()
                .trim();
        }

        function extractPointNumberFromCode(code) {
            const m = String(code || '').match(/(\d+)\s*$/);
            if (!m) return 1;
            const n = parseInt(m[1], 10);
            if (!Number.isFinite(n) || n < 1 || n > 8) return 1;
            return n;
        }

        function sortEspacosByCodigo(espacos) {
            return [...(espacos || [])].sort((a, b) => {
                const aCod = String(a?.codigo || '');
                const bCod = String(b?.codigo || '');
                const aNumMatch = aCod.match(/(\d+)\s*$/);
                const bNumMatch = bCod.match(/(\d+)\s*$/);
                const aNum = aNumMatch ? parseInt(aNumMatch[1], 10) : Number.MAX_SAFE_INTEGER;
                const bNum = bNumMatch ? parseInt(bNumMatch[1], 10) : Number.MAX_SAFE_INTEGER;
                if (aNum !== bNum) return aNum - bNum;
                return aCod.localeCompare(bCod, 'pt-BR');
            });
        }

        function sortIlhasByDefinedOrder(rawIlhas) {
            const orderMap = new Map(
                ILHA_DISPLAY_ORDER.map((name, index) => [normalizeTextForSort(name), index])
            );

            return [...(rawIlhas || [])]
                .map(ilha => ({
                    ...ilha,
                    espacos_amostrais: sortEspacosByCodigo(ilha.espacos_amostrais || [])
                }))
                .sort((a, b) => {
                    const aName = normalizeTextForSort(a?.nome);
                    const bName = normalizeTextForSort(b?.nome);
                    const aIdx = orderMap.has(aName) ? orderMap.get(aName) : Number.MAX_SAFE_INTEGER;
                    const bIdx = orderMap.has(bName) ? orderMap.get(bName) : Number.MAX_SAFE_INTEGER;
                    if (aIdx !== bIdx) return aIdx - bIdx;
                    return String(a?.nome || '').localeCompare(String(b?.nome || ''), 'pt-BR');
                });
        }

        function toFiniteNumber(value) {
            const n = Number(value);
            return Number.isFinite(n) ? n : null;
        }

        function buildIlhaMatchKey(rawNome) {
            return normalizeTextForSort(rawNome || '');
        }

        function buildEspacoMatchKey(ilhaId, rawCode) {
            return `${String(ilhaId || '')}|${normalizeTextForSort(rawCode || '')}`;
        }

        function mergeGeoServerLocationsIntoIlhas(geoPayload) {
            const geoserverIlhaById = new Map();
            const geoserverIlhaByName = new Map();
            (geoPayload?.ilhas || []).forEach(ilha => {
                if (ilha?.id !== undefined && ilha?.id !== null) geoserverIlhaById.set(String(ilha.id), ilha);
                const nameKey = buildIlhaMatchKey(ilha?.nome);
                if (nameKey) geoserverIlhaByName.set(nameKey, ilha);
            });

            const geoserverPontoByEspacoId = new Map();
            const geoserverPontoByCode = new Map();
            (geoPayload?.pontos || []).forEach(ponto => {
                if (ponto?.espaco_amostral_id !== undefined && ponto?.espaco_amostral_id !== null) {
                    geoserverPontoByEspacoId.set(String(ponto.espaco_amostral_id), ponto);
                }
                const codeKey = buildEspacoMatchKey(ponto?.ilha_id, ponto?.codigo || ponto?.nome);
                if (codeKey && codeKey !== '|') {
                    geoserverPontoByCode.set(codeKey, ponto);
                }
            });

            (ilhas || []).forEach(ilha => {
                const gsIlha =
                    geoserverIlhaById.get(String(ilha?.id)) ||
                    geoserverIlhaByName.get(buildIlhaMatchKey(ilha?.nome));

                if (gsIlha) {
                    const lat = toFiniteNumber(gsIlha?.coords?.[0]);
                    const lon = toFiniteNumber(gsIlha?.coords?.[1]);
                    if (lat !== null && lon !== null) {
                        ilha.coords = [lat, lon];
                    }

                    if (gsIlha.geometry && typeof gsIlha.geometry === 'object') {
                        ilha.geojson = JSON.stringify({
                            type: 'FeatureCollection',
                            features: [
                                {
                                    type: 'Feature',
                                    geometry: gsIlha.geometry,
                                    properties: { id: ilha.id, nome: ilha.nome }
                                }
                            ]
                        });
                    }
                }

                (ilha?.espacos_amostrais || []).forEach(espaco => {
                    const byId = geoserverPontoByEspacoId.get(String(espaco?.id));
                    const byCode = geoserverPontoByCode.get(
                        buildEspacoMatchKey(ilha?.id, espaco?.codigo || espaco?.nome)
                    );
                    const ponto = byId || byCode;
                    if (!ponto) return;

                    const lat = toFiniteNumber(ponto.latitude);
                    const lon = toFiniteNumber(ponto.longitude);
                    if (lat === null || lon === null) return;
                    espaco.latitude = lat;
                    espaco.longitude = lon;
                });
            });
        }

        function setMapBackgroundToSatellite() {
            if (!map) return;
            if (baseLayerGeoServerWms && map.hasLayer(baseLayerGeoServerWms)) {
                map.removeLayer(baseLayerGeoServerWms);
            }
            if (baseLayerSatellite && !map.hasLayer(baseLayerSatellite)) {
                baseLayerSatellite.addTo(map);
            }
            geoserverWmsActive = false;
        }

        function configureGeoServerWmsBaseLayer(payload) {
            if (!map) return false;
            const wmsUrl = String(payload?.config?.public_wms_url || '').trim();
            const wmsLayers = String(payload?.config?.wms_layers || '').trim();
            if (!wmsUrl || !wmsLayers) {
                setMapBackgroundToSatellite();
                return false;
            }

            try {
                if (baseLayerGeoServerWms && map.hasLayer(baseLayerGeoServerWms)) {
                    map.removeLayer(baseLayerGeoServerWms);
                }
                baseLayerGeoServerWms = L.tileLayer.wms(wmsUrl, {
                    layers: wmsLayers,
                    format: 'image/png',
                    transparent: true,
                    version: '1.1.1',
                    tiled: true,
                    opacity: 0.7
                });
                baseLayerGeoServerWms.on('tileerror', function () {
                    if (!geoserverWmsActive) return;
                    console.warn('Falha ao carregar tiles WMS do GeoServer; removendo sobreposicao WMS.');
                    setMapBackgroundToSatellite();
                });

                if (baseLayerSatellite && !map.hasLayer(baseLayerSatellite)) {
                    baseLayerSatellite.addTo(map);
                }
                baseLayerGeoServerWms.addTo(map);
                geoserverWmsActive = true;
                return true;
            } catch (err) {
                console.warn('Falha ao configurar camada WMS do GeoServer:', err);
                setMapBackgroundToSatellite();
                return false;
            }
        }

        async function enrichIlhasWithGeoServerLocations() {
            try {
                const token = localStorage.getItem('authToken');
                const response = await fetch('/api/geoserver/locations', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (!response.ok) return false;

                const payload = await response.json();
                if (Array.isArray(payload?.warnings) && payload.warnings.length > 0) {
                    console.warn('GeoServer warnings:', payload.warnings);
                }

                const wmsApplied = configureGeoServerWmsBaseLayer(payload);

                if (payload?.source !== 'geoserver') {
                    geoserverSourceActive = false;
                    return wmsApplied;
                }

                mergeGeoServerLocationsIntoIlhas(payload);
                geoserverSourceActive = true;
                return true;
            } catch (err) {
                geoserverSourceActive = false;
                setMapBackgroundToSatellite();
                console.warn('Falha ao enriquecer localizacoes com GeoServer:', err);
                return false;
            }
        }

        function formatDateBR(dateIso) {
            if (!dateIso) return '-';
            const d = new Date(dateIso);
            if (Number.isNaN(d.getTime())) return dateIso;
            return d.toLocaleDateString('pt-BR');
        }

        function updateMapLabelVisibility() {
            if (!map) return;
            const mapEl = document.getElementById('map');
            if (!mapEl) return;
            const zoom = map.getZoom();
            mapEl.classList.toggle('show-ilha-labels', zoom >= 10);
            mapEl.classList.toggle('show-estacao-labels', zoom >= 13);
        }

        async function handleLogin(event) {
            event.preventDefault();
            var user = document.getElementById('username').value.trim();
            var pass = document.getElementById('password').value.trim();
            var errorEl = document.getElementById('loginError');
            var btn = event.target.querySelector('button');

            btn.disabled = true;
            btn.textContent = "Verificando...";

            try {
                const formData = new URLSearchParams();
                formData.append('username', user);
                formData.append('password', pass);

                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded'
                    },
                    body: formData
                });

                if (response.ok) {
                    const data = await response.json();
                    authToken = data.access_token;
                    localStorage.setItem('authToken', authToken);
                    hydrateAuthStateFromToken();
                    if (!currentUser) {
                        currentUser = user;
                        localStorage.setItem('currentUser', currentUser);
                    }
                    if (!currentUserPerfil) {
                        currentUserPerfil = 'usuario';
                        localStorage.setItem('currentUserPerfil', currentUserPerfil);
                    }

                    errorEl.textContent = "";
                    document.getElementById('loginScreen').style.display = 'none';
                    var appEl = document.getElementById('app');
                    appEl.style.display = 'flex';
                    appEl.removeAttribute('aria-hidden');
                    setAppLoading(true);
                    updateUserStatus();
                    await initMap();
                    setAppLoading(false);
                } else {
                    errorEl.textContent = "Credenciais inválidas.";
                }
            } catch (e) {
                setAppLoading(false);
                errorEl.textContent = "Erro de conexão: " + e.message;
            } finally {
                btn.disabled = false;
                btn.textContent = "Entrar";
            }
        }

        function handleLogout() {
            localStorage.removeItem('authToken');
            localStorage.removeItem('currentUser');
            localStorage.removeItem('currentUserPerfil');
            authToken = null;
            currentUser = null;
            currentUserPerfil = null;
            location.reload();
        }

        function updateUserStatus() {
            if (currentUser) {
                const perfil = String(getCurrentPerfil() || '').trim();
                const usuario = String(currentUser || '').trim();
                const sameLabel = perfil && usuario && perfil.toLowerCase() === usuario.toLowerCase();
                document.getElementById('userStatus').textContent = sameLabel
                    ? `Ola, ${usuario}`
                    : `Ola, ${usuario}${perfil ? ` (${perfil})` : ''}`;
            } else {
                document.getElementById('userStatus').textContent = "";
            }
            applyProfileVisibility();
        }

        // Modal Generic
        function openMockModal(key) {
            if (!currentUser) return;
            var content = mockContent[key];
            if (!content) return;
            modalTitleEl.textContent = content.title;
            modalBodyEl.innerHTML = content.html;
            modalOverlay.style.display = 'flex';
            modalOverlay.setAttribute('aria-hidden', 'false');

            // Special init for Campanha Filter
            if (key === 'campanha') {
                loadFilterCampanhas();
            } else if (key === 'ilha') {
                loadFilterIlhas();
            } else if (key === 'imagens') {
                loadGaleriaImagens();
            } else if (key === 'documentos') {
                loadDocumentos();
            }
        }

        function closeMockModal() {
            modalOverlay.style.display = 'none';
            modalOverlay.setAttribute('aria-hidden', 'true');
        }

        // --- Documentos Logic ---
        async function loadDocumentos() {
            const container = document.getElementById('docsList');
            if (!container) return;

            container.innerHTML = '<div style="color:#c5d8e3;">Carregando documentos...</div>';

            try {
                const response = await fetch('/api/documentos');
                if (response.ok) {
                    const docs = await response.json();
                    if (docs.length === 0) {
                        container.innerHTML = '<div style="color:#999; font-style:italic;">Nenhum documento encontrado.</div>';
                        return;
                    }

                    let html = '<ul class="mock-list">';
                    docs.forEach(doc => {
                        html += `<li style="margin-bottom: 8px;">
                            <a href="${doc.url}" target="_blank" style="color: #2ec1f1; text-decoration: none; font-weight: bold;">
                                <span style="margin-right:5px;">📄</span> ${doc.titulo}
                            </a>
                            <div style="font-size: 11px; color: #777; margin-left: 24px;">
                                ${doc.tipo ? `<span class="pill" style="margin-right:5px;">${doc.tipo}</span>` : ''}
                                <span>${doc.data ? new Date(doc.data).toLocaleDateString() : ''}</span>
                                ${doc.campanha ? ` - Campanha: ${doc.campanha}` : ''}
                            </div>
                        </li>`;
                    });
                    html += '</ul>';
                    container.innerHTML = html;
                } else {
                    container.innerHTML = '<div style="color:#ffc2c2;">Erro ao carregar documentos.</div>';
                }
            } catch (e) {
                console.error(e);
                container.innerHTML = '<div style="color:#ffc2c2;">Erro de conexão.</div>';
            }
        }

        // Campanha Filter Logic
        let allCampanhasCache = [];

        async function loadFilterCampanhas() {
            const select = document.getElementById('filterCampanhaSelect');
            if (!select) return;

            select.innerHTML = '<option value="">Carregando...</option>';

            try {
                const response = await fetch('/api/all-campanhas');
                if (response.ok) {
                    const data = await response.json();
                    allCampanhasCache = data.campanhas;

                    select.innerHTML = '<option value="">-- Selecione --</option>';
                    if (allCampanhasCache.length === 0) {
                        select.innerHTML += '<option value="" disabled>Nenhuma campanha encontrada</option>';
                    } else {
                        allCampanhasCache.forEach(c => {
                            const opt = document.createElement('option');
                            opt.value = getCampaignPublicId(c);
                            const ilhaLabel = c.ilha_nome || (Array.isArray(c.ilha_names) ? c.ilha_names.join(', ') : '');
                            opt.textContent = ilhaLabel ? `${c.nome} (${c.data}) - ${ilhaLabel}` : `${c.nome} (${c.data})`;
                            select.appendChild(opt);
                        });
                    }
                } else {
                    select.innerHTML = '<option value="">Erro ao carregar</option>';
                }
            } catch (e) {
                console.error(e);
                select.innerHTML = '<option value="">Erro de conexão</option>';
            }
        }

        function applyCampanhaFilter() {
            const select = document.getElementById('filterCampanhaSelect');
            const campanhaId = String(select.value || '').trim();

            if (!campanhaId) {
                alert("Selecione uma campanha");
                return;
            }

            // Find details in cache or just pass what we have
            const campanha = allCampanhasCache.find(c => getCampaignPublicId(c) === campanhaId);

            if (campanha) {
                // Open Details Modal
                openCampaignDetails(getCampaignPublicId(campanha), campanha.ilha_id, campanha.nome);
                // Close the filter modal
                closeMockModal();
            }
        }

        async function loadFilterIlhas() {
            const select = document.getElementById('filterIlhaSelect');
            if (!select) return;

            select.innerHTML = '<option value="">Carregando...</option>';

            try {
                if (!Array.isArray(ilhas) || ilhas.length === 0) {
                    await fetchIlhas();
                }

                const orderedIlhas = sortIlhasByDefinedOrder(ilhas || []);
                select.innerHTML = '<option value="">-- Selecione --</option>';

                orderedIlhas.forEach(ilha => {
                    const opt = document.createElement('option');
                    opt.value = ilha.id;
                    opt.textContent = ilha.nome || ('Ilha ' + ilha.id);
                    select.appendChild(opt);
                });

                if (selectedIlhaId && Array.from(select.options).some(opt => String(opt.value) === String(selectedIlhaId))) {
                    select.value = String(selectedIlhaId);
                }
            } catch (e) {
                console.error(e);
                select.innerHTML = '<option value="">Erro ao carregar ilhas</option>';
            }
        }

        async function applyIlhaFilter() {
            const select = document.getElementById('filterIlhaSelect');
            if (!select) return;

            const ilhaId = String(select.value || '');
            if (!ilhaId) {
                alert("Selecione uma ilha");
                return;
            }

            if (!Array.isArray(ilhas) || ilhas.length === 0) {
                await fetchIlhas();
            }

            const ilha = (ilhas || []).find(i => String(i.id) === ilhaId);
            if (!ilha) {
                alert("Ilha nao encontrada");
                return;
            }

            selectedIlhaId = ilhaId;
            const ilhaSelect = document.getElementById('ilhaSelect');
            if (ilhaSelect) ilhaSelect.value = ilhaId;
            onIlhaSelected();

            if (!mapStarted) await initMap();

            try {
                if (ilha.geojson) {
                    const geo = JSON.parse(ilha.geojson);
                    const bounds = L.geoJSON(geo).getBounds();
                    if (bounds && bounds.isValid()) {
                        map.fitBounds(bounds.pad(0.15));
                    }
                } else if (Array.isArray(ilha.coords) && ilha.coords.length >= 2) {
                    const lat = Number(ilha.coords[0]);
                    const lon = Number(ilha.coords[1]);
                    if (Number.isFinite(lat) && Number.isFinite(lon)) {
                        map.setView([lat, lon], Math.max(map.getZoom(), 12));
                    }
                }
            } catch (e) {
                console.error(e);
            }

            closeMockModal();
        }

        // Detail Modal
        var detailModal = document.getElementById('detailModal');
        function openDetailModal(props) {
            document.getElementById('detailTitle').textContent = props.nome || "Detalhes";

            // Populate mock data
            document.getElementById('detailUpdates').innerHTML = "Última vistoria: 12/01/2025<br>Status: Monitorado";

            // Mock Images
            document.getElementById('detailImage').src = "https://via.placeholder.com/400x200?text=Ilha+" + encodeURIComponent(props.nome);

            // Mock Info
            const infoHtml = `
            <div><strong>Área:</strong> 42ha</div>
            <div><strong>Profundidade Média:</strong> 8m</div>
            <div><strong>Temperatura:</strong> 24°C</div>
            <div><strong>Coral-sol:</strong> <span style='color:${props.tem_coralsol ? "#ff5555" : "#55ff55"}'>${props.tem_coralsol ? "DETECTADO" : "NÃO DETECTADO"}</span></div>
        `;
            document.getElementById('detailInfo').innerHTML = infoHtml;

            // Mock Campaigns
            let campsHtml = "<li><span class='pill'>Jan 2025</span> Vistoria Completa</li><li><span class='pill'>Out 2024</span> Monitoramento Rápido</li>";
            document.getElementById('detailCampaigns').innerHTML = campsHtml;

            detailModal.style.display = 'flex';
            detailModal.setAttribute('aria-hidden', 'false');
        }

        function closeDetailModal() {
            detailModal.style.display = 'none';
            detailModal.setAttribute('aria-hidden', 'true');
        }

        // Station Modal
        var stationModal = document.getElementById('stationModal');
        async function openStationModal(stationId, stationName) {
            const title = stationName ? stationName : ("Estacao " + stationId);
            document.getElementById('stationTitle').textContent = title;

            const tbody = document.getElementById('stationTableBody');
            const caption = document.getElementById('stationImageCaption');
            tbody.innerHTML = '<tr><td style="padding:8px;">Carregando dados...</td></tr>';
            caption.textContent = 'Carregando imagens...';
            currentMediaList = [];
            currentMediaIndex = 0;
            updateStationImage();

            stationModal.style.display = 'flex';
            stationModal.setAttribute('aria-hidden', 'false');

            try {
                const token = localStorage.getItem('authToken');
                const res = await fetch(`/api/estacoes/${stationId}/ultima-campanha`, {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Falha ao carregar estacao');

                if (!data.found) {
                    tbody.innerHTML = `
                        <tr><td style="padding:8px; color:#666;">Nenhum dado registrado</td></tr>
                        <tr><td style="padding:8px; color:#777;">Esta estacao ainda nao foi amostrada em nenhuma campanha.</td></tr>
                    `;
                    currentMediaList = [];
                    currentMediaIndex = 0;
                    updateStationImage();
                    caption.textContent = 'Sem imagens para esta estacao';
                    return;
                }

                const cor = getStatusColor(data.cor_status);
                const camp = data.campanha || {};
                const dados = data.dados || {};
                const estacao = data.estacao || {};
                const diasTxt = data.dias_desde_campanha == null ? '-' : (data.dias_desde_campanha + ' dia(s)');
                const fmtNum = (v, dec = 2) => (v === null || v === undefined || v === '' || Number.isNaN(Number(v)))
                    ? '-'
                    : Number(v).toFixed(dec);

                tbody.innerHTML = `
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Campanha</strong></td><td style="padding:8px;">${camp.nome || '-'}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Data campanha</strong></td><td style="padding:8px;">${formatDateBR(camp.data)}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Atualizacao</strong></td><td style="padding:8px;"><span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:${cor}; margin-right:6px;"></span>${diasTxt}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Data coleta</strong></td><td style="padding:8px;">${formatDateBR(dados.data)}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Metodo coleta</strong></td><td style="padding:8px;">${dados.metodo_origem || estacao.metodologia || '-'}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Observacoes</strong></td><td style="padding:8px;">${dados.observacoes || '-'}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Prof. inicial (m)</strong></td><td style="padding:8px;">${fmtNum(dados.profundidade_inicial)}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Prof. final (m)</strong></td><td style="padding:8px;">${fmtNum(dados.profundidade_final)}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Temp. inicial (°C)</strong></td><td style="padding:8px;">${fmtNum(dados.temperatura_inicial)}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Temp. final (°C)</strong></td><td style="padding:8px;">${fmtNum(dados.temperatura_final)}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Visib. inicial (m)</strong></td><td style="padding:8px;">${fmtNum(dados.visibilidade_inicial)}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Visib. final (m)</strong></td><td style="padding:8px;">${fmtNum(dados.visibilidade_final)}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Fotos</strong></td><td style="padding:8px;">${dados.num_fotoquadrados ?? 0}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Buscas ativas</strong></td><td style="padding:8px;">${dados.num_buscas_ativas ?? 0}</td></tr>
                    <tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;"><strong>Video transectos</strong></td><td style="padding:8px;">${dados.num_video_transectos ?? 0}</td></tr>
                    <tr><td style="padding:8px;"><strong>Coordenadas</strong></td><td style="padding:8px;">${estacao.latitude ?? '-'}, ${estacao.longitude ?? '-'}</td></tr>
                `;

                currentMediaList = Array.isArray(data.media) ? data.media : [];
                currentMediaIndex = 0;
                updateStationImage();
                return;
            } catch (e) {
                tbody.innerHTML = `<tr><td style="padding:8px; color:#b00020;">Erro ao carregar dados: ${e.message}</td></tr>`;
                currentMediaList = [];
                currentMediaIndex = 0;
                updateStationImage();
                return;
            }
        }

        function closeStationModal() {
            stationModal.style.display = 'none';
            stationModal.setAttribute('aria-hidden', 'true');
        }

        function updateStationImage() {
            const imgEl = document.getElementById('stationImage');
            const caption = document.getElementById('stationImageCaption');
            if (!currentMediaList || currentMediaList.length === 0) {
                imgEl.removeAttribute('src');
                imgEl.style.display = 'none';
                if (caption) caption.textContent = 'Sem imagens para esta estacao';
                return;
            }
            imgEl.style.display = 'block';
            imgEl.src = currentMediaList[currentMediaIndex];
            if (caption) caption.textContent = `Imagem ${currentMediaIndex + 1} de ${currentMediaList.length}`;
        }
        function nextImage() {
            if (!currentMediaList || currentMediaList.length === 0) return;
            currentMediaIndex = (currentMediaIndex + 1) % currentMediaList.length;
            updateStationImage();
        }
        function prevImage() {
            if (!currentMediaList || currentMediaList.length === 0) return;
            currentMediaIndex = (currentMediaIndex - 1 + currentMediaList.length) % currentMediaList.length;
            updateStationImage();
        }

        // Lightbox
        function openLightbox(url, caption) {
            document.getElementById('lightboxContent').innerHTML = `<img src="${url}" style="max-width:100%; max-height:80vh; border-radius:4px;">`;
            document.getElementById('lightboxCaption').textContent = caption || "";
            document.getElementById('lightbox').style.display = "flex";
        }
        function closeLightbox() {
            document.getElementById('lightbox').style.display = "none";
        }

        function bindOverlayClose(modalId, closeFnName) {
            const overlay = document.getElementById(modalId);
            if (!overlay || overlay.dataset.overlayCloseBound === '1') return;
            overlay.dataset.overlayCloseBound = '1';
            overlay.addEventListener('click', function (e) {
                if (e.target !== overlay) return;
                const fn = window[closeFnName];
                if (typeof fn === 'function') fn();
            });
        }

        function setupOverlayCloseHandlers() {
            bindOverlayClose('mockModal', 'closeMockModal');
            bindOverlayClose('detailModal', 'closeDetailModal');
            bindOverlayClose('stationModal', 'closeStationModal');
            bindOverlayClose('gerenciarDadosModal', 'closeGerenciarDadosModal');
            bindOverlayClose('campaignDetailsModal', 'closeCampaignDetailsModal');
            bindOverlayClose('registrationModal', 'closeRegistrationModal');
            bindOverlayClose('userManagementModal', 'closeUserManagementModal');
            bindOverlayClose('coralSolModal', 'closeCoralSolModal');
            bindOverlayClose('methodPickerModal', 'cancelMethodPickerModal');
        }

        setupOverlayCloseHandlers();

        // Data Management Modal
        var dataModal = document.getElementById('gerenciarDadosModal');
        function getDataFlowActionLabel(action) {
            const labels = {
                inicio: 'Aguardando escolha',
                new_campaign: 'Nova campanha',
                questionario: 'Lancamento individual',
                lote: 'Envio em lote',
                estacoes: 'Gerenciar estacoes',
                lista: 'Consulta de campanhas'
            };
            return labels[action] || 'Aguardando escolha';
        }

        function getDataFlowStepLabel(tabName) {
            const labels = {
                inicio: 'Inicio',
                ilha: 'Selecionar ilha',
                campanha: 'Montagem da campanha',
                lista: 'Consulta de campanhas',
                questionario: 'Lancamento individual',
                lote: 'Montagem do lote',
                estacoes: 'Gestao de estacoes'
            };
            return labels[tabName] || 'Inicio';
        }

        function getDataFlowDefaultHint(tabName, action) {
            if (tabName === 'inicio') return 'Selecione uma acao para iniciar o cadastro.';
            if (tabName === 'ilha') {
                if (pendingDataTabAfterIlha) {
                    return 'Selecione a ilha para continuar o fluxo em aberto.';
                }
                return 'Defina a ilha de contexto antes de consultar campanhas, lote ou estacoes.';
            }
            if (tabName === 'campanha') return 'Monte a campanha selecionando ilhas, estacoes e equipe.';
            if (tabName === 'questionario') return 'Escolha a campanha, depois a estacao, e registre um metodo por vez.';
            if (tabName === 'lote') return 'Escolha a campanha e preencha os registros das estacoes em uma unica submissao.';
            if (tabName === 'estacoes') return 'Gerencie os pontos amostrais antes de iniciar novas campanhas.';
            if (tabName === 'lista') return 'Consulte rapidamente as campanhas ja cadastradas para a ilha selecionada.';
            return getDataFlowActionLabel(action);
        }

        function getSelectedCampaignLabelForFlow() {
            if (currentDataTab === 'questionario' || currentDataFlowAction === 'questionario') {
                const sel = document.getElementById('qCampanhaSelect');
                if (sel && sel.value) {
                    const opt = sel.options[sel.selectedIndex];
                    return opt ? opt.textContent : 'Campanha selecionada';
                }
            }
            if (currentDataTab === 'lote' || currentDataFlowAction === 'lote') {
                const sel = document.getElementById('batchCampanhaSelect');
                if (sel && sel.value) {
                    const opt = sel.options[sel.selectedIndex];
                    return opt ? opt.textContent : 'Campanha selecionada';
                }
            }
            if ((currentDataFlowAction === 'new_campaign' || currentDataTab === 'campanha') && getCampaignPublicId(lastCreatedCampaignContext?.campanha)) {
                const campanha = lastCreatedCampaignContext.campanha;
                return getCampaignDisplayLabel(campanha);
            }
            return '-';
        }

        function setFlowButtonState(buttonId, active) {
            const button = document.getElementById(buttonId);
            if (!button) return;
            button.style.background = active ? '#edf8fd' : '#fff';
            button.style.borderColor = active ? '#0f8bb3' : '#c7d8e6';
            button.style.color = active ? '#155574' : '#36566f';
        }

        function clearCampanhaResultMessage() {
            const campanhaResult = document.getElementById('campanhaResult');
            if (!campanhaResult) return;
            campanhaResult.style.display = 'none';
            campanhaResult.textContent = '';
            campanhaResult.innerHTML = '';
        }

        function updateDataFlowHeader() {
            const titleEl = document.getElementById('dataFlowTitle');
            const hintEl = document.getElementById('dataFlowHint');
            const ilhaEl = document.getElementById('dataSummaryIlha');
            const campanhaEl = document.getElementById('dataSummaryCampanha');
            const estacaoEl = document.getElementById('dataSummaryEstacao');
            const modoEl = document.getElementById('dataSummaryModo');
            const etapaEl = document.getElementById('dataSummaryEtapa');
            if (!titleEl || !hintEl || !ilhaEl || !campanhaEl || !estacaoEl || !modoEl || !etapaEl) return;

            const ilha = (ilhas || []).find(item => String(item.id) === String(selectedIlhaId));
            const ilhaLabel = ilha?.nome || '-';
            const campanhaLabel = getSelectedCampaignLabelForFlow();
            const estacaoLabel = (currentDataFlowAction === 'questionario' || currentDataTab === 'questionario') && selectedQEstacaoInfo
                ? (selectedQEstacaoInfo.codigo || ('Estacao ' + (selectedQEstacaoInfo.numero || selectedQEstacaoInfo.id)))
                : '-';
            const modoLabel = getDataFlowActionLabel(currentDataFlowAction);
            const etapaLabel = getDataFlowStepLabel(currentDataTab);
            const titleMap = {
                inicio: 'Escolha o fluxo de trabalho',
                new_campaign: 'Fluxo de criacao de campanha',
                questionario: 'Fluxo de lancamento individual',
                lote: 'Fluxo de envio em lote',
                estacoes: 'Fluxo de gestao de estacoes',
                lista: 'Fluxo de consulta'
            };

            titleEl.textContent = titleMap[currentDataFlowAction] || 'Gerenciamento de dados';
            hintEl.textContent = dataFlowNotice || getDataFlowDefaultHint(currentDataTab, currentDataFlowAction);
            ilhaEl.textContent = 'Ilha: ' + ilhaLabel;
            campanhaEl.textContent = 'Campanha: ' + campanhaLabel;
            estacaoEl.textContent = 'Estacao: ' + estacaoLabel;
            modoEl.textContent = 'Modo: ' + modoLabel;
            etapaEl.textContent = 'Etapa: ' + etapaLabel;

            ['dataActionNewCampaign', 'dataActionQuestionario', 'dataActionLote', 'dataActionEstacoes', 'dataActionLista']
                .forEach(id => setFlowButtonState(id, false));
            if (currentDataFlowAction === 'new_campaign') setFlowButtonState('dataActionNewCampaign', true);
            if (currentDataFlowAction === 'questionario') setFlowButtonState('dataActionQuestionario', true);
            if (currentDataFlowAction === 'lote') setFlowButtonState('dataActionLote', true);
            if (currentDataFlowAction === 'estacoes') setFlowButtonState('dataActionEstacoes', true);
            if (currentDataFlowAction === 'lista') setFlowButtonState('dataActionLista', true);

            ['Inicio', 'Ilha', 'Campanha', 'Questionario', 'Lote', 'Estacoes'].forEach(name => {
                const stepButton = document.getElementById('dataStep' + name);
                if (!stepButton) return;
                const isActive = currentDataTab === name.toLowerCase();
                stepButton.style.background = isActive ? '#edf8fd' : '#fff';
                stepButton.style.borderColor = isActive ? '#0f8bb3' : '#c7d8e6';
                stepButton.style.color = isActive ? '#155574' : '#36566f';
            });
        }

        function startDataFlow(action) {
            currentDataFlowAction = action || 'inicio';
            dataFlowNotice = '';
            if (currentDataFlowAction === 'new_campaign') {
                lastCreatedCampaignContext = null;
                clearCampanhaResultMessage();
            }

            const targetByAction = {
                inicio: 'inicio',
                new_campaign: 'campanha',
                questionario: 'questionario',
                lote: 'lote',
                estacoes: 'estacoes',
                lista: 'lista'
            };
            switchDataTab(targetByAction[currentDataFlowAction] || 'inicio', { action: currentDataFlowAction });
        }

        function openGerenciarDadosModal() {
            if (!currentUser) return;
            if (!canAccessGerenciamentoDados()) return;
            if (!dataModal) return;
            dataModal.style.display = 'flex';
            dataModal.setAttribute('aria-hidden', 'false');
            if (ilhas.length === 0) fetchIlhas().catch(() => { }); // Load if empty
            dataFlowNotice = '';
            pendingDataTabAfterIlha = null;
            currentDataFlowAction = 'inicio';
            switchDataTab('inicio', { action: 'inicio' });
        }
        function closeGerenciarDadosModal() {
            if (!dataModal) return;
            dataModal.style.display = 'none';
            dataModal.setAttribute('aria-hidden', 'true');
        }

        function switchDataTab(tabName, options = {}) {
            if (tabName === 'estacoes' && !canAccessCadastroPorIlhas()) return;
            const requiresIlha = new Set(['lista', 'questionario', 'lote', 'estacoes']);
            if (options.action) {
                currentDataFlowAction = options.action;
            } else if (tabName === 'campanha') {
                currentDataFlowAction = 'new_campaign';
            } else if (['questionario', 'lote', 'estacoes', 'lista', 'inicio'].includes(tabName)) {
                currentDataFlowAction = tabName === 'inicio' ? 'inicio' : tabName;
            }

            if (requiresIlha.has(tabName) && !selectedIlhaId) {
                pendingDataTabAfterIlha = tabName;
                dataFlowNotice = 'Selecione a ilha para continuar.';
                tabName = 'ilha';
            } else if (tabName !== 'ilha') {
                pendingDataTabAfterIlha = null;
                dataFlowNotice = '';
            }

            currentDataTab = tabName;

            // Hide all content
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(el => el.style.display = 'none');

            // Deactivate all tabs
            const tabs = document.querySelectorAll('.data-tab');
            tabs.forEach(el => el.classList.remove('active'));

            // Activate selected
            const contentId = 'content' + tabName.charAt(0).toUpperCase() + tabName.slice(1);
            const tabId = 'tab' + tabName.charAt(0).toUpperCase() + tabName.slice(1);
            const contentEl = document.getElementById(contentId);
            const tabEl = document.getElementById(tabId);
            if (!contentEl) return;
            contentEl.style.display = 'block';
            if (tabEl) tabEl.classList.add('active');

            // Specific loaders
            if (tabName === 'campanha') {
                loadBases();
                loadEmbarcacoes();
                loadEquipe();
                loadIlhasSelectionForCampaign();
            } else if (tabName === 'usuarios') {
                loadUsers();
            } else if (tabName === 'lista') {
                loadCampanhasList();
            } else if (tabName === 'lote') {
                const ilhaSelect = document.getElementById('ilhaSelect');
                if (!selectedIlhaId && ilhaSelect && ilhaSelect.value) {
                    selectedIlhaId = String(ilhaSelect.value);
                }
                syncBatchSelectedIlhaInfo();
                loadCampanhasForBatch();
            } else if (tabName === 'questionario') {
                const ilhaSelect = document.getElementById('ilhaSelect');
                if (!selectedIlhaId && ilhaSelect && ilhaSelect.value) {
                    selectedIlhaId = String(ilhaSelect.value);
                }
                syncQuestionarioSelectedIlhaInfo();
                loadCampanhasForQuestionario();
            }
            updateDataFlowHeader();
        }

        // MAP LOGIC
        async function initMap() {
            if (mapStarted) {
                setTimeout(() => map.invalidateSize(), 100);
                return;
            }

            map = L.map('map', {
                zoomControl: false,
                attributionControl: false
            }).setView([-23.8, -45.4], 10);

            // Satellite basemap. GeoServer WMS is used as an overlay when available.
            baseLayerSatellite = L.tileLayer('http://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', {
                maxZoom: 20,
                subdomains: ['mt0', 'mt1', 'mt2', 'mt3']
            }).addTo(map);

            mapStarted = true;

            // Initial Load
            await fetchIlhas();
            updateMapLabelVisibility();

            // Events
            map.on('click', function (e) {
                if (measureMode) {
                    addMeasurePoint(e.latlng);
                } else if (identifyMode) {
                    // Click handling for identify is usually on markers, but map click can reset
                }
            });
            map.on('zoomend', updateMapLabelVisibility);
        }

        function zoomIn() { map.zoomIn(); }
        function zoomOut() { map.zoomOut(); }
        function resetView() { map.setView([-23.8, -45.4], 10); }

        function toggleGisToolbar() {
            const tb = document.getElementById('gisToolbar');
            tb.classList.toggle('hidden');
        }

        async function fetchIlhas() {
            try {
                const token = localStorage.getItem('authToken');
                const response = await fetch('/api/ilhas', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (!response.ok) throw new Error("Falha ao carregar ilhas");
                const data = await response.json();
                ilhas = sortIlhasByDefinedOrder(data.ilhas || data);
                await enrichIlhasWithGeoServerLocations();

                // Populate Select
                const select = document.getElementById('ilhaSelect');
                select.innerHTML = '<option value="">-- Selecione uma ilha --</option>';
                ilhas.forEach(ilha => {
                    const opt = document.createElement('option');
                    opt.value = ilha.id;
                    opt.textContent = ilha.nome;
                    select.appendChild(opt);
                });
                if (selectedIlhaId && Array.from(select.options).some(opt => String(opt.value) === String(selectedIlhaId))) {
                    select.value = String(selectedIlhaId);
                }

                // Check if user has admin access? (Assuming yes for simplicity of this demo)

                renderIlhasOnMap();
                loadIlhasSelectionForCampaign();
                syncQuestionarioSelectedIlhaInfo();
                syncBatchSelectedIlhaInfo();
                updateDataFlowHeader();
                return true;

            } catch (e) {
                console.error(e);
                throw e;
            }
        }

        function renderIlhasOnMap() {
            // Clear existing
            if (layerIlhas) layerIlhas.clearLayers();
            if (layerEspacos) layerEspacos.clearLayers();
            ilhaMarkers = [];

            layerIlhas = L.layerGroup().addTo(map);
            layerEspacos = L.layerGroup().addTo(map);

            ilhas.forEach(ilha => {
                let layer;
                if (ilha.geojson) {
                    const geo = JSON.parse(ilha.geojson);
                    layer = L.geoJSON(geo, {
                        style: { color: '#ffcc00', weight: 2, fillOpacity: 0.1 }
                    });
                } else if (ilha.coords) {
                    // coords is [lat, lon]
                    layer = L.circleMarker(ilha.coords, {
                        color: '#36b4da',
                        fillColor: '#36b4da',
                        radius: 5,
                        weight: 1.5,
                        fillOpacity: 0.45
                    });
                }

                if (layer) {
                    layer.bindTooltip(ilha.nome, { permanent: true, direction: 'top', className: 'label-ilha' });
                    layer.on('click', () => {
                        // Auto-select island in tab 1
                        document.getElementById('ilhaSelect').value = ilha.id;
                        onIlhaSelected();
                        openGerenciarDadosModal();
                    });
                    layer.addTo(layerIlhas);
                }

                (ilha.espacos_amostrais || []).forEach(espaco => {
                    const lat = parseFloat(espaco.latitude);
                    const lon = parseFloat(espaco.longitude);
                    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

                    const cor = getStatusColor(espaco.cor_status);
                    const marker = L.circleMarker([lat, lon], {
                        color: cor,
                        fillColor: cor,
                        radius: 8,
                        weight: 2,
                        fillOpacity: 0.9
                    });

                    const nomePonto = espaco.codigo || espaco.nome || `Estacao ${espaco.id}`;
                    marker.bindTooltip(nomePonto, { permanent: true, direction: 'top', className: 'label-estacao' });

                    const camp = espaco.latest_campaign;
                    const campTxt = camp ? `${camp.nome || 'Campanha'} (${formatDateBR(camp.data)})` : 'Nenhuma campanha';
                    marker.bindPopup(`
                        <div style="font-size:12px; line-height:1.4;">
                            <div><strong>${nomePonto}</strong></div>
                            <div>Ilha: ${ilha.nome}</div>
                            <div>Ultima campanha: ${campTxt}</div>
                        </div>
                    `);

                    marker.on('click', () => openStationModal(espaco.id, nomePonto));
                    marker.addTo(layerEspacos);
                });
            });
        }

        function toggleIlhas() {
            ilhasVisiveis = !ilhasVisiveis;
            if (ilhasVisiveis) {
                if (layerIlhas) map.addLayer(layerIlhas);
                if (layerEspacos) map.addLayer(layerEspacos);
            } else {
                if (layerIlhas) map.removeLayer(layerIlhas);
                if (layerEspacos) map.removeLayer(layerEspacos);
            }
        }

        // Measurement Tool
        function toggleMeasureMode() {
            measureMode = !measureMode;
            if (measureMode) {
                document.body.style.cursor = 'crosshair';
                measurePoints = [];
                document.getElementById('measureBox').style.display = 'block';
                document.getElementById('measureBox').textContent = "Clique para medir...";
            } else {
                document.body.style.cursor = 'default';
                if (measureLine) map.removeLayer(measureLine);
                document.getElementById('measureBox').style.display = 'none';
            }
        }

        function addMeasurePoint(latlng) {
            measurePoints.push(latlng);
            if (measurePoints.length > 1) {
                let totalDist = 0;
                for (let i = 0; i < measurePoints.length - 1; i++) {
                    totalDist += measurePoints[i].distanceTo(measurePoints[i + 1]);
                }
                document.getElementById('measureBox').textContent = "Distância: " + totalDist.toFixed(1) + " m";

                if (measureLine) map.removeLayer(measureLine);
                measureLine = L.polyline(measurePoints, { color: 'red' }).addTo(map);
            }
        }

        function clearMeasurements() {
            measurePoints = [];
            if (measureLine) map.removeLayer(measureLine);
            document.getElementById('measureBox').textContent = "Medida: 0 m";
        }

        function toggleIdentifyMode() {
            identifyMode = !identifyMode;
            alert(identifyMode ? "Modo Identificar ATIVADO. Clique nas ilhas." : "Modo Identificar DESATIVADO.");
        }

        // --- Data Management Logic ---

        var selectedIlhaId = null;

        function syncQuestionarioSelectedIlhaInfo() {
            const info = document.getElementById('qSelectedIlhaInfo');
            if (!info) return;

            if (!selectedIlhaId) {
                info.textContent = 'Ilha selecionada: -';
                return;
            }

            const ilha = (ilhas || []).find(i => String(i.id) === String(selectedIlhaId));
            const ilhaNome = ilha?.nome || ('ID ' + selectedIlhaId);
            info.textContent = 'Ilha selecionada: ' + ilhaNome;
        }

        function syncBatchSelectedIlhaInfo() {
            const info = document.getElementById('batchSelectedIlhaInfo');
            if (!info) return;

            if (!selectedIlhaId) {
                info.textContent = 'Ilha selecionada: -';
                return;
            }

            const ilha = (ilhas || []).find(i => String(i.id) === String(selectedIlhaId));
            const ilhaNome = ilha?.nome || ('ID ' + selectedIlhaId);
            info.textContent = 'Ilha selecionada: ' + ilhaNome;
        }

        function onIlhaSelected() {
            const ilhaSelect = document.getElementById('ilhaSelect');
            const ilhaInfo = document.getElementById('ilhaInfo');
            if (!ilhaSelect || !ilhaInfo) return;
            const id = ilhaSelect.value;
            if (!id) {
                selectedIlhaId = null;
                selectedQCampanhaId = null;
                selectedQEstacaoId = null;
                selectedQEstacaoInfo = null;
                selectedBatchCampanhaId = null;
                ilhaInfo.textContent = "";
                syncQuestionarioSelectedIlhaInfo();
                syncBatchSelectedIlhaInfo();
                updateDataFlowHeader();
                return;
            }
            selectedIlhaId = id;
            selectedQCampanhaId = null;
            selectedQEstacaoId = null;
            selectedQEstacaoInfo = null;
            selectedBatchCampanhaId = null;
            syncQuestionarioSelectedIlhaInfo();
            syncBatchSelectedIlhaInfo();
            const ilha = ilhas.find(i => i.id == id);
            if (ilha) {
                const lat = Array.isArray(ilha.coords) && ilha.coords.length >= 2 ? Number(ilha.coords[0]) : null;
                const lon = Array.isArray(ilha.coords) && ilha.coords.length >= 2 ? Number(ilha.coords[1]) : null;
                const latTxt = Number.isFinite(lat) ? lat.toFixed(5) : '-';
                const lonTxt = Number.isFinite(lon) ? lon.toFixed(5) : '-';
                ilhaInfo.innerHTML = `
                    <strong>Ilha Selecionada:</strong> ${ilha.nome}<br>
                    Coordenadas: ${latTxt}, ${lonTxt}<br>
                    <div style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap;">
                        <button onclick="downloadMandatoryExports()" style="padding: 4px 8px; font-size: 11px; background: #0f8bb3; color: white; border: none; border-radius: 4px; cursor: pointer;">
                            Download Obrigatorio (WMF + WMS)
                        </button>
                        <button onclick="downloadWmfPontos()" style="padding: 4px 8px; font-size: 11px; background: #0a6f8a; color: white; border: none; border-radius: 4px; cursor: pointer;">
                            Download WMF Pontos
                        </button>
                        <button onclick="downloadWmfCampanhas()" style="padding: 4px 8px; font-size: 11px; background: #0a6f8a; color: white; border: none; border-radius: 4px; cursor: pointer;">
                            Download WMF Campanhas
                        </button>
                        <button onclick="downloadWmfPontosIlhas()" style="padding: 4px 8px; font-size: 11px; background: #0a6f8a; color: white; border: none; border-radius: 4px; cursor: pointer;">
                            Download WMF Pontos das Ilhas
                        </button>
                    </div>
                `;

                // Enable other tabs hints
                const campanhaFormInfo = document.getElementById('campanhaFormInfo');
                if (campanhaFormInfo) campanhaFormInfo.style.display = 'none';
                const campanhasList = document.getElementById('campanhasList');
                if (campanhasList) campanhasList.innerHTML = "Carregando campanhas...";

                // Auto switch to list? Maybe not, stay on tab.
            }

            const tabQuestionario = document.getElementById('tabQuestionario');
            if (tabQuestionario && tabQuestionario.classList.contains('active')) {
                loadCampanhasForQuestionario();
            }
            updateDataFlowHeader();
            if (pendingDataTabAfterIlha) {
                const nextTab = pendingDataTabAfterIlha;
                pendingDataTabAfterIlha = null;
                switchDataTab(nextTab, { action: currentDataFlowAction });
            }
        }

        // --- Create Campaign ---
        function triggerDownload(url) {
            const link = document.createElement('a');
            link.href = url;
            link.target = '_blank';
            link.rel = 'noopener';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        function downloadMandatoryExports() {
            if (!selectedIlhaId) {
                alert("Selecione uma ilha primeiro.");
                return;
            }
            triggerDownload(`/api/export/wmf/${selectedIlhaId}`);
            triggerDownload(`/api/export/wms/${selectedIlhaId}`);
        }

        function downloadWmfPontos() {
            if (!selectedIlhaId) {
                alert("Selecione uma ilha primeiro.");
                return;
            }
            triggerDownload(`/api/export/wmf/${selectedIlhaId}/pontos`);
        }

        function downloadWmfCampanhas() {
            if (!selectedIlhaId) {
                alert("Selecione uma ilha primeiro.");
                return;
            }
            triggerDownload(`/api/export/wmf/${selectedIlhaId}/campanhas`);
        }

        function downloadWmfPontosIlhas() {
            if (!selectedIlhaId) {
                alert("Selecione uma ilha primeiro.");
                return;
            }
            triggerDownload(`/api/export/wmf/global/pontos-ilhas`);
        }

        async function loadBases() {
            const res = await fetch('/api/bases-apoio', { headers: { 'Authorization': 'Bearer ' + authToken } });
            const bases = await res.json();
            const sel = document.getElementById('campanhaBase');
            sel.innerHTML = '<option value="">-- Selecione --</option>';
            bases.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.id;
                opt.textContent = b.nome;
                sel.appendChild(opt);
            });
        }
        async function loadEmbarcacoes() {
            const res = await fetch('/api/embarcacoes', { headers: { 'Authorization': 'Bearer ' + authToken } });
            const embs = await res.json();
            const sel = document.getElementById('campanhaEmbarcacao');
            sel.innerHTML = '<option value="">-- Selecione --</option>';
            embs.forEach(e => {
                const opt = document.createElement('option');
                opt.value = e.id;
                opt.textContent = e.nome;
                sel.appendChild(opt);
            });
        }

        // Auto-Fill Name and Team Logic
        async function loadEquipe() {
            const res = await fetch('/api/equipe', { headers: { 'Authorization': 'Bearer ' + authToken } });
            const membros = await res.json();

            const container = document.getElementById('equipeList');
            if (container) {
                container.innerHTML = '';
                if (membros.length === 0) {
                    container.innerHTML = '<div style="color:#999; font-size:12px;">Nenhum membro cadastrado.</div>';
                    return;
                }

                membros.forEach(m => {
                    const div = document.createElement('div');
                    div.style.marginBottom = '5px';
                    const check = document.createElement('input');
                    check.type = 'checkbox';
                    check.value = m.id;
                    check.name = 'equipe_member';
                    check.style.marginRight = '8px';

                    const label = document.createElement('span');
                    label.textContent = m.nome_completo + (m.funcao ? ` (${m.funcao})` : '');
                    label.style.fontSize = '12px';
                    label.style.color = '#333';

                    div.appendChild(check);
                    div.appendChild(label);
                    container.appendChild(div);
                });
            }
        }



        function getSelectedTeam() {
            const checkboxes = document.querySelectorAll('input[name="equipe_member"]:checked');
            return Array.from(checkboxes).map(cb => parseInt(cb.value));
        }

        let campaignSelectionState = {};
        let activeCampaignIslandId = null;

        function initializeCampaignSelectionState() {
            const nextState = {};
            (ilhas || []).forEach(ilha => {
                const prev = campaignSelectionState[String(ilha.id)] || {};
                const espacosState = {};
                (ilha.espacos_amostrais || []).forEach(ea => {
                    const prevEspaco = prev.espacos?.[String(ea.id)] || {};
                    const prevSelected = prevEspaco.selected === true || (Array.isArray(prevEspaco.pontos) && prevEspaco.pontos.length > 0);
                    espacosState[String(ea.id)] = {
                        selected: prevSelected,
                        point_number: extractPointNumberFromCode(ea.codigo)
                    };
                });
                nextState[String(ilha.id)] = {
                    ativo: !!prev.ativo,
                    methodKey: prev.methodKey || null,
                    espacos: espacosState
                };
            });
            campaignSelectionState = nextState;
            if (!activeCampaignIslandId && ilhas.length > 0) activeCampaignIslandId = String(ilhas[0].id);
        }

        function countCampaignSelection() {
            let ilhasCount = 0;
            let espacosCount = 0;
            let pontosCount = 0;
            Object.values(campaignSelectionState).forEach(ilhaState => {
                let ilhaHasSelection = false;
                Object.values(ilhaState.espacos || {}).forEach(espacoState => {
                    if (espacoState.selected) {
                        ilhaHasSelection = true;
                        espacosCount += 1;
                        pontosCount += 1;
                    }
                });
                if (ilhaState.ativo || ilhaHasSelection) ilhasCount += 1;
            });
            return { ilhasCount, espacosCount, pontosCount };
        }

        function updateIlhasSelectionSummary() {
            const summary = document.getElementById('ilhaSelectionSummary');
            if (!summary) return;
            const c = countCampaignSelection();
            summary.innerHTML = `<span>Ilhas: ${c.ilhasCount}</span><span>Estacoes: ${c.espacosCount}</span><span>Pontos: ${c.pontosCount}</span>`;
        }

        function getEspacoMethodKey(espaco) {
            const metodologia = normalizeTextForSort(espaco?.metodologia || '');
            if (metodologia.includes('ba') || metodologia.includes('busca')) return 'ba';
            if (metodologia.includes('fq') || metodologia.includes('vt') || metodologia.includes('foto') || metodologia.includes('video')) return 'fqvt';
            return null;
        }

        function isEspacoCompatibleWithMethod(espaco, methodKey) {
            if (!methodKey) return true;
            return getEspacoMethodKey(espaco) === methodKey;
        }

        function getMethodLabel(methodKey) {
            if (methodKey === 'ba') return 'Busca Ativa';
            if (methodKey === 'fqvt') return 'Foto Quadrado / Video Transecto';
            return 'Nao definido';
        }

        function setIslandMethodSelection(ilhaId, methodKey) {
            const ilha = ilhas.find(i => String(i.id) === String(ilhaId));
            const ilhaState = campaignSelectionState[String(ilhaId)];
            if (!ilha || !ilhaState) return;

            ilhaState.methodKey = methodKey;
            let hasAny = false;
            (ilha.espacos_amostrais || []).forEach(ea => {
                const shouldSelect = isEspacoCompatibleWithMethod(ea, methodKey);
                ilhaState.espacos[String(ea.id)].selected = shouldSelect;
                if (shouldSelect) hasAny = true;
            });
            ilhaState.ativo = hasAny;
        }

        function clearIslandSelection(ilhaId) {
            const ilhaState = campaignSelectionState[String(ilhaId)];
            if (!ilhaState) return;
            ilhaState.ativo = false;
            ilhaState.methodKey = null;
            Object.values(ilhaState.espacos || {}).forEach(espacoState => { espacoState.selected = false; });
        }

        function togglePointSelection(ilhaId, espacoId) {
            const ilhaState = campaignSelectionState[String(ilhaId)];
            const espacoState = ilhaState?.espacos?.[String(espacoId)];
            if (!espacoState) return;
            const ilha = ilhas.find(i => String(i.id) === String(ilhaId));
            const espaco = (ilha?.espacos_amostrais || []).find(ea => String(ea.id) === String(espacoId));
            if (ilhaState?.methodKey && !isEspacoCompatibleWithMethod(espaco, ilhaState.methodKey)) return;
            espacoState.selected = !espacoState.selected;
            if (!ilhaState) return;
            ilhaState.ativo = Object.values(ilhaState.espacos || {}).some(s => s.selected);
        }

        function openMethodPickerModal() {
            const modal = document.getElementById('methodPickerModal');
            if (!modal) return;
            modal.style.display = 'flex';
            modal.setAttribute('aria-hidden', 'false');
            const firstOption = modal.querySelector('[data-method-value="1"]');
            if (firstOption) firstOption.focus();
        }

        function closeMethodPickerModal() {
            const modal = document.getElementById('methodPickerModal');
            if (!modal) return;
            modal.style.display = 'none';
            modal.setAttribute('aria-hidden', 'true');
        }

        function settleMethodPicker(rawValue) {
            const resolve = methodPickerResolver;
            methodPickerResolver = null;
            closeMethodPickerModal();
            if (typeof resolve !== 'function') return;
            if (rawValue === '1') {
                resolve('ba');
                return;
            }
            if (rawValue === '2' || rawValue === '3') {
                resolve('fqvt');
                return;
            }
            resolve(null);
        }

        function cancelMethodPickerModal() {
            settleMethodPicker(null);
        }

        function bindMethodPickerInteractions() {
            const modal = document.getElementById('methodPickerModal');
            if (!modal || modal.dataset.boundMethodPicker === '1') return;
            modal.dataset.boundMethodPicker = '1';

            modal.addEventListener('click', function (e) {
                const option = e.target.closest('[data-method-value]');
                if (option) {
                    e.preventDefault();
                    settleMethodPicker(option.dataset.methodValue);
                    return;
                }
                const cancelBtn = e.target.closest('#methodPickerCancelBtn');
                if (cancelBtn) {
                    e.preventDefault();
                    cancelMethodPickerModal();
                }
            });

            document.addEventListener('keydown', function (e) {
                if (modal.style.display !== 'flex') return;
                if (e.key === 'Escape') {
                    e.preventDefault();
                    cancelMethodPickerModal();
                    return;
                }
                if (e.key === '1' || e.key === '2' || e.key === '3') {
                    e.preventDefault();
                    settleMethodPicker(e.key);
                }
            });
        }

        async function askMethodForIslandSelection() {
            bindMethodPickerInteractions();
            if (methodPickerResolver) {
                methodPickerResolver(null);
                methodPickerResolver = null;
            }
            return new Promise(resolve => {
                methodPickerResolver = resolve;
                openMethodPickerModal();
            });
        }

        function renderCampaignIslandDetails() {
            const detail = document.getElementById('ilhaDetailPane');
            if (!detail) return;
            const ilha = ilhas.find(i => String(i.id) === String(activeCampaignIslandId));
            if (!ilha) {
                detail.innerHTML = '<div style="font-size:12px; color:#777;">Selecione uma ilha para ver os pontos.</div>';
                return;
            }
            const ilhaState = campaignSelectionState[String(ilha.id)] || { ativo: false, methodKey: null, espacos: {} };
            const espacos = ilha.espacos_amostrais || [];
            const methodKey = ilhaState.methodKey || null;
            const visibleEspacos = methodKey
                ? espacos.filter(ea => isEspacoCompatibleWithMethod(ea, methodKey))
                : espacos;
            const selectedVisibleCount = visibleEspacos.filter(ea => (ilhaState.espacos[String(ea.id)] || {}).selected).length;

            const bannerHtml = methodKey
                ? `<div class="method-selection-banner">
                        <span>Metodo selecionado: ${getMethodLabel(methodKey)}</span>
                        <span style="margin-left:8px;">Pontos a cadastrar: ${selectedVisibleCount}</span>
                   </div>`
                : `<div class="method-selection-banner empty">Selecione um metodo para filtrar os pontos que serao cadastrados nesta ilha.</div>`;

            detail.innerHTML = `
                <div class="ilha-card-header" style="margin-bottom:10px;">
                    <span>${ilha.nome}</span>
                    <span class="ilha-meta">${visibleEspacos.length} estacao(oes)</span>
                </div>
                <div class="ilha-tools">
                    <button type="button" class="ilha-tool-btn" data-action="method-ba">Selecionar BA</button>
                    <button type="button" class="ilha-tool-btn" data-action="method-fqvt">Selecionar FQ/VT</button>
                    <button type="button" class="ilha-tool-btn" data-action="clear-island">Limpar ilha</button>
                </div>
                ${bannerHtml}
                <div>
                    ${visibleEspacos.length === 0 ? `
                        <div style="font-size:12px; color:#7c8d99; padding:8px; border:1px dashed #d5e5f1; border-radius:8px;">
                            Nenhuma estacao encontrada para o metodo selecionado.
                        </div>
                    ` : visibleEspacos.map(ea => {
                        const state = ilhaState.espacos[String(ea.id)] || { selected: false };
                        const pointNumber = Number.isFinite(Number(state.point_number))
                            ? Number(state.point_number)
                            : extractPointNumberFromCode(ea.codigo);
                        const latTxt = Number.isFinite(Number(ea.latitude)) ? Number(ea.latitude).toFixed(5) : '-';
                        const lonTxt = Number.isFinite(Number(ea.longitude)) ? Number(ea.longitude).toFixed(5) : '-';
                        return `
                            <div class="espaco-card">
                                <div class="espaco-title">
                                    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                                        <input type="checkbox" class="picker-checkbox" data-action="toggle-point" data-ilha-id="${ilha.id}" data-espaco-id="${ea.id}" ${state.selected ? 'checked' : ''}>
                                        <span>${ea.codigo || ('EA ' + ea.id)}</span>
                                    </label>
                                    <span style="margin-left:auto; font-size:10px; color:#4f6d80; background:#edf5fb; border:1px solid #d5e5f1; border-radius:999px; padding:2px 8px;">${ea.metodologia || '-'}</span>
                                </div>
                                <div style="margin-left:30px; margin-top:2px; font-size:11px; color:#5b7284;">
                                    Coordenadas: ${latTxt}, ${lonTxt}
                                </div>
                                <div style="margin-left:30px; margin-top:4px;">
                                    <span class="point-pill">Ponto a cadastrar: ${pointNumber}</span>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        }

        function renderCampaignIslandSelector() {
            const container = document.getElementById('ilhasSelectionContainer');
            if (!container) return;
            if (!Array.isArray(ilhas) || ilhas.length === 0) {
                container.innerHTML = '<div style="color:#999; font-size:12px;">Carregando ilhas...</div>';
                return;
            }

            const listHtml = ilhas.map(ilha => {
                const isActive = String(ilha.id) === String(activeCampaignIslandId);
                const ilhaState = campaignSelectionState[String(ilha.id)] || {};
                const ilhaChecked = Object.values(ilhaState.espacos || {}).some(s => s.selected) || ilhaState.ativo;
                const checked = ilhaChecked ? 'checked' : '';
                return `
                    <button type="button" class="ilha-list-item ${isActive ? 'active' : ''}" data-action="focus-island" data-ilha-id="${ilha.id}">
                        <input type="checkbox" class="picker-checkbox" data-action="toggle-island" data-ilha-id="${ilha.id}" ${checked}>
                        <span>${ilha.nome}</span>
                    </button>
                `;
            }).join('');

            container.innerHTML = `
                <div id="ilhaSelectionSummary" class="ilha-selection-summary">Ilhas: 0 Estacoes: 0 Pontos: 0</div>
                <div class="ilha-master-detail">
                    <div id="ilhaListPane" class="ilha-list">${listHtml}</div>
                    <div id="ilhaDetailPane" class="ilha-detail-panel"></div>
                </div>
            `;

            renderCampaignIslandDetails();
            updateIlhasSelectionSummary();
        }

        function bindIlhasSelectionInteractions() {
            const container = document.getElementById('ilhasSelectionContainer');
            if (!container || container.dataset.boundSelectionUX === '1') return;
            container.dataset.boundSelectionUX = '1';

            container.addEventListener('click', async function (e) {
                const target = e.target;
                const actionEl = target.closest('[data-action]');
                if (!actionEl) return;
                const action = actionEl.dataset.action;
                const ilhaId = actionEl.dataset.ilhaId ? String(actionEl.dataset.ilhaId) : activeCampaignIslandId;

                if (action === 'focus-island') {
                    activeCampaignIslandId = ilhaId;
                    renderCampaignIslandSelector();
                    return;
                }

                if (action === 'toggle-island') {
                    e.stopPropagation();
                    if (actionEl.checked) {
                        let methodKey = campaignSelectionState[ilhaId]?.methodKey || null;
                        if (!methodKey) {
                            methodKey = await askMethodForIslandSelection();
                        }
                        if (!methodKey) {
                            actionEl.checked = false;
                            return;
                        }
                        setIslandMethodSelection(ilhaId, methodKey);
                    } else {
                        clearIslandSelection(ilhaId);
                    }
                    activeCampaignIslandId = ilhaId;
                    renderCampaignIslandSelector();
                    return;
                }

                if (action === 'method-ba') setIslandMethodSelection(activeCampaignIslandId, 'ba');
                if (action === 'method-fqvt') setIslandMethodSelection(activeCampaignIslandId, 'fqvt');
                if (action === 'clear-island') clearIslandSelection(activeCampaignIslandId);

                if (action === 'toggle-point') {
                    const espacoId = actionEl.dataset.espacoId;
                    togglePointSelection(activeCampaignIslandId, espacoId);
                }

                renderCampaignIslandSelector();
            });
        }

        function loadIlhasSelectionForCampaign() {
            initializeCampaignSelectionState();
            renderCampaignIslandSelector();
            bindIlhasSelectionInteractions();
        }

        function buildCampanhaIlhasPayload() {
            const ilhasPayload = [];
            Object.entries(campaignSelectionState).forEach(([ilhaId, ilhaState]) => {
                const ilha = (ilhas || []).find(i => String(i.id) === String(ilhaId));
                const selecao = [];
                Object.entries(ilhaState.espacos || {}).forEach(([espacoId, espacoState]) => {
                    if (espacoState.selected) {
                        const espaco = (ilha?.espacos_amostrais || []).find(ea => String(ea.id) === String(espacoId));
                        if (ilhaState.methodKey && !isEspacoCompatibleWithMethod(espaco, ilhaState.methodKey)) return;
                        const pontoNumero = Number.isFinite(Number(espacoState.point_number))
                            ? Number(espacoState.point_number)
                            : 1;
                        selecao.push({ espaco_amostral_id: parseInt(espacoId, 10), pontos: [pontoNumero] });
                    }
                });
                if (selecao.length > 0) {
                    ilhasPayload.push({ ilha_id: parseInt(ilhaId, 10), selecao: selecao });
                }
            });
            return ilhasPayload;
        }

        function inferQuestionarioMethodsFromSelection(ilhasPayload) {
            const methods = new Set();
            (ilhasPayload || []).forEach(ilhaSel => {
                const ilha = (ilhas || []).find(i => String(i.id) === String(ilhaSel.ilha_id));
                (ilhaSel.selecao || []).forEach(sel => {
                    const espaco = (ilha?.espacos_amostrais || []).find(ea => String(ea.id) === String(sel.espaco_amostral_id));
                    const metodologia = normalizeTextForSort(espaco?.metodologia || '');
                    if (metodologia.includes('ba') || metodologia.includes('busca')) methods.add('busca');
                    if (metodologia.includes('vt') || metodologia.includes('video')) methods.add('video');
                    if (metodologia.includes('fq') || metodologia.includes('foto')) methods.add('foto');
                });
            });
            if (methods.size === 0) {
                methods.add('busca');
                methods.add('video');
                methods.add('foto');
            }
            return Array.from(methods);
        }

        async function openQuestionarioForCreatedCampaign(campanha, ilhasPayload, mode = 'questionario') {
            const campanhaPublicId = getCampaignPublicId(campanha);
            if (!campanha || !campanhaPublicId) return;

            const campanhaIdTxt = String(campanhaPublicId);
            const firstIlhaId = ilhasPayload?.[0]?.ilha_id;
            lastCreatedCampaignContext = { campanha, ilhasPayload };
            if (firstIlhaId) {
                selectedIlhaId = String(firstIlhaId);
                const ilhaSelect = document.getElementById('ilhaSelect');
                if (ilhaSelect) ilhaSelect.value = String(firstIlhaId);
                onIlhaSelected();
            }

            const methodHints = inferQuestionarioMethodsFromSelection(ilhasPayload);
            campanhaMethodHints[campanhaIdTxt] = methodHints;

            if (mode === 'lote') {
                currentDataFlowAction = 'lote';
                switchDataTab('lote', { action: 'lote' });
                await loadCampanhasForBatch();
                const batchCampanhaSelect = document.getElementById('batchCampanhaSelect');
                if (batchCampanhaSelect) {
                    if (!Array.from(batchCampanhaSelect.options).some(opt => String(opt.value) === campanhaIdTxt)) {
                        const opt = document.createElement('option');
                        opt.value = campanhaIdTxt;
                        const nome = campanha.nome || ('Campanha ' + campanhaIdTxt);
                        opt.textContent = campanha.data ? `${nome} (${campanha.data})` : nome;
                        batchCampanhaSelect.appendChild(opt);
                    }
                    batchCampanhaSelect.value = campanhaIdTxt;
                }
                onBatchCampanhaSelected();
                updateDataFlowHeader();
                return;
            }

            currentDataFlowAction = 'questionario';
            switchDataTab('questionario', { action: 'questionario' });
            await loadCampanhasForQuestionario();

            const qCampanhaSelect = document.getElementById('qCampanhaSelect');
            if (qCampanhaSelect) {
                if (!Array.from(qCampanhaSelect.options).some(opt => String(opt.value) === campanhaIdTxt)) {
                    const opt = document.createElement('option');
                    opt.value = campanhaIdTxt;
                    const nome = campanha.nome || ('Campanha ' + campanhaIdTxt);
                    opt.textContent = campanha.data ? `${nome} (${campanha.data})` : nome;
                    qCampanhaSelect.appendChild(opt);
                }
                qCampanhaSelect.value = campanhaIdTxt;
            }

            onQuestionarioCampanhaSelected();

            if (methodHints.length === 1) {
                showMethodForm(methodHints[0]);
            }
            updateDataFlowHeader();
        }

        async function openCreatedCampaignDataMode(mode) {
            if (!getCampaignPublicId(lastCreatedCampaignContext?.campanha)) return;
            await openQuestionarioForCreatedCampaign(
                lastCreatedCampaignContext.campanha,
                lastCreatedCampaignContext.ilhasPayload,
                mode
            );
        }

        function renderCreatedCampaignSuccess(campanha, ilhasPayload) {
            const campanhaResult = document.getElementById('campanhaResult');
            if (!campanhaResult) return;

            lastCreatedCampaignContext = { campanha, ilhasPayload };
            campanhaResult.style.display = 'block';
            campanhaResult.style.background = '#d4edda';
            campanhaResult.style.color = '#155724';
            campanhaResult.innerHTML = `
                <div style="font-weight:700;">Cadastro realizado com sucesso.</div>
            `;
            updateDataFlowHeader();
        }

        async function createCampanha(e) {
            e.preventDefault();
            if (isCreatingCampanha) return;
            const ilhasPayload = buildCampanhaIlhasPayload();
            if (ilhasPayload.length === 0) {
                alert("Selecione ao menos uma ilha e uma estacao (ponto amostral).");
                return;
            }

            const submitBtn = document.querySelector('#campanhaForm button[type="submit"]');
            const originalSubmitText = submitBtn ? submitBtn.textContent : '';
            isCreatingCampanha = true;
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Criando campanha...';
                submitBtn.style.opacity = '0.75';
                submitBtn.style.cursor = 'wait';
            }

            const body = {
                ilhas: ilhasPayload,
                nome: document.getElementById('campanhaNome').value,
                data: document.getElementById('campanhaData').value,
                descricao: document.getElementById('campanhaDesc').value,
                base_apoio_id: document.getElementById('campanhaBase').value ? parseInt(document.getElementById('campanhaBase').value) : null,
                embarcacao_id: document.getElementById('campanhaEmbarcacao').value ? parseInt(document.getElementById('campanhaEmbarcacao').value) : null,
                membros_equipe: getSelectedTeam()
            };

            try {
                const res = await fetch('/api/campanhas', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + authToken
                    },
                    body: JSON.stringify(body)
                });
                const data = await res.json();
                if (res.ok) {
                    const campanhaForm = document.getElementById('campanhaForm');
                    if (campanhaForm) campanhaForm.reset();
                    loadIlhasSelectionForCampaign();
                    currentDataFlowAction = 'new_campaign';
                    renderCreatedCampaignSuccess(data.campanha, ilhasPayload);
                    updateDataFlowHeader();
                } else {
                    let msg = "Erro ao criar";
                    if (data.detail) {
                        if (typeof data.detail === 'string') {
                            msg = data.detail;
                        } else if (Array.isArray(data.detail)) {
                            msg = data.detail.map(e => `${e.loc.join('.')} - ${e.msg}`).join('; ');
                        } else {
                            msg = JSON.stringify(data.detail);
                        }
                    }
                    throw new Error(msg);
                }
            } catch (err) {
                const campanhaResult = document.getElementById('campanhaResult');
                if (campanhaResult) {
                    campanhaResult.textContent = "Erro: " + err.message;
                    campanhaResult.style.display = 'block';
                    campanhaResult.style.background = '#f8d7da';
                    campanhaResult.style.color = '#721c24';
                }
                updateDataFlowHeader();
            } finally {
                isCreatingCampanha = false;
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalSubmitText || 'Criar Campanha';
                    submitBtn.style.opacity = '1';
                    submitBtn.style.cursor = 'pointer';
                }
            }
        }

        // --- Uploads ---
        async function uploadGeospatial(e) { /* Placeholder logic - same as before */ e.preventDefault(); alert("Funcionalidade de upload simulada."); }
        async function uploadMedia(e) { /* Placeholder logic - same as before */ e.preventDefault(); alert("Funcionalidade de upload simulada."); }

        // --- List Campaigns ---
        async function loadCampanhasList() {
            if (!selectedIlhaId) return;
            const res = await fetch(`/api/ilhas/${selectedIlhaId}/campanhas`, { headers: { 'Authorization': 'Bearer ' + authToken } });
            const data = await res.json();
            const list = data.campanhas || [];
            const container = document.getElementById('campanhasList');

            if (list.length === 0) {
                container.innerHTML = "Nenhuma campanha encontrada para esta ilha.";
                return;
            }

            // Simple HTML list
            let html = '<ul class="mock-list">';
            list.forEach(c => {
                html += `<li><strong>${c.nome}</strong> (${c.data})</li>`;
            });
            html += '</ul>';
            container.innerHTML = html;
        }

        function escapeHtml(value) {
            return String(value == null ? '' : value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function setBatchResult(kind, message) {
            const result = document.getElementById('batchResult');
            if (!result) return;

            const palette = {
                info: { background: '#edf7ff', color: '#214b66' },
                success: { background: '#d4edda', color: '#155724' },
                error: { background: '#f8d7da', color: '#721c24' }
            };
            const tone = palette[kind] || palette.info;
            result.style.display = 'block';
            result.style.background = tone.background;
            result.style.color = tone.color;
            result.textContent = message;
        }

        function clearBatchResult() {
            const result = document.getElementById('batchResult');
            if (!result) return;
            result.style.display = 'none';
            result.textContent = '';
        }

        function renderBatchPlaceholder(message, isError = false) {
            const container = document.getElementById('batchStationsContainer');
            if (!container) return;
            const border = isError ? '#e5b9b9' : '#c7d8e6';
            const color = isError ? '#8c3f3f' : '#6a8193';
            const background = isError ? '#fff7f7' : '#fbfdff';
            container.innerHTML = `
                <div style="padding:12px; border:1px dashed ${border}; border-radius:8px; color:${color}; background:${background};">
                    ${escapeHtml(message)}
                </div>
            `;
        }

        function resetBatchStationsUI(message, isError = false) {
            const toolbar = document.getElementById('batchStationsToolbar');
            if (toolbar) toolbar.style.display = 'none';
            renderBatchPlaceholder(message, isError);
        }

        async function loadCampanhasForBatch() {
            const sel = document.getElementById('batchCampanhaSelect');
            if (!sel) return;

            clearBatchResult();

            if (!selectedIlhaId) {
                selectedBatchCampanhaId = null;
                sel.innerHTML = '<option value="">Selecione uma ilha na aba 1 primeiro</option>';
                resetBatchStationsUI('Selecione uma ilha para listar as campanhas.');
                updateDataFlowHeader();
                return;
            }

            try {
                const res = await fetch(`/api/ilhas/${selectedIlhaId}/campanhas`, {
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(getErrorMessage(data, 'falha ao carregar campanhas'));
                }

                const list = data.campanhas || [];
                const preferredValue = [selectedBatchCampanhaId, selectedQCampanhaId]
                    .map(value => String(value || '').trim())
                    .find(value => value && list.some(item => getCampaignPublicId(item) === value)) || '';

                sel.innerHTML = '<option value="">-- Selecione --</option>';
                list.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = getCampaignPublicId(c);
                    opt.textContent = c.data ? `${c.nome} (${c.data})` : c.nome;
                    sel.appendChild(opt);
                });

                sel.value = preferredValue;
                onBatchCampanhaSelected();
                updateDataFlowHeader();
            } catch (err) {
                selectedBatchCampanhaId = null;
                sel.innerHTML = '<option value="">-- Erro ao carregar --</option>';
                resetBatchStationsUI('Nao foi possivel carregar as campanhas desta ilha.', true);
                setBatchResult('error', 'Erro ao carregar campanhas: ' + err.message);
                updateDataFlowHeader();
            }
        }

        function buildBatchBuscaFields() {
            return `
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-bottom:10px;">
                    <label style="font-size:12px; color:#36566f;">Numero da busca
                        <input type="number" data-field="numero_busca" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Data
                        <input type="date" data-field="data" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Hora inicio
                        <input type="time" data-field="hora" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Duracao (HH:MM:SS)
                        <input type="text" data-field="duracao" placeholder="00:30:00" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Prof. inicial (m)
                        <input type="number" step="0.01" data-field="profundidade_inicial" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Prof. final (m)
                        <input type="number" step="0.01" data-field="profundidade_final" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Temp. inicial (C)
                        <input type="number" step="0.01" data-field="temperatura_inicial" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Temp. final (C)
                        <input type="number" step="0.01" data-field="temperatura_final" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Visib. vertical (m)
                        <input type="number" step="0.01" data-field="visibilidade_vertical" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Visib. horizontal (m)
                        <input type="number" step="0.01" data-field="visibilidade_horizontal" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Latitude
                        <input type="number" step="0.000001" data-field="latitude" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Longitude
                        <input type="number" step="0.000001" data-field="longitude" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                </div>
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:8px; margin-bottom:10px;">
                    <label style="font-size:12px; color:#36566f;">Planilha Excel
                        <input type="file" data-field="planilha_excel" accept=".xls,.xlsx" style="width:100%; margin-top:4px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Percurso GPX/KML
                        <input type="file" data-field="arquivo_percurso" accept=".gpx,.kml,.kmz" style="width:100%; margin-top:4px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Imagem meteo
                        <input type="file" data-field="imagem_meteo" accept="image/*" style="width:100%; margin-top:4px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Imagens da busca
                        <input type="file" data-field="imagens" accept="image/*" multiple style="width:100%; margin-top:4px;">
                    </label>
                </div>
                <div style="padding:10px; border:1px dashed #d9e5ec; border-radius:8px; background:#fbfdff; margin-bottom:10px;">
                    <label style="display:flex; align-items:center; gap:8px; font-size:12px; color:#36566f; font-weight:700;">
                        <input type="checkbox" data-field="encontrou_coral_sol" onchange="toggleBatchCoralFields(this)">
                        Encontrou coral-sol
                    </label>
                    <div class="batch-coral-fields" style="display:none; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-top:10px;">
                        <label style="font-size:12px; color:#36566f;">Data coral
                            <input type="date" data-field="coral_data" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                        </label>
                        <label style="font-size:12px; color:#36566f;">Hora coral
                            <input type="time" data-field="coral_hora" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                        </label>
                        <label style="font-size:12px; color:#36566f;">Temp. inicial coral
                            <input type="number" step="0.01" data-field="coral_temp_inicial" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                        </label>
                        <label style="font-size:12px; color:#36566f;">Temp. final coral
                            <input type="number" step="0.01" data-field="coral_temp_final" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                        </label>
                        <label style="font-size:12px; color:#36566f;">Prof. inicial coral
                            <input type="number" step="0.01" data-field="coral_prof_inicial" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                        </label>
                        <label style="font-size:12px; color:#36566f;">Prof. final coral
                            <input type="number" step="0.01" data-field="coral_prof_final" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                        </label>
                        <label style="font-size:12px; color:#36566f;">IAR
                            <input type="number" step="0.0001" data-field="coral_iar" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                        </label>
                        <label style="font-size:12px; color:#36566f;">Abundancia
                            <input type="text" data-field="coral_abundancia" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                        </label>
                        <label style="font-size:12px; color:#36566f; grid-column:1/-1;">Imagens coral-sol
                            <input type="file" data-field="coral_imagens" accept="image/*" multiple style="width:100%; margin-top:4px;">
                        </label>
                    </div>
                </div>
                <label style="display:block; font-size:12px; color:#36566f;">Observacoes
                    <textarea data-field="observacoes" rows="3" placeholder="Observacoes adicionais para a Busca Ativa" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px; resize:vertical;"></textarea>
                </label>
            `;
        }

        function buildBatchVideoFields() {
            return `
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-bottom:10px;">
                    <label style="font-size:12px; color:#36566f;">Nome do video
                        <input type="text" data-field="nome_video" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Data
                        <input type="date" data-field="data" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Hora
                        <input type="time" data-field="hora" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Prof. inicial (m)
                        <input type="number" step="0.01" data-field="profundidade_inicial" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Prof. final (m)
                        <input type="number" step="0.01" data-field="profundidade_final" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Temp. inicial (C)
                        <input type="number" step="0.01" data-field="temperatura_inicial" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Temp. final (C)
                        <input type="number" step="0.01" data-field="temperatura_final" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Visib. vertical (m)
                        <input type="number" step="0.01" data-field="visibilidade_vertical" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Visib. horizontal (m)
                        <input type="number" step="0.01" data-field="visibilidade_horizontal" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Riqueza especifica
                        <input type="number" step="0.0001" data-field="riqueza_especifica" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Shannon
                        <input type="number" step="0.0001" data-field="diversidade_shannon" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Jaccard
                        <input type="number" step="0.0001" data-field="equitabilidade_jaccard" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                </div>
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:8px; margin-bottom:10px;">
                    <label style="font-size:12px; color:#36566f;">Arquivo de video
                        <input type="file" data-field="video_url" accept="video/*" style="width:100%; margin-top:4px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Imagem meteo
                        <input type="file" data-field="imagem_meteo" accept="image/*" style="width:100%; margin-top:4px;">
                    </label>
                </div>
                <label style="display:block; font-size:12px; color:#36566f;">Observacoes
                    <textarea data-field="observacoes" rows="3" placeholder="Observacoes adicionais para o Video Transecto" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px; resize:vertical;"></textarea>
                </label>
            `;
        }

        function buildBatchFotoFields() {
            return `
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-bottom:10px;">
                    <label style="font-size:12px; color:#36566f;">Data
                        <input type="date" data-field="data" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Hora
                        <input type="time" data-field="hora" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Profundidade (m)
                        <input type="number" step="0.01" data-field="profundidade" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Temperatura (C)
                        <input type="number" step="0.01" data-field="temperatura" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Visib. vertical (m)
                        <input type="number" step="0.01" data-field="visibilidade_vertical" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Visib. horizontal (m)
                        <input type="number" step="0.01" data-field="visibilidade_horizontal" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Riqueza especifica
                        <input type="number" step="0.0001" data-field="riqueza_especifica" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Shannon
                        <input type="number" step="0.0001" data-field="diversidade_shannon" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Jaccard
                        <input type="number" step="0.0001" data-field="equitabilidade_jaccard" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                    </label>
                </div>
                <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:8px; margin-bottom:10px;">
                    <label style="font-size:12px; color:#36566f;">Imagem mosaico
                        <input type="file" data-field="imagem_mosaico_url" accept="image/*" style="width:100%; margin-top:4px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Imagens complementares
                        <input type="file" data-field="imagens_complementares_upload" accept="image/*" multiple style="width:100%; margin-top:4px;">
                    </label>
                    <label style="font-size:12px; color:#36566f;">Imagem meteo
                        <input type="file" data-field="imagem_meteo" accept="image/*" style="width:100%; margin-top:4px;">
                    </label>
                </div>
                <label style="display:block; font-size:12px; color:#36566f; margin-bottom:10px;">URLs complementares (JSON ou separadas por virgula)
                    <input type="text" data-field="imagens_complementares_manual" placeholder='["http://...", "http://..."]' style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px;">
                </label>
                <label style="display:block; font-size:12px; color:#36566f;">Observacoes
                    <textarea data-field="observacoes" rows="3" placeholder="Observacoes adicionais para o Foto Quadrado" style="width:100%; margin-top:4px; padding:8px; border:1px solid #ccd9e2; border-radius:6px; resize:vertical;"></textarea>
                </label>
            `;
        }

        function buildBatchMethodCard(methodKey, config) {
            let bodyHtml = '';
            if (methodKey === 'busca') bodyHtml = buildBatchBuscaFields();
            if (methodKey === 'video') bodyHtml = buildBatchVideoFields();
            if (methodKey === 'foto') bodyHtml = buildBatchFotoFields();

            return `
                <div class="batch-method-card" data-method="${methodKey}" style="border:1px solid ${config.color}; border-radius:10px; padding:12px; background:#fff;">
                    <label style="display:flex; align-items:center; gap:8px; cursor:pointer;">
                        <input type="checkbox" data-batch-include="true" onchange="toggleBatchMethodSection(this)">
                        <span style="font-size:13px; font-weight:700; color:${config.color};">${config.title}</span>
                        <span style="font-size:11px; color:#6a8193;">${config.hint}</span>
                    </label>
                    <div class="batch-method-body" style="margin-top:10px; opacity:0.55;">
                        ${bodyHtml}
                    </div>
                </div>
            `;
        }

        function renderBatchStations(campanhaId, stations) {
            const container = document.getElementById('batchStationsContainer');
            const toolbar = document.getElementById('batchStationsToolbar');
            if (!container) return;

            const list = sortEspacosByCodigo(Array.isArray(stations) ? stations : []);
            if (list.length === 0) {
                if (toolbar) toolbar.style.display = 'none';
                renderBatchPlaceholder('Nenhuma estacao cadastrada para esta campanha.');
                return;
            }

            const catalogMap = new Map(getQuestionarioMethodCatalog().map(item => [item.key, item]));
            container.innerHTML = list.map(station => {
                const methods = inferQuestionarioMethodsFromStation(station, campanhaId)
                    .map(key => catalogMap.get(key))
                    .filter(Boolean);
                const code = escapeHtml(station.codigo || ('Estacao ' + (station.numero || station.id)));
                const method = escapeHtml(station.metodologia || 'Metodologia nao informada');
                const counters = `BA ${station.num_buscas || 0} | VT ${station.num_videos || 0} | FQ ${station.num_fotos || 0}`;

                return `
                    <div class="batch-station-card" data-estacao-id="${station.id}" style="border:1px solid #d5e5f1; border-radius:12px; padding:14px; background:#f9fcff;">
                        <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start; flex-wrap:wrap; margin-bottom:12px;">
                            <div>
                                <div style="font-size:13px; font-weight:700; color:#0f4f67;">${code}</div>
                                <div style="font-size:11px; color:#5d7485; margin-top:4px;">${method}</div>
                            </div>
                            <div style="font-size:11px; color:#6a8193; padding:6px 8px; border-radius:999px; background:#edf7ff;">${escapeHtml(counters)}</div>
                        </div>
                        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:10px;">
                            ${methods.map(item => buildBatchMethodCard(item.key, item)).join('')}
                        </div>
                    </div>
                `;
            }).join('');

            if (toolbar) toolbar.style.display = 'flex';
            container.querySelectorAll('input[data-batch-include="true"]').forEach(checkbox => toggleBatchMethodSection(checkbox));
            container.querySelectorAll('input[data-field="encontrou_coral_sol"]').forEach(checkbox => toggleBatchCoralFields(checkbox));
        }

        async function loadBatchStations(campanhaId) {
            const container = document.getElementById('batchStationsContainer');
            if (!container) return;

            container.innerHTML = '<div style="padding:12px; border:1px dashed #c7d8e6; border-radius:8px; color:#6a8193; background:#fbfdff;">Carregando estacoes...</div>';
            clearBatchResult();

            try {
                const res = await fetch(`/api/campanhas/${campanhaId}/estacoes`, {
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                const data = await res.json().catch(() => ([]));
                if (!res.ok) {
                    throw new Error(getErrorMessage(data, 'falha ao carregar estacoes'));
                }

                const stations = Array.isArray(data) ? data : [];
                campaignStationsCache[String(campanhaId)] = stations;
                renderBatchStations(campanhaId, stations);
                updateDataFlowHeader();
            } catch (err) {
                resetBatchStationsUI('Nao foi possivel carregar as estacoes da campanha.', true);
                setBatchResult('error', 'Erro ao carregar estacoes: ' + err.message);
                updateDataFlowHeader();
            }
        }

        function onBatchCampanhaSelected() {
            const sel = document.getElementById('batchCampanhaSelect');
            if (!sel) return;

            clearBatchResult();
            selectedBatchCampanhaId = sel.value || null;
            if (!selectedBatchCampanhaId) {
                resetBatchStationsUI('Selecione uma campanha para montar o lote.');
                updateDataFlowHeader();
                return;
            }

            loadBatchStations(selectedBatchCampanhaId);
            updateDataFlowHeader();
        }

        function toggleBatchMethodSection(checkbox) {
            const methodCard = checkbox ? checkbox.closest('.batch-method-card') : null;
            const body = methodCard ? methodCard.querySelector('.batch-method-body') : null;
            if (!methodCard || !body) return;

            const isActive = !!checkbox.checked;
            body.style.opacity = isActive ? '1' : '0.55';
            body.querySelectorAll('input, textarea, select').forEach(el => {
                el.disabled = !isActive;
            });
            methodCard.style.background = isActive ? '#fcfeff' : '#fff';
            methodCard.style.boxShadow = isActive ? 'inset 0 0 0 1px rgba(15,139,179,0.08)' : 'none';

            methodCard.querySelectorAll('input[data-field="encontrou_coral_sol"]').forEach(el => toggleBatchCoralFields(el));
        }

        function toggleBatchCoralFields(checkbox) {
            const methodCard = checkbox ? checkbox.closest('.batch-method-card') : null;
            const coralFields = methodCard ? methodCard.querySelector('.batch-coral-fields') : null;
            const includeCheckbox = methodCard ? methodCard.querySelector('input[data-batch-include="true"]') : null;
            if (!coralFields) return;

            const shouldShow = !!(includeCheckbox && includeCheckbox.checked && checkbox && checkbox.checked);
            coralFields.style.display = shouldShow ? 'grid' : 'none';
            coralFields.querySelectorAll('input, textarea, select').forEach(el => {
                el.disabled = !shouldShow;
            });
        }

        function markAllBatchMethodCheckboxes(checked) {
            const container = document.getElementById('batchStationsContainer');
            if (!container) return;

            container.querySelectorAll('input[data-batch-include="true"]').forEach(checkbox => {
                checkbox.checked = !!checked;
                toggleBatchMethodSection(checkbox);
            });
        }

        function getScopedFieldValue(scope, fieldName) {
            const el = scope ? scope.querySelector(`[data-field="${fieldName}"]`) : null;
            return el ? String(el.value || '').trim() : '';
        }

        function getScopedFieldNumber(scope, fieldName) {
            return parseNullableNumber(getScopedFieldValue(scope, fieldName));
        }

        function getScopedFieldChecked(scope, fieldName) {
            const el = scope ? scope.querySelector(`input[data-field="${fieldName}"]`) : null;
            return !!(el && el.checked);
        }

        function getScopedFieldFiles(scope, fieldName) {
            const el = scope ? scope.querySelector(`input[type="file"][data-field="${fieldName}"]`) : null;
            return el && el.files ? Array.from(el.files) : [];
        }

        function sectionHasMeaningfulContent(scope, fieldNames) {
            return (fieldNames || []).some(fieldName => {
                const el = scope ? scope.querySelector(`[data-field="${fieldName}"]`) : null;
                if (!el) return false;
                if (el.type === 'file') return !!(el.files && el.files.length);
                if (el.type === 'checkbox') return !!el.checked;
                return String(el.value || '').trim() !== '';
            });
        }
        // --- Users Admin ---
        let selectedPasswordUserId = null;

        function getErrorMessage(data, fallback) {
            if (!data) return fallback;
            if (typeof data.detail === 'string') return data.detail;
            if (Array.isArray(data.detail)) return data.detail.map(item => item.msg || JSON.stringify(item)).join('; ');
            return fallback;
        }

        async function loadUsers() {
            const tbody = document.getElementById('usersListBody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="5" style="padding:8px;">Carregando...</td></tr>';

            try {
                const res = await fetch('/api/users', {
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    tbody.innerHTML = `<tr><td colspan="5" style="padding:8px;">Erro ao carregar usuarios: ${getErrorMessage(err, 'falha na consulta')}</td></tr>`;
                    return;
                }

                const users = await res.json();
                if (!Array.isArray(users) || users.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="padding:8px;">Nenhum usuario encontrado.</td></tr>';
                    return;
                }

                const currentUsername = localStorage.getItem('currentUser') || '';
                let html = '';

                users.forEach(u => {
                    const nomePerfil = (u.perfil || 'usuario');
                    const ativo = !!u.ativo;
                    const isSelf = currentUsername === u.username;
                    const safeUsername = String(u.username || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                    const btnToggle = ativo
                        ? `<button onclick="deactivateUser(${u.id})" ${isSelf ? 'disabled' : ''} style="padding:4px 8px; font-size:11px; border:1px solid #b37b7b; background:#fff5f5; color:#9a2c2c; border-radius:4px; cursor:${isSelf ? 'not-allowed' : 'pointer'};">Desativar</button>`
                        : `<button onclick="activateUser(${u.id})" style="padding:4px 8px; font-size:11px; border:1px solid #6ca07b; background:#f1fff5; color:#1f6b34; border-radius:4px; cursor:pointer;">Reativar</button>`;
                    const btnDelete = `<button onclick="logicalDeleteUser(${u.id})" ${isSelf ? 'disabled' : ''} style="padding:4px 8px; font-size:11px; border:1px solid #9a4040; background:#fff; color:#9a4040; border-radius:4px; cursor:${isSelf ? 'not-allowed' : 'pointer'};">Excluir</button>`;

                    html += `<tr style="border-bottom:1px solid #eee;">
                        <td style="padding:5px;">${u.id}</td>
                        <td style="padding:5px;">${u.username}</td>
                        <td style="padding:5px;">${nomePerfil}</td>
                        <td style="padding:5px;">${ativo ? 'Sim' : 'Nao'}</td>
                        <td style="padding:5px;">
                            <div style="display:flex; gap:6px; flex-wrap:wrap;">
                                <button onclick="openUserPasswordChange(${u.id}, '${safeUsername}')" style="padding:4px 8px; font-size:11px; border:1px solid #8aa9bf; background:#f3faff; color:#225474; border-radius:4px; cursor:pointer;">Alterar senha</button>
                                ${btnToggle}
                                ${btnDelete}
                            </div>
                        </td>
                    </tr>`;
                });

                tbody.innerHTML = html;
            } catch (err) {
                tbody.innerHTML = `<tr><td colspan="5" style="padding:8px;">Erro de conexao: ${err.message}</td></tr>`;
            }
        }

        async function createUser(e) {
            e.preventDefault();
            const resultEl = document.getElementById('createUserResult');
            resultEl.textContent = 'Criando...';
            resultEl.style.color = '#555';

            const body = {
                username: document.getElementById('newUsername').value,
                email: document.getElementById('newEmail').value,
                nome_completo: document.getElementById('newNome').value,
                password: document.getElementById('newPassword').value,
                perfil: document.getElementById('newPerfil').value
            };

            try {
                const res = await fetch('/api/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
                    body: JSON.stringify(body)
                });

                if (res.ok) {
                    resultEl.textContent = 'Usuario criado com sucesso.';
                    resultEl.style.color = 'green';
                    document.getElementById('createUserForm').reset();
                    loadUsers();
                    return;
                }

                const err = await res.json().catch(() => ({}));
                resultEl.textContent = 'Erro ao criar usuario: ' + getErrorMessage(err, 'falha na criacao');
                resultEl.style.color = 'red';
            } catch (err) {
                resultEl.textContent = 'Erro de conexao: ' + err.message;
                resultEl.style.color = 'red';
            }
        }

        function openUserPasswordChange(userId, username) {
            selectedPasswordUserId = userId;
            const panel = document.getElementById('passwordResetPanel');
            const target = document.getElementById('passwordResetTarget');
            const result = document.getElementById('passwordResetResult');
            const pass1 = document.getElementById('resetPasswordNew');
            const pass2 = document.getElementById('resetPasswordConfirm');
            if (!panel || !target || !result || !pass1 || !pass2) return;

            target.textContent = 'Usuario: ' + username + ' (ID ' + userId + ')';
            result.textContent = '';
            pass1.value = '';
            pass2.value = '';
            panel.style.display = 'block';
        }

        function cancelUserPasswordChange() {
            selectedPasswordUserId = null;
            const panel = document.getElementById('passwordResetPanel');
            const result = document.getElementById('passwordResetResult');
            if (panel) panel.style.display = 'none';
            if (result) result.textContent = '';
        }

        async function submitUserPasswordChange(e) {
            e.preventDefault();
            const result = document.getElementById('passwordResetResult');
            const pass1 = document.getElementById('resetPasswordNew').value;
            const pass2 = document.getElementById('resetPasswordConfirm').value;

            if (!selectedPasswordUserId) {
                result.textContent = 'Selecione um usuario para alterar a senha.';
                result.style.color = 'red';
                return;
            }

            if (!pass1 || pass1.length < 4) {
                result.textContent = 'A senha deve ter no minimo 4 caracteres.';
                result.style.color = 'red';
                return;
            }

            if (pass1 !== pass2) {
                result.textContent = 'As senhas nao conferem.';
                result.style.color = 'red';
                return;
            }

            result.textContent = 'Salvando...';
            result.style.color = '#555';

            try {
                const res = await fetch(`/api/users/${selectedPasswordUserId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + authToken },
                    body: JSON.stringify({ password: pass1 })
                });

                if (res.ok) {
                    result.textContent = 'Senha alterada com sucesso.';
                    result.style.color = 'green';
                    setTimeout(cancelUserPasswordChange, 800);
                    return;
                }

                const err = await res.json().catch(() => ({}));
                result.textContent = 'Erro ao alterar senha: ' + getErrorMessage(err, 'falha na atualizacao');
                result.style.color = 'red';
            } catch (err) {
                result.textContent = 'Erro de conexao: ' + err.message;
                result.style.color = 'red';
            }
        }

        async function deactivateUser(userId) {
            if (!confirm('Confirmar desativacao deste usuario?')) return;
            const res = await fetch(`/api/users/${userId}/deactivate`, {
                method: 'PATCH',
                headers: { 'Authorization': 'Bearer ' + authToken }
            });
            if (res.ok) {
                loadUsers();
                return;
            }
            const err = await res.json().catch(() => ({}));
            alert('Erro ao desativar: ' + getErrorMessage(err, 'falha'));
        }

        async function activateUser(userId) {
            const res = await fetch(`/api/users/${userId}/activate`, {
                method: 'PATCH',
                headers: { 'Authorization': 'Bearer ' + authToken }
            });
            if (res.ok) {
                loadUsers();
                return;
            }
            const err = await res.json().catch(() => ({}));
            alert('Erro ao reativar: ' + getErrorMessage(err, 'falha'));
        }

        async function logicalDeleteUser(userId) {
            if (!confirm('Confirmar exclusao logica deste usuario?')) return;
            const res = await fetch(`/api/users/${userId}`, {
                method: 'DELETE',
                headers: { 'Authorization': 'Bearer ' + authToken }
            });
            if (res.ok) {
                cancelUserPasswordChange();
                loadUsers();
                return;
            }
            const err = await res.json().catch(() => ({}));
            alert('Erro ao excluir: ' + getErrorMessage(err, 'falha'));
        }

        // --- Questionario Context ---
        async function loadCampanhasForQuestionario() {
            const sel = document.getElementById('qCampanhaSelect');
            if (!sel) return;
            if (!selectedIlhaId) {
                sel.innerHTML = '<option>Selecione uma ilha na aba 1 primeiro</option>';
                updateDataFlowHeader();
                return;
            }
            const res = await fetch(`/api/ilhas/${selectedIlhaId}/campanhas`, { headers: { 'Authorization': 'Bearer ' + authToken } });
            const data = await res.json();
            const list = data.campanhas || [];
            const previousValue = selectedQCampanhaId && list.some(item => getCampaignPublicId(item) === String(selectedQCampanhaId))
                ? String(selectedQCampanhaId)
                : '';

            sel.innerHTML = '<option value="">-- Selecione --</option>';
            list.forEach(c => {
                const opt = document.createElement('option');
                opt.value = getCampaignPublicId(c);
                opt.textContent = c.nome + " (" + c.data + ")";
                sel.appendChild(opt);
            });
            sel.value = previousValue;
            onQuestionarioCampanhaSelected();
            updateDataFlowHeader();
        }

        function getQuestionarioMethodCatalog() {
            return [
                { key: 'busca', title: 'Busca Ativa', hint: 'Registro de dados BA', color: '#2d8f4f' },
                { key: 'video', title: 'Video Transecto', hint: 'Registro de dados VT', color: '#0f8bb3' },
                { key: 'foto', title: 'Foto Quadrado', hint: 'Registro de dados FQ', color: '#9a5d2d' }
            ];
        }

        function inferQuestionarioMethodsFromStation(estacao, campanhaIdHint = selectedQCampanhaId) {
            const methods = new Set();
            const metodologia = normalizeTextForSort(estacao?.metodologia || '');
            if (metodologia.includes('ba') || metodologia.includes('busca')) methods.add('busca');
            if (metodologia.includes('vt') || metodologia.includes('video')) methods.add('video');
            if (metodologia.includes('fq') || metodologia.includes('foto')) methods.add('foto');

            if (methods.size === 0 && campanhaIdHint) {
                (campanhaMethodHints[String(campanhaIdHint)] || []).forEach(item => methods.add(item));
            }

            if (methods.size === 0) {
                methods.add('busca');
                methods.add('video');
                methods.add('foto');
            }

            return Array.from(methods);
        }

        function renderQuestionarioStations(campanhaId, stations) {
            const qGrid = document.getElementById('qStationsGrid');
            if (!qGrid) return;

            if (!Array.isArray(stations) || stations.length === 0) {
                qGrid.innerHTML = '<div style="grid-column:1/-1; padding:10px; border:1px dashed #c7d8e6; border-radius:8px; color:#6a8193; background:#fbfdff;">Nenhuma estacao cadastrada para esta campanha.</div>';
                return;
            }

            qGrid.innerHTML = stations.map(station => {
                const stationId = String(station.id);
                const active = String(selectedQEstacaoId || '') === stationId;
                const border = active ? '#0f8bb3' : '#d5e5f1';
                const background = active ? '#eaf7ff' : '#ffffff';
                const code = station.codigo || ('Estacao ' + (station.numero || station.id));
                const method = station.metodologia || 'Metodologia nao informada';
                const counters = `BA ${station.num_buscas || 0} | VT ${station.num_videos || 0} | FQ ${station.num_fotos || 0}`;
                return `
                    <button type="button" onclick="selectQuestionarioStation('${campanhaId}', '${stationId}')"
                        style="padding:10px; border:1px solid ${border}; background:${background}; color:#1f3b4d; border-radius:8px; cursor:pointer; text-align:left;">
                        <div style="font-size:12px; font-weight:700; color:#0f4f67;">${code}</div>
                        <div style="font-size:10px; color:#5d7485; margin-top:3px;">${method}</div>
                        <div style="font-size:10px; color:#7590a1; margin-top:6px;">${counters}</div>
                    </button>
                `;
            }).join('');
        }

        function updateSelectedStationInfo() {
            const info = document.getElementById('qSelectedStationInfo');
            if (!info) return;

            if (!selectedQEstacaoInfo) {
                info.style.display = 'none';
                info.textContent = '';
                return;
            }

            const code = selectedQEstacaoInfo.codigo || ('Estacao ' + (selectedQEstacaoInfo.numero || selectedQEstacaoInfo.id));
            const method = selectedQEstacaoInfo.metodologia || 'Sem metodologia definida';
            info.style.display = 'block';
            info.textContent = `Estacao selecionada: ${code} | ${method}`;
        }

        function renderQuestionarioMethodActions(methodHints) {
            const qMethodActions = document.getElementById('qMethodActions');
            const qMethodGrid = document.getElementById('qMethodGrid');
            if (!qMethodActions || !qMethodGrid) return;

            if (!selectedQEstacaoInfo) {
                qMethodActions.style.display = 'none';
                qMethodGrid.innerHTML = '';
                return;
            }

            const catalog = getQuestionarioMethodCatalog();
            const normalizedHints = Array.from(new Set((methodHints || []).map(v => String(v || '').toLowerCase())));
            const options = normalizedHints.length > 0
                ? catalog.filter(item => normalizedHints.includes(item.key))
                : catalog;

            if (options.length === 0) {
                qMethodActions.style.display = 'none';
                qMethodGrid.innerHTML = '';
                return;
            }

            qMethodActions.style.display = 'block';
            qMethodGrid.innerHTML = options.map(item => `
                <button type="button" onclick="showMethodForm('${item.key}')"
                    style="padding:10px; border:1px solid ${item.color}; background:#fff; color:#1f3b4d; border-radius:8px; cursor:pointer; text-align:left;">
                    <div style="font-size:12px; font-weight:700; color:${item.color};">${item.title}</div>
                    <div style="font-size:10px; color:#5d7485; margin-top:2px;">${item.hint}</div>
                </button>
            `).join('');
        }

        async function loadQuestionarioStations(campanhaId) {
            const qGrid = document.getElementById('qStationsGrid');
            if (!qGrid) return;

            qGrid.innerHTML = '<div style="grid-column:1/-1; padding:10px; border:1px dashed #c7d8e6; border-radius:8px; color:#6a8193; background:#fbfdff;">Carregando estacoes...</div>';

            try {
                const res = await fetch(`/api/campanhas/${campanhaId}/estacoes`, {
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                const data = await res.json().catch(() => ([]));
                if (!res.ok) {
                    throw new Error(getErrorMessage(data, 'falha ao carregar estacoes'));
                }

                const stations = Array.isArray(data) ? data : [];
                campaignStationsCache[String(campanhaId)] = stations;

                if (selectedQEstacaoId && !stations.some(station => String(station.id) === String(selectedQEstacaoId))) {
                    selectedQEstacaoId = null;
                    selectedQEstacaoInfo = null;
                }

                if (!selectedQEstacaoId && stations.length === 1) {
                    selectedQEstacaoId = String(stations[0].id);
                    selectedQEstacaoInfo = stations[0];
                } else if (selectedQEstacaoId) {
                    selectedQEstacaoInfo = stations.find(station => String(station.id) === String(selectedQEstacaoId)) || null;
                }

                renderQuestionarioStations(campanhaId, stations);
                updateSelectedStationInfo();
                renderQuestionarioMethodActions(inferQuestionarioMethodsFromStation(selectedQEstacaoInfo));
                updateDataFlowHeader();
            } catch (err) {
                qGrid.innerHTML = `<div style="grid-column:1/-1; padding:10px; border:1px dashed #e5b9b9; border-radius:8px; color:#8c3f3f; background:#fff7f7;">Erro ao carregar estacoes: ${err.message}</div>`;
                updateDataFlowHeader();
            }
        }

        function selectQuestionarioStation(campanhaId, estacaoId) {
            const stations = campaignStationsCache[String(campanhaId)] || [];
            selectedQEstacaoId = String(estacaoId);
            selectedQEstacaoInfo = stations.find(station => String(station.id) === String(estacaoId)) || null;
            renderQuestionarioStations(campanhaId, stations);
            updateSelectedStationInfo();
            renderQuestionarioMethodActions(inferQuestionarioMethodsFromStation(selectedQEstacaoInfo));
            hideMethodForm();
            updateDataFlowHeader();
        }

        function onQuestionarioCampanhaSelected() {
            const qCampanhaSelect = document.getElementById('qCampanhaSelect');
            const qStep2 = document.getElementById('qStep2');
            if (!qCampanhaSelect || !qStep2) return;
            const val = qCampanhaSelect.value;
            selectedQCampanhaId = val || null;
            selectedQEstacaoId = null;
            selectedQEstacaoInfo = null;
            if (val) {
                qStep2.style.display = 'block';
                updateSelectedStationInfo();
                renderQuestionarioMethodActions([]);
                loadQuestionarioStations(val);
                loadMethodsSummary(val);
            } else {
                qStep2.style.display = 'none';
                const methodsList = document.getElementById('methodsList');
                if (methodsList) methodsList.textContent = '';
                const qGrid = document.getElementById('qStationsGrid');
                if (qGrid) qGrid.innerHTML = '';
                const qMethodGrid = document.getElementById('qMethodGrid');
                if (qMethodGrid) qMethodGrid.innerHTML = '';
                const qMethodActions = document.getElementById('qMethodActions');
                if (qMethodActions) qMethodActions.style.display = 'none';
                updateSelectedStationInfo();
                hideMethodForm();
            }
            updateDataFlowHeader();
        }

        function showMethodForm(type) {
            if (!selectedQCampanhaId || !selectedQEstacaoId) {
                alert("Selecione uma estacao antes de registrar o metodo.");
                return;
            }
            const formsContainer = document.getElementById('hiddenFormsContainer');
            const formBusca = document.getElementById('formBusca');
            const formVideo = document.getElementById('formVideo');
            const formFoto = document.getElementById('formFoto');
            if (!formBusca || !formVideo || !formFoto) return;
            if (formsContainer) formsContainer.style.display = 'block';

            formBusca.style.display = 'none';
            formVideo.style.display = 'none';
            formFoto.style.display = 'none';

            if (type === 'busca') formBusca.style.display = 'block';
            if (type === 'video') formVideo.style.display = 'block';
            if (type === 'foto') formFoto.style.display = 'block';

            const formMap = {
                busca: formBusca,
                video: formVideo,
                foto: formFoto
            };
            const activeForm = formMap[type];
            if (activeForm && typeof activeForm.scrollIntoView === 'function') {
                activeForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }

        function hideMethodForm(type) {
            const formsContainer = document.getElementById('hiddenFormsContainer');
            const formBusca = document.getElementById('formBusca');
            const formVideo = document.getElementById('formVideo');
            const formFoto = document.getElementById('formFoto');
            if (!formBusca || !formVideo || !formFoto) return;

            if (type === 'busca') formBusca.style.display = 'none';
            if (type === 'video') formVideo.style.display = 'none';
            if (type === 'foto') formFoto.style.display = 'none';
            if (!type) {
                formBusca.style.display = 'none';
                formVideo.style.display = 'none';
                formFoto.style.display = 'none';
            }

            const isAnyVisible = [formBusca, formVideo, formFoto]
                .some(el => el.style.display === 'block');
            if (formsContainer) formsContainer.style.display = isAnyVisible ? 'block' : 'none';
        }

        // Coral Sol Modal Logic
        let coralSolDetails = null;

        function toggleCoralSolModal() {
            const chk = document.getElementById('buscaCoralsol');
            const modal = document.getElementById('coralSolModal');
            const coralImages = document.getElementById('coralImagensFile');
            if (!chk || !modal) return;
            if (chk.checked) {
                modal.style.display = 'flex';
            } else {
                if (coralImages) coralImages.value = '';
                coralSolDetails = null;
            }
        }

        function closeCoralSolModal() {
            const modal = document.getElementById('coralSolModal');
            const chk = document.getElementById('buscaCoralsol');
            const coralImages = document.getElementById('coralImagensFile');
            if (modal) modal.style.display = 'none';
            if (chk) chk.checked = false;
            if (coralImages) coralImages.value = '';
            coralSolDetails = null;
        }

        function confirmCoralSolDetails() {
            const dataEl = document.getElementById('coralData');
            const horaEl = document.getElementById('coralHora');
            const tempIniEl = document.getElementById('coralTempIni');
            const tempFimEl = document.getElementById('coralTempFim');
            const profIniEl = document.getElementById('coralProfIni');
            const profFimEl = document.getElementById('coralProfFim');
            const iarEl = document.getElementById('coralIAR');
            const dataVal = dataEl ? dataEl.value : '';
            const horaVal = horaEl ? horaEl.value : '';
            const tempIni = tempIniEl ? tempIniEl.value : '';
            const tempFim = tempFimEl ? tempFimEl.value : '';
            const profIni = profIniEl ? profIniEl.value : '';
            const profFim = profFimEl ? profFimEl.value : '';
            const iar = iarEl ? iarEl.value : '';

            coralSolDetails = {
                data: dataVal,
                hora: horaVal,
                temp_inicial: tempIni,
                temp_final: tempFim,
                prof_inicial: profIni,
                prof_final: profFim,
                iar: iar
            };
            const modal = document.getElementById('coralSolModal');
            if (modal) modal.style.display = 'none';
        }

        function getInputValue(id) {
            const el = document.getElementById(id);
            return el ? String(el.value || '').trim() : '';
        }

        function parseNullableNumber(value) {
            const txt = String(value == null ? '' : value).trim();
            if (!txt) return null;
            const n = Number(txt);
            return Number.isFinite(n) ? n : null;
        }

        function buildIsoDateTime(dateValue, timeValue) {
            const d = String(dateValue || '').trim();
            if (!d) return null;
            const t = String(timeValue || '').trim() || '00:00:00';
            const tWithSeconds = t.length === 5 ? (t + ':00') : t;
            return `${d}T${tWithSeconds}`;
        }

        function addDurationToIsoDateTime(startIso, durationText) {
            const txt = String(durationText || '').trim();
            if (!startIso || !txt) return null;
            const m = txt.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
            if (!m) return null;
            const hh = Number(m[1]);
            const mm = Number(m[2]);
            const ss = Number(m[3] || '0');
            if (!Number.isFinite(hh) || !Number.isFinite(mm) || !Number.isFinite(ss)) return null;
            const start = new Date(startIso);
            if (Number.isNaN(start.getTime())) return null;
            const end = new Date(start.getTime() + (((hh * 60 + mm) * 60 + ss) * 1000));
            const pad = n => String(n).padStart(2, '0');
            const y = end.getFullYear();
            const mo = pad(end.getMonth() + 1);
            const d = pad(end.getDate());
            const h = pad(end.getHours());
            const mi = pad(end.getMinutes());
            const se = pad(end.getSeconds());
            return `${y}-${mo}-${d}T${h}:${mi}:${se}`;
        }

        function formatObsValue(value, suffix = '') {
            if (value === null || value === undefined || value === '' || Number.isNaN(value)) return '-';
            return String(value) + suffix;
        }

        function parseUrlListInput(value) {
            const txt = String(value || '').trim();
            if (!txt) return [];
            try {
                const parsed = JSON.parse(txt);
                if (Array.isArray(parsed)) {
                    return parsed.map(item => String(item || '').trim()).filter(Boolean);
                }
            } catch (e) {
                return txt.split(',').map(item => item.trim()).filter(Boolean);
            }
            return [];
        }

        async function uploadFilesForCampaign(campanhaId, ilhaId, files) {
            const list = Array.from(files || []).filter(Boolean);
            if (!list.length) return [];
            if (!campanhaId || !ilhaId) {
                throw new Error('Campanha ou ilha nao informada para o upload.');
            }

            const formData = new FormData();
            list.forEach(file => formData.append('files', file));

            const res = await fetch(`/api/campanhas/${campanhaId}/media?ilha_id=${ilhaId}`, {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + authToken },
                body: formData
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(getErrorMessage(data, 'falha no upload'));
            }
            if (!data.success || !Array.isArray(data.files)) {
                throw new Error('Resposta inesperada do upload de arquivos.');
            }

            return data.files.map(file => file?.url || file).filter(Boolean);
        }

        async function uploadSingleFileForCampaign(campanhaId, ilhaId, file) {
            if (!file) return null;
            const uploaded = await uploadFilesForCampaign(campanhaId, ilhaId, [file]);
            return uploaded[0] || null;
        }

        // Upload Helper (Single)
        async function uploadMethodFile(inputId) {
            const input = document.getElementById(inputId);
            if (!input || !input.files || input.files.length === 0) return null;
            return uploadSingleFileForCampaign(selectedQCampanhaId, selectedIlhaId, input.files[0] || null);
        }

        // Upload Multiple Helper
        async function uploadMultipleMethodFiles(inputId) {
            const input = document.getElementById(inputId);
            if (!input || !input.files || input.files.length === 0) return [];
            return uploadFilesForCampaign(selectedQCampanhaId, selectedIlhaId, Array.from(input.files));
        }

        async function collectBatchBuscaPayload(section, campanhaId, ilhaId) {
            const hasContent = sectionHasMeaningfulContent(section, [
                'numero_busca',
                'data',
                'hora',
                'duracao',
                'profundidade_inicial',
                'profundidade_final',
                'temperatura_inicial',
                'temperatura_final',
                'visibilidade_vertical',
                'visibilidade_horizontal',
                'latitude',
                'longitude',
                'planilha_excel',
                'arquivo_percurso',
                'imagem_meteo',
                'imagens',
                'observacoes',
                'encontrou_coral_sol',
                'coral_data',
                'coral_hora',
                'coral_temp_inicial',
                'coral_temp_final',
                'coral_prof_inicial',
                'coral_prof_final',
                'coral_iar',
                'coral_abundancia',
                'coral_imagens'
            ]);
            if (!hasContent) return null;

            const [excelUrl, percursoUrl, meteoUrl, buscaImagesUrls, coralImagesUrls] = await Promise.all([
                uploadSingleFileForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'planilha_excel')[0] || null),
                uploadSingleFileForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'arquivo_percurso')[0] || null),
                uploadSingleFileForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'imagem_meteo')[0] || null),
                uploadFilesForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'imagens')),
                uploadFilesForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'coral_imagens'))
            ]);

            const startIso = buildIsoDateTime(getScopedFieldValue(section, 'data'), getScopedFieldValue(section, 'hora'));
            const endIso = addDurationToIsoDateTime(startIso, getScopedFieldValue(section, 'duracao'));
            const encontrouCoralSol = getScopedFieldChecked(section, 'encontrou_coral_sol');

            const coralDetails = {
                data: getScopedFieldValue(section, 'coral_data'),
                hora: getScopedFieldValue(section, 'coral_hora'),
                temp_inicial: getScopedFieldValue(section, 'coral_temp_inicial'),
                temp_final: getScopedFieldValue(section, 'coral_temp_final'),
                prof_inicial: getScopedFieldValue(section, 'coral_prof_inicial'),
                prof_final: getScopedFieldValue(section, 'coral_prof_final'),
                iar: getScopedFieldValue(section, 'coral_iar'),
                abundancia: getScopedFieldValue(section, 'coral_abundancia'),
                imagens: coralImagesUrls || []
            };
            const hasCoralDetails = Object.values(coralDetails).some(value => {
                if (Array.isArray(value)) return value.length > 0;
                return String(value || '').trim() !== '';
            });
            const observacaoLivre = getScopedFieldValue(section, 'observacoes');
            const observacoesBusca = [
                'Metodo utilizado: Busca Ativa',
                `Quantidade de fotos: ${Array.isArray(buscaImagesUrls) ? buscaImagesUrls.length : 0} (Coral-sol: ${Array.isArray(coralImagesUrls) ? coralImagesUrls.length : 0})`,
                `Coral-sol encontrado: ${encontrouCoralSol ? 'Sim' : 'Nao'}`,
                `Visibilidade inicial/final (m): ${formatObsValue(getScopedFieldNumber(section, 'visibilidade_vertical'))} / ${formatObsValue(getScopedFieldNumber(section, 'visibilidade_horizontal'))}`,
                `Temperatura inicial/final (C): ${formatObsValue(getScopedFieldNumber(section, 'temperatura_inicial'))} / ${formatObsValue(getScopedFieldNumber(section, 'temperatura_final'))}`,
                observacaoLivre ? `Observacoes: ${observacaoLivre}` : ''
            ].filter(Boolean).join(' | ');

            return {
                numero_busca: getScopedFieldNumber(section, 'numero_busca'),
                data_hora_inicio: startIso,
                data_hora_fim: endIso,
                encontrou_coral_sol: encontrouCoralSol,
                profundidade_inicial: getScopedFieldNumber(section, 'profundidade_inicial'),
                profundidade_final: getScopedFieldNumber(section, 'profundidade_final'),
                temperatura_inicial: getScopedFieldNumber(section, 'temperatura_inicial'),
                temperatura_final: getScopedFieldNumber(section, 'temperatura_final'),
                visibilidade_vertical: getScopedFieldNumber(section, 'visibilidade_vertical'),
                visibilidade_horizontal: getScopedFieldNumber(section, 'visibilidade_horizontal'),
                latitude: getScopedFieldNumber(section, 'latitude'),
                longitude: getScopedFieldNumber(section, 'longitude'),
                detalhes_coral: encontrouCoralSol && hasCoralDetails ? coralDetails : null,
                imagens: buscaImagesUrls,
                planilha_excel_url: excelUrl,
                arquivo_percurso_url: percursoUrl,
                dados_meteo: meteoUrl ? { imagem_meteo_url: meteoUrl } : null,
                observacoes: observacoesBusca
            };
        }

        async function collectBatchVideoPayload(section, campanhaId, ilhaId) {
            const hasContent = sectionHasMeaningfulContent(section, [
                'nome_video',
                'data',
                'hora',
                'profundidade_inicial',
                'profundidade_final',
                'temperatura_inicial',
                'temperatura_final',
                'visibilidade_vertical',
                'visibilidade_horizontal',
                'riqueza_especifica',
                'diversidade_shannon',
                'equitabilidade_jaccard',
                'video_url',
                'imagem_meteo',
                'observacoes'
            ]);
            if (!hasContent) return null;

            const videoFile = getScopedFieldFiles(section, 'video_url')[0] || null;
            const [videoUrl, meteoUrl] = await Promise.all([
                uploadSingleFileForCampaign(campanhaId, ilhaId, videoFile),
                uploadSingleFileForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'imagem_meteo')[0] || null)
            ]);

            const observacaoLivre = getScopedFieldValue(section, 'observacoes');
            const observacoesVideo = [
                'Metodo utilizado: Video Transecto',
                `Visibilidade inicial/final (m): ${formatObsValue(getScopedFieldNumber(section, 'visibilidade_vertical'))} / ${formatObsValue(getScopedFieldNumber(section, 'visibilidade_horizontal'))}`,
                `Temperatura inicial/final (C): ${formatObsValue(getScopedFieldNumber(section, 'temperatura_inicial'))} / ${formatObsValue(getScopedFieldNumber(section, 'temperatura_final'))}`,
                observacaoLivre ? `Observacoes: ${observacaoLivre}` : ''
            ].filter(Boolean).join(' | ');

            return {
                nome_video: getScopedFieldValue(section, 'nome_video') || (videoFile ? videoFile.name : null),
                data_hora: buildIsoDateTime(getScopedFieldValue(section, 'data'), getScopedFieldValue(section, 'hora')),
                video_url: videoUrl,
                profundidade_inicial: getScopedFieldNumber(section, 'profundidade_inicial'),
                profundidade_final: getScopedFieldNumber(section, 'profundidade_final'),
                temperatura_inicial: getScopedFieldNumber(section, 'temperatura_inicial'),
                temperatura_final: getScopedFieldNumber(section, 'temperatura_final'),
                visibilidade_vertical: getScopedFieldNumber(section, 'visibilidade_vertical'),
                visibilidade_horizontal: getScopedFieldNumber(section, 'visibilidade_horizontal'),
                riqueza_especifica: getScopedFieldNumber(section, 'riqueza_especifica'),
                diversidade_shannon: getScopedFieldNumber(section, 'diversidade_shannon'),
                equitabilidade_jaccard: getScopedFieldNumber(section, 'equitabilidade_jaccard'),
                dados_meteo: meteoUrl ? { imagem_meteo_url: meteoUrl } : null,
                observacoes: observacoesVideo
            };
        }

        async function collectBatchFotoPayload(section, campanhaId, ilhaId) {
            const hasContent = sectionHasMeaningfulContent(section, [
                'data',
                'hora',
                'profundidade',
                'temperatura',
                'visibilidade_vertical',
                'visibilidade_horizontal',
                'riqueza_especifica',
                'diversidade_shannon',
                'equitabilidade_jaccard',
                'imagem_mosaico_url',
                'imagens_complementares_upload',
                'imagens_complementares_manual',
                'imagem_meteo',
                'observacoes'
            ]);
            if (!hasContent) return null;

            const [mosaicoUrl, complementaresUpload, meteoUrl] = await Promise.all([
                uploadSingleFileForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'imagem_mosaico_url')[0] || null),
                uploadFilesForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'imagens_complementares_upload')),
                uploadSingleFileForCampaign(campanhaId, ilhaId, getScopedFieldFiles(section, 'imagem_meteo')[0] || null)
            ]);

            const complementaresManual = parseUrlListInput(getScopedFieldValue(section, 'imagens_complementares_manual'));
            const complementares = [...(complementaresUpload || []), ...complementaresManual]
                .filter((url, index, arr) => !!url && arr.indexOf(url) === index);
            const observacaoLivre = getScopedFieldValue(section, 'observacoes');
            const totalImagens = (mosaicoUrl ? 1 : 0) + complementares.length;
            const observacoesFoto = [
                'Metodo utilizado: Foto Quadrado',
                `Quantidade de imagens: ${totalImagens}`,
                `Visibilidade vertical/horizontal (m): ${formatObsValue(getScopedFieldNumber(section, 'visibilidade_vertical'))} / ${formatObsValue(getScopedFieldNumber(section, 'visibilidade_horizontal'))}`,
                `Temperatura (C): ${formatObsValue(getScopedFieldNumber(section, 'temperatura'))}`,
                observacaoLivre ? `Observacoes: ${observacaoLivre}` : ''
            ].filter(Boolean).join(' | ');

            return {
                data_hora: buildIsoDateTime(getScopedFieldValue(section, 'data'), getScopedFieldValue(section, 'hora')),
                profundidade: getScopedFieldNumber(section, 'profundidade'),
                temperatura: getScopedFieldNumber(section, 'temperatura'),
                visibilidade_vertical: getScopedFieldNumber(section, 'visibilidade_vertical'),
                visibilidade_horizontal: getScopedFieldNumber(section, 'visibilidade_horizontal'),
                imagem_mosaico_url: mosaicoUrl,
                imagens_complementares: complementares,
                riqueza_especifica: getScopedFieldNumber(section, 'riqueza_especifica'),
                diversidade_shannon: getScopedFieldNumber(section, 'diversidade_shannon'),
                equitabilidade_jaccard: getScopedFieldNumber(section, 'equitabilidade_jaccard'),
                dados_meteo: meteoUrl ? { imagem_meteo_url: meteoUrl } : null,
                observacoes: observacoesFoto
            };
        }

        async function submitBatchUpload() {
            if (isSubmittingBatchUpload) return;
            if (!selectedIlhaId || !selectedBatchCampanhaId) {
                alert('Selecione a ilha e a campanha antes de enviar o lote.');
                return;
            }

            const container = document.getElementById('batchStationsContainer');
            const submitBtn = document.getElementById('batchSubmitBtn');
            if (!container || !submitBtn) return;

            const stationCards = Array.from(container.querySelectorAll('.batch-station-card'));
            if (stationCards.length === 0) {
                alert('Nao ha estacoes disponiveis para envio em lote.');
                return;
            }

            const originalText = submitBtn.textContent;
            isSubmittingBatchUpload = true;
            submitBtn.disabled = true;
            submitBtn.textContent = 'Enviando lote...';
            submitBtn.style.opacity = '0.75';
            clearBatchResult();
            setBatchResult('info', 'Enviando arquivos e montando o lote...');

            try {
                const payload = { estacoes: [] };

                for (const stationCard of stationCards) {
                    const estacaoId = parseInt(stationCard.getAttribute('data-estacao-id') || '', 10);
                    if (!Number.isFinite(estacaoId)) continue;

                    const estacaoPayload = {
                        estacao_amostral_id: estacaoId,
                        buscas_ativas: [],
                        video_transectos: [],
                        fotoquadrados: []
                    };

                    const buscaSection = stationCard.querySelector('.batch-method-card[data-method="busca"]');
                    const buscaEnabled = !!buscaSection?.querySelector('input[data-batch-include="true"]')?.checked;
                    if (buscaEnabled) {
                        const buscaPayload = await collectBatchBuscaPayload(buscaSection, selectedBatchCampanhaId, selectedIlhaId);
                        if (buscaPayload) estacaoPayload.buscas_ativas.push(buscaPayload);
                    }

                    const videoSection = stationCard.querySelector('.batch-method-card[data-method="video"]');
                    const videoEnabled = !!videoSection?.querySelector('input[data-batch-include="true"]')?.checked;
                    if (videoEnabled) {
                        const videoPayload = await collectBatchVideoPayload(videoSection, selectedBatchCampanhaId, selectedIlhaId);
                        if (videoPayload) estacaoPayload.video_transectos.push(videoPayload);
                    }

                    const fotoSection = stationCard.querySelector('.batch-method-card[data-method="foto"]');
                    const fotoEnabled = !!fotoSection?.querySelector('input[data-batch-include="true"]')?.checked;
                    if (fotoEnabled) {
                        const fotoPayload = await collectBatchFotoPayload(fotoSection, selectedBatchCampanhaId, selectedIlhaId);
                        if (fotoPayload) estacaoPayload.fotoquadrados.push(fotoPayload);
                    }

                    if (estacaoPayload.buscas_ativas.length || estacaoPayload.video_transectos.length || estacaoPayload.fotoquadrados.length) {
                        payload.estacoes.push(estacaoPayload);
                    }
                }

                if (payload.estacoes.length === 0) {
                    throw new Error('Nenhum metodo foi marcado com dados preenchidos para envio.');
                }

                const res = await fetch(`/api/campanhas/${selectedBatchCampanhaId}/envio-lote`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + authToken
                    },
                    body: JSON.stringify(payload)
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(getErrorMessage(data, 'falha ao enviar lote'));
                }

                const totals = data.totais || {};
                await loadBatchStations(selectedBatchCampanhaId);
                setBatchResult(
                    'success',
                    `Lote enviado com sucesso. BA: ${totals.buscas_ativas || 0} | VT: ${totals.video_transectos || 0} | FQ: ${totals.fotoquadrados || 0}`
                );

                if (selectedQCampanhaId && String(selectedQCampanhaId) === String(selectedBatchCampanhaId)) {
                    loadMethodsSummary(selectedQCampanhaId);
                    loadQuestionarioStations(selectedQCampanhaId);
                }
            } catch (err) {
                setBatchResult('error', 'Erro no envio em lote: ' + err.message);
            } finally {
                isSubmittingBatchUpload = false;
                submitBtn.disabled = false;
                submitBtn.textContent = originalText || 'Enviar lote';
                submitBtn.style.opacity = '1';
            }
        }

        // Real Submit Handlers
        async function createBuscaAtiva(e) {
            e.preventDefault();
            if (!selectedQCampanhaId || !selectedQEstacaoId) {
                alert("Selecione uma campanha e uma estacao.");
                return;
            }
            try {

            // Uploads
            const excelUrl = await uploadMethodFile('buscaExcelFile');
            const percUrl = await uploadMethodFile('buscaPercursoFile');
            const meteoUrl = await uploadMethodFile('buscaMeteoFile');
            const buscaImagesUrls = await uploadMultipleMethodFiles('buscaImagensFile');
            const coralImagesUrls = await uploadMultipleMethodFiles('coralImagensFile');

            // Date/Time
            const startIso = buildIsoDateTime(getInputValue('buscaData'), getInputValue('buscaHora'));
            const endIso = addDurationToIsoDateTime(startIso, getInputValue('buscaDuracao'));

            // Numeric fields
            const lat = parseNullableNumber(getInputValue('buscaLat'));
            const lon = parseNullableNumber(getInputValue('buscaLon'));
            const profIni = parseNullableNumber(getInputValue('buscaProfIni'));
            const profFim = parseNullableNumber(getInputValue('buscaProfFin'));
            const tempIni = parseNullableNumber(getInputValue('buscaTempIni'));
            const tempFim = parseNullableNumber(getInputValue('buscaTempFin'));
            const visV = parseNullableNumber(getInputValue('buscaVisV'));
            const visH = parseNullableNumber(getInputValue('buscaVisH'));

            const encontrouCoralSol = !!document.getElementById('buscaCoralsol')?.checked;
            const coralPayload = encontrouCoralSol && coralSolDetails ? { ...coralSolDetails } : null;
            if (coralPayload) {
                coralPayload.imagens = coralImagesUrls || [];
            }
            const qtdBuscaFotos = Array.isArray(buscaImagesUrls) ? buscaImagesUrls.length : 0;
            const qtdCoralFotos = Array.isArray(coralImagesUrls) ? coralImagesUrls.length : 0;
            const qtdTotalFotos = qtdBuscaFotos + qtdCoralFotos;
            const observacoesBusca = [
                'Metodo utilizado: Busca Ativa',
                `Quantidade de fotos: ${qtdTotalFotos} (Busca Ativa: ${qtdBuscaFotos}, Coral-sol: ${qtdCoralFotos})`,
                `Coral-sol encontrado: ${encontrouCoralSol ? 'Sim' : 'Nao'}`,
                `Visibilidade inicial/final (m): ${formatObsValue(visV)} / ${formatObsValue(visH)}`,
                `Temperatura inicial/final (°C): ${formatObsValue(tempIni)} / ${formatObsValue(tempFim)}`
            ].join(' | ');

            const body = {
                campanha_id: String(selectedQCampanhaId),
                estacao_amostral_id: parseInt(selectedQEstacaoId),
                numero_busca: parseNullableNumber(getInputValue('buscaNumero')),
                data_hora_inicio: startIso,
                data_hora_fim: endIso,
                encontrou_coral_sol: encontrouCoralSol,
                profundidade_inicial: profIni,
                profundidade_final: profFim,
                temperatura_inicial: tempIni,
                temperatura_final: tempFim,
                visibilidade_vertical: visV,
                visibilidade_horizontal: visH,
                latitude: lat,
                longitude: lon,
                detalhes_coral: coralPayload,
                imagens: buscaImagesUrls,
                planilha_excel_url: excelUrl,
                arquivo_percurso_url: percUrl,
                dados_meteo: { imagem_meteo_url: meteoUrl },
                observacoes: observacoesBusca
            };

            await saveMethod('/api/campanhas/' + selectedQCampanhaId + '/busca-ativa', body, 'busca');
            } catch (err) {
                alert("Erro ao preparar envio: " + err.message);
            }
        }

        async function createVideoTransecto(e) {
            e.preventDefault();
            if (!selectedQCampanhaId || !selectedQEstacaoId) {
                alert("Selecione uma campanha e uma estacao.");
                return;
            }
            try {
            const videoFile = document.getElementById('videoFile')?.files?.[0] || null;
            const videoUrl = await uploadMethodFile('videoFile');
            const meteoUrl = await uploadMethodFile('videoMeteoFile');
            const dataHora = buildIsoDateTime(getInputValue('videoData'), getInputValue('videoHora'));
            const videoProfIni = parseNullableNumber(getInputValue('videoProfIni'));
            const videoProfFim = parseNullableNumber(getInputValue('videoProfFin'));
            const videoTempIni = parseNullableNumber(getInputValue('videoTempIni'));
            const videoTempFim = parseNullableNumber(getInputValue('videoTempFin'));
            const videoVisV = parseNullableNumber(getInputValue('videoVisV'));
            const videoVisH = parseNullableNumber(getInputValue('videoVisH'));
            const observacoesVideo = [
                'Metodo utilizado: Video Transecto',
                'Quantidade de fotos: 0',
                `Visibilidade inicial/final (m): ${formatObsValue(videoVisV)} / ${formatObsValue(videoVisH)}`,
                `Temperatura inicial/final (°C): ${formatObsValue(videoTempIni)} / ${formatObsValue(videoTempFim)}`
            ].join(' | ');

                const body = {
                    campanha_id: String(selectedQCampanhaId),
                    estacao_amostral_id: parseInt(selectedQEstacaoId),
                    nome_video: videoFile ? videoFile.name : "Video Uploaded",
                data_hora: dataHora,
                video_url: videoUrl,
                profundidade_inicial: videoProfIni,
                profundidade_final: videoProfFim,
                temperatura_inicial: videoTempIni,
                temperatura_final: videoTempFim,
                visibilidade_vertical: videoVisV,
                visibilidade_horizontal: videoVisH,
                riqueza_especifica: parseNullableNumber(getInputValue('videoRiqueza')),
                diversidade_shannon: parseNullableNumber(getInputValue('videoShannon')),
                equitabilidade_jaccard: parseNullableNumber(getInputValue('videoJaccard')),
                dados_meteo: { imagem_meteo_url: meteoUrl },
                observacoes: observacoesVideo
            };
            await saveMethod('/api/campanhas/' + selectedQCampanhaId + '/video-transectos', body, 'video');
            } catch (err) {
                alert("Erro ao preparar envio: " + err.message);
            }
        }

        async function createFotoquadrado(e) {
            e.preventDefault();
            if (!selectedQCampanhaId || !selectedQEstacaoId) {
                alert("Selecione uma campanha e uma estacao.");
                return;
            }
            try {
            const mosUrl = await uploadMethodFile('fotoMosaicoFile');
            const meteoUrl = await uploadMethodFile('fotoMeteoFile');
            const complementaresUpload = await uploadMultipleMethodFiles('fotoComplementaresFiles');
            const complementaresManual = parseUrlListInput(getInputValue('fotoComplementares'));
            const complementares = [...complementaresUpload, ...complementaresManual]
                .filter((url, index, arr) => !!url && arr.indexOf(url) === index);
            const totalFotosFoto = (mosUrl ? 1 : 0) + complementares.length;
            const dataHora = buildIsoDateTime(getInputValue('fotoData'), getInputValue('fotoHora'));
            const fotoProf = parseNullableNumber(getInputValue('fotoProf'));
            const fotoTemp = parseNullableNumber(getInputValue('fotoTemp'));
            const fotoVisV = parseNullableNumber(getInputValue('fotoVisV'));
            const fotoVisH = parseNullableNumber(getInputValue('fotoVisH'));
            const observacoesFoto = [
                'Metodo utilizado: Foto Quadrado',
                `Quantidade de imagens: ${totalFotosFoto}`,
                `Visibilidade vertical/horizontal (m): ${formatObsValue(fotoVisV)} / ${formatObsValue(fotoVisH)}`,
                `Temperatura (°C): ${formatObsValue(fotoTemp)}`
            ].join(' | ');

            const body = {
                campanha_id: String(selectedQCampanhaId),
                estacao_amostral_id: parseInt(selectedQEstacaoId),
                data_hora: dataHora,
                profundidade: fotoProf,
                temperatura: fotoTemp,
                visibilidade_vertical: fotoVisV,
                visibilidade_horizontal: fotoVisH,
                imagem_mosaico_url: mosUrl,
                imagens_complementares: complementares,
                riqueza_especifica: parseNullableNumber(getInputValue('fotoRiqueza')),
                diversidade_shannon: parseNullableNumber(getInputValue('fotoShannon')),
                equitabilidade_jaccard: parseNullableNumber(getInputValue('fotoJaccard')),
                dados_meteo: { imagem_meteo_url: meteoUrl },
                observacoes: observacoesFoto
            };

            await saveMethod('/api/campanhas/' + selectedQCampanhaId + '/fotoquadrados', body, 'foto');
            } catch (err) {
                alert("Erro ao preparar envio: " + err.message);
            }
        }

        async function saveMethod(endpoint, body, type) {
            try {
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + authToken
                    },
                    body: JSON.stringify(body)
                });
                if (res.ok) {
                    alert("Salvo com sucesso!");
                    hideMethodForm(type);
                    loadMethodsSummary(selectedQCampanhaId);
                    if (selectedQCampanhaId) {
                        loadQuestionarioStations(selectedQCampanhaId);
                    }
                } else {
                    const err = await res.json().catch(() => ({}));
                    alert("Erro ao salvar: " + getErrorMessage(err, 'falha'));
                }
            } catch (e) { console.error(e); }
        }

        async function loadMethodsSummary(campanhaId) {
            const methodsList = document.getElementById('methodsList');
            if (!methodsList) return;
            methodsList.textContent = "Carregando registros...";
            try {
                const res = await fetch(`/api/campanhas/${campanhaId}/metodos`, {
                    headers: { 'Authorization': 'Bearer ' + authToken }
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    throw new Error(getErrorMessage(data, 'falha ao carregar'));
                }

                const qtdBuscas = Array.isArray(data.buscas) ? data.buscas.length : 0;
                const qtdVideos = Array.isArray(data.videos) ? data.videos.length : 0;
                const qtdFotos = Array.isArray(data.fotos) ? data.fotos.length : 0;

                methodsList.innerHTML = `
                    <div style="margin-top:10px; padding:10px; border:1px solid #d5e5f1; border-radius:8px; background:#f7fbff;">
                        <div style="font-size:12px; color:#36566f; font-weight:700; margin-bottom:4px;">Resumo da campanha selecionada</div>
                        <div style="font-size:12px; color:#4a6a81;">Busca Ativa: ${qtdBuscas}</div>
                        <div style="font-size:12px; color:#4a6a81;">Video Transecto: ${qtdVideos}</div>
                        <div style="font-size:12px; color:#4a6a81;">Foto Quadrado: ${qtdFotos}</div>
                    </div>
                `;
            } catch (err) {
                methodsList.textContent = "Nao foi possivel carregar o resumo dos registros.";
            }
        }
        // Galeria de Imagens Logic
        async function loadGaleriaImagens() {
            const container = document.getElementById('galeriaContainer');
            const loading = document.getElementById('galeriaLoading');
            if (!container || !loading) return;

            // Reset
            container.innerHTML = '';
            container.style.display = 'none';
            loading.style.display = 'block';

            try {
                const response = await fetch('/api/galeria-imagens');
                if (response.ok) {
                    const data = await response.json();
                    renderGaleriaImagens(data.ilhas);
                } else {
                    container.innerHTML = '<div style="color:#ffc2c2;">Erro ao carregar imagens.</div>';
                }
            } catch (e) {
                console.error(e);
                container.innerHTML = '<div style="color:#ffc2c2;">Erro de conexão.</div>';
            } finally {
                loading.style.display = 'none';
                container.style.display = 'block';
            }
        }

        function renderGaleriaImagens(ilhas) {
            const container = document.getElementById('galeriaContainer');

            if (!ilhas || ilhas.length === 0) {
                container.innerHTML = '<div style="color:#c5d8e3;">Nenhuma imagem encontrada.</div>';
                return;
            }

            ilhas.forEach(ilha => {
                const ilhaSection = document.createElement('div');
                ilhaSection.style.marginBottom = '20px';
                ilhaSection.style.borderBottom = '1px solid rgba(255,255,255,0.1)';
                ilhaSection.style.paddingBottom = '15px';

                const title = document.createElement('h4');
                title.textContent = ilha.nome;
                title.style.color = '#2ec1f1';
                title.style.marginBottom = '10px';
                title.style.borderLeft = '3px solid #0f8bb3';
                title.style.paddingLeft = '10px';
                ilhaSection.appendChild(title);

                if (ilha.imagens && ilha.imagens.length > 0) {
                    const grid = document.createElement('div');
                    grid.style.display = 'grid';
                    grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(140px, 1fr))';
                    grid.style.gap = '10px';

                    ilha.imagens.forEach(img => {
                        const card = document.createElement('div');
                        card.style.background = 'rgba(6,20,31,0.6)';
                        card.style.borderRadius = '6px';
                        card.style.overflow = 'hidden';
                        card.style.border = '1px solid rgba(255,255,255,0.1)';

                        const imgWrapper = document.createElement('div');
                        imgWrapper.style.height = '100px';
                        imgWrapper.style.overflow = 'hidden';
                        imgWrapper.style.display = 'flex';
                        imgWrapper.style.alignItems = 'center';
                        imgWrapper.style.justifyContent = 'center';
                        imgWrapper.style.backgroundColor = '#000';

                        const image = document.createElement('img');
                        image.src = img.url;
                        image.style.width = '100%';
                        image.style.height = '100%';
                        image.style.objectFit = 'cover';
                        image.style.cursor = 'pointer';
                        image.onclick = () => window.open(img.url, '_blank');

                        imgWrapper.appendChild(image);
                        card.appendChild(imgWrapper);

                        const info = document.createElement('div');
                        info.style.padding = '8px';

                        const type = document.createElement('div');
                        type.textContent = img.type;
                        type.style.fontSize = '10px';
                        type.style.color = '#2ec1f1';
                        type.style.fontWeight = 'bold';
                        type.style.marginBottom = '4px';

                        const date = document.createElement('div');
                        if (img.date) {
                            const dateObj = new Date(img.date);
                            date.textContent = dateObj.toLocaleDateString();
                        } else {
                            date.textContent = "-";
                        }
                        date.style.fontSize = '10px';
                        date.style.color = '#777';

                        const label = document.createElement('div');
                        label.textContent = img.label;
                        label.title = img.label;
                        label.style.fontSize = '11px';
                        label.style.color = '#c5d8e3';
                        label.style.whiteSpace = 'nowrap';
                        label.style.overflow = 'hidden';
                        label.style.textOverflow = 'ellipsis';
                        label.style.marginTop = '4px';

                        info.appendChild(type);
                        info.appendChild(date);
                        info.appendChild(label);
                        card.appendChild(info);

                        grid.appendChild(card);
                    });

                    ilhaSection.appendChild(grid);
                } else {
                    const noImgs = document.createElement('div');
                    noImgs.textContent = 'Nenhuma imagem registrada.';
                    noImgs.style.fontSize = '12px';
                    noImgs.style.color = '#666';
                    noImgs.style.fontStyle = 'italic';
                    ilhaSection.appendChild(noImgs);
                }

                container.appendChild(ilhaSection);
            });
        }
    
