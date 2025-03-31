const express = require('express');
const cors = require('cors');
const axios = require('axios');
const { HttpsProxyAgent } = require('https-proxy-agent'); // ← ACHTUNG: geschweifte Klammern!

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// BrightData Proxy-Konfiguration
const proxyUrl = 'http://brd-customer-hl_46ab8084-zone-datacenter_proxy1:1q735kkv57ub@brd.superproxy.io:33335';
const agent = new HttpsProxyAgent(proxyUrl); // ← Richtig!

// Route zum Abrufen der Zulassungsstellen
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
    console.error('❌ Fehler beim Abruf:', error.message);
    res.status(500).json({ error: 'Fehler beim Abruf der Zulassungsstelle' });
  }
});

app.listen(PORT, () => {
  console.log(`✅ Server läuft auf Port ${PORT}`);
});
