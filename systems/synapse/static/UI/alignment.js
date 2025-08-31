// JavaScript for the Synapse Alignment Tool
const API_BASE = 'http://127.0.0.1:8000';

document.addEventListener('DOMContentLoaded', fetchNextPair);

const container = document.getElementById('comparison-container');

async function fetchNextPair() {
    container.innerHTML = '<div id="loading-state">Loading next comparison...</div>';
    try {
        const response = await fetch(`${API_BASE}/values/get_comparison_pair`);
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Failed to fetch pair');
        }
        const data = await response.json();
        renderPair(data);
    } catch (error) {
        container.innerHTML = `<div id="loading-state" style="color: #e57373;">Error: ${error.message}. No more pairs to compare for now.</div>`;
    }
}

function renderPair(data) {
    container.innerHTML = `
        <div class="comparison-card" id="card-a">
            <h2>Outcome A</h2>
            <pre>${JSON.stringify(data.episode_a, null, 2)}</pre>
            <button class="choice-btn" onclick="submitPreference('${data.episode_a.episode_id}', '${data.episode_b.episode_id}')">I Prefer Outcome A</button>
        </div>
        <div class="comparison-card" id="card-b">
            <h2>Outcome B</h2>
            <pre>${JSON.stringify(data.episode_b, null, 2)}</pre>
            <button class="choice-btn" onclick="submitPreference('${data.episode_b.episode_id}', '${data.episode_a.episode_id}')">I Prefer Outcome B</button>
        </div>
    `;
}

async function submitPreference(winnerId, loserId) {
    try {
        const response = await fetch(`${API_BASE}/values/submit_preference`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                winner_episode_id: winnerId,
                loser_episode_id: loserId,
                reasoning: "UI-based preference"
            })
        });
        if (!response.ok) throw new Error('Failed to submit preference');
        
        // Success, load the next pair for the user
        fetchNextPair();

    } catch (error) {
        console.error('Submission error:', error);
        container.innerHTML = `<div id="loading-state" style="color: #e57373;">Error submitting preference. Please try again.</div>`;
    }
}