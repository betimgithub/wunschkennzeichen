const express = require('express');
const axios = require('axios');
const HttpsProxyAgent = require('https-proxy-agent');

// Initialisiere Express
const app = express();
const port = 3000;

// Setze den Brightdata-Proxy (diese Werte solltest du mit deinen eigenen ersetzen)
const proxyUrl = 'http://brd.superproxy.io:33335';  // Deine Proxy-URL
const proxyAuth = 'brd-customer-hl_46ab8084-zone-datacenter_proxy1:1q735kkv57ub';  // Dein Authentifizierungsschlüssel

// Setze den Proxy-Agent
const agent = new HttpsProxyAgent({
  host: 'brd.superproxy.io',
  port: 33335,
  auth: proxyAuth,  // Authentifizierung mit deinem Brightdata-Schlüssel
});

// API-Route, um die Anfrage durch den Proxy zu senden
app.get('/api/check', async (req, res) => {
  const { numberPlateText, registrationOfficeServiceId } = req.query;  // Extrahiere die benötigten Parameter aus der Anfrage
  
  try {
    // Sende die Anfrage an die Wunschkennzeichen-API durch den Brightdata-Proxy
    const response = await axios.post('https://wunschkennzeichen.zulassung.de/api/check', {
      numberPlateText: numberPlateText,
      registrationOfficeServiceId: registrationOfficeServiceId,
      vehicleType: 'CAR',
      licensePlateType: 'REGULAR',
      secondLineLength: null,
      editableLength: 8,
      startMonth: null,
      endMonth: null
    }, {
      headers: {
        'Content-Type': 'application/json',
      },
      httpsAgent: agent,  // Nutze den Proxy-Agent
    });

    // Sende die Antwort an den Client
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
