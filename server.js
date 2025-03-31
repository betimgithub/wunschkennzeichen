const express = require('express');
const cors = require('cors');
const axios = require('axios');
const HttpsProxyAgent = require('https-proxy-agent');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// BrightData Proxy-Konfiguration
const agent = new HttpsProxyAgent({
  host: 'brd.superproxy.io',
  port: 33335,
  auth: 'brd-customer-hl_46ab8084-zone-datacenter_proxy1:1q735kkv57ub',
});

// Route zum Abrufen der Service-IDs über BrightData
app.get('/api/service', async (req, res) => {
  const regionCode = req.query.regionCode || 'WI';
  const url = `https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${regionCode}`;

  try {
    const response = await axios.get(url, {
      httpsAgent: agent,
      headers: {
        'accept': 'application/json',
      },
    });

    res.json(response.data);
  } catch (error) {
    console.error('❌ Fehler beim Abruf der Zulassungsstelle:', error.message);
    res.status(500).json({ error: 'Fehler beim Abruf der Zulassungsstelle' });
  }
});

// Fallback für alle anderen Routen
app.use((req, res) => {
  res.status(404).json({ error: 'Route nicht gefunden' });
});

// Server starten
app.listen(PORT, () => {
  console.log(`✅ Server läuft auf Port ${PORT}`);
});
