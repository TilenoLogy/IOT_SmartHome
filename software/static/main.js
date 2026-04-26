// Light Controls
const lightAutoMode = document.getElementById('lightAutoMode');
const lightOnBtn = document.getElementById('lightOnBtn');
const lightOffBtn = document.getElementById('lightOffBtn');
const lightColor = document.getElementById('lightColor');
const lightBadge = document.getElementById('lightBadge');

// Window Controls
const windowAutoMode = document.getElementById('windowAutoMode');
const windowOpenBtn = document.getElementById('windowOpenBtn');
const windowCloseBtn = document.getElementById('windowCloseBtn');
const windowBadge = document.getElementById('windowBadge');

// Occupancy Controls
const occupantCountDisplay = document.getElementById('occupantCountDisplay');
const occupantHeaderDisplay = document.getElementById('occupantHeaderDisplay');
const occupantListDisplay = document.getElementById('occupantListDisplay');

// Light Auto Mode Logic
lightAutoMode.addEventListener('change', function() {
    const isAuto = this.checked;
    lightOnBtn.disabled = isAuto;
    lightOffBtn.disabled = isAuto;
    lightColor.disabled = isAuto;
});

// Setup shared function to update UI from API data
const updateUIWithStatus = (data) => {
    document.getElementById("tempDisplay").innerText = `${data.temp !== null ? data.temp : 'N/A'}°C`;
    document.getElementById("humidityDisplay").innerText = `${data.humidity !== null ? data.humidity : 'N/A'}%`;
    if (data.window) {
        windowBadge.textContent = 'OPEN';
        windowBadge.className = 'badge on';
    } else {
        windowBadge.textContent = 'CLOSED';
        windowBadge.className = 'badge off';
    }
    windowAutoMode.checked = !!data.auto_mode;
    windowOpenBtn.disabled = !!data.auto_mode;
    windowCloseBtn.disabled = !!data.auto_mode;
};

// Window Auto Mode Logic
windowAutoMode.addEventListener('change', async function() {
    const isAuto = this.checked;
    windowOpenBtn.disabled = isAuto;
    windowCloseBtn.disabled = isAuto;
    
    const response = await fetch('/window_auto_mode');
    const data = await response.json();
    updateUIWithStatus(data);
});

// Status visual updates (just for demo polish)
lightOnBtn.addEventListener('click', () => { lightBadge.textContent = 'ON'; lightBadge.className = 'badge on'; });
lightOffBtn.addEventListener('click', () => { lightBadge.textContent = 'OFF'; lightBadge.className = 'badge off'; });

// Window Control Fetch Requests
windowOpenBtn.addEventListener('click', async () => { 
    const response = await fetch('/window_open');
    const data = await response.json();
    updateUIWithStatus(data);
});
windowCloseBtn.addEventListener('click', async () => { 
    const response = await fetch('/window_close');
    const data = await response.json();
    updateUIWithStatus(data);
});

// Fetch Occupancy data
async function fetchOccupants() {
    try {
        let response = await fetch('/api/occupants');
        let data = await response.json();
        
        const count = data.count !== undefined ? data.count : 0;
        occupantCountDisplay.innerText = count;
        if (occupantHeaderDisplay) occupantHeaderDisplay.innerText = count;
        
        // Update Live Badge properly
        const occupantBadge = document.getElementById('occupantBadge');
        if (data.camera_connected) {
            occupantBadge.textContent = 'LIVE';
            occupantBadge.className = 'badge on';
        } else {
            occupantBadge.textContent = 'OFFLINE';
            occupantBadge.className = 'badge off';
        }
        
        occupantListDisplay.innerHTML = '';
        if (!data.camera_connected) {
            occupantListDisplay.innerHTML = '<li style="color: #f87171;">Camera stream is disconnected.</li>';
        } else if (!data.occupants || data.occupants.length === 0) {
            occupantListDisplay.innerHTML = '<li>Room is empty.</li>';
        } else {
            if (data.unresolved_exit_count > 0) {
                const warning = document.createElement('li');
                warning.style.color = '#fbbf24';
                warning.style.marginBottom = '8px';
                warning.textContent = `* Unresolved exits: ${data.unresolved_exit_count}. Some identities may be stale.`;
                occupantListDisplay.appendChild(warning);
            }

            data.occupants.forEach(occ => {
                let li = document.createElement('li');
                // Supports both old string format and new structured payload.
                if (typeof occ === 'string') {
                    let parts = occ.split('_');
                    let name = parts.length > 1 ? parts.slice(1).join('_') : occ;
                    li.textContent = name;
                } else {
                    const marker = occ.certain ? '' : ' *';
                    li.textContent = `${occ.name}${marker}`;
                }
                occupantListDisplay.appendChild(li);
            });
        }
    } catch (error) {
        console.error("Error fetching occupants:", error);
    }
}

// 3 Second Polling Loop
setInterval(async function() {
    try {
        let response = await fetch('/api/status'); // Python returns JSON: {"temp": 24, "window": true}
        let data = await response.json();
        updateUIWithStatus(data);
        
        fetchOccupants();
    } catch (e) {
        console.error("Polling error: ", e);
    }
}, 3000);

// Chart Logic
const ctx = document.getElementById('windowChart').getContext('2d');
const windowChart = new Chart(ctx, {
    type: 'line', 
    data: {
        labels: [], 
        datasets: [
            {
                label: 'Temperature (°C)',
                data: [], 
                borderColor: 'rgba(255, 99, 132, 1)', 
                backgroundColor: 'rgba(255, 99, 132, 0.2)',
                borderWidth: 2,
                tension: 0.3,
                yAxisID: 'y' 
            },
            {
                label: 'Humidity (%)',
                data: [], 
                borderColor: 'rgba(54, 162, 235, 1)', 
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                borderWidth: 2,
                tension: 0.3,
                yAxisID: 'y1' 
            }
        ]
    },
    options: {
        responsive: true, 
        scales: {
            y: {
                type: 'linear',
                display: true,
                position: 'left',
                title: { display: true, text: 'Temperature (°C)' }
            },
            y1: {
                type: 'linear',
                display: true,
                position: 'right',
                title: { display: true, text: 'Humidity (%)' },
                grid: { drawOnChartArea: false } 
            }
        }
    }
});

// 1 Minute Data Polling for Chart
setInterval(async function() {
    try {
        let response = await fetch('/api/status');
        let data = await response.json();
        
        let now = new Date();
        let timeString = now.getHours() + ":" + now.getMinutes() + ":" + now.getSeconds();

        windowChart.data.labels.push(timeString);
        windowChart.data.datasets[0].data.push(data.temp);
        windowChart.data.datasets[1].data.push(data.humidity);

        if (windowChart.data.labels.length > 20) {
            windowChart.data.labels.shift();             
            windowChart.data.datasets[0].data.shift();   
            windowChart.data.datasets[1].data.shift();   
        }

        windowChart.update();
        
    } catch (error) {
        console.error("Error fetching data for chart:", error);
    }
}, 60000);
