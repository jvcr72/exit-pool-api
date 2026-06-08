/**
 * Exit Poll - Municipio Maneiro, Estado Nueva Esparta
 * Frontend Application with Client-Side IndexedDB Database
 */

// Global App State
const state = {
    db: null,
    currentTab: 'dashboard',
    votersCount: 0,
    search: {
        query: '',
        center: '',
        table: '',
        status: 'todos',
        page: 1,
        pageSize: 24,
        totalPages: 1
    },
    importTempData: null, // Holds parsed file data before mapping
    importHeaders: [],
    requiredFields: {
        nombre_completo: 'Nombre Completo',
        cedula: 'Cédula de Identidad',
        centro_votacion: 'Centro de Votación',
        mesa: 'Mesa de Votación'
    },
    optionalFields: {
        direccion: 'Dirección de Habitación',
        edad: 'Edad',
        telefono: 'Número Telefónico',
        correo: 'Correo Electrónico',
        estado_civil: 'Estado Civil'
    },
    fieldMapping: {}
};

// Real-world Maneiro voting centers list for mock data and defaults
const MANEIRO_CENTERS = [
    "U.E. Colegio San Nicolás de Bari (Pampatar)",
    "L.B. Archipiélago de Los Testigos (Playa El Ángel)",
    "U.E. Municipal Bernardo Acosta (Pampatar)",
    "U.E.N. Francisco Antonio Rísquez (Pampatar)",
    "Liceo Ángel Noriega Pérez (Pampatar)",
    "E.B. Nstra Sra de las Nieves (Apostadero)",
    "U.E. Colegio El Ángel (Playa El Ángel)",
    "U.E. Colegio Guayamurí (Sector Los Cerritos)"
];

// Document Ready
document.addEventListener('DOMContentLoaded', () => {
    initDatabase()
        .then(() => {
            initApp();
            showNotification('Base de datos IndexedDB inicializada correctamente.', 'success');
        })
        .catch(err => {
            console.error('Error inicializando base de datos:', err);
            showNotification('Error al iniciar la base de datos local.', 'error');
        });
});

// ==========================================
// 1. DATABASE OPERATIONS (IndexedDB)
// ==========================================

function initDatabase() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('ManeiroExitPollDB', 1);

        request.onerror = (e) => reject(e.target.error);
        
        request.onsuccess = (e) => {
            state.db = e.target.result;
            resolve();
        };

        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            
            // Create store for voters
            if (!db.objectStoreNames.contains('votantes')) {
                const store = db.createObjectStore('votantes', { keyPath: 'id', autoIncrement: true });
                
                // Indexes for searching and stats
                store.createIndex('cedula', 'cedula', { unique: true });
                store.createIndex('nombre_completo', 'nombre_completo', { unique: false });
                store.createIndex('centro_votacion', 'centro_votacion', { unique: false });
                store.createIndex('mesa', 'mesa', { unique: false });
                store.createIndex('ha_votado', 'ha_votado', { unique: false });
            }
        };
    });
}

// Clear the database
function clearDatabase() {
    return new Promise((resolve, reject) => {
        if (!state.db) return reject('Base de datos no inicializada');
        
        const transaction = state.db.transaction(['votantes'], 'readwrite');
        const store = transaction.objectStore('votantes');
        const request = store.clear();
        
        request.onsuccess = () => resolve();
        request.onerror = (e) => reject(e.target.error);
    });
}

// Bulk insert voters
function insertVotersBatch(voters) {
    return new Promise((resolve, reject) => {
        if (!state.db) return reject('Base de datos no inicializada');
        
        const transaction = state.db.transaction(['votantes'], 'readwrite');
        const store = transaction.objectStore('votantes');
        
        let successCount = 0;
        let skipCount = 0;

        transaction.oncomplete = () => {
            resolve({ successCount, skipCount });
        };

        transaction.onerror = (e) => {
            reject(e.target.error);
        };

        // Get index to check for duplicates by cedula
        const cedulaIndex = store.index('cedula');

        // Recursive put to handle potential duplicate check in transaction
        function processNext(index) {
            if (index >= voters.length) return;

            const voter = voters[index];
            // Format cedula: strip extra characters, keep letters and numbers
            const cleanCedula = String(voter.cedula).trim();
            
            // Check if cedula exists
            const checkReq = cedulaIndex.get(cleanCedula);
            checkReq.onsuccess = (e) => {
                if (e.target.result) {
                    // Duplicate found, skip
                    skipCount++;
                    processNext(index + 1);
                } else {
                    // Set default vote status
                    voter.ha_votado = voter.ha_votado ? parseInt(voter.ha_votado) : 0;
                    voter.fecha_voto = voter.fecha_voto || null;
                    voter.cedula = cleanCedula;
                    
                    const addReq = store.add(voter);
                    addReq.onsuccess = () => {
                        successCount++;
                        processNext(index + 1);
                    };
                    addReq.onerror = (err) => {
                        console.error('Error insertando votante:', err);
                        skipCount++;
                        processNext(index + 1);
                    };
                }
            };
        }

        processNext(0);
    });
}

// Toggle has_voted status
function toggleVoterStatus(id, newStatus) {
    return new Promise((resolve, reject) => {
        const transaction = state.db.transaction(['votantes'], 'readwrite');
        const store = transaction.objectStore('votantes');
        
        const getReq = store.get(id);
        getReq.onsuccess = (e) => {
            const voter = e.target.result;
            if (!voter) return reject('Votante no encontrado');
            
            voter.ha_votado = newStatus ? 1 : 0;
            voter.fecha_voto = newStatus ? new Date().toISOString() : null;
            
            const putReq = store.put(voter);
            putReq.onsuccess = () => resolve(voter);
            putReq.onerror = (err) => reject(err.target.error);
        };
        getReq.onerror = (err) => reject(err.target.error);
    });
}

// Get filter parameters options (Centros and Mesas list)
function getFilterOptions() {
    return new Promise((resolve, reject) => {
        const transaction = state.db.transaction(['votantes'], 'readonly');
        const store = transaction.objectStore('votantes');
        
        const centersSet = new Set();
        const tablesMap = {}; // center -> Set of tables
        
        const request = store.openCursor();
        request.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
                const voter = cursor.value;
                if (voter.centro_votacion) {
                    centersSet.add(voter.centro_votacion);
                    if (voter.mesa) {
                        if (!tablesMap[voter.centro_votacion]) {
                            tablesMap[voter.centro_votacion] = new Set();
                        }
                        tablesMap[voter.centro_votacion].add(voter.mesa);
                    }
                }
                cursor.continue();
            } else {
                resolve({
                    centers: Array.from(centersSet).sort(),
                    tables: tablesMap
                });
            }
        };
        request.onerror = (e) => reject(e.target.error);
    });
}

// Query / Search voters with filters and pagination
function queryVoters(searchQuery, center, table, status, page, pageSize) {
    return new Promise((resolve, reject) => {
        const transaction = state.db.transaction(['votantes'], 'readonly');
        const store = transaction.objectStore('votantes');
        
        let voters = [];
        const queryClean = searchQuery.toLowerCase().trim();
        
        // Open cursor to iterate and filter
        const request = store.openCursor();
        
        request.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
                const voter = cursor.value;
                let match = true;
                
                // Filter by search query (Name or Cedula)
                if (queryClean) {
                    const nameMatch = voter.nombre_completo.toLowerCase().includes(queryClean);
                    const cedulaMatch = String(voter.cedula).toLowerCase().includes(queryClean);
                    if (!nameMatch && !cedulaMatch) match = false;
                }
                
                // Filter by Center
                if (match && center && voter.centro_votacion !== center) {
                    match = false;
                }
                
                // Filter by Table
                if (match && table && String(voter.mesa) !== String(table)) {
                    match = false;
                }
                
                // Filter by Voted Status
                if (match && status !== 'todos') {
                    const isVoted = voter.ha_votado === 1;
                    if (status === 'si-voto' && !isVoted) match = false;
                    if (status === 'no-voto' && isVoted) match = false;
                }
                
                if (match) {
                    voters.push(voter);
                }
                
                cursor.continue();
            } else {
                // Done iterating, apply sorting (by name or id)
                voters.sort((a, b) => a.nombre_completo.localeCompare(b.nombre_completo));
                
                // Apply pagination
                const totalItems = voters.length;
                const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
                const startIndex = (page - 1) * pageSize;
                const paginatedVoters = voters.slice(startIndex, startIndex + pageSize);
                
                resolve({
                    voters: paginatedVoters,
                    totalItems,
                    totalPages,
                    currentPage: page
                });
            }
        };
        
        request.onerror = (e) => reject(e.target.error);
    });
}

// Compute statistics in real-time
function getStatistics() {
    return new Promise((resolve, reject) => {
        const transaction = state.db.transaction(['votantes'], 'readonly');
        const store = transaction.objectStore('votantes');
        
        let totalVoters = 0;
        let totalVoted = 0;
        const centersStats = {}; // centerName -> { total, voted, tables: { tableId -> { total, voted } } }
        
        const request = store.openCursor();
        
        request.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
                const voter = cursor.value;
                totalVoters++;
                
                const votedVal = voter.ha_votado === 1 ? 1 : 0;
                totalVoted += votedVal;
                
                const center = voter.centro_votacion || 'Sin Centro Definido';
                const table = voter.mesa || 'Sin Mesa';
                
                if (!centersStats[center]) {
                    centersStats[center] = {
                        total: 0,
                        voted: 0,
                        tables: {}
                    };
                }
                
                centersStats[center].total++;
                centersStats[center].voted += votedVal;
                
                if (!centersStats[center].tables[table]) {
                    centersStats[center].tables[table] = {
                        total: 0,
                        voted: 0
                    };
                }
                
                centersStats[center].tables[table].total++;
                centersStats[center].tables[table].voted += votedVal;
                
                cursor.continue();
            } else {
                resolve({
                    totalVoters,
                    totalVoted,
                    centersCount: Object.keys(centersStats).length,
                    centersStats
                });
            }
        };
        
        request.onerror = (e) => reject(e.target.error);
    });
}

// Get all voters for CSV export
function getAllVotersForExport() {
    return new Promise((resolve, reject) => {
        const transaction = state.db.transaction(['votantes'], 'readonly');
        const store = transaction.objectStore('votantes');
        const voters = [];
        
        const request = store.openCursor();
        request.onsuccess = (e) => {
            const cursor = e.target.result;
            if (cursor) {
                voters.push(cursor.value);
                cursor.continue();
            } else {
                resolve(voters);
            }
        };
        request.onerror = (e) => reject(e.target.error);
    });
}


// ==========================================
// 2. APP INITIALIZATION AND NAVIGATION
// ==========================================

function initApp() {
    // Tab switching
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.getAttribute('data-tab');
            switchTab(tabName);
        });
    });
    
    // Drag & Drop event listeners
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    
    dropZone.addEventListener('click', () => fileInput.click());
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleUploadedFile(e.target.files[0]);
        }
    });
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleUploadedFile(e.dataTransfer.files[0]);
        }
    });
    
    // Search input keyup
    const searchInput = document.getElementById('voter-search-input');
    searchInput.addEventListener('input', debounce((e) => {
        state.search.query = e.target.value;
        state.search.page = 1;
        updateVotersSearchList();
    }, 300));
    
    // Filter selectors changes
    document.getElementById('filter-center').addEventListener('change', (e) => {
        state.search.center = e.target.value;
        state.search.page = 1;
        populateTableFilterOptions(e.target.value);
        updateVotersSearchList();
    });
    
    document.getElementById('filter-table').addEventListener('change', (e) => {
        state.search.table = e.target.value;
        state.search.page = 1;
        updateVotersSearchList();
    });
    
    document.getElementById('filter-status').addEventListener('change', (e) => {
        state.search.status = e.target.value;
        state.search.page = 1;
        updateVotersSearchList();
    });
    
    // Pagination buttons
    document.getElementById('btn-prev-page').addEventListener('click', () => {
        if (state.search.page > 1) {
            state.search.page--;
            updateVotersSearchList();
        }
    });
    
    document.getElementById('btn-next-page').addEventListener('click', () => {
        if (state.search.page < state.search.totalPages) {
            state.search.page++;
            updateVotersSearchList();
        }
    });
    
    // Mapping confirmation buttons
    document.getElementById('btn-confirm-import').addEventListener('click', confirmColumnMapping);
    document.getElementById('btn-cancel-mapping').addEventListener('click', () => {
        document.getElementById('mapping-panel').classList.add('hidden');
        document.getElementById('drop-zone').classList.remove('hidden');
        state.importTempData = null;
    });
    
    // Load mock data button
    document.getElementById('btn-load-mock').addEventListener('click', loadMockDataForManeiro);
    
    // Clear Database button
    document.getElementById('btn-clear-db').addEventListener('click', () => {
        if (confirm('¿Estás seguro de borrar toda la base de datos? Se perderán todos los votantes y los registros de votos.')) {
            clearDatabase()
                .then(() => {
                    showNotification('Base de datos borrada con éxito.', 'success');
                    updateGlobalStats();
                    switchTab('dashboard');
                })
                .catch(err => {
                    showNotification('Error al borrar la base de datos: ' + err, 'error');
                });
        }
    });
    
    // Export databases
    document.getElementById('btn-export-database-full').addEventListener('click', exportDatabase);
    document.getElementById('btn-export-dashboard').addEventListener('click', exportDatabase);
    
    // Close notification
    document.getElementById('notification-close').addEventListener('click', () => {
        document.getElementById('notification-banner').classList.add('hidden');
    });
    
    // Initial UI load
    updateGlobalStats();
}

function switchTab(tabName) {
    state.currentTab = tabName;
    
    // Update active class on nav buttons
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
        if (btn.getAttribute('data-tab') === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    // Update tab visibility
    const tabPanes = document.querySelectorAll('.tab-pane');
    tabPanes.forEach(pane => {
        if (pane.id === `tab-${tabName}`) {
            pane.classList.add('active');
        } else {
            pane.classList.remove('active');
        }
    });
    
    // Header text updating
    const sectionTitle = document.getElementById('current-section-title');
    const sectionSubtitle = document.getElementById('current-section-subtitle');
    
    if (tabName === 'dashboard') {
        sectionTitle.textContent = 'Estadísticas de Participación';
        sectionSubtitle.textContent = 'Visualización en tiempo real del exit poll electoral';
        updateGlobalStats();
    } else if (tabName === 'search') {
        sectionTitle.textContent = 'Registro de Votantes';
        sectionSubtitle.textContent = 'Búsqueda de ciudadanos y registro de voto boca de urna';
        updateVotersSearchList();
    } else if (tabName === 'import') {
        sectionTitle.textContent = 'Migración de Datos';
        sectionSubtitle.textContent = 'Carga el padrón de votantes desde archivos Excel o CSV';
    } else if (tabName === 'settings') {
        sectionTitle.textContent = 'Ajustes del Sistema';
        sectionSubtitle.textContent = 'Gestión y exportación de la base de datos de votantes';
    }
}


// ==========================================
// 3. EXCEL / CSV IMPORT AND COLUMN MAPPING
// ==========================================

function handleUploadedFile(file) {
    const dropZone = document.getElementById('drop-zone');
    const progressContainer = document.getElementById('import-progress-container');
    const progressBar = document.getElementById('import-progress-bar');
    const statusText = document.getElementById('import-progress-status');
    
    dropZone.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    progressBar.style.width = '20%';
    statusText.textContent = 'Leyendo archivo...';
    
    const fileReader = new FileReader();
    
    fileReader.onload = (e) => {
        progressBar.style.width = '50%';
        statusText.textContent = 'Procesando formato...';
        
        const data = e.target.result;
        const fileName = file.name.toLowerCase();
        
        try {
            let records = [];
            
            // Check if XLSX library is loaded, otherwise fallback to CSV for offline usage
            if (fileName.endsWith('.csv')) {
                // Read as text
                const text = new TextDecoder('utf-8').decode(data);
                records = parseCSV(text);
            } else if (typeof XLSX !== 'undefined') {
                // Read as Excel binary
                const workbook = XLSX.read(data, { type: 'binary' });
                const firstSheetName = workbook.SheetNames[0];
                const worksheet = workbook.Sheets[firstSheetName];
                records = XLSX.utils.sheet_to_json(worksheet, { header: 1 }); // Read raw cells array
            } else {
                throw new Error('La librería Excel no está cargada. Para trabajar offline, guarda el Excel como un archivo .CSV y vuelve a cargarlo.');
            }
            
            if (!records || records.length < 2) {
                throw new Error('El archivo cargado no contiene suficientes registros.');
            }
            
            // Extract headers (first row) and data rows
            state.importHeaders = records[0].map(h => String(h).trim());
            state.importTempData = records.slice(1).filter(row => row.some(cell => cell !== null && cell !== undefined && cell !== ''));
            
            progressBar.style.width = '80%';
            statusText.textContent = 'Configurando mapeo de columnas...';
            
            setTimeout(() => {
                progressContainer.classList.add('hidden');
                setupColumnMappingView();
            }, 300);
            
        } catch (err) {
            console.error(err);
            progressContainer.classList.add('hidden');
            dropZone.classList.remove('hidden');
            showNotification('Error al leer el archivo: ' + err.message, 'error');
        }
    };
    
    fileReader.onerror = () => {
        progressContainer.classList.add('hidden');
        dropZone.classList.remove('hidden');
        showNotification('Error de lectura del sistema de archivos.', 'error');
    };
    
    if (file.name.toLowerCase().endsWith('.csv')) {
        fileReader.readAsArrayBuffer(file);
    } else {
        fileReader.readAsBinaryString(file);
    }
}

// Custom simple offline CSV parser
function parseCSV(text) {
    const lines = [];
    let row = [""];
    let inQuotes = false;

    for (let i = 0; i < text.length; i++) {
        const char = text[i];
        const nextChar = text[i + 1];

        if (char === '"') {
            if (inQuotes && nextChar === '"') {
                row[row.length - 1] += '"';
                i++; // skip next quote
            } else {
                inQuotes = !inQuotes;
            }
        } else if (char === ',' && !inQuotes) {
            row.push("");
        } else if ((char === '\r' || char === '\n') && !inQuotes) {
            if (char === '\r' && nextChar === '\n') {
                i++; // skip \n
            }
            lines.push(row);
            row = [""];
        } else {
            row[row.length - 1] += char;
        }
    }
    
    if (row.length > 1 || row[0] !== "") {
        lines.push(row);
    }
    
    return lines;
}

// Generate UI for mapping excel columns to schema fields
function setupColumnMappingView() {
    const mappingPanel = document.getElementById('mapping-panel');
    const mappingGrid = document.getElementById('mapping-grid');
    mappingGrid.innerHTML = '';
    mappingPanel.classList.remove('hidden');
    
    state.fieldMapping = {};
    
    // Helper to auto-map based on common strings
    const matchHeader = (fieldName, label) => {
        const keys = {
            nombre_completo: ['nombre', 'completo', 'voto', 'vocal', 'elector', 'ciudadano', 'name', 'fullname'],
            cedula: ['cedula', 'identidad', 'ci', 'id', 'documento', 'v-'],
            centro_votacion: ['centro', 'votacion', 'colegio', 'escuela', 'liceo', 'lugar', 'center'],
            mesa: ['mesa', 'urn', 'box', 'table'],
            direccion: ['direccion', 'habita', 'casa', 'calle', 'vivienda', 'address'],
            edad: ['edad', 'years', 'age'],
            telefono: ['telefono', 'celular', 'phone', 'movil'],
            correo: ['correo', 'email', 'mail'],
            estado_civil: ['civil', 'estado civil', 'marital']
        };
        
        const matchedField = keys[fieldName];
        return state.importHeaders.findIndex(header => {
            const h = header.toLowerCase();
            return matchedField.some(key => h.includes(key));
        });
    };
    
    const allFields = { ...state.requiredFields, ...state.optionalFields };
    
    Object.keys(allFields).forEach(fieldKey => {
        const isRequired = state.requiredFields.hasOwnProperty(fieldKey);
        const fieldLabel = allFields[fieldKey];
        
        const row = document.createElement('div');
        row.className = 'mapping-row';
        
        const labelDiv = document.createElement('div');
        labelDiv.className = 'mapping-label';
        labelDiv.innerHTML = fieldLabel + (isRequired ? '<span>*</span>' : ' (Opcional)');
        
        const select = document.createElement('select');
        select.className = 'form-select';
        select.id = `map-${fieldKey}`;
        
        // Add default empty option
        const emptyOpt = document.createElement('option');
        emptyOpt.value = '';
        emptyOpt.textContent = '-- Seleccionar columna --';
        select.appendChild(emptyOpt);
        
        // Add file headers
        state.importHeaders.forEach((header, index) => {
            const opt = document.createElement('option');
            opt.value = index;
            opt.textContent = header;
            select.appendChild(opt);
        });
        
        // Auto select if match found
        const matchedIndex = matchHeader(fieldKey, fieldLabel);
        if (matchedIndex !== -1) {
            select.value = matchedIndex;
            state.fieldMapping[fieldKey] = matchedIndex;
        }
        
        select.addEventListener('change', (e) => {
            if (e.target.value === '') {
                delete state.fieldMapping[fieldKey];
            } else {
                state.fieldMapping[fieldKey] = parseInt(e.target.value);
            }
        });
        
        row.appendChild(labelDiv);
        row.appendChild(select);
        mappingGrid.appendChild(row);
    });
}

function confirmColumnMapping() {
    // Validate required fields
    const missingFields = [];
    Object.keys(state.requiredFields).forEach(reqKey => {
        if (state.fieldMapping[reqKey] === undefined || state.fieldMapping[reqKey] === '') {
            missingFields.push(state.requiredFields[reqKey]);
        }
    });
    
    if (missingFields.length > 0) {
        alert(`Debes mapear los siguientes campos requeridos: ${missingFields.join(', ')}`);
        return;
    }
    
    const mappingPanel = document.getElementById('mapping-panel');
    const progressContainer = document.getElementById('import-progress-container');
    const progressBar = document.getElementById('import-progress-bar');
    const statusText = document.getElementById('import-progress-status');
    
    mappingPanel.classList.add('hidden');
    progressContainer.classList.remove('hidden');
    progressBar.style.width = '10%';
    statusText.textContent = 'Mapeando registros...';
    
    // Process records in microtasks to not freeze browser UI
    setTimeout(() => {
        const votersToInsert = [];
        const totalRows = state.importTempData.length;
        
        for (let i = 0; i < totalRows; i++) {
            const row = state.importTempData[i];
            const voter = {};
            
            // Map mapped fields
            Object.keys(state.fieldMapping).forEach(fieldKey => {
                const colIndex = state.fieldMapping[fieldKey];
                voter[fieldKey] = row[colIndex] !== undefined ? String(row[colIndex]).trim() : '';
            });
            
            // Clean/convert some fields
            if (voter.edad) voter.edad = parseInt(voter.edad) || 0;
            if (voter.mesa) voter.mesa = String(voter.mesa).replace(/^(mesa|table)\s*/i, '');
            
            votersToInsert.push(voter);
        }
        
        progressBar.style.width = '40%';
        statusText.textContent = `Insertando ${votersToInsert.length} votantes en base de datos...`;
        
        setTimeout(() => {
            insertVotersBatch(votersToInsert)
                .then(result => {
                    progressBar.style.width = '100%';
                    statusText.textContent = 'Migración completa';
                    
                    setTimeout(() => {
                        progressContainer.classList.add('hidden');
                        document.getElementById('drop-zone').classList.remove('hidden');
                        
                        showNotification(`¡Importación éxitosa! Insertados: ${result.successCount} nuevos votantes. Duplicados omitidos: ${result.skipCount}.`, 'success');
                        
                        state.importTempData = null;
                        updateGlobalStats();
                        switchTab('dashboard');
                    }, 500);
                })
                .catch(err => {
                    progressContainer.classList.add('hidden');
                    document.getElementById('drop-zone').classList.remove('hidden');
                    showNotification('Error al insertar registros en la base de datos: ' + err, 'error');
                });
        }, 100);
    }, 100);
}


// ==========================================
// 4. MOCK DATA GENERATOR FOR MANEIRO
// ==========================================

function loadMockDataForManeiro() {
    if (state.votersCount > 0) {
        if (!confirm('Ya existen datos en el sistema. ¿Deseas agregar los datos de prueba del Municipio Maneiro adicionalmente?')) {
            return;
        }
    }
    
    const mockVoters = [];
    const firstNames = ["Carlos", "María", "José", "Ana", "Luis", "Carmen", "Juan", "Rosa", "Pedro", "Luisa", "Miguel", "Patricia", "Jorge", "Elizabeth", "Francisco", "Gabriela", "Jesús", "Yolanda", "Manuel", "Yusmeri", "Alexander", "Sandra", "Daniel", "Diana", "Rafael", "Adriana", "Diego", "Verónica", "Oscar", "Mónica"];
    const lastNames = ["Rodríguez", "González", "Hernández", "Díaz", "García", "Martínez", "Pérez", "López", "Gómez", "Flores", "Sánchez", "Ramírez", "Reyes", "Ruiz", "Morales", "Acosta", "Brito", "Marval", "Vásquez", "Rondón", "Salazar", "Guzmán", "Mendoza", "Villalba", "Fernández", "Suárez", "Ortega", "Pino", "Rengel", "Guerra"];
    const maritalStatus = ["Soltero(a)", "Casado(a)", "Divorciado(a)", "Viudo(a)", "Concubinato"];
    const addressSectors = ["Casco de Pampatar", "Sector Jorge Coll", "Playa El Ángel", "Urb. San Lorenzo", "Sector Apostadero", "Urbanización Playa El Ángel", "Sector Los Cerritos", "El Caranta"];
    
    // Generate 150 voters
    for (let i = 0; i < 150; i++) {
        const fn = firstNames[Math.floor(Math.random() * firstNames.length)];
        const ln1 = lastNames[Math.floor(Math.random() * lastNames.length)];
        const ln2 = lastNames[Math.floor(Math.random() * lastNames.length)];
        const fullName = `${fn} ${ln1} ${ln2}`;
        
        // Cédula standard for Venezuela (between 12M and 28M)
        const ciVal = Math.floor(Math.random() * 16000000) + 12000000;
        const cedula = `V-${ciVal.toLocaleString('de-DE')}`; // format V-XX.XXX.XXX
        
        const age = Math.floor(Math.random() * 62) + 18;
        const status = maritalStatus[Math.floor(Math.random() * maritalStatus.length)];
        const sector = addressSectors[Math.floor(Math.random() * addressSectors.length)];
        const address = `${sector}, Calle ${Math.floor(Math.random()*10)+1}, Casa N° ${Math.floor(Math.random()*100)+1}`;
        
        const phone = `04${[12,14,16,24][Math.floor(Math.random()*4)]}-${Math.floor(1000000 + Math.random() * 9000000)}`;
        const email = `${fn.toLowerCase()}.${ln1.toLowerCase()}${Math.floor(Math.random()*90)+10}@gmail.com`;
        
        const center = MANEIRO_CENTERS[Math.floor(Math.random() * MANEIRO_CENTERS.length)];
        const table = String(Math.floor(Math.random() * 4) + 1); // tables 1 to 4
        
        // Randomly simulate that some have already voted (e.g. 35% participation to start)
        const hasVoted = Math.random() < 0.35 ? 1 : 0;
        let voteTime = null;
        if (hasVoted) {
            const hoursAgo = Math.random() * 8; // voted in last 8 hours
            voteTime = new Date(Date.now() - hoursAgo * 3600 * 1000).toISOString();
        }
        
        mockVoters.push({
            nombre_completo: fullName,
            cedula: cedula,
            direccion: address,
            edad: age,
            centro_votacion: center,
            telefono: phone,
            correo: email,
            estado_civil: status,
            mesa: table,
            ha_votado: hasVoted,
            fecha_voto: voteTime
        });
    }
    
    // Insert mock voters in database
    insertVotersBatch(mockVoters)
        .then(result => {
            showNotification(`¡Datos de prueba cargados con éxito! Insertados: ${result.successCount} votantes simulados del Municipio Maneiro.`, 'success');
            updateGlobalStats();
            switchTab('dashboard');
        })
        .catch(err => {
            showNotification('Error al crear los datos de prueba: ' + err, 'error');
        });
}


// ==========================================
// 5. DASHBOARD STATISTICS ENGINE
// ==========================================

function updateGlobalStats() {
    getStatistics()
        .then(stats => {
            state.votersCount = stats.totalVoters;
            
            // Update counts badge
            const badgeText = document.getElementById('badge-text');
            const voterCountBadge = document.getElementById('voter-count-badge');
            
            if (stats.totalVoters === 0) {
                badgeText.textContent = 'Base de datos vacía';
                voterCountBadge.className = 'badge badge-indigo';
                document.getElementById('no-data-dashboard').classList.remove('hidden');
                document.getElementById('centers-list-container').classList.add('hidden');
                
                // Reset stats display
                document.getElementById('stat-total-voters').textContent = '0';
                document.getElementById('stat-total-voted').textContent = '0';
                document.getElementById('stat-voted-percent').textContent = '0% del total';
                document.getElementById('stat-total-centers').textContent = '0';
                document.getElementById('stat-total-tables').textContent = '0 mesas';
                document.getElementById('general-participation-percent').textContent = '0%';
                document.getElementById('summary-voted-count').textContent = '0';
                document.getElementById('summary-pending-count').textContent = '0';
                
                // Disable search field
                document.getElementById('voter-search-input').disabled = true;
                document.getElementById('filter-center').disabled = true;
                document.getElementById('filter-table').disabled = true;
                document.getElementById('filter-status').disabled = true;
                document.getElementById('search-instruction-text').textContent = 'Por favor, importa votantes para habilitar la búsqueda.';
                document.getElementById('btn-export-database-full').disabled = true;
                
                // Draw zero circle progress
                updateCircleProgress(0);
                return;
            }
            
            // Enable search field and options
            document.getElementById('voter-search-input').disabled = false;
            document.getElementById('filter-center').disabled = false;
            document.getElementById('filter-table').disabled = false;
            document.getElementById('filter-status').disabled = false;
            document.getElementById('search-instruction-text').textContent = 'Escribe una Cédula de Identidad o Nombre para comenzar a buscar.';
            document.getElementById('btn-export-database-full').disabled = false;
            
            // Compute general counts
            badgeText.textContent = `${stats.totalVoters.toLocaleString('de-DE')} votantes registrados`;
            voterCountBadge.className = 'badge badge-teal';
            
            document.getElementById('stat-total-voters').textContent = stats.totalVoters.toLocaleString('de-DE');
            document.getElementById('stat-total-voted').textContent = stats.totalVoted.toLocaleString('de-DE');
            
            const generalParticipation = stats.totalVoters > 0 ? (stats.totalVoted / stats.totalVoters) * 100 : 0;
            document.getElementById('stat-voted-percent').textContent = `${generalParticipation.toFixed(1)}% del total`;
            
            // Calculate total tables count
            let totalTables = 0;
            Object.values(stats.centersStats).forEach(c => {
                totalTables += Object.keys(c.tables).length;
            });
            
            document.getElementById('stat-total-centers').textContent = stats.centersCount;
            document.getElementById('stat-total-tables').textContent = `${totalTables} mesas electorales`;
            
            // Side panel metrics
            document.getElementById('general-participation-percent').textContent = `${generalParticipation.toFixed(1)}%`;
            document.getElementById('summary-voted-count').textContent = stats.totalVoted.toLocaleString('de-DE');
            document.getElementById('summary-pending-count').textContent = (stats.totalVoters - stats.totalVoted).toLocaleString('de-DE');
            
            // Render circle progress bar
            updateCircleProgress(generalParticipation);
            
            // Build filter lists if search options are empty
            syncSearchFilters();
            
            // Render centers list
            document.getElementById('no-data-dashboard').classList.add('hidden');
            const listContainer = document.getElementById('centers-list-container');
            listContainer.classList.remove('hidden');
            renderCentersBreakdown(stats.centersStats);
        })
        .catch(err => {
            console.error('Error al actualizar estadísticas:', err);
            showNotification('Error al recargar el dashboard.', 'error');
        });
}

function updateCircleProgress(percent) {
    const circle = document.getElementById('progress-ring-circle');
    const radius = circle.r.baseVal.value;
    const circumference = 2 * Math.PI * radius; // 477.52
    
    circle.style.strokeDasharray = `${circumference} ${circumference}`;
    
    const offset = circumference - (percent / 100) * circumference;
    circle.style.strokeDashoffset = offset;
}

function renderCentersBreakdown(centersStats) {
    const container = document.getElementById('centers-list-container');
    container.innerHTML = '';
    
    // Sort centers by name
    const sortedCenters = Object.keys(centersStats).sort();
    
    sortedCenters.forEach((centerName, idx) => {
        const data = centersStats[centerName];
        const participation = data.total > 0 ? (data.voted / data.total) * 100 : 0;
        
        const card = document.createElement('div');
        card.className = 'center-row-card';
        card.id = `center-card-${idx}`;
        
        // Content of row
        card.innerHTML = `
            <div class="center-header-row" onclick="toggleCenterCardExpanded(${idx})">
                <div class="center-title-area">
                    <svg class="chevron-icon" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                    <span class="center-name">${centerName}</span>
                </div>
                <div class="center-voted-stats">
                    <div class="progress-container-mini">
                        <div class="progress-bar-fill-mini" style="width: ${participation}%"></div>
                    </div>
                    <span class="stats-number"><strong>${data.voted}</strong> de ${data.total} (${participation.toFixed(1)}%)</span>
                </div>
            </div>
            <div class="center-tables-detail">
                <div class="tables-grid-header">
                    <span>Mesa</span>
                    <span>Progreso de Votos</span>
                    <span>Participación (%)</span>
                </div>
                <div class="tables-rows-container">
                    ${renderTablesRowsHTML(data.tables)}
                </div>
            </div>
        `;
        
        container.appendChild(card);
    });
}

function renderTablesRowsHTML(tables) {
    // Sort tables keys
    const sortedTables = Object.keys(tables).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    
    return sortedTables.map(tableKey => {
        const tData = tables[tableKey];
        const percent = tData.total > 0 ? (tData.voted / tData.total) * 100 : 0;
        return `
            <div class="table-row-item">
                <span class="table-num">Mesa N° ${tableKey}</span>
                <span class="stats-number"><strong>${tData.voted}</strong> de ${tData.total}</span>
                <span class="table-participation">
                    <div class="progress-container-mini" style="width: 80px;">
                        <div class="progress-bar-fill-mini" style="width: ${percent}%"></div>
                    </div>
                    <span>${percent.toFixed(1)}%</span>
                </span>
            </div>
        `;
    }).join('');
}

// Global click function for expanding center items
window.toggleCenterCardExpanded = function(cardIndex) {
    const card = document.getElementById(`center-card-${cardIndex}`);
    if (card) {
        card.classList.toggle('expanded');
    }
};

// Sync filter option lists on Search pane
function syncSearchFilters() {
    getFilterOptions()
        .then(options => {
            const centerSelect = document.getElementById('filter-center');
            const currentSelectedCenter = centerSelect.value;
            
            // Keep "Todos"
            centerSelect.innerHTML = '<option value="">Todos los Centros</option>';
            
            options.centers.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c;
                opt.textContent = c;
                centerSelect.appendChild(opt);
            });
            
            // Restore selection if still exists
            if (options.centers.includes(currentSelectedCenter)) {
                centerSelect.value = currentSelectedCenter;
            }
            
            populateTableFilterOptions(centerSelect.value, options.tables);
        })
        .catch(err => console.error('Error sincronizando filtros:', err));
}

function populateTableFilterOptions(centerName, cachedTables = null) {
    const tableSelect = document.getElementById('filter-table');
    const currentSelectedTable = tableSelect.value;
    
    tableSelect.innerHTML = '<option value="">Todas las Mesas</option>';
    
    const fillTables = (tables) => {
        if (!centerName) return;
        
        const set = tables[centerName];
        if (set) {
            const sorted = Array.from(set).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
            sorted.forEach(t => {
                const opt = document.createElement('option');
                opt.value = t;
                opt.textContent = `Mesa N° ${t}`;
                tableSelect.appendChild(opt);
            });
            
            if (sorted.includes(currentSelectedTable)) {
                tableSelect.value = currentSelectedTable;
            }
        }
    };
    
    if (cachedTables) {
        fillTables(cachedTables);
    } else {
        getFilterOptions()
            .then(options => fillTables(options.tables))
            .catch(err => console.error(err));
    }
}


// ==========================================
// 6. VOTER SEARCH AND LIVE VOTING REGISTRATION
// ==========================================

function updateVotersSearchList() {
    if (state.votersCount === 0) {
        document.getElementById('search-empty-state').classList.remove('hidden');
        document.getElementById('voters-results-container').classList.add('hidden');
        document.getElementById('voters-pagination').classList.add('hidden');
        return;
    }
    
    queryVoters(
        state.search.query,
        state.search.center,
        state.search.table,
        state.search.status,
        state.search.page,
        state.search.pageSize
    )
        .then(result => {
            state.search.totalPages = result.totalPages;
            
            const resultsContainer = document.getElementById('voters-results-container');
            const emptyState = document.getElementById('search-empty-state');
            const pagination = document.getElementById('voters-pagination');
            
            if (result.voters.length === 0) {
                emptyState.classList.remove('hidden');
                emptyState.querySelector('h5').textContent = 'Sin resultados';
                emptyState.querySelector('p').textContent = 'No encontramos ningún elector con esos filtros de búsqueda.';
                resultsContainer.classList.add('hidden');
                pagination.classList.add('hidden');
                return;
            }
            
            emptyState.classList.add('hidden');
            resultsContainer.classList.remove('hidden');
            pagination.classList.remove('hidden');
            
            // Render Cards
            resultsContainer.innerHTML = '';
            
            result.voters.forEach(voter => {
                const isVoted = voter.ha_votado === 1;
                const card = document.createElement('div');
                card.className = `voter-card ${isVoted ? 'voted' : ''}`;
                card.id = `voter-card-${voter.id}`;
                
                // Format timestamp
                let timestampText = '';
                if (isVoted && voter.fecha_voto) {
                    const date = new Date(voter.fecha_voto);
                    timestampText = `<span class="voter-timestamp">Registrado: ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${date.toLocaleDateString()}</span>`;
                }
                
                card.innerHTML = `
                    <div class="voter-card-header">
                        <span class="voter-name">${voter.nombre_completo}</span>
                        <span class="voter-id-badge">${voter.cedula}</span>
                    </div>
                    <div class="voter-details-list">
                        <div class="voter-detail-row">
                            <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="12 6 12 12 16 14"/></svg>
                            <span>${voter.edad ? voter.edad + ' años' : 'Edad N/D'} — ${voter.estado_civil || 'Edo. Civil N/D'}</span>
                        </div>
                        <div class="voter-detail-row">
                            <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                            <span><strong>${voter.centro_votacion}</strong> (Mesa ${voter.mesa})</span>
                        </div>
                        ${voter.direccion ? `
                        <div class="voter-detail-row">
                            <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                            <span>${voter.direccion}</span>
                        </div>` : ''}
                        ${voter.telefono ? `
                        <div class="voter-detail-row">
                            <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                            <span>${voter.telefono}</span>
                        </div>` : ''}
                    </div>
                    <div class="voter-actions">
                        <button class="btn-vote-toggle ${isVoted ? 'btn-voted' : 'btn-unvoted'}" onclick="handleVoteToggle(${voter.id}, ${isVoted ? 0 : 1})">
                            ${isVoted ? `
                                <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                                <span class="btn-voted-text">Registrado (Votó)</span>
                                <span class="btn-voted-hover-text">Anular Voto</span>
                            ` : `
                                <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                                <span>Registrar Voto</span>
                            `}
                        </button>
                        ${timestampText}
                    </div>
                `;
                
                resultsContainer.appendChild(card);
            });
            
            // Pagination controls update
            document.getElementById('pagination-info').textContent = `Página ${result.currentPage} de ${result.totalPages} (Total: ${result.totalItems.toLocaleString('de-DE')} electores)`;
            document.getElementById('btn-prev-page').disabled = result.currentPage === 1;
            document.getElementById('btn-next-page').disabled = result.currentPage === result.totalPages;
        })
        .catch(err => {
            console.error('Error al realizar búsqueda:', err);
            showNotification('Error al cargar lista de electores.', 'error');
        });
}

// Global toggle vote action
window.handleVoteToggle = function(voterId, nextStatus) {
    toggleVoterStatus(voterId, nextStatus === 1)
        .then(updatedVoter => {
            const isVoted = updatedVoter.ha_votado === 1;
            
            // Action feedback notification
            if (isVoted) {
                showNotification(`Voto registrado con éxito para: ${updatedVoter.nombre_completo}.`, 'success');
            } else {
                showNotification(`Registro de voto cancelado para: ${updatedVoter.nombre_completo}.`, 'success');
            }
            
            // Update counts in badges and side lists instantly
            updateVotersSearchList();
            
            // Sincronizar conteo en header badge
            getStatistics().then(stats => {
                document.getElementById('badge-text').textContent = `${stats.totalVoters.toLocaleString('de-DE')} votantes registrados`;
            });
        })
        .catch(err => {
            console.error(err);
            showNotification('Error al actualizar estado del voto.', 'error');
        });
};


// ==========================================
// 7. EXPORT DATA TO CSV (Excel Compatible)
// ==========================================

function exportDatabase() {
    getAllVotersForExport()
        .then(voters => {
            if (voters.length === 0) {
                alert('No hay votantes registrados para exportar.');
                return;
            }
            
            // Setup CSV header and contents
            // Using UTF-8 BOM so Excel respects accents and Spanish characters (ñ, á, é...)
            let csvContent = '\uFEFF';
            
            const columns = [
                'Cédula de Identidad', 
                'Nombre Completo', 
                'Edad', 
                'Estado Civil',
                'Dirección', 
                'Teléfono', 
                'Correo Electrónico',
                'Centro de Votación', 
                'Mesa', 
                'Ha Votado (Exit Poll)', 
                'Fecha y Hora del Voto'
            ];
            
            csvContent += columns.map(c => `"${c.replace(/"/g, '""')}"`).join(',') + '\n';
            
            voters.forEach(v => {
                const hasVotedText = v.ha_votado === 1 ? 'SÍ' : 'NO';
                let voteDateText = '';
                if (v.ha_votado === 1 && v.fecha_voto) {
                    const date = new Date(v.fecha_voto);
                    voteDateText = date.toLocaleString();
                }
                
                const row = [
                    v.cedula || '',
                    v.nombre_completo || '',
                    v.edad || '',
                    v.estado_civil || '',
                    v.direccion || '',
                    v.telefono || '',
                    v.correo || '',
                    v.centro_votacion || '',
                    v.mesa || '',
                    hasVotedText,
                    voteDateText
                ];
                
                csvContent += row.map(cell => {
                    const cellStr = String(cell);
                    return `"${cellStr.replace(/"/g, '""')}"`;
                }).join(',') + '\n';
            });
            
            // Trigger browser download
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            
            // Filename timestamped
            const now = new Date();
            const dateStr = `${now.getFullYear()}${(now.getMonth()+1).toString().padStart(2,'0')}${now.getDate().toString().padStart(2,'0')}_${now.getHours().toString().padStart(2,'0')}${now.getMinutes().toString().padStart(2,'0')}`;
            
            link.setAttribute('href', url);
            link.setAttribute('download', `exit_poll_maneiro_${dateStr}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            showNotification('Reporte descargado con éxito.', 'success');
        })
        .catch(err => {
            console.error('Error exportando datos:', err);
            showNotification('Error al exportar la base de datos.', 'error');
        });
}


// ==========================================
// 8. UTILITIES (Debounce, Notifications)
// ==========================================

function showNotification(message, type = 'success') {
    const banner = document.getElementById('notification-banner');
    const msgSpan = document.getElementById('notification-message');
    
    msgSpan.textContent = message;
    
    if (type === 'success') {
        banner.style.backgroundColor = 'rgba(20, 184, 166, 0.1)';
        banner.style.borderColor = 'rgba(20, 184, 166, 0.2)';
        msgSpan.style.color = '#2dd4bf';
    } else {
        banner.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
        banner.style.borderColor = 'rgba(239, 68, 68, 0.2)';
        msgSpan.style.color = '#f87171';
    }
    
    banner.classList.remove('hidden');
    
    // Auto hide after 6 seconds
    if (window.notificationTimeout) {
        clearTimeout(window.notificationTimeout);
    }
    
    window.notificationTimeout = setTimeout(() => {
        banner.classList.add('hidden');
    }, 6000);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
