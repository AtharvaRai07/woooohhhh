const form = document.getElementById("plan-form");
const submitBtn = document.getElementById("submit-btn");
const resultSection = document.getElementById("result");
const resultMeta = document.getElementById("result-meta");
const resultContent = document.getElementById("result-content");

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function splitLines(text) {
    return String(text || "")
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean);
}

function renderParagraphs(text) {
    const lines = splitLines(text);
    if (!lines.length) {
        return "<p>No data available.</p>";
    }
    return lines.map((line) => `<p>${escapeHtml(line)}</p>`).join("");
}

function renderList(text) {
    const lines = splitLines(text);
    if (!lines.length) {
        return "<p>No data available.</p>";
    }
    return `<ul class=\"result-list\">${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`;
}

function renderBudgetOptimizer(text) {
    const lines = splitLines(text);
    if (!lines.length) {
        return "<p>No data available.</p>";
    }

    const tierHeaderPattern = /^(LOW|MEDIUM|LUXURY)\s+PLAN\s*\((.+)\):$/i;
    const introLines = [];
    const tiers = [];
    const footerLines = [];
    let currentTier = null;

    for (const line of lines) {
        const tierMatch = line.match(tierHeaderPattern);
        if (tierMatch) {
            currentTier = {
                level: tierMatch[1].toUpperCase(),
                budget: tierMatch[2],
                details: []
            };
            tiers.push(currentTier);
            continue;
        }

        if (currentTier) {
            const isFooter = /^Live inputs counted:/i.test(line);
            if (isFooter) {
                currentTier = null;
                footerLines.push(line);
            } else {
                currentTier.details.push(line.replace(/^-\s*/, ""));
            }
            continue;
        }

        if (/^Live inputs counted:/i.test(line)) {
            footerLines.push(line);
            continue;
        }

        introLines.push(line);
    }

    const introHtml = introLines.length
        ? `<p class=\"budget-intro\">${escapeHtml(introLines.join(" "))}</p>`
        : "";

    const tiersHtml = tiers.length
        ? `<div class=\"budget-tier-grid\">${tiers.map((tier) => {
            const toneClass = `tier-${tier.level.toLowerCase()}`;
            const details = tier.details.length
                ? `<ul class=\"budget-tier-list\">${tier.details.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
                : "<p>No tier details available.</p>";

            return `
<article class="budget-tier ${toneClass}">
    <header class="budget-tier-header">
        <p class="budget-tier-label">${escapeHtml(tier.level)} PLAN</p>
        <p class="budget-tier-amount">${escapeHtml(tier.budget)}</p>
    </header>
    ${details}
</article>
`.trim();
        }).join("")}</div>`
        : renderList(text);

    const footerHtml = footerLines.length
        ? `<p class=\"budget-footer\">${escapeHtml(footerLines.join(" | "))}</p>`
        : "";

    return `${introHtml}${tiersHtml}${footerHtml}`;
}

function shortSentence(text) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    if (!clean) {
        return "No data available.";
    }
    const sentence = clean.split(/(?<=[.!?])\s+/)[0] || clean;
    return sentence.length > 180 ? `${sentence.slice(0, 177)}...` : sentence;
}

function parseAttractionCount(text) {
    const match = String(text || "").match(/(\d+)\.\s+/g);
    return match ? match.length : 0;
}

function parseBudgetTierAmounts(text) {
    const source = String(text || "");
    const getAmount = (tier) => {
        const m = source.match(new RegExp(`${tier}\\s+PLAN\\s*\\(([^)]+)\\):`, "i"));
        return m ? m[1] : "N/A";
    };

    return {
        low: getAmount("LOW"),
        medium: getAmount("MEDIUM"),
        luxury: getAmount("LUXURY")
    };
}

function renderTripSummary(plan) {
    const weatherSummary = shortSentence(plan.weather);
    const hotelSummary = shortSentence(plan.hotels);
    const restaurantSummary = shortSentence(plan.restaurants);
    const attractionCount = parseAttractionCount(plan.attractions);
    const budget = parseBudgetTierAmounts(plan.budget_optimizer);

    return `
<section class="result-card summary-card">
    <h3>Trip Summary</h3>
    <div class="summary-grid">
        <article class="summary-item">
            <p class="summary-label">Weather Outlook</p>
            <p class="summary-text">${escapeHtml(weatherSummary)}</p>
        </article>
        <article class="summary-item">
            <p class="summary-label">Availability Snapshot</p>
            <ul class="summary-list">
                <li>Hotels: ${escapeHtml(hotelSummary)}</li>
                <li>Restaurants: ${escapeHtml(restaurantSummary)}</li>
                <li>Attractions found: ${escapeHtml(String(attractionCount || "0"))}</li>
            </ul>
        </article>
        <article class="summary-item summary-item-wide">
            <p class="summary-label">Budget Tiers</p>
            <div class="summary-tier-row">
                <span class="summary-pill low">LOW: ${escapeHtml(budget.low)}</span>
                <span class="summary-pill medium">MEDIUM: ${escapeHtml(budget.medium)}</span>
                <span class="summary-pill luxury">LUXURY: ${escapeHtml(budget.luxury)}</span>
            </div>
        </article>
    </div>
</section>
`.trim();
}

function renderSignatureItinerary(text) {
    const lines = splitLines(text);
    if (!lines.length) {
        return "<p>No data available.</p>";
    }

    const dayPattern = /^Day\s*(\d+)(?:\s+([A-Za-z]+))?:\s*(.+)$/i;
    const introLines = [];
    const trailingLines = [];
    const dayOrder = [];
    const dayMap = new Map();

    for (const line of lines) {
        const dayMatch = line.match(dayPattern);
        if (dayMatch) {
            const dayNumber = dayMatch[1];
            const slot = dayMatch[2];
            const details = dayMatch[3];
            const activity = slot ? `${slot}: ${details}` : details;

            if (!dayMap.has(dayNumber)) {
                dayMap.set(dayNumber, []);
                dayOrder.push(dayNumber);
            }
            dayMap.get(dayNumber).push(activity);
            continue;
        }

        if (dayOrder.length === 0) {
            introLines.push(line);
        } else {
            trailingLines.push(line);
        }
    }

    if (!dayOrder.length) {
        return renderList(text);
    }

    const introHtml = introLines.length
        ? `<p class=\"itinerary-intro\">${escapeHtml(introLines.join(" "))}</p>`
        : "";

    const daysHtml = `<div class=\"itinerary-days\">${dayOrder.map((day) => {
        const activities = dayMap.get(day) || [];
        const listItems = activities.map((activity) => `<li>${escapeHtml(activity)}</li>`).join("");

        return `
<article class="itinerary-day-block">
    <h4 class="itinerary-day-title">DAY - ${escapeHtml(day)}</h4>
    <ul class="itinerary-activity-list">${listItems}</ul>
</article>
`.trim();
    }).join("")}</div>`;

    const trailingHtml = trailingLines.length
        ? `<p class=\"itinerary-note\">Detailed data inputs are summarized above for readability.</p>`
        : "";

    return `${introHtml}${daysHtml}${trailingHtml}`;
}

function renderPlanResult(plan) {
    const destination = escapeHtml(plan.destination || "Your Destination");
    const warning = plan.warning ? `<div class=\"warning-note\">${escapeHtml(plan.warning)}</div>` : "";

    return `
<article class="result-shell">
    <header class="result-hero">
        <p class="result-kicker">Concierge Plan</p>
        <h2>${destination}</h2>
        <div class="chip-row">
            <span class="chip">Live APIs</span>
            <span class="chip">Weather + Seasonal Estimate</span>
            <span class="chip">Low / Medium / Luxury</span>
        </div>
    </header>

    ${warning}

    ${renderTripSummary(plan)}

    <section class="result-card">
        <h3>Weather Intelligence</h3>
        ${renderParagraphs(plan.weather)}
    </section>

    <section class="result-card">
        <h3>Hotel Intelligence</h3>
        ${renderList(plan.hotels)}
    </section>

    <section class="result-card two-col">
        <div>
            <h3>Restaurant Intelligence</h3>
            ${renderList(plan.restaurants)}
        </div>
        <div>
            <h3>Attraction Intelligence</h3>
            ${renderList(plan.attractions)}
        </div>
    </section>

    <section class="result-card">
        <h3>Currency Intelligence</h3>
        ${renderParagraphs(plan.currency)}
    </section>

    <section class="result-card">
        <h3>Budget Optimizer</h3>
        ${renderBudgetOptimizer(plan.budget_optimizer)}
    </section>

    <section class="result-card">
        <h3>Signature Itinerary</h3>
        ${renderSignatureItinerary(plan.itinerary)}
    </section>
</article>
`.trim();
}

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const data = new FormData(form);
    const payload = Object.fromEntries(data.entries());
    payload.adults = Number(payload.adults);
    payload.budget_amount = Number(payload.budget_amount);
    payload.budget_currency = payload.budget_currency.toUpperCase();

    submitBtn.disabled = true;
    submitBtn.textContent = "Generating...";

    try {
        const res = await fetch("/api/v1/plan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const detail = await res.text();
            throw new Error(detail || "Request failed");
        }

        const plan = await res.json();
        resultMeta.textContent = `Generated for ${plan.destination} at ${new Date(plan.generated_at).toLocaleString()}`;
        resultContent.innerHTML = renderPlanResult(plan);
        resultSection.classList.remove("hidden");
        resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
        resultMeta.textContent = "Error";
        resultContent.textContent = String(err);
        resultSection.classList.remove("hidden");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Generate Plan";
    }
});
