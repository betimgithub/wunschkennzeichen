const express = require('express');
const fetch = require('node-fetch');
const cors = require('cors');

const app = express();
const port = 3000;

// CORS Middleware
app.use(cors());
app.use(express.json());  // Body Parsing für POST Anfragen

// API-Route zum Abrufen der Service ID basierend auf dem RegionCode
app.get('/api/service', async (req, res) => {
  const regionCode = req.query.regionCode;
  const apiUrl = `https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${regionCode}`;

  try {
    const response = await fetch(apiUrl);
    const data = await response.json();
    if (data.registrationOfficeServices.length > 0) {
      const serviceId = data.registrationOfficeServices[0].registrationOfficeServiceId;
      res.json({ serviceId });
    } else {
      res.status(404).json({ error: "Keine Service-ID gefunden" });
    }
  } catch (error) {
    console.error("Fehler beim Abruf der Service-ID:", error);
    res.status(500).json({ error: "Fehler beim Abrufen der Service-ID" });
  }
});

// API-Route zum Prüfen der Verfügbarkeit eines Wunschkennzeichens
app.post('/check', async (req, res) => {
  const apiUrl = 'https://wunschkennzeichen.zulassung.de/api/check';
  const payload = req.body;

  try {
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    res.json(data);
  } catch (error) {
    console.error("Fehler beim Abruf der Verfügbarkeit:", error);
    res.status(500).json({ error: "Fehler beim Abrufen der Verfügbarkeit" });
  }
});

// Server starten
app.listen(port, () => {
  console.log(`Server läuft auf http://localhost:${port}`);
});
