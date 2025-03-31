const express = require('express');
const axios = require('axios');
const bodyParser = require('body-parser');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

const BRIGHTDATA_PROXY = {
    host: 'brd.superproxy.io',
    port: 33335,
    auth: {
        username: 'brd-customer-hl_46ab8084-zone-datacenter_proxy1',
        password: '1q735kkv57ub'
    }
};

app.use(bodyParser.json());
app.use(express.static(path.join(__dirname, 'public')));

// GET /service/WI
app.get('/service/:regionCode', async (req, res) => {
    try {
        const region = req.params.regionCode;
        const response = await axios.get(`https://wunschkennzeichen.zulassung.de/api/registrationOfficeServices?regionCode=${region}`, {
            proxy: BRIGHTDATA_PROXY
        });
        res.json(response.data);
    } catch (err) {
        res.status(500).json({ error: 'Fehler beim Service-Request', detail: err.message });
    }
});

// POST /check
app.post('/check', async (req, res) => {
    try {
        const response = await axios.post('https://wunschkennzeichen.zulassung.de/api/check', req.body, {
            proxy: BRIGHTDATA_PROXY
        });
        res.json(response.data);
    } catch (err) {
        res.status(500).json({ error: 'Fehler beim Check-Request', detail: err.message });
    }
});

app.listen(PORT, () => {
    console.log(`Server läuft auf http://localhost:${PORT}`);
});
