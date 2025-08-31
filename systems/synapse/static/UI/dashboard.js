// JavaScript for the Synapse Observability Dashboard
const API_BASE = 'http://127.0.0.1:8000'; // Assuming local Synapse API

document.addEventListener('DOMContentLoaded', () => {
    fetchGlobalStats();
    fetchQDCoverage();

    document.getElementById('fetch-episode-btn').addEventListener('click', fetchEpisodeTrace);
});

async function fetchGlobalStats() {
    try {
        const response = await fetch(`${API_BASE}/obs/global_stats`);
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        
        document.getElementById('total-episodes').textContent = data.total_episodes;
        document.getElementById('total-arms').textContent = data.total_arms;
        document.getElementById('active-niches').textContent = data.active_niches;
        document.getElementById('firewall-blocks').textContent = data.firewall_blocks_total;
        document.getElementById('status-light').classList.replace('offline', 'online');
    } catch (error) {
        console.error('Failed to fetch global stats:', error);
        document.getElementById('status-light').classList.replace('online', 'offline');
    }
}

async function fetchQDCoverage() {
    try {
        const response = await fetch(`${API_BASE}/obs/qd_coverage`);
        const data = await response.json();
        const grid = document.getElementById('qd-grid');
        grid.innerHTML = ''; // Clear previous data
        data.niches.forEach(nicheData => {
            const item = document.createElement('div');
            item.className = 'niche-item';
            item.innerHTML = `
                <strong>Niche:</strong> ${nicheData.niche.join(', ')}<br>
                <strong>Champion:</strong> ${nicheData.champion_arm_id}<br>
                <strong>Score:</strong> ${nicheData.score.toFixed(3)}<br>
                <strong>Share:</strong> ${(nicheData.fitness_share * 100).toFixed(2)}%
            `;
            grid.appendChild(item);
        });
    } catch (error) {
        console.error('Failed to fetch QD coverage:', error);
    }
}

async function fetchEpisodeTrace() {
    const episodeId = document.getElementById('episode-id-input').value.trim();
    const outputEl = document.getElementById('episode-trace-output');
    if (!episodeId) {
        outputEl.textContent = JSON.stringify({ error: "Please enter an Episode ID." }, null, 2);
        return;
    }
    outputEl.textContent = JSON.stringify({ status: `Fetching ${episodeId}...` }, null, 2);

    try {
        const response = await fetch(`${API_BASE}/obs/episode/${episodeId}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to fetch episode');
        outputEl.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
        console.error('Failed to fetch episode trace:', error);
        outputEl.textContent = JSON.stringify({ error: error.message }, null, 2);
    }
}