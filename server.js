const express = require('express');
const axios = require('axios');
const https = require('https');
const HttpsProxyAgent = require('https-proxy-agent');

// Initialisiere Express und erstelle eine Route
const app = express();
const port = 3000;

// Setze den Proxy-Server (Brightdata)
const proxyUrl = 'http://brd.superproxy.io:33335'; // Proxy-URL von Brightdata
const agent = new HttpsProxyAgent({
  host: 'brd.superproxy.io',
  port: 33335,
  auth: 'brd-customer-hl_46ab8084-zone-datacenter_proxy1:1q735kkv57ub', // Dein Proxy-Authentifizierungsschlüssel
  rejectUnauthorized: false // SSL-Zertifikatsvalidierung deaktivieren
});

// Damit CORS funktioniert, stellen wir die entsprechenden Header ein
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  next();
});

// API-Route, die für die Anfrage zuständig ist
app.get('/api/service', async (req, res) => {
  const regionCode = req.query.regionCode;

  try {
    // Sende eine Anfrage an die wunschkennzeichen API über den Proxy
    const response = await axios.get(`https://wunschkennzeichen.zulassung.de/api/service?regionCode=${regionCode}`, { 
      httpsAgent: agent 
    });

    res.json(response.data); // Antwort an den Client zurücksenden
  } catch (error) {
    console.error('Fehler beim Abruf:', error);
    res.status(500).json({ error: 'Fehler beim Abruf der Daten' });
  }
});

// Starte den Server
app.listen(port, () => {
  console.log(`Server läuft auf http://localhost:${port}`);
});
