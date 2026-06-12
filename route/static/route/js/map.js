const map = L.map("map", {
    zoomControl: true,
    attributionControl: true,
}).setView([39.8283, -98.5795], 4);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);

L.control.scale({ imperial: true, metric: false, position: "bottomleft" }).addTo(map);

let routeLayer = null;
let markerLayer = L.layerGroup().addTo(map);

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(";").shift();
    }
    return "";
}

function decodePolyline(encoded) {
    let index = 0;
    const len = encoded.length;
    let lat = 0;
    let lng = 0;
    const coordinates = [];

    while (index < len) {
        let result = 0;
        let shift = 0;
        let byte;

        do {
            byte = encoded.charCodeAt(index++) - 63;
            result |= (byte & 0x1f) << shift;
            shift += 5;
        } while (byte >= 0x20);

        const deltaLat = (result & 1) ? ~(result >> 1) : (result >> 1);
        lat += deltaLat;

        result = 0;
        shift = 0;

        do {
            byte = encoded.charCodeAt(index++) - 63;
            result |= (byte & 0x1f) << shift;
            shift += 5;
        } while (byte >= 0x20);

        const deltaLng = (result & 1) ? ~(result >> 1) : (result >> 1);
        lng += deltaLng;

        coordinates.push([lat / 1e5, lng / 1e5]);
    }

    return coordinates;
}

function formatDuration(seconds) {
    const totalMinutes = Math.round(seconds / 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    }
    return `${minutes} min`;
}

function pinIcon(label, background) {
    return L.divIcon({
        className: "route-pin",
        html: `
            <div class="pin-marker" style="background:${background}">
                <span>${label}</span>
            </div>
            <div class="pin-tail" style="border-top-color:${background}"></div>
        `,
        iconSize: [36, 46],
        iconAnchor: [18, 46],
        popupAnchor: [0, -40],
    });
}

function refreshMapSize() {
    setTimeout(() => map.invalidateSize(), 0);
    setTimeout(() => map.invalidateSize(), 200);
}

const form = document.getElementById("route-form");
const submitBtn = document.getElementById("submit-btn");
const errorBox = document.getElementById("error");
const summaryBox = document.getElementById("summary");
const stopsBox = document.getElementById("stops");
const stopsList = document.getElementById("stops-list");
const mapToolbar = document.getElementById("map-toolbar");

window.addEventListener("resize", refreshMapSize);
refreshMapSize();

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("hidden");
    submitBtn.disabled = true;
    submitBtn.textContent = "Planning...";

    const payload = {
        start: document.getElementById("start").value.trim(),
        end: document.getElementById("end").value.trim(),
    };

    try {
        const response = await fetch("/api/route/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Failed to plan route.");
        }

        renderRoute(data);
    } catch (error) {
        errorBox.textContent = error.message;
        errorBox.classList.remove("hidden");
        summaryBox.classList.add("hidden");
        stopsBox.classList.add("hidden");
        mapToolbar.classList.add("hidden");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Plan Route";
    }
});

function renderRoute(data) {
    if (routeLayer) {
        map.removeLayer(routeLayer);
    }
    markerLayer.clearLayers();

    const coordinates = decodePolyline(data.route_polyline);
    const routeStart = coordinates[0];
    const routeEnd = coordinates[coordinates.length - 1];

    routeLayer = L.polyline(coordinates, {
        color: "#2563eb",
        weight: 5,
        opacity: 0.85,
    }).addTo(map);

    L.marker(routeStart, {
        icon: pinIcon("A", "#16a34a"),
        zIndexOffset: 2000,
    })
        .addTo(markerLayer)
        .bindPopup(`<strong>Start</strong><br>${data.start.label}`);

    L.marker(routeEnd, {
        icon: pinIcon("B", "#dc2626"),
        zIndexOffset: 3000,
    })
        .addTo(markerLayer)
        .bindPopup(`<strong>End</strong><br>${data.end.label}`);

    data.fuel_stops.forEach((stop, index) => {
        L.marker([stop.lat, stop.lng], {
            icon: L.divIcon({
                className: "fuel-marker",
                html: `<div class="fuel-badge">${index + 1}</div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 15],
            }),
            zIndexOffset: 1000 + index,
        })
            .addTo(markerLayer)
            .bindPopup(
                `<strong>${stop.name}</strong><br>${stop.city}, ${stop.state}<br>$${stop.price.toFixed(3)}/gal`
            );
    });

    const bounds = L.latLngBounds(coordinates);
    data.fuel_stops.forEach((stop) => bounds.extend([stop.lat, stop.lng]));
    map.fitBounds(bounds, { padding: [80, 80] });

    const durationText = formatDuration(data.duration_seconds);
    const distanceText = `${data.distance_miles.toFixed(1)} mi`;
    const costText = `$${data.total_cost.toFixed(2)}`;
    const fuelText = `${data.total_fuel_used_gallons.toFixed(1)} gal`;
    const stopsText = `${data.fuel_stops.length} stop${data.fuel_stops.length === 1 ? "" : "s"}`;

    document.getElementById("distance").textContent = distanceText;
    document.getElementById("duration").textContent = durationText;
    document.getElementById("fuel-used").textContent = fuelText;
    document.getElementById("total-cost").textContent = costText;
    document.getElementById("stop-count").textContent = String(data.fuel_stops.length);
    summaryBox.classList.remove("hidden");

    document.getElementById("route-title").textContent = `${data.start.label} → ${data.end.label}`;
    document.getElementById("chip-distance").textContent = distanceText;
    document.getElementById("chip-duration").textContent = durationText;
    document.getElementById("chip-fuel").textContent = fuelText;
    document.getElementById("chip-cost").textContent = costText;
    document.getElementById("chip-stops").textContent = stopsText;
    mapToolbar.classList.remove("hidden");

    stopsList.innerHTML = "";
    if (data.fuel_stops.length === 0) {
        stopsList.innerHTML = "<li>No fuel stops needed for this route.</li>";
    } else {
        data.fuel_stops.forEach((stop, index) => {
            const item = document.createElement("li");
            item.innerHTML = `
                <strong>${index + 1}. ${stop.name}</strong><br>
                ${stop.city}, ${stop.state}<br>
                $${stop.price.toFixed(3)}/gal · ${stop.leg_distance_miles.toFixed(1)} mi leg · $${stop.leg_cost.toFixed(2)}
            `;
            stopsList.appendChild(item);
        });
    }
    stopsBox.classList.remove("hidden");
    refreshMapSize();
}
