const express = require('express');
const axios = require('axios');
const cors = require('cors');
const HttpsProxyAgent = require('https-proxy-agent');

const app = express();
const port = 3000;

// CORS Middleware aktivieren
app.use(cors());

// Proxy-Konfiguration (Brightdata)
const proxyUrl = 'http://brd.superproxy.io:33335';
const proxyAuth = 'brd-customer-hl_46ab8084-zone-datacenter_proxy1:1q735kkv57ub';
const agent = new HttpsProxyAgent({
  host: 'brd.superproxy.io',
  port: 33335,
  auth: proxyAuth
});

// API-Route für Service-Abfrage
app.get('/api/service', async (req, res) => {
  const regionCode = req.query.regionCode; // RegionCode vom Client

  try {
    // Anfrage an die Wunschkennzeichen-API (als Beispiel)
    const response = await axios.get(`https://wunschkennzeichen.zulassung.de/api/service?regionCode=${regionCode}`, {
      httpsAgent: agent // Proxy-Agent einfügen
    });

    res.json(response.data); // Antwort zurück an den Client
  } catch (error) {
    console.error('Fehler beim Abruf:', error);
    res.status(500).json({ error: 'Fehler beim Abruf der Daten' });
  }
});

// API-Route für die Verfügbarkeit eines Kennzeichens (Check)
app.post('/api/check', async (req, res) => {
  const { numberPlateText, registrationOfficeServiceId } = req.body;

  try {
    // Anfrage an die Wunschkennzeichen-API mit Payload
    const response = await axios.post('https://wunschkennzeichen.zulassung.de/api/check', {
      numberPlateText,
      registrationOfficeServiceId,
      vehicleType: 'CAR',
      licensePlateType: 'REGULAR',
      secondLineLength: null,
      editableLength: 8,
      startMonth: null,
      endMonth: null
    }, {
      httpsAgent: agent // Proxy-Agent
    });

    res.json(response.data); // Antwort zurück an den Client
  } catch (error) {
    console.error('Fehler beim Abruf:', error);
    res.status(500).json({ error: 'Fehler beim Abruf der Verfügbarkeit' });
  }
});

// Server starten
app.listen(port, () => {
  console.log(`Server läuft auf http://localhost:${port}`);
});
