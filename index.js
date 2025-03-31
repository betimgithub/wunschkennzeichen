const express = require('express');
const axios = require('axios');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;

// BrightData Proxy Zugangsdaten
const PROXY_HOST = 'brd.superproxy.io';
const PROXY_PORT = 33335;
const PROXY_USER = 'brd-customer-hl_46ab8084-zone-datacenter_proxy1';
const PROXY_PASS = '1q735kkv57ub';

// Middleware
app.use(cors());
app.use(express.json());

// Axios-Konfiguration mit Proxy
const axiosProxy = axios.create({
  proxy: {
    host: PROXY_HOST,
    port: PROXY_PORT,
    auth: {
      username: PROXY_USER,
      password: PROXY_PASS
    }
  }
});

// === [1] GET /api/service?regionCode=WI ===
app.get('/api/service', async (req, res) => {
  const { regionCode } = req.query;

  try {
    const response = await axiosProxy.get(
      `https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${regionCode}`
    );

    res.json(response.data);
  } catch (err) {
    console.error('Fehler bei /api/service:', err.message);
    res.status(500).json({ error: 'Fehler beim Abruf der Zulassungsstelle' });
  }
});

// === [2] POST /api/check ===
app.post('/api/check', async (req, res) => {
  const payload = req.body;

  try {
    const response = await axiosProxy.post(
      'https://wunschkennzeichen.zulassung.de/api/check',
      payload,
      {
        headers: {
          'Content-Type': 'application/json'
        }
      }
    );

    res.json(response.data);
  } catch (err) {
    console.error('Fehler bei /api/check:', err.message);
    res.status(500).json({ error: 'Fehler beim Check des Kennzeichens' });
  }
});

// === Server Start ===
app.listen(PORT, () => {
  console.log(`✅ Server läuft auf Port ${PORT}`);
});
