const express = require('express');
const axios = require('axios');

// Initialisiere Express und erstelle eine Route
const app = express();
const port = 3000;

// API-Route, die für die Anfrage zuständig ist
app.get('/api/service', async (req, res) => {
  const regionCode = req.query.regionCode;

  console.log(`Anfrage an API mit RegionCode: ${regionCode}`);
  const url = `https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${regionCode}`;
  console.log(`Verwendete URL: ${url}`);

  try {
    // Sende eine Anfrage an die API (ohne Proxy)
    const response = await axios.get(url); // Axios ohne Proxy

    // Antwort an den Client zurücksenden
    res.json(response.data); // Antwortdaten im JSON-Format an den Client senden
  } catch (error) {
    // Fehlerprotokollierung
    console.error('Fehler beim Abruf:', error.response ? error.response.data : error.message);
    res.status(500).json({ error: 'Fehler beim Abruf der Daten' });
  }
});

// Starte den Server
app.listen(port, () => {
  console.log(`Server läuft auf http://localhost:${port}`);
});
