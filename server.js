const express = require('express');
const axios = require('axios');
const app = express();
const port = 3000;

// Middleware, um JSON zu verarbeiten
app.use(express.json());

// API-Route für das Abrufen der ServiceID und der Formate für den RegionCode
app.get('/api/service', async (req, res) => {
    const regionCode = req.query.regionCode;

    if (!regionCode) {
        return res.status(400).json({ error: "RegionCode wird benötigt." });
    }

    try {
        // Anfrage an die wunschkennzeichen API, um die Service-Daten zu erhalten
        const response = await axios.get(`https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${regionCode}`);

        // Antwort zurück an den Client
        res.json(response.data);
    } catch (error) {
        console.error('Fehler beim Abrufen der Service-Daten:', error);
        res.status(500).json({ error: "Fehler beim Abrufen der Service-Daten" });
    }
});

// API-Route für das Überprüfen der Verfügbarkeit eines Wunschkennzeichens
app.post('/api/check', async (req, res) => {
    const { numberPlateText, registrationOfficeServiceId, vehicleType, licensePlateType, secondLineLength, editableLength, startMonth, endMonth } = req.body;

    // Prüfen, ob alle erforderlichen Daten gesendet wurden
    if (!numberPlateText || !registrationOfficeServiceId || !vehicleType || !licensePlateType) {
        return res.status(400).json({ error: "Fehlende Eingabedaten." });
    }

    try {
        // Anfrage an die wunschkennzeichen API zur Überprüfung der Verfügbarkeit
        const response = await axios.post('https://wunschkennzeichen.zulassung.de/api/check', {
            numberPlateText,
            registrationOfficeServiceId,
            vehicleType,
            licensePlateType,
            secondLineLength,
            editableLength,
            startMonth,
            endMonth
        });

        // Antwort zurück an den Client
        res.json(response.data);
    } catch (error) {
        console.error('Fehler beim Überprüfen der Verfügbarkeit:', error);
        res.status(500).json({ error: "Fehler beim Überprüfen der Verfügbarkeit" });
    }
});

// Start des Servers
app.listen(port, () => {
    console.log(`Server läuft auf http://localhost:${port}`);
});
