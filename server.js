const express = require('express');
const fetch = require('node-fetch');
const HttpsProxyAgent = require('https-proxy-agent');
const app = express();
app.use(express.json());
const cors = require('cors');
app.use(cors());
// Bright Data Proxy Zugang
const BDATA = {
    host: 'brd.superproxy.io',
    port: 33335,
    username: 'brd-customer-hl_46ab8084-zone-datacenter_proxy1',
    password: '1q735kkv57ub'
};

function getAgent() {
    const proxyUrl = `http://${BDATA.username}:${BDATA.password}@${BDATA.host}:${BDATA.port}`;
    return new HttpsProxyAgent(proxyUrl);
}

app.post('/check', async (req, res) => {
    const { plate } = req.body;
    if (!plate || !plate.includes(' ')) {
        return res.status(400).json({ error: 'Ungültiges Kennzeichen-Format' });
    }

    const prefix = plate.split(' ')[0];

    try {
        const officeRes = await fetch('https://wunschkennzeichen-reservieren.jetzt/api/registrationOfficeSearch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: prefix }),
            agent: getAgent()
        });

        const officeData = await officeRes.json();
        const serviceId = officeData.registrationOfficeServices?.[0]?.registrationOfficeServiceId;

        if (!serviceId) {
            return res.status(404).json({ error: 'Zulassungsstelle nicht gefunden.' });
        }

        const checkRes = await fetch('https://wunschkennzeichen-reservieren.jetzt/api/checkAvailability', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                numberPlateText: plate,
                registrationOfficeServiceId: serviceId,
                vehicleType: "CAR",
                licensePlateType: "REGULAR",
                secondLineLength: null,
                editableLength: 8,
                startMonth: null,
                endMonth: null
            }),
            agent: getAgent()
        });

        const checkData = await checkRes.json();
        res.json(checkData);
    } catch (error) {
        console.error('Fehler:', error.message);
        res.status(500).json({ error: 'Fehler beim Verfügbarkeitscheck' });
    }
});

app.listen(3000, () => {
    console.log('✅ Bright Data Proxy läuft auf http://localhost:3000');
});
