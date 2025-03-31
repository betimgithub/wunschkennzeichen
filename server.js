const express = require('express');
const axios = require('axios');
const https = require('https');
const HttpsProxyAgent = require('https-proxy-agent');

// Initialisiere Express und erstelle eine Route
const app = express();
const port = 3000;

// Setze den Proxy-Server (Brightdata)
const proxyUrl = 'http://brd.superproxy.io:33335'; // Proxy-URL von Brightdata

// Definiere den HttpsProxyAgent mit der richtigen Konfiguration
const agent = new HttpsProxyAgent({
  host: 'brd.superproxy.io',
  port: 33335,
  auth: 'brd-customer-hl_46ab8084-zone-datacenter_proxy1:1q735kkv57ub', // Dein Proxy-Authentifizierungsschlüssel
  rejectUnauthorized: false // SSL-Zertifikatsvalidierung deaktivieren
});

// API-Route, die für die Anfrage zuständig ist
app.get('/api/service', async (req, res) => {
  const regionCode = req.query.regionCode;

  // Protokolliere die Region und die Anfrage-URL
  console.log(`Anfrage an API mit RegionCode: ${regionCode}`);

  try {
    // Erstelle die vollständige URL
    const url = `https://wunschkennzeichen.zulassung.de/api/service?regionCode=${regionCode}`;
    console.log(`Verwendete URL: ${url}`); // Protokolliere die vollständige URL

    // Sende die Anfrage an die API über den Proxy
    const response = await axios.get(url, {
      httpsAgent: agent
    });

    // Rückgabe der Antwort an den Client
    res.json(response.data);
  } catch (error) {
    console.error('Fehler beim Abruf:', error);
    res.status(500).json({ error: 'Fehler beim Abruf der Daten' });
  }
});

// Starte den Server
app.listen(port, () => {
  console.log(`Server läuft auf http://localhost:${port}`);
});
