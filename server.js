const express = require('express');
const axios = require('axios');
const https = require('https');
const HttpsProxyAgent = require('https-proxy-agent');
const app = express();
const cors = require('cors');
app.use(cors())

const app = express();
const port = 3000;

// Setze den Proxy-Server (Brightdata)
const proxyUrl = 'http://brd.superproxy.io:33335'; // Proxy-URL von Brightdata
const agent = new HttpsProxyAgent({
  proxy: {
    host: 'brd.superproxy.io',
    port: 33335,
    auth: 'brd-customer-hl_46ab8084-zone-datacenter_proxy1:1q735kkv57ub' // Dein Proxy-Authentifizierungsschlüssel
  },
  rejectUnauthorized: false // SSL-Zertifikatsvalidierung deaktivieren
});

// Route zum Abrufen der Service-ID basierend auf dem RegionCode
app.get('/api/service', async (req, res) => {
  const regionCode = req.query.regionCode;

  try {
    const response = await axios.get(`https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${regionCode}`, { 
      httpsAgent: agent
    });

    const serviceId = response.data.registrationOfficeServices[0].registrationOfficeServiceId;
    res.json({ serviceId }); // Gebe die serviceId zurück
  } catch (error) {
    console.error('Fehler beim Abruf:', error);
    res.status(500).json({ error: 'Fehler beim Abruf der Service-ID' });
  }
});

// Route zum Überprüfen des Wunschkennzeichens
app.post('/api/check', async (req, res) => {
  const { numberPlateText, registrationOfficeServiceId } = req.body;

  const payload = {
    numberPlateText: numberPlateText,
    registrationOfficeServiceId: registrationOfficeServiceId,
    vehicleType: "CAR", // Beispiel: Fahrzeugtyp
    licensePlateType: "REGULAR", // Beispiel: Normales Kennzeichen
    secondLineLength: null,
    editableLength: 8, // Beispiel: Länge des Kennzeichens
    startMonth: null,
    endMonth: null
  };

  try {
    // Sende eine Anfrage an die API zur Überprüfung der Verfügbarkeit
    const response = await axios.post('https://wunschkennzeichen.zulassung.de/api/check', payload, { 
      httpsAgent: agent
    });

    res.json(response.data); // Rückgabe der Antwort der API (Verfügbarkeit)
  } catch (error) {
    console.error('Fehler beim Abruf der Verfügbarkeit:', error);
    res.status(500).json({ error: 'Fehler beim Abruf der Verfügbarkeit' });
  }
});

// Starte den Server
app.listen(port, () => {
  console.log(`Server läuft auf http://localhost:${port}`);
});
